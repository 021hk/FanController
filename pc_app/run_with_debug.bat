@echo off
REM ============================================================
REM  run_with_debug.bat - Run FanController with error display
REM
REM  This script runs the app and if it crashes, shows the error
REM  instead of silently closing.
REM ============================================================

setlocal
chcp 65001 >nul 2>&1

echo.
echo ==========================================================
echo   Fan Controller - Debug Mode
echo ==========================================================
echo.

REM Find the FanController executable
set "APP_PATH=C:\Program Files\ESP8266 Fan Controller\FanController.exe"

if not exist "%APP_PATH%" (
    echo ERROR: FanController.exe not found at:
    echo   %APP_PATH%
    echo.
    echo Please install the app first.
    pause
    exit /b 1
)

echo Starting FanController in debug mode...
echo If it crashes, the error will be shown here.
echo.
echo Log file location: %APPDATA%\FanController\app.log
echo.

REM Run the app and wait for it to exit
"%APP_PATH%"

REM Check exit code
if %errorlevel% neq 0 (
    echo.
    echo ==========================================================
    echo   APPLICATION CRASHED
    echo   Exit code: %errorlevel%
    echo ==========================================================
    echo.
    echo Checking log file...
    echo.

    set "LOG_FILE=%APPDATA%\FanController\app.log"
    if exist "%LOG_FILE%" (
        echo Last 30 lines of app.log:
        echo ----------------------------------------
        powershell -NoProfile -Command "Get-Content '%LOG_FILE%' -Tail 30"
        echo ----------------------------------------
    ) else (
        echo Log file not found at %LOG_FILE%
    )
) else (
    echo.
    echo Application exited normally.
)

echo.
echo Press any key to close...
pause >nul
