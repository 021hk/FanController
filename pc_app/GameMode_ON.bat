@echo off
REM ============================================================
REM  GameMode_ON.bat - Quick Game Mode toggle (fans 100%)
REM  Edit ESP_IP below to match your ESP8266 IP address.
REM ============================================================

set ESP_IP=192.168.4.1
set ESP_PORT=80

echo Activating Game Mode (all fans 100%%)...
curl -s "http://%ESP_IP%:%ESP_PORT%/set?fan=gpu&percent=100&mode=game" > nul
curl -s "http://%ESP_IP%:%ESP_PORT%/set?fan=cpu&percent=100&mode=game" > nul
timeout /t 1 > nul
echo Done. All fans now at 100%%.
