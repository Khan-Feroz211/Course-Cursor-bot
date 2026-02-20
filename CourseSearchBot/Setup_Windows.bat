@echo off
title Course Search Bot — Setup
echo.
echo  ============================================
echo    Course Search Bot — First Time Setup
echo  ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python is not installed.
    echo  Please download Python 3.11 from https://www.python.org/downloads/
    echo  Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo  [1/3] Creating virtual environment...
python -m venv venv
if errorlevel 1 goto error

echo  [2/3] Activating and installing dependencies...
call venv\Scripts\activate.bat
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
if errorlevel 1 goto error

echo  [3/3] Creating folders...
if not exist "course_docs" mkdir course_docs
if not exist "data" mkdir data

echo.
echo  ============================================
echo   Setup complete! 
echo   Run "Launch.bat" to start the app.
echo  ============================================
echo.
pause
exit /b 0

:error
echo.
echo  ERROR: Setup failed. Please contact support.
pause
exit /b 1
