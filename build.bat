@echo off
title Build Lenovo RGB
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -BuildExe -NoAutostart -NoShortcut %*
echo.
pause
