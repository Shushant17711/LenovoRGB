@echo off
:: Batch script to add LenovoRGB to Windows Startup with Administrator Privileges
:: This script must be run as Administrator!

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Failure: Please right-click this script and select "Run as administrator".
    pause
    exit /b 1
)

set "EXE_PATH=%~dp0dist\LenovoRGB.exe"

if not exist "%EXE_PATH%" (
    echo Error: Could not find LenovoRGB.exe at %EXE_PATH%
    echo Make sure you have built the executable first!
    pause
    exit /b 1
)

echo Adding LenovoRGB to Windows Startup...

:: Create a scheduled task that runs on log on with highest privileges
schtasks /create /tn "LenovoRGB_Startup" /tr "\"%EXE_PATH%\"" /sc onlogon /rl highest /f

if %errorLevel% equ 0 (
    echo.
    echo Successfully added LenovoRGB to startup!
    echo It will now run automatically in the background as Administrator when you log in.
) else (
    echo.
    echo Failed to add to startup.
)

pause
