# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for a single-file LenovoRGB.exe (windowed, no console)."""

import os
import sys

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

hiddenimports = []
if sys.platform == "win32":
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
    binaries=[],
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
