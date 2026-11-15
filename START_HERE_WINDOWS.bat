@echo off
setlocal
cd /d "%~dp0backend"
echo ============================================
echo  PortfolioIQ - Local Development Launcher
 echo ============================================
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 (
    python -m venv .venv
    if errorlevel 1 goto :error
  )
)
echo Installing / verifying dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error
echo.
echo Open http://127.0.0.1:8000 in your browser.
echo Press Ctrl+C in this window to stop the server.
echo.
".venv\Scripts\python.exe" -m uvicorn main:app --reload
pause
exit /b 0
:error
echo.
echo Setup failed. Confirm Python 3.11 or later is installed and accessible.
pause
exit /b 1
