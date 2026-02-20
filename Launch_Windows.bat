@echo off
title Course Search Bot
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo  Please run Setup_Windows.bat first!
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python main.py
