@echo off
title Lenovo RGB Uninstaller
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -Uninstall %*
echo.
pause
