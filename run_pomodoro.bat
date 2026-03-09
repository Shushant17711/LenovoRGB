@echo off
title Lenovo LOQ Pomodoro Timer
cd /d "%~dp0"
echo Starting Pomodoro Timer (25min Work / 5min Break)...
python loq_rgb.py --mode pomodoro
pause
