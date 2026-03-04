@echo off
setlocal EnableDelayedExpansion
title Prof. AI Assistant

echo.
echo ╔══════════════════════════════════════╗
echo ║         Prof. AI Assistant v1.0      ║
echo ║      Starting up, please wait...     ║
echo ╚══════════════════════════════════════╝
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo Python is not installed.
  echo Please install Python 3.11+ from: https://www.python.org/downloads/
  pause
  exit /b 1
)

for /f "tokens=2 delims= " %%a in ('python -V 2^>^&1') do set PYVER=%%a
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
  set PYMAJOR=%%a
  set PYMINOR=%%b
)
if !PYMAJOR! LSS 3 (
  echo Python 3.11+ is required. Detected: %PYVER%
  echo Download: https://www.python.org/downloads/
  pause
  exit /b 1
)
if !PYMAJOR! EQU 3 if !PYMINOR! LSS 11 (
  echo Python 3.11+ is required. Detected: %PYVER%
  echo Download: https://www.python.org/downloads/
  pause
  exit /b 1
)

where ollama >nul 2>&1
if errorlevel 1 (
  echo Ollama is not installed.
  echo Please install from: https://ollama.com/
  pause
  exit /b 1
)

ollama list | findstr /I "llama3" >nul 2>&1
if errorlevel 1 (
  echo 📥 Downloading AI model (one-time ~4GB, please wait)...
  ollama pull llama3
  if errorlevel 1 (
    echo Failed to pull llama3 model. Check internet and try again.
    pause
    exit /b 1
  )
)

if not exist venv (
  echo 📦 First-time setup, installing (2-3 minutes)...
  python -m venv venv
  if errorlevel 1 (
    echo Failed to create virtual environment.
    pause
    exit /b 1
  )
  call venv\Scripts\pip install -r requirements.txt --quiet
  if errorlevel 1 (
    echo Failed to install dependencies.
    pause
    exit /b 1
  )
)
if not exist .env copy .env.example .env >nul

if not exist data\logs mkdir data\logs
if not exist data\users mkdir data\users

curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
  start /B ollama serve
  timeout /t 2 /nobreak >nul
)

start /B cmd /c "timeout /t 4 /nobreak >nul && start http://localhost:8000"

echo ✅ Prof. AI Assistant is running!
echo 📌 Open: http://localhost:8000
echo 🛑 Close this window to stop.
echo.

call venv\Scripts\uvicorn main:app --host 127.0.0.1 --port 8000 --log-level warning

endlocal
