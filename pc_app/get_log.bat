@echo off
REM ============================================================
REM  get_log.bat - Collect diagnostic info and save to Desktop
REM
REM  Just double-click this file. It will:
REM   1. Read app.log + stdout.log
REM   2. Run a live temperature test
REM   3. Save everything to Desktop\FanController_Log.txt
REM   4. Open the file in Notepad
REM ============================================================

setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

echo.
echo ==========================================================
echo   Fan Controller - Log Collector
echo ==========================================================
echo.

REM Get Desktop path
set "DESKTOP=%USERPROFILE%\Desktop"
if not exist "%DESKTOP%" set "DESKTOP=%USERPROFILE%\OneDrive\Desktop"
if not exist "%DESKTOP%" set "DESKTOP=%USERPROFILE%"

set "OUTFILE=%DESKTOP%\FanController_Log.txt"

echo Collecting system info...
echo ============================================ > "%OUTFILE%"
echo Fan Controller - Diagnostic Log >> "%OUTFILE%"
echo Generated: %date% %time% >> "%OUTFILE%"
echo ============================================ >> "%OUTFILE%"
echo. >> "%OUTFILE%"

echo SYSTEM INFO >> "%OUTFILE%"
echo ------------ >> "%OUTFILE%"
echo OS: %OS% >> "%OUTFILE%"
ver >> "%OUTFILE%"
echo Username: %USERNAME% >> "%OUTFILE%"
echo Computer: %COMPUTERNAME% >> "%OUTFILE%"
echo. >> "%OUTFILE%"

REM Get GPU info
echo GPU INFO >> "%OUTFILE%"
echo -------- >> "%OUTFILE%"
powershell -NoProfile -Command "Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion, AdapterRAM | Format-List" >> "%OUTFILE%" 2>&1
echo. >> "%OUTFILE%"

REM Get CPU info
echo CPU INFO >> "%OUTFILE%"
echo -------- >> "%OUTFILE%"
powershell -NoProfile -Command "Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors | Format-List" >> "%OUTFILE%" 2>&1
echo. >> "%OUTFILE%"

echo APP LOG (last 100 lines) >> "%OUTFILE%"
echo ----------------------- >> "%OUTFILE%"
set "APPLOG=%APPDATA%\FanController\app.log"
if exist "%APPLOG%" (
    powershell -NoProfile -Command "Get-Content '%APPLOG%' -Tail 100" >> "%OUTFILE%" 2>&1
) else (
    echo app.log NOT FOUND at %APPLOG% >> "%OUTFILE%"
)
echo. >> "%OUTFILE%"

echo STDOUT LOG (last 50 lines) >> "%OUTFILE%"
echo ------------------------- >> "%OUTFILE%"
set "STDOUTLOG=%APPDATA%\FanController\stdout.log"
if exist "%STDOUTLOG%" (
    powershell -NoProfile -Command "Get-Content '%STDOUTLOG%' -Tail 50" >> "%OUTFILE%" 2>&1
) else (
    echo stdout.log NOT FOUND >> "%OUTFILE%"
)
echo. >> "%OUTFILE%"

echo ============================================ >> "%OUTFILE%"
echo LIVE TEMPERATURE TEST >> "%OUTFILE%"
echo ============================================ >> "%OUTFILE%"
echo. >> "%OUTFILE%"

REM Test 1: LHM WMI namespace check
echo Test 1: Checking LHM WMI namespace... >> "%OUTFILE%"
powershell -NoProfile -Command "try { $sensors = Get-CimInstance -Namespace 'root/LibreHardwareMonitor' -ClassName Sensor -ErrorAction Stop | Where-Object { $_.SensorType -eq 'Temperature' -and $_.Value -gt 0 }; if ($sensors) { Write-Output 'LHM WMI: AVAILABLE'; Write-Output ('Sensor count: ' + $sensors.Count); Write-Output ''; Write-Output 'ALL TEMPERATURE SENSORS:'; $sensors | Sort-Object Value -Descending | ForEach-Object { Write-Output ('  ' + $_.Value.ToString() + '°C | ' + $_.Name + ' | ' + $_.Parent) } } else { Write-Output 'LHM WMI: NO SENSORS' } } catch { Write-Output ('LHM WMI: NOT AVAILABLE - ' + $_.Exception.Message) }" >> "%OUTFILE%" 2>&1
echo. >> "%OUTFILE%"

REM Test 2: OpenHardwareMonitor WMI namespace
echo Test 2: Checking OpenHardwareMonitor WMI namespace... >> "%OUTFILE%"
powershell -NoProfile -Command "try { $sensors = Get-CimInstance -Namespace 'root/OpenHardwareMonitor' -ClassName Sensor -ErrorAction Stop | Where-Object { $_.SensorType -eq 'Temperature' -and $_.Value -gt 0 }; if ($sensors) { Write-Output 'OHM WMI: AVAILABLE'; Write-Output ('Sensor count: ' + $sensors.Count); Write-Output ''; Write-Output 'ALL TEMPERATURE SENSORS:'; $sensors | Sort-Object Value -Descending | ForEach-Object { Write-Output ('  ' + $_.Value.ToString() + '°C | ' + $_.Name + ' | ' + $_.Parent) } } else { Write-Output 'OHM WMI: NO SENSORS' } } catch { Write-Output ('OHM WMI: NOT AVAILABLE - ' + $_.Exception.Message) }" >> "%OUTFILE%" 2>&1
echo. >> "%OUTFILE%"

REM Test 3: nvidia-smi
echo Test 3: Checking nvidia-smi... >> "%OUTFILE%"
where nvidia-smi >nul 2>&1
if %errorlevel%==0 (
    echo nvidia-smi: AVAILABLE >> "%OUTFILE%"
    nvidia-smi --query-gpu=temperature.gpu,name --format=csv,noheader,nounits >> "%OUTFILE%" 2>&1
) else (
    echo nvidia-smi: NOT FOUND >> "%OUTFILE%"
)
echo. >> "%OUTFILE%"

REM Test 4: MSAcpi_ThermalZoneTemperature
echo Test 4: Checking MSAcpi_ThermalZoneTemperature... >> "%OUTFILE%"
powershell -NoProfile -Command "try { $t = Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction Stop | Select-Object -First 1; if ($t) { $k = $t.CurrentTemperature / 10; $c = $k - 273.15; Write-Output ('CPU temp (ACPI): ' + [math]::Round($c,1) + '°C') } else { Write-Output 'ACPI: no data' } } catch { Write-Output ('ACPI: NOT AVAILABLE - ' + $_.Exception.Message) }" >> "%OUTFILE%" 2>&1
echo. >> "%OUTFILE%"

REM Test 5: Check if LHM.exe is running
echo Test 5: Is LibreHardwareMonitor.exe running? >> "%OUTFILE%"
tasklist /FI "IMAGENAME eq LibreHardwareMonitor.exe" >> "%OUTFILE%" 2>&1
echo. >> "%OUTFILE%"

REM Test 6: Check if FanController is running
echo Test 6: Is FanController.exe running? >> "%OUTFILE%"
tasklist /FI "IMAGENAME eq FanController.exe" >> "%OUTFILE%" 2>&1
echo. >> "%OUTFILE%"

REM Test 7: Admin check
echo Test 7: Admin status >> "%OUTFILE%"
net session >nul 2>&1
if %errorlevel%==0 (
    echo Running as: ADMINISTRATOR >> "%OUTFILE%"
) else (
    echo Running as: NORMAL USER (no admin) >> "%OUTFILE%"
)
echo. >> "%OUTFILE%"

echo ============================================ >> "%OUTFILE%"
echo END OF LOG >> "%OUTFILE%"
echo ============================================ >> "%OUTFILE%"

echo.
echo ✓ Log saved to:
echo    %OUTFILE%
echo.
echo Opening file in Notepad...
echo.

start notepad "%OUTFILE%"

echo.
echo You can now send this file to the developer.
echo Press any key to close...
pause >nul
