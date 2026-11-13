from __future__ import annotations

import os
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk
from typing import Any

import numpy as np
import pydicom
from PIL import Image, ImageTk
from pydicom.dataset import Dataset


@dataclass
class Volume:
    voxels: np.ndarray
    row_spacing: float
    column_spacing: float
    slice_spacing: float
    initial_level: float
    initial_width: float
    description: str


@dataclass
class SeriesEntry:
    path: str
    header: Dataset


class SeriesPicker(tk.Toplevel):
    def __init__(self, parent: tk.Tk, series: dict[str, list[SeriesEntry]]) -> None:
        super().__init__(parent)
        self.title("DICOMシリーズを選択")
        self.transient(parent)
        self.grab_set()
        self.selection: list[SeriesEntry] | None = None

        ttk.Label(self, text="読み込むシリーズを選択してください:").pack(
            padx=12, pady=(12, 4), anchor="w"
        )
        self.listbox = tk.Listbox(self, width=76, height=min(12, len(series)))
        self.listbox.pack(fill="both", expand=True, padx=12, pady=4)
        self.series_entries = list(series.values())
        for entries in self.series_entries:
            header = entries[0].header
            description = str(getattr(header, "SeriesDescription", "名称なし"))
            number = str(getattr(header, "SeriesNumber", "-"))
            self.listbox.insert(
                "end", f"Series {number} | {description} | {len(entries)} 枚"
            )
        if self.series_entries:
            self.listbox.selection_set(0)
        self.listbox.bind("<Double-Button-1>", lambda _event: self.accept())

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=12, pady=(4, 12))
        ttk.Button(buttons, text="読み込む", command=self.accept).pack(
            side="right", padx=(4, 0)
        )
        ttk.Button(buttons, text="キャンセル", command=self.destroy).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.wait_visibility()
        self.focus_set()

    def accept(self) -> None:
        selected = self.listbox.curselection()
        if selected:
            self.selection = self.series_entries[selected[0]]
            self.destroy()


class DicomViewer:
    PLANE_NAMES = {"axial": "Axial", "coronal": "Coronal", "sagittal": "Sagittal"}

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("DICOM 3断面 Viewer")
        self.root.geometry("1440x900")
        self.root.minsize(1000, 700)
        self.volume: Volume | None = None
        self.indices = {"axial": 0, "coronal": 0, "sagittal": 0}
        self.levels = {"axial": 40.0, "coronal": 40.0, "sagittal": 40.0}
        self.widths = {"axial": 400.0, "coronal": 400.0, "sagittal": 400.0}
        self.canvases: dict[str, tk.Canvas] = {}
        self.position_scales: dict[str, tk.Scale] = {}
        self.level_scales: dict[str, tk.Scale] = {}
        self.width_scales: dict[str, tk.Scale] = {}
        self.photos: dict[str, ImageTk.PhotoImage] = {}

        self._create_menu()
        self._create_layout()
        self.root.bind("<Control-o>", lambda _event: self.open_files())
        self._draw_placeholders()

    def _create_menu(self) -> None:
        menu_bar = tk.Menu(self.root)
        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="DICOMファイルを開く...", command=self.open_files)
        file_menu.add_command(label="フォルダーを開く...", command=self.open_folder)
        file_menu.add_separator()
        file_menu.add_command(label="終了", command=self.root.destroy)
        menu_bar.add_cascade(label="ファイル", menu=file_menu)
        self.root.config(menu=menu_bar)

    def _create_layout(self) -> None:
        toolbar = ttk.Frame(self.root, padding=(10, 8))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="DICOMファイルを開く", command=self.open_files).pack(
            side="left"
        )
        ttk.Button(toolbar, text="フォルダーを開く", command=self.open_folder).pack(
            side="left", padx=(8, 0)
        )
        self.status = ttk.Label(toolbar, text="DICOMシリーズを読み込んでください")
        self.status.pack(side="left", padx=14)

        panes = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        panes.pack(fill="both", expand=True)
        for column, plane in enumerate(self.PLANE_NAMES):
            panes.columnconfigure(column, weight=1, uniform="plane")
            panes.rowconfigure(0, weight=1)
            panel = ttk.LabelFrame(panes, text=self.PLANE_NAMES[plane], padding=6)
            panel.grid(row=0, column=column, sticky="nsew", padx=4)
            panel.rowconfigure(0, weight=1)
            panel.columnconfigure(0, weight=1)

            canvas = tk.Canvas(panel, background="#101014", highlightthickness=0)
            canvas.grid(row=0, column=0, sticky="nsew")
            canvas.bind(
                "<Configure>", lambda _event, key=plane: self._draw_plane(key)
            )
            self.canvases[plane] = canvas

            controls = ttk.Frame(panel)
            controls.grid(row=1, column=0, sticky="ew", pady=(6, 0))
            controls.columnconfigure(1, weight=1)
            self.position_scales[plane] = self._add_scale(
                controls, "位置", plane, "position", 0, 1
            )
            self.level_scales[plane] = self._add_scale(
                controls, "WL", plane, "level", 1, 1
            )
            self.width_scales[plane] = self._add_scale(
                controls, "WW", plane, "width", 2, 1
            )

    def _add_scale(
        self, parent: ttk.Frame, label: str, plane: str, kind: str, row: int, maximum: int
    ) -> tk.Scale:
        ttk.Label(parent, text=label, width=5).grid(row=row, column=0, sticky="w")
        scale = tk.Scale(
            parent,
            from_=0,
            to=maximum,
            orient="horizontal",
            showvalue=True,
            resolution=1,
            highlightthickness=0,
            command=lambda value, key=plane, scale_kind=kind: self._scale_changed(
                key, scale_kind, value
            ),
        )
        scale.grid(row=row, column=1, sticky="ew")
        scale.configure(state="disabled")
        return scale

    def _draw_placeholders(self) -> None:
        for canvas in self.canvases.values():
            canvas.create_text(
                200,
                200,
                text="DICOMデータを読み込んでください",
                fill="#dddddd",
                font=("Yu Gothic UI", 13),
            )

    def open_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="DICOMファイルを選択",
            filetypes=(("DICOM / すべてのファイル", "*"),),
        )
        if paths:
            self._select_and_load(list(paths))

    def open_folder(self) -> None:
        folder = filedialog.askdirectory(title="DICOMフォルダーを選択")
        if folder:
            paths = [
                os.path.join(directory, filename)
                for directory, _subdirs, filenames in os.walk(folder)
                for filename in filenames
            ]
            self._select_and_load(paths)

    def _select_and_load(self, paths: list[str]) -> None:
        self.status.configure(text="DICOMシリーズを検索しています...")
        self.root.update_idletasks()
        series, unreadable_count = self._find_series(paths)
        if not series:
            self.status.configure(text="読み込めるシリーズがありません")
            messagebox.showerror(
                "DICOMを読み込めません",
                "選択した場所に読み込めるDICOMスライスがありませんでした。\n"
                "CTのDICOMファイルを選択してください。",
                parent=self.root,
            )
            return

        if len(series) == 1:
            entries = next(iter(series.values()))
        else:
            picker = SeriesPicker(self.root, series)
            self.root.wait_window(picker)
            entries = picker.selection
            if entries is None:
                self.status.configure(text="読み込みをキャンセルしました")
                return

        try:
            volume = self._load_volume(entries)
        except (ValueError, OSError, RuntimeError, AttributeError) as error:
            self.status.configure(text="読み込みに失敗しました")
            messagebox.showerror("DICOMを読み込めません", str(error), parent=self.root)
            return

        self._show_volume(volume)
        skipped = f"（非DICOM/対象外 {unreadable_count} 件を除外）" if unreadable_count else ""
        self.status.configure(
            text=(
                f"{volume.description} | "
                f"{volume.voxels.shape[2]}×{volume.voxels.shape[1]}×"
                f"{volume.voxels.shape[0]} slices{skipped}"
            )
        )

    @staticmethod
    def _find_series(paths: list[str]) -> tuple[dict[str, list[SeriesEntry]], int]:
        series: dict[str, list[SeriesEntry]] = {}
        unreadable_count = 0
        for path in paths:
            try:
                header = pydicom.dcmread(path, stop_before_pixels=True)
            except (OSError, pydicom.errors.InvalidDicomError, ValueError):
                unreadable_count += 1
                continue
            if (
                not getattr(header, "SeriesInstanceUID", None)
                or not getattr(header, "SOPInstanceUID", None)
                or not getattr(header, "Rows", None)
                or not getattr(header, "Columns", None)
                or getattr(header, "NumberOfFrames", 1) != 1
            ):
                unreadable_count += 1
                continue
            uid = str(header.SeriesInstanceUID)
            series.setdefault(uid, []).append(SeriesEntry(path, header))
        return series, unreadable_count

    @staticmethod
    def _load_volume(entries: list[SeriesEntry]) -> Volume:
        if not entries:
            raise ValueError("シリーズに画像が含まれていません。")

        first = entries[0].header
        try:
            orientation = np.asarray(first.ImageOrientationPatient, dtype=float)
            row_spacing, column_spacing = map(float, first.PixelSpacing)
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError("画像の向きまたは画素間隔の情報がありません。") from error
        if orientation.size != 6 or min(row_spacing, column_spacing) <= 0:
            raise ValueError("画像の向きまたは画素間隔の値が不正です。")

        row_direction = orientation[:3]
        column_direction = orientation[3:]
        normal = np.cross(row_direction, column_direction)
        if (
            abs(row_direction[0]) < 0.999
            or abs(column_direction[1]) < 0.999
            or abs(normal[2]) < 0.999
        ):
            raise ValueError(
                "このViewerは軸位（Axial）方向に並んだDICOMシリーズに対応しています。"
            )

        records: list[tuple[float, SeriesEntry]] = []
        for entry in entries:
            header = entry.header
            try:
                current_orientation = np.asarray(
                    header.ImageOrientationPatient, dtype=float
                )
                position = np.asarray(header.ImagePositionPatient, dtype=float)
                current_spacing = np.asarray(header.PixelSpacing, dtype=float)
            except (AttributeError, TypeError, ValueError) as error:
                raise ValueError(
                    f"位置・向き・画素間隔の情報がないファイルがあります:\n{entry.path}"
                ) from error
            if (
                current_orientation.shape != (6,)
                or not np.allclose(current_orientation, orientation, atol=1e-4)
                or not np.allclose(current_spacing, [row_spacing, column_spacing], rtol=1e-4)
            ):
                raise ValueError("シリーズ内で画像の向きまたは画素間隔が一致しません。")
            records.append((float(np.dot(position, normal)), entry))
        records.sort(key=lambda item: item[0])

        distances = np.diff([position for position, _entry in records])
        if len(distances):
            if np.any(distances <= 0):
                raise ValueError("スライス位置が重複しているか、順序が不正です。")
            slice_spacing = float(np.median(distances))
            if not np.allclose(distances, slice_spacing, rtol=0.01, atol=0.05):
                raise ValueError(
                    "スライス間隔が不均一なシリーズです。等間隔のシリーズを選択してください。"
                )
        else:
            slice_spacing = float(
                getattr(first, "SpacingBetweenSlices", getattr(first, "SliceThickness", 1.0))
            )
        if slice_spacing <= 0:
            raise ValueError("スライス間隔の値が不正です。")

        slices: list[np.ndarray] = []
        for _position, entry in records:
            try:
                dataset = pydicom.dcmread(entry.path)
                pixels = np.asarray(dataset.pixel_array)
            except (OSError, ValueError, RuntimeError, AttributeError) as error:
                raise ValueError(
                    f"DICOMの画素データを読み込めません:\n{entry.path}\n{error}"
                ) from error
            if pixels.ndim != 2 or pixels.shape != (int(first.Rows), int(first.Columns)):
                raise ValueError("全スライスが同じサイズの2次元画像である必要があります。")
            if int(getattr(dataset, "SamplesPerPixel", 1)) != 1:
                raise ValueError("カラー画像には対応していません。")
            pixels = pixels.astype(np.float32)
            pixels = (
                pixels * float(getattr(dataset, "RescaleSlope", 1.0))
                + float(getattr(dataset, "RescaleIntercept", 0.0))
            )
            if row_direction[0] < 0:
                pixels = np.fliplr(pixels)
            if column_direction[1] < 0:
                pixels = np.flipud(pixels)
            slices.append(pixels)

        voxels = np.stack(slices)
        low, high = (float(value) for value in np.percentile(voxels, [1, 99]))
        initial_level = (low + high) / 2
        initial_width = max(high - low, 1.0)

        def first_number(value: Any) -> float:
            try:
                return float(value[0])
            except (TypeError, KeyError, IndexError):
                return float(value)

        try:
            initial_level = first_number(first.WindowCenter)
        except (AttributeError, TypeError, ValueError, IndexError):
            pass
        try:
            window_width = first_number(first.WindowWidth)
            if window_width > 0:
                initial_width = window_width
        except (AttributeError, TypeError, ValueError, IndexError):
            pass
        description = str(getattr(first, "SeriesDescription", "DICOM"))
        return Volume(
            voxels=voxels,
            row_spacing=row_spacing,
            column_spacing=column_spacing,
            slice_spacing=slice_spacing,
            initial_level=initial_level,
            initial_width=initial_width,
            description=description,
        )

    def _show_volume(self, volume: Volume) -> None:
        self.volume = volume
        nz, ny, nx = volume.voxels.shape
        self.indices = {
            "axial": nz // 2,
            "coronal": ny // 2,
            "sagittal": nx // 2,
        }
        data_min = float(np.min(volume.voxels))
        data_max = float(np.max(volume.voxels))
        level_min = int(np.floor(data_min))
        level_max = int(np.ceil(data_max))
        if level_min == level_max:
            level_max = level_min + 1
        width_max = max(1, int(np.ceil(data_max - data_min)))
        for plane, count in (("axial", nz), ("coronal", ny), ("sagittal", nx)):
            self.position_scales[plane].configure(
                from_=0, to=max(0, count - 1), state="normal"
            )
            self.position_scales[plane].set(self.indices[plane])
            self.level_scales[plane].configure(
                from_=level_min, to=level_max, state="normal"
            )
            self.level_scales[plane].set(round(volume.initial_level))
            self.width_scales[plane].configure(from_=1, to=width_max, state="normal")
            self.width_scales[plane].set(
                min(max(1, round(volume.initial_width)), width_max)
            )
            self.levels[plane] = volume.initial_level
            self.widths[plane] = min(volume.initial_width, float(width_max))
        self._draw_all()

    def _scale_changed(self, plane: str, kind: str, value: str) -> None:
        if self.volume is None:
            return
        numeric_value = float(value)
        if kind == "position":
            self.indices[plane] = int(round(numeric_value))
            self._draw_all()
        elif kind == "level":
            self.levels[plane] = numeric_value
            self._draw_plane(plane)
        elif kind == "width":
            self.widths[plane] = max(1.0, numeric_value)
            self._draw_plane(plane)

    def _draw_all(self) -> None:
        for plane in self.PLANE_NAMES:
            self._draw_plane(plane)

    def _draw_plane(self, plane: str) -> None:
        volume = self.volume
        canvas = self.canvases[plane]
        canvas.delete("all")
        if volume is None:
            canvas.create_text(
                max(0, canvas.winfo_width() // 2),
                max(0, canvas.winfo_height() // 2),
                text="DICOMデータを読み込んでください",
                fill="#dddddd",
            )
            return

        nz, ny, nx = volume.voxels.shape
        z, y, x = self.indices["axial"], self.indices["coronal"], self.indices["sagittal"]
        if plane == "axial":
            image_data = np.flipud(volume.voxels[z, :, :])
            physical_width = nx * volume.column_spacing
            physical_height = ny * volume.row_spacing
            crosshairs = (
                ("vertical", (x + 0.5) / nx),
                ("horizontal", (ny - y - 0.5) / ny),
            )
        elif plane == "coronal":
            image_data = np.flipud(volume.voxels[:, y, :])
            physical_width = nx * volume.column_spacing
            physical_height = nz * volume.slice_spacing
            crosshairs = (
                ("vertical", (x + 0.5) / nx),
                ("horizontal", (nz - z - 0.5) / nz),
            )
        else:
            image_data = np.flipud(volume.voxels[:, :, x])
            physical_width = ny * volume.row_spacing
            physical_height = nz * volume.slice_spacing
            crosshairs = (
                ("vertical", (y + 0.5) / ny),
                ("horizontal", (nz - z - 0.5) / nz),
            )

        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        ratio = min(width / physical_width, height / physical_height)
        image_width = max(1, min(width, round(physical_width * ratio)))
        image_height = max(1, min(height, round(physical_height * ratio)))
        left = (width - image_width) // 2
        top = (height - image_height) // 2

        level = self.levels[plane]
        window = self.widths[plane]
        gray = np.clip((image_data - (level - window / 2)) * (255.0 / window), 0, 255)
        image = Image.fromarray(gray.astype(np.uint8), mode="L").resize(
            (image_width, image_height), Image.Resampling.NEAREST
        )
        photo = ImageTk.PhotoImage(image)
        self.photos[plane] = photo
        canvas.create_image(left, top, anchor="nw", image=photo)
        for orientation, fraction in crosshairs:
            if orientation == "vertical":
                line_x = left + fraction * image_width
                canvas.create_line(
                    line_x, top, line_x, top + image_height, fill="#36ff68", width=1
                )
            else:
                line_y = top + fraction * image_height
                canvas.create_line(
                    left, line_y, left + image_width, line_y, fill="#36ff68", width=1
                )
        canvas.create_text(
            8,
            8,
            anchor="nw",
            text=f"{self.PLANE_NAMES[plane]}  {self.indices[plane] + 1}",
            fill="#ffffff",
            font=("Yu Gothic UI", 10, "bold"),
        )


def main() -> None:
    root = tk.Tk()
    DicomViewer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
