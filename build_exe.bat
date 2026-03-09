@echo off
echo Building LenovoRGB GUI executable...
pyinstaller --noconsole --onefile --hidden-import loq_rgb --name LenovoRGB ui.py
echo Build complete. Executable should be in the 'dist' folder.
pause
