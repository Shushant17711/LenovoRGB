@echo off
echo Building LenovoRGB GUI executable...
pyinstaller --noconsole --onefile --hidden-import loq_rgb --add-binary "hidapi.dll;." --name LenovoRGB ui.py
echo Build complete. Executable should be in the 'dist' folder.
pause

