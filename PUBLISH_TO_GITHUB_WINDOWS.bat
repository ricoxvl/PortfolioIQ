@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "REPO_URL=https://github.com/ricoxvl/PortfolioIQ.git"

echo =====================================================
echo PortfolioIQ - Publish source to your PRIVATE GitHub repo

echo Target: %REPO_URL%
echo =====================================================
echo.
echo This will create a Git commit and push project source to GitHub.
echo It will NOT upload ignored local databases, .env files, or API keys.
echo.
choice /C YN /M "Proceed with the pre-publish scan and GitHub push"
if errorlevel 2 goto :cancel

where git >nul 2>&1
if errorlevel 1 (
  echo ERROR: Git is not installed or not on PATH.
  echo Install Git for Windows: https://git-scm.com/downloads/win
  goto :failed
)

if not exist ".git" (
  git init -b main
  if errorlevel 1 goto :failed
)

git symbolic-ref HEAD refs/heads/main
if errorlevel 1 goto :failed

git add -A
if errorlevel 1 goto :failed

echo.
echo Running the definitive pre-publish safety scan on staged files...
where py >nul 2>&1
if not errorlevel 1 (
  py -3 scripts\prepublish_check.py
) else (
  python scripts\prepublish_check.py
)
if errorlevel 1 (
  echo Security scan failed. Nothing has been pushed.
  goto :failed
)

set "EXISTING_REMOTE="
for /f "delims=" %%U in ('git remote get-url origin 2^>nul') do set "EXISTING_REMOTE=%%U"
if defined EXISTING_REMOTE (
  if /I not "%EXISTING_REMOTE%"=="%REPO_URL%" (
    echo ERROR: This folder's origin remote points somewhere else:
    echo %EXISTING_REMOTE%
    echo Nothing has been pushed. Review the remote before retrying.
    goto :failed
  )
) else (
  git remote add origin "%REPO_URL%"
  if errorlevel 1 goto :failed
)

rem Re-running on an unchanged repository should not create a needless commit.
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "Build PortfolioIQ investment intelligence platform"
  if errorlevel 1 (
    echo.
    echo If Git requested your identity, configure it using:
    echo git config --global user.name "Your Name"
    echo git config --global user.email "your-github-email@example.com"
    echo Then run this launcher again.
    goto :failed
  )
)

echo.
echo Pushing to your private repository. Git may open a browser sign-in...
git push -u origin main
if errorlevel 1 (
  echo.
  echo Push failed. Check GitHub sign-in and repository access, then retry.
  goto :failed
)

echo.
echo SUCCESS - Project pushed to https://github.com/ricoxvl/PortfolioIQ
echo Next: open the Actions tab and inspect the workflow runs.
start "" "https://github.com/ricoxvl/PortfolioIQ/actions"
pause
exit /b 0

:cancel
echo Cancelled - no files pushed.
pause
exit /b 0

:failed
echo.
echo No additional action will be attempted. See the error above.
pause
exit /b 1
