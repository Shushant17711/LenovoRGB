@echo off
title Lenovo LOQ CPU Monitor
cd /d "%~dp0"
echo Starting CPU/Memory Monitor...
python loq_rgb.py --mode cpu
pause
