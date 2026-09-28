@echo off
REM ============================================================
REM  GameMode_OFF.bat - Reset fans to Auto curve
REM  Edit ESP_IP below to match your ESP8266 IP address.
REM ============================================================

set ESP_IP=192.168.4.1
set ESP_PORT=80

echo Resetting fans to Auto curve...
curl -s "http://%ESP_IP%:%ESP_PORT%/set?fan=gpu&percent=0&mode=auto" > nul
curl -s "http://%ESP_IP%:%ESP_PORT%/set?fan=cpu&percent=0&mode=auto" > nul
timeout /t 1 > nul
echo Done. Fans back to Auto.
