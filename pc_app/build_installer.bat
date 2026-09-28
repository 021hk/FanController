@echo off
REM ============================================================
REM  build_installer.bat - Builds FanController installer
REM  ----------------------------------------------------------
REM  This script does EVERYTHING:
REM    1. Installs Python deps (PyInstaller, etc.)
REM    2. Downloads LibreHardwareMonitorLib.dll if missing
REM    3. Builds the .exe with PyInstaller
REM    4. Compiles the .exe installer with Inno Setup
REM    5. Outputs: dist/FanController-Setup-v1.0.0.exe
REM
REM  Just double-click this file. Done.
REM ============================================================

setlocal EnableDelayedExpansion
cd /d "%~dp0"

set VERSION=1.0.0
set APPNAME=FanController
set OUTDIR=build_output
set DISTDIR=dist

echo.
echo ==========================================================
echo   Building %APPNAME% v%VERSION% installer (Hotspot Edition)
echo ==========================================================
echo.

REM --- 1. Check Python ---
echo [1/6] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo         Install Python 3.10+ from: https://python.org/downloads
    echo         IMPORTANT: tick "Add Python to PATH" during install
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo       Python %PYVER% OK

REM --- 2. Check pip and install requirements ---
echo.
echo [2/6] Installing Python dependencies...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt pyinstaller pywin32 >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    echo         Try manually: pip install -r requirements.txt
    pause
    exit /b 1
)
echo       Dependencies installed

REM --- 3. Download LibreHardwareMonitorLib.dll if missing ---
echo.
echo [3/6] Checking LibreHardwareMonitorLib.dll...
if not exist "LibreHardwareMonitorLib.dll" (
    echo       Not found. Downloading from GitHub...
    powershell -Command ^
        "$ProgressPreference = 'SilentlyContinue';" ^
        "$url = 'https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/v0.9.6/LibreHardwareMonitor.zip';" ^
        "$zip = 'lhm.zip';" ^
        "$extractDir = 'lhm_extracted';" ^
        "Invoke-WebRequest -Uri $url -OutFile $zip;" ^
        "Expand-Archive -Path $zip -DestinationPath $extractDir -Force;" ^
        "$dll = Get-ChildItem -Path $extractDir -Recurse -Filter 'LibreHardwareMonitorLib.dll' | Select-Object -First 1;" ^
        "if ($dll) { Copy-Item $dll.FullName -Destination '.' -Force; }" ^
        "$cfg = Get-ChildItem -Path $extractDir -Recurse -Filter 'LibreHardwareMonitorLib.dll.config' | Select-Object -First 1;" ^
        "if ($cfg) { Copy-Item $cfg.FullName -Destination '.' -Force; }" ^
        "$hid = Get-ChildItem -Path $extractDir -Recurse -Filter 'HidSharp.dll' | Select-Object -First 1;" ^
        "if ($hid) { Copy-Item $hid.FullName -Destination '.' -Force; }" ^
        "Remove-Item $zip -Force; Remove-Item $extractDir -Recurse -Force"
    if exist "LibreHardwareMonitorLib.dll" (
        echo       LHM downloaded successfully
    ) else (
        echo [WARNING] Could not download LHM. App will use nvidia-smi fallback.
        choice /C YN /M "Continue without LHM"
        if errorlevel 2 exit /b 1
    )
) else (
    echo       LHM already present
)

REM --- 4. Generate icon if missing ---
echo.
echo [4/6] Checking icon.ico...
if not exist "icon.ico" (
    echo       Generating icon...
    python icon_generator.py
    if not exist "icon.ico" (
        echo [WARNING] Icon generation failed, using default
    )
) else (
    echo       icon.ico present
)

REM --- 5. Clean and build exe ---
echo.
echo [5/6] Building standalone executable...
if exist %OUTDIR% rmdir /s /q %OUTDIR%
if exist %DISTDIR% rmdir /s /q %DISTDIR%
if exist build rmdir /s /q build

python -m PyInstaller fan_controller.spec --noconfirm --clean
if errorlevel 1 (
    echo [ERROR] PyInstaller failed.
    echo         Check the output above for errors.
    pause
    exit /b 1
)

if not exist "%DISTDIR%\%APPNAME%\%APPNAME%.exe" (
    echo [ERROR] Expected output not found: %DISTDIR%\%APPNAME%\%APPNAME%.exe
    pause
    exit /b 1
)
echo       Built: %DISTDIR%\%APPNAME%\%APPNAME%.exe

REM Copy LHM DLLs + bat files into dist
echo.
echo       Copying extra files...
for %%f in (LibreHardwareMonitorLib.dll LibreHardwareMonitorLib.dll.config HidSharp.dll GameMode_ON.bat GameMode_OFF.bat) do (
    if exist "%%f" copy "%%f" "%DISTDIR%\%APPNAME%\" >nul
)
if exist "LibreHardwareMonitorLib.resources" (
    xcopy /E /I /Y "LibreHardwareMonitorLib.resources" "%DISTDIR%\%APPNAME%\LibreHardwareMonitorLib.resources\" >nul
)

REM --- 6. Compile installer with Inno Setup ---
echo.
echo [6/6] Compiling installer with Inno Setup...

set ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=C:\Program Files\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" (
    echo [WARNING] Inno Setup 6 not found.
    echo          Please download from: https://jrsoftware.org/isdl.php
    echo          After install, run this script again.
    echo.
    echo You can still use the standalone folder:
    echo   %DISTDIR%\%APPNAME%\%APPNAME%.exe
    pause
    exit /b 0
)

"%ISCC%" /Q installer.iss
if errorlevel 1 (
    echo [ERROR] Inno Setup compilation failed.
    pause
    exit /b 1
)

echo.
echo ==========================================================
echo   SUCCESS! Installer built.
echo ==========================================================
echo.
echo   Installer:  %DISTDIR%\%APPNAME%-Setup-v%VERSION%.exe
echo   Folder:    %DISTDIR%\%APPNAME%\
echo.
echo Next steps:
echo   1. Run the installer on any Windows 10/11 x64 PC
echo   2. Connect to WiFi network "FanController" (pass: 12345678)
echo   3. Launch "ESP8266 Fan Controller" from Start Menu
echo.
pause
