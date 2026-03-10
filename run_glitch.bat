@echo off
title Lenovo LOQ Glitch Mode
echo Requesting Administrative Privileges...
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    del "%temp%\getadmin.vbs"
    exit /B
)
cd /d "%~dp0"
echo Admin privileges acquired. Starting Glitch mode...
python loq_rgb.py --mode glitch
pause
