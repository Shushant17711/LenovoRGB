@echo off
title Lenovo RGB Installer
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
