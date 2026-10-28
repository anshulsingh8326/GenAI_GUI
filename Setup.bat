@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title GenAI GUI setup

rem ============================================================================
rem  GenAI GUI prerequisite setup
rem
rem  Checks/creates the local backend environment, checks Git (required for
rem  ComfyUI node installs), and builds the Vue frontend when its sources are
rem  newer than frontend\dist.
rem
rem  Missing tools are only installed after a Y/N prompt. Portable uv
rem  (tools\uv.exe) and Node.js (tools\node) are downloaded on consent; uv
rem  installs Python into tools\python. Git uses winget when available,
rem  otherwise the official download page is offered.
rem
rem  Launch.bat calls this with --launch on first run / when a build is needed.
rem ============================================================================

set "FROM_LAUNCH="
if /I "%~1"=="--launch" set "FROM_LAUNCH=1"
set "PY=backend\.venv\Scripts\python.exe"
set "PYTHON="
set "UV="
rem Keep the Python that uv downloads inside this project. It is never added
rem to the system PATH; only backend\.venv uses it.
set "UV_PYTHON_INSTALL_DIR=%CD%\tools\python"
set "UV_PYTHON_PREFERENCE=only-managed"
set "UV_LINK_MODE=copy"

echo.
echo [setup] GenAI GUI prerequisites
echo.

call :ensure_backend
if errorlevel 1 goto :fail
call :ensure_git
call :ensure_frontend
if errorlevel 1 goto :fail

echo.
echo [setup] Ready.
if not defined FROM_LAUNCH pause
exit /b 0

rem ------------------------------------------------------------ backend env --
:ensure_backend
set "BACKEND_REPAIR="
if exist "%PY%" (
  "%PY%" -c "import fastapi" >nul 2>nul
  if !errorlevel! EQU 0 (
    echo [ok] backend\.venv
    exit /b 0
  )
  set "BACKEND_REPAIR=1"
)
if defined BACKEND_REPAIR (
  echo [warn] backend\.venv cannot run from this folder - repairing it...
) else (
  echo [setup] backend\.venv is missing - creating it...
)
if exist "tools\uv.exe" set "UV=%CD%\tools\uv.exe"
if not defined UV (
  where uv >nul 2>nul
  if !errorlevel! EQU 0 set "UV=uv"
)
if not defined UV (
  echo.
  echo       uv was not found. It is a single portable executable, so it can
  echo       create the project venv and download Python without an installer.
  echo       Manual install: https://docs.astral.sh/uv/getting-started/installation/
  choice /C YN /M "Download portable uv into tools\ now"
  if !errorlevel! EQU 1 (
    powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\download-uv.ps1"
    if !errorlevel! NEQ 0 (
      echo [error] uv download failed.
      echo         Download it manually from:
      echo         https://docs.astral.sh/uv/getting-started/installation/
      exit /b 1
    )
    if exist "tools\uv.exe" set "UV=%CD%\tools\uv.exe"
  )
)
if defined UV (
  echo [setup] Installing a project-local Python with uv...
  "!UV!" python install 3.13 --no-bin --no-registry
  if !errorlevel! NEQ 0 exit /b 1
  echo [setup] Syncing backend dependencies with uv...
  "!UV!" sync --directory backend
  if !errorlevel! NEQ 0 exit /b 1
) else (
  call :ensure_python
  if errorlevel 1 exit /b 1
  echo [setup] uv not available - using Python + pip as a fallback...
  if defined BACKEND_REPAIR (
    !PYTHON! -m venv --clear backend\.venv
  ) else (
    !PYTHON! -m venv backend\.venv
  )
  if !errorlevel! NEQ 0 exit /b 1
  "%PY%" -m pip install --upgrade pip
  rem keep this list in sync with backend\pyproject.toml
  "%PY%" -m pip install "fastapi>=0.115" "httpx>=0.28" "mcp>=1.0" "pillow>=11.0" "psutil>=6.0" "python-multipart>=0.0.18" "uvicorn[standard]>=0.32"
  if !errorlevel! NEQ 0 exit /b 1
)
if not exist "%PY%" (
  echo [error] backend\.venv was not created.
  exit /b 1
)
"%PY%" -c "import fastapi" >nul 2>nul
if !errorlevel! NEQ 0 (
  echo [error] backend\.venv was created but cannot import its dependencies.
  exit /b 1
)
echo [ok] backend\.venv
exit /b 0

:ensure_python
if defined PYTHON exit /b 0
where python >nul 2>nul
if !errorlevel! EQU 0 (
  set "PYTHON=python"
  exit /b 0
)
where py >nul 2>nul
if !errorlevel! EQU 0 (
  set "PYTHON=py -3"
  exit /b 0
)
echo.
echo [missing] Python 3.11+ was not found.
echo           uv is the recommended route because it keeps Python inside
echo           tools\python. A system Python 3.11+ is only a fallback.
echo           Download: https://www.python.org/downloads/windows/
where winget >nul 2>nul
if !errorlevel! NEQ 0 (
  echo.
  echo           winget is not available on this PC.
  choice /C YN /M "Open the Python download page now"
  if !errorlevel! EQU 1 start "" "https://www.python.org/downloads/windows/"
  echo [error] Install Python 3.11+ and run Setup.bat again.
  exit /b 1
)
choice /C YN /M "Install Python 3.13 with winget now"
if !errorlevel! NEQ 1 (
  echo.
  echo [warn] Python is required for the fallback. Install it manually:
  echo        https://www.python.org/downloads/windows/
  choice /C YN /M "Open the Python download page now"
  if !errorlevel! EQU 1 start "" "https://www.python.org/downloads/windows/"
  exit /b 1
)
call :winget_install Python.Python.3.13
if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PATH=%LocalAppData%\Programs\Python\Python313;%LocalAppData%\Programs\Python\Python313\Scripts;!PATH!"
if exist "%ProgramFiles%\Python313\python.exe" set "PATH=%ProgramFiles%\Python313;%ProgramFiles%\Python313\Scripts;!PATH!"
where python >nul 2>nul
if !errorlevel! EQU 0 (
  set "PYTHON=python"
  exit /b 0
)
where py >nul 2>nul
if !errorlevel! EQU 0 (
  set "PYTHON=py -3"
  exit /b 0
)
echo [warn] Python was installed but is not visible in this window yet.
echo        Restart Setup/Launch and run Setup.bat again.
exit /b 1

rem ------------------------------------------------------------------- git --
:ensure_git
where git >nul 2>nul
if !errorlevel! EQU 0 (
  echo [ok] Git
  exit /b 0
)
echo.
echo [missing] Git was not found.
echo           Git is required for ComfyUI node installs and updates.
echo           Download: https://git-scm.com/download/win
echo           The app itself can still start, but node install buttons stay disabled.
where winget >nul 2>nul
if !errorlevel! NEQ 0 goto :git_offer_download
choice /C YN /M "Install Git for Windows with winget now"
if !errorlevel! EQU 1 (
  call :winget_install Git.Git
  if exist "%ProgramFiles%\Git\cmd\git.exe" set "PATH=%ProgramFiles%\Git\cmd;!PATH!"
  where git >nul 2>nul
  if !errorlevel! EQU 0 (
    echo [ok] Git
    exit /b 0
  )
  echo [warn] Git was installed but is not visible in this window yet.
  echo        Restart Setup/Launch after the installer completes.
  exit /b 0
)
:git_offer_download
echo.
choice /C YN /M "Open the Git download page now"
if !errorlevel! EQU 1 (
  start "" "https://git-scm.com/download/win"
  echo [setup] Opened the Git download page. Install Git, then restart Setup/Launch.
) else (
  echo [setup] Skipped. Install Git later from the link above.
)
echo [warn] Continuing without Git - node installs stay disabled until it is installed.
exit /b 0

rem --------------------------------------------------------------- frontend --
:ensure_frontend
set "BUILD_NEEDED="
if not exist "frontend\dist\index.html" set "BUILD_NEEDED=1"
if not defined BUILD_NEEDED (
  powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\needs-frontend-build.ps1"
  if !errorlevel! EQU 0 set "BUILD_NEEDED=1"
)
if not defined BUILD_NEEDED (
  echo [ok] frontend\dist
  exit /b 0
)
echo [setup] frontend\dist is missing or older than the Vue sources...
if exist "tools\node\npm.cmd" set "PATH=%CD%\tools\node;!PATH!"
where npm >nul 2>nul
if !errorlevel! NEQ 0 (
  echo.
  if exist "frontend\dist\index.html" (
    echo [warn] Node.js/npm was not found. The existing frontend build will be used.
    echo        Download: https://nodejs.org/en/download
    echo        Install Node.js and run Setup.bat to rebuild after Vue source changes.
    if not defined FROM_LAUNCH (
      choice /C YN /M "Open the Node.js download page now"
      if !errorlevel! EQU 1 start "" "https://nodejs.org/en/download"
    )
    exit /b 0
  )
  echo [missing] Node.js/npm was not found.
  echo           Node.js is required for the first frontend build.
  echo           Portable option: download Node.js into tools\node - no installer.
  echo           Download: https://nodejs.org/en/download
  choice /C YN /M "Download portable Node.js into tools\node now"
  if !errorlevel! EQU 1 (
    powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\download-node.ps1"
    if !errorlevel! EQU 0 (
      if exist "tools\node\npm.cmd" set "PATH=%CD%\tools\node;!PATH!"
      where npm >nul 2>nul
      if !errorlevel! EQU 0 goto :frontend_ready
    )
    echo [warn] Portable Node.js is not ready; checking winget next.
  )
  where winget >nul 2>nul
  if !errorlevel! NEQ 0 (
    echo.
    echo           winget is not available on this PC.
    choice /C YN /M "Open the Node.js download page now"
    if !errorlevel! EQU 1 start "" "https://nodejs.org/en/download"
    echo [error] Install Node.js and run Setup.bat again.
    exit /b 1
  )
  choice /C YN /M "Install Node.js LTS with winget now"
  if !errorlevel! EQU 1 (
    call :winget_install OpenJS.NodeJS.LTS
    if exist "%ProgramFiles%\nodejs\npm.cmd" set "PATH=%ProgramFiles%\nodejs;!PATH!"
    where npm >nul 2>nul
    if !errorlevel! NEQ 0 (
      echo [warn] Node.js was installed but npm is not visible in this window yet.
      echo        Restart Setup/Launch and run Setup.bat again.
      exit /b 1
    )
  ) else (
    echo.
    echo [warn] Node.js is required to build the frontend.
    echo        https://nodejs.org/en/download
    choice /C YN /M "Open the Node.js download page now"
    if !errorlevel! EQU 1 start "" "https://nodejs.org/en/download"
    exit /b 1
  )
)
:frontend_ready
pushd frontend
if not exist node_modules (
  if exist package-lock.json (call npm ci) else (call npm install)
  if !errorlevel! NEQ 0 (popd & exit /b 1)
)
call npm run build
set "BUILD_ERR=!errorlevel!"
popd
if not "!BUILD_ERR!"=="0" exit /b 1
if not exist "frontend\dist\index.html" (
  echo [error] The frontend build did not produce frontend\dist\index.html.
  exit /b 1
)
echo [ok] frontend\dist
exit /b 0

rem ------------------------------------------------------------ winget helper --
:winget_install
winget install --id %~1 -e --source winget --accept-package-agreements --accept-source-agreements
exit /b !errorlevel!

:fail
echo.
echo [setup] Setup failed - see the messages above.
if not defined FROM_LAUNCH pause
exit /b 1
