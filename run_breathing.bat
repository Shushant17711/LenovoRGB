@echo off
title Lenovo LOQ Breathing Animation
cd /d "%~dp0"
echo Starting Breathing Color Cycle...
python loq_rgb.py --mode breathing
pause
