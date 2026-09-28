@echo off
REM ============================================================
REM  push_to_github.bat
REM  ----------------------------------------------------------
REM  One-click script to:
REM    1. Initialize a local git repo
REM    2. Commit all files
REM    3. Push to GitHub (you provide the URL)
REM    4. GitHub Actions will auto-build the .exe installer
REM    5. You download the .exe from GitHub Actions artifacts
REM
REM  Prerequisites:
REM    - Git installed (https://git-scm.com/download/win)
REM    - A GitHub account
REM    - Create an empty repo on GitHub (no README)
REM
REM  Usage:
REM    1. Create a new empty repo on github.com
REM    2. Copy the URL (e.g. https://github.com/USER/REPO.git)
REM    3. Run this script, paste URL when prompted
REM ============================================================

setlocal EnableDelayedExpansion
cd /d "%~dp0\.."

echo.
echo ==========================================================
echo   Push project to GitHub
echo ==========================================================
echo.

REM --- 1. Check git ---
echo [1/4] Checking Git...
git --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Git not installed.
    echo         Download from: https://git-scm.com/download/win
    pause
    exit /b 1
)
echo       Git OK

REM --- 2. Initialize ---
echo.
echo [2/4] Initializing git repository...
if not exist ".git" (
    git init
    git branch -M main
)
git config user.name  >nul 2>&1
if errorlevel 1 (
    set /p GIT_NAME="Enter your GitHub username: "
    git config user.name "!GIT_NAME!"
    set /p GIT_EMAIL="Enter your GitHub email: "
    git config user.email "!GIT_EMAIL!"
)

REM --- 3. Create .gitignore if missing ---
if not exist ".gitignore" (
    (
        echo __pycache__/
        echo *.pyc
        echo build/
        echo dist/
        echo build_output/
        echo *.spec.bak
        echo config.json
        echo lhm.zip
        echo lhm_extracted/
        echo .vscode/
        echo .idea/
    ) > .gitignore
)

REM --- 4. Add and commit ---
echo.
echo [3/4] Adding files...
git add .
git commit -m "Initial commit: ESP8266 Fan Controller (AP/Hotspot mode)" >nul 2>&1
if errorlevel 1 (
    echo       Nothing new to commit, continuing...
) else (
    echo       Committed
)

REM --- 5. Push ---
echo.
echo [4/4] Pushing to GitHub...
echo.
echo Create an EMPTY repo on GitHub first ^(no README, no .gitignore^).
echo   1. Go to https://github.com/new
echo   2. Repository name: FanController
echo   3. Set to Public or Private
echo   4. DO NOT check "Add a README"
echo   5. Click "Create repository"
echo   6. Copy the URL like: https://github.com/USER/FanController.git
echo.
set /p REPO_URL="Paste your repo URL here: "

git remote remove origin >nul 2>&1
git remote add origin %REPO_URL%
git push -u origin main

if errorlevel 1 (
    echo.
    echo [ERROR] Push failed. Common issues:
    echo          - Wrong URL
    echo          - Need to authenticate (use a Personal Access Token)
    echo          - Repo not empty
    pause
    exit /b 1
)

echo.
echo ==========================================================
echo   SUCCESS! Code pushed to GitHub.
echo ==========================================================
echo.
echo Next steps:
echo   1. Go to your repo on github.com
echo   2. Click the "Actions" tab
echo   3. Wait for "Build Windows Installer" workflow to complete (~3-5 min)
echo   4. Click on the latest run
echo   5. Scroll down to "Artifacts"
echo   6. Download "FanController-Setup-v1.0.0" - that's your .exe installer!
echo.
echo Alternative: To get a release with downloadable .exe:
echo   1. Run: git tag v1.0.0
echo   2. Run: git push origin v1.0.0
echo   3. GitHub will create a Release with the .exe attached
echo.
pause
