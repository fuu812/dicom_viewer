# DICOM 3断面 Viewer

Axial・Coronal・Sagittalの3断面を表示するPython製DICOM Viewerです。

## 動作環境

- Python 3.10以降
- Windows / macOS / Linux（Tkinterが利用できる環境）
- 軸位方向に撮影された、画素間隔と位置情報を持つDICOM画像シリーズ

## インストールと起動

```powershell
python -m pip install -r requirements.txt
python main.py
```

## 操作方法

1. 「ファイル」メニューまたは上部のボタンからDICOMファイル、もしくはDICOMを含むフォルダーを選びます。
2. 複数シリーズが見つかった場合は、表示するシリーズを選んで「読み込む」を押します。
3. 各断面の「位置」スライダーでスライス位置を移動します。選択位置に対応する線が他の2断面にも表示され、連動して動きます。
4. 各断面のWL（Window Level）とWW（Window Width）スライダーで表示の明るさとコントラストを調整します。

このViewerは、幾何情報のない画像、カラー画像、マルチフレーム画像、斜め方向または不均一間隔のシリーズには対応していません。読み込みに対応できないデータを選んだ場合は、エラー内容を画面に表示します。
