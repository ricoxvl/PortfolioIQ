@echo off
setlocal
cd /d "%~dp0"
echo ================================================
echo   PortfolioIQ v0.5 - Secure Research Workspace
echo ================================================
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 (
    python -m venv .venv
    if errorlevel 1 goto :error
  )
)
echo Installing Python dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error
where npm >nul 2>&1
if errorlevel 1 (
  echo Node.js not found. Using included offline fallback interface.
) else (
  echo Building React + TypeScript frontend...
  pushd web
  call npm install --no-audit --no-fund
  if not errorlevel 1 (
    call npm run build
  )
  popd
  if not exist "web\dist\index.html" echo React build unavailable - using built-in fallback UI.
)
echo.
echo Open http://127.0.0.1:8000
".venv\Scripts\python.exe" -m uvicorn server.app:app --host 127.0.0.1 --port 8000
pause
exit /b 0
:error
echo Python setup failed. Install Python 3.11+ and retry.
pause
exit /b 1
