@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Civil Engineering ^& Courses Counseller

echo.
echo ==========================================
echo   Civil Engineering ^& Courses Counseller
echo       Starting up, please wait...
echo ==========================================
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

:: Skip all Ollama setup when using Groq cloud AI
if exist .env (
  findstr /I "AI_BACKEND=groq" .env >nul 2>&1
  if not errorlevel 1 goto skipollama_install
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
  echo Downloading AI model - one-time about 4GB, please wait...
  ollama pull llama3
  if errorlevel 1 (
    echo Failed to pull llama3 model. Check internet and try again.
    pause
    exit /b 1
  )
)

:skipollama_install
if not exist venv (
  echo First-time setup, installing for 2-3 minutes...
  py -3.11 -m venv venv 2>nul
  if errorlevel 1 python -m venv venv
  if errorlevel 1 (
    echo Failed to create virtual environment.
    pause
    exit /b 1
  )
  call venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
  if errorlevel 1 (
    echo Failed to install dependencies.
    pause
    exit /b 1
  )
)
if not exist .env copy .env.example .env >nul

if not exist data\logs mkdir data\logs
if not exist data\users mkdir data\users

:: Check if using Groq cloud AI (no Ollama needed)
findstr /I "AI_BACKEND=groq" .env >nul 2>&1
if not errorlevel 1 (
  findstr /I "GROQ_API_KEY=" .env >nul 2>&1
  for /f "tokens=2 delims==" %%k in ('findstr /I "GROQ_API_KEY" .env 2^>nul') do set GK=%%k
  if "!GK!"=="" (
    echo.
    echo  ========================================================
    echo   ACTION REQUIRED: Set your Groq API key in .env
    echo   1. Open: %CD%\.env
    echo   2. Paste your key after GROQ_API_KEY=
    echo   3. Get a free key at: https://console.groq.com
    echo  ========================================================
    echo.
    start notepad.exe .env
    pause
    exit /b 1
  )
  echo Using Groq Cloud AI ^(fast mode^) - Ollama not required.
  goto startserver
)

where ollama >nul 2>&1
if errorlevel 1 (
  echo Starting Ollama AI engine...
  start /B ollama serve
  echo Waiting for Ollama to be ready...
  timeout /t 5 /nobreak >nul
  :waitollama
  curl -s http://localhost:11434/api/tags >nul 2>&1
  if errorlevel 1 (
    timeout /t 2 /nobreak >nul
    goto waitollama
  )
  echo Ollama is ready.
)

:startserver
start /B "" venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --log-level info

echo Waiting for server to be ready...
set POLL=0
:waitserver
timeout /t 3 /nobreak >nul
set /a POLL+=3
curl -s http://localhost:8000 >nul 2>&1
if not errorlevel 1 goto serverup
if !POLL! LSS 120 goto waitserver
echo [WARNING] Server is taking longer than usual, opening browser anyway...
:serverup
echo Server is ready ^(waited !POLL! seconds^). Opening browser...
start http://localhost:8000

echo.
echo Civil Engineering ^& Courses Counseller is running at http://localhost:8000
echo Close this window to stop.
echo.

:keepalive
timeout /t 10 /nobreak >nul
curl -s http://localhost:8000 >nul 2>&1
if not errorlevel 1 goto keepalive
echo Server has stopped.
pause
