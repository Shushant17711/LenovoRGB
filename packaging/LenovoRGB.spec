# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for a single-file LenovoRGB.exe (windowed, no console)."""

import os
import sys

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

binaries = []
if sys.platform == "win32":
    # hidapi ships hidapi.dll next to hid.pyd. Copy it explicitly so the
    # one-file exe does not depend on a DLL being on PATH.
    try:
        import glob

        import hid

        hid_dir = os.path.dirname(hid.__file__)
        binaries += [(path, ".") for path in glob.glob(os.path.join(hid_dir, "*.dll"))]
    except Exception:
        pass

    hiddenimports += [
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
        "pystray._win32",
    ]
else:
    hiddenimports += [
        "pynput.keyboard._xorg",
        "pynput.mouse._xorg",
        "pystray._xorg",
        "pynput.keyboard._uinput",
        "hidraw",
        "evdev",
        "evdev.ecodes",
        "Xlib",
    ]

hiddenimports += [
    "hid",
    "soundcard",
    "mss",
    "PIL._tkinter_finder",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageGrab",
]

for package in ("pystray",):
    hiddenimports += collect_submodules(package)

datas = [(os.path.join(ROOT, "src", "lenovorgb", "assets"), "lenovorgb/assets")]

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "ruff", "_pytest", "unittest", "tests", "setuptools"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="LenovoRGB",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(SPECPATH, "icon.ico"),
)
