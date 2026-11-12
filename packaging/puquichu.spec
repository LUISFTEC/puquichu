# -*- mode: python ; coding: utf-8 -*-
# Receta de PyInstaller: empaqueta Puquichu con Python, Qt y sus librerías.
# Uso (desde la raíz del proyecto):  python -m PyInstaller packaging/puquichu.spec
import os

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821 (SPECPATH lo define PyInstaller)

a = Analysis(  # noqa: F821
    [os.path.join(ROOT, "app.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "assets"), "assets")],
    hiddenimports=collect_submodules("yt_dlp") + ["mpris"],
    excludes=["tkinter", "unittest", "pydoc", "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtWebEngineCore", "PyQt6.QtPdf"],
    noarchive=False,
)
# VLC se usa desde el sistema (dependencia del paquete): una copia suelta de libvlc
# dentro del paquete no encuentra sus módulos y no puede reproducir nada.
a.binaries = [b for b in a.binaries if not os.path.basename(b[0]).startswith(("libvlc", "libvlccore"))]

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="puquichu",
    console=False,
    upx=False,
    icon=os.path.join(ROOT, "assets", "puquichu.png"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="puquichu", upx=False)  # noqa: F821
