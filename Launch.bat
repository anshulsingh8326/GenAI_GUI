@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title GenAI GUI backend - Ctrl+C or close this window to stop

rem ============================================================================
rem  GenAI GUI launcher
rem
rem  One double-click:
rem    1. creates backend\.venv (one time - via uv, or Python + pip fallback)
rem    2. builds frontend\dist (one time - needs Node.js/npm)
rem    3. runs the backend IN THIS WINDOW - it serves the built frontend - and
rem       opens the app in your browser once the backend is up
rem
rem  Everything lives inside this folder: backend\.venv, frontend\node_modules,
rem  frontend\dist, data\. The only external tools are uv (or Python 3.11+)
rem  and Node.js - see README in tools\ for the fully self-contained option.
rem
rem  To stop the app: press Ctrl+C here (or just close this window).
rem  Backend logs stream right here in this console.
rem ============================================================================

set "PY=backend\.venv\Scripts\python.exe"
set "URL=http://127.0.0.1:8766"

rem ------------------------------------------------------------- backend env --
if not exist "%PY%" (
  echo [setup] Backend environment missing - creating backend\.venv ...
  set "UV="
  where uv >nul 2>nul
  if !errorlevel! EQU 0 set "UV=uv"
  if not defined UV if exist "tools\uv.exe" set "UV=tools\uv.exe"
  if defined UV (
    "!UV!" sync --directory backend --link-mode copy
  ) else (
    where python >nul 2>nul
    if !errorlevel! NEQ 0 goto :nopython
    echo        uv not found - falling back to Python + pip ^(needs internet^) ...
    python -m venv backend\.venv
    "%PY%" -m pip install --upgrade pip
    rem keep this list in sync with backend\pyproject.toml
    "%PY%" -m pip install "fastapi>=0.115" "httpx>=0.28" "mcp>=1.0" "pillow>=11.0" "psutil>=6.0" "python-multipart>=0.0.18" "uvicorn[standard]>=0.32"
  )
  if not exist "%PY%" goto :fail
)

rem ---------------------------------------------------------- frontend build --
if not exist "frontend\dist\index.html" (
  echo [setup] Frontend not built yet - building frontend\dist ...
  where npm >nul 2>nul
  if !errorlevel! NEQ 0 goto :nonode
  pushd frontend
  if not exist node_modules (
    if exist package-lock.json ( call npm ci ) else ( call npm install )
    if !errorlevel! NEQ 0 ( popd & goto :fail )
  )
  call npm run build
  set "BUILD_ERR=!errorlevel!"
  popd
  if not "!BUILD_ERR!"=="0" goto :fail
)

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

:nopython
echo.
echo Could not create the backend environment: neither "uv" nor Python was found.
echo Install uv (https://docs.astral.sh/uv/) - or copy uv.exe into the tools\
echo folder next to this script - and run Launch.bat again.
echo.
pause
exit /b 1

:nonode
echo.
echo The frontend has never been built and Node.js/npm was not found.
echo Install Node.js (https://nodejs.org/) and run Launch.bat again.
echo.
pause
exit /b 1

:fail
echo.
echo Setup failed - see the messages above.
echo.
pause
exit /b 1
