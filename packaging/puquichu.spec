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
    hiddenimports=collect_submodules("yt_dlp") + ["mpris", "player", "PyQt6.QtMultimedia"],
    excludes=["tkinter", "unittest", "pydoc", "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtWebEngineCore", "PyQt6.QtPdf"],
    noarchive=False,
)
# La librería de C++ (y la de soporte de GCC) se toman siempre del sistema: el paquete se arma en
# Ubuntu 22.04 y en sistemas más nuevos otras librerías del sistema (ffmpeg, códecs) necesitan
# la versión más reciente. La del sistema nunca es más vieja que la de 22.04.
a.binaries = [b for b in a.binaries if not os.path.basename(b[0]).startswith(("libstdc++.so", "libgcc_s.so"))]

# El cliente de sonido (PulseAudio/PipeWire) también se toma del sistema, por la misma razón.
a.binaries = [b for b in a.binaries if not os.path.basename(b[0]).startswith(("libpulse", "libpulsecommon"))]

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
