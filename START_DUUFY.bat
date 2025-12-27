@echo off
title Duufy Server
color 0A
echo.
echo  ============================================
echo     DUUFY - Do you often forget? Duufy don't
echo  ============================================
echo.
echo  Starting services...
echo.

cd /d "%~dp0"

:: Start ngrok in background
start "Duufy Ngrok" /min cmd /c "ngrok http 8000"

:: Wait for ngrok to start
timeout /t 3 /nobreak > nul

:: Start server (foreground - keeps window open)
echo  [OK] Ngrok tunnel starting...
echo  [OK] Starting FastAPI server...
echo.
echo  ============================================
echo   Server: http://127.0.0.1:8000
echo   App:    http://127.0.0.1:8000/app
echo   Ngrok:  http://127.0.0.1:4040 (for public URL)
echo  ============================================
echo.
echo  Press Ctrl+C to stop
echo.

C:\Users\Grums\Documents\App_projekt_python\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

pause
