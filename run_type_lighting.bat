@echo off
title Lenovo LOQ Type-Lighting
echo Requesting Administrative Privileges (required for global keyboard hooks)...
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    del "%temp%\getadmin.vbs"
    exit /B
)
cd /d "%~dp0"
echo Admin privileges acquired. Starting Type-Lighting...
python loq_rgb.py --mode type
pause