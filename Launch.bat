@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title GenAI GUI backend - Ctrl+C or close this window to stop

rem ============================================================================
rem  GenAI GUI launcher
rem
rem  One double-click:
rem    1. calls Setup.bat when backend\.venv or the frontend build is missing;
rem       Setup handles uv/Python, Git and (only when needed) Node.js/npm;
rem    2. rebuilds frontend\dist when Vue sources/config are newer than the
rem       existing build (and npm is available);
rem    3. runs the backend IN THIS WINDOW - it serves the built frontend - and
rem       opens the app in your browser once the backend is up.
rem
rem  Everything lives inside this folder: backend\.venv, frontend\node_modules,
rem  frontend\dist, data\. The only external tools are uv (or Python 3.11+),
rem  Git for ComfyUI node installs, and Node.js for rebuilding the frontend.
rem  See tools\README.md and Setup.bat.
rem
rem  To stop the app: press Ctrl+C here (or just close this window).
rem  Backend logs stream right here in this console.
rem ============================================================================

set "PY=backend\.venv\Scripts\python.exe"
set "URL=http://127.0.0.1:8766"
set "SETUP_NEEDED="

if not exist "%PY%" set "SETUP_NEEDED=1"
if not exist "frontend\dist\index.html" set "SETUP_NEEDED=1"
if not defined SETUP_NEEDED (
  powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\needs-frontend-build.ps1"
  if !errorlevel! EQU 0 (
    where npm >nul 2>nul
    if !errorlevel! EQU 0 (
      set "SETUP_NEEDED=1"
    ) else (
      echo [warn] Vue sources are newer than frontend\dist, but Node.js/npm was not found.
      echo        Using the existing build. Install Node.js and run Setup.bat to rebuild.
    )
  )
)

if defined SETUP_NEEDED (
  echo [setup] Preparing the backend/frontend - see Setup.bat for details.
  call "%~dp0Setup.bat" --launch
  if errorlevel 1 goto :fail
)

if not exist "%PY%" goto :nosetup
if not exist "frontend\dist\index.html" goto :nosetup

rem -------------------------------------------------- already running? --------
powershell -NoProfile -Command "try{if((Invoke-WebRequest -UseBasicParsing '%URL%/api/health' -TimeoutSec 2).StatusCode -eq 200){exit 0}}catch{};exit 1" >nul 2>nul
if !errorlevel! EQU 0 (
  echo [app] Backend is already running - opening %URL%
  start "" "%URL%"
  exit /b 0
)

rem -------------------------------------------------------------- start app ---
echo [app] Starting backend - the app will open at %URL% when it is ready.
echo       Logs stream below. Press Ctrl+C to stop the app.
echo.
rem background helper (no extra window): waits for /api/health, then opens the browser
start /b "" powershell -NoProfile -Command "$i=0; while($i -lt 120){ try{ if((Invoke-WebRequest -UseBasicParsing '%URL%/api/health' -TimeoutSec 2).StatusCode -eq 200){ Start-Process '%URL%'; exit } }catch{}; Start-Sleep -Milliseconds 500; $i++ }" >nul 2>&1

"%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8766 --app-dir "%~dp0backend"

echo.
echo [app] Backend stopped.
exit /b 0

:nosetup
echo.
echo Backend setup did not finish. Run Setup.bat to see what is missing.
echo.
pause
exit /b 1

:fail
echo.
echo Setup failed - see the messages above.
echo.
pause
exit /b 1
