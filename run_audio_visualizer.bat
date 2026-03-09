@echo off
title Lenovo LOQ Audio Visualizer
cd /d "%~dp0"
echo Starting Audio Visualizer...
python loq_rgb.py --mode audio
pause
