@echo off
REM ============================================================
REM  check_connection.bat - Diagnostic tool for ESP8266 connection
REM
REM  Just double-click to run. It will check:
REM  1. COM ports available (and which one is ESP8266)
REM  2. WiFi connection to FanController hotspot
REM  3. Serial port test (if ESP8266 detected)
REM ============================================================

setlocal
chcp 65001 >nul 2>&1

echo.
echo ==========================================================
echo   ESP8266 Connection Diagnostic
echo ==========================================================
echo.

REM Try to find python
set "PYTHON="
for %%p in (python py python3) do (
    where %%p >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON=%%p"
        goto found
    )
)
:found

if "%PYTHON%"=="" (
    echo Python not found in PATH.
    echo Please install Python from: https://python.org/downloads
    pause
    exit /b 1
)

echo Using Python: %PYTHON%
echo.
%PYTHON% "%~dp0check_connection.py"
echo.
pause
