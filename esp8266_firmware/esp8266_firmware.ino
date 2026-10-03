/* ============================================================
 *  ESP8266 Dual PWM Fan Controller - v3.0 (Stable + Auto Mode)
 *  ----------------------------------------------------------
 *  Target  : NodeMCU 1.0 (ESP-12E Module) - V3
 *  WiFi    : AP (Hotspot)
 *    SSID:     FanController
 *    Password: 12345678
 *    IP:       192.168.4.1
 *
 *  Features:
 *    - 2x PWM fan outputs (CPU, GPU) at 25kHz
 *    - WebSocket server on port 81 (real-time)
 *    - HTTP REST on port 80 (fallback)
 *    - USB Serial fallback (115200 baud)
 *    - Physical button for Game Mode toggle
 *    - 4 profiles (Silent/Balanced/Performance/Game)
 *    - AUTO mode: fans follow temperature curve from PC
 *    - MANUAL mode: fans stay at fixed percent
 *    - GAME mode: all fans 100%
 *    - FAILSAFE: 70% if PC lost contact >30s
 *    - EEPROM persistence
 * ============================================================
 */

#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ESP8266mDNS.h>
#include <WebSocketsServer.h>
#include <ArduinoJson.h>
#include <EEPROM.h>

// ============================================================
//  USER CONFIG
// ============================================================
const char* AP_SSID      = "FanController";
const char* AP_PASSWORD   = "12345678";   // min 8 chars

IPAddress AP_IP      (192, 168, 4, 1);
IPAddress AP_GATEWAY (192, 168, 4, 1);
IPAddress AP_SUBNET  (255, 255, 255, 0);

#define AP_CHANNEL     1
#define AP_MAX_CLIENTS 4

// ============================================================
//  PINS (NodeMCU V3)
// ============================================================
#define FAN_CPU_PIN     5   // D1 = GPIO5  (PWM output)
#define FAN_GPU_PIN     4   // D2 = GPIO4  (PWM output)
#define FAN_CPU_TACH    12  // D6 = GPIO12 (RPM input from CPU fan tach)
#define FAN_GPU_TACH    13  // D7 = GPIO13 (RPM input from GPU fan tach)
#define BUTTON_PIN      14  // D5 = GPIO14 (Game Mode button)
#define STATUS_LED      2   // D4 = GPIO2  (onboard LED, active low)

// ============================================================
//  CONSTANTS
// ============================================================
#define PWM_FREQ_HZ      25000UL
#define PWM_RANGE        1023
#define PWM_MIN_DUTY     102
#define PERCENT_TO_DUTY(p)  ((p * PWM_RANGE) / 100)

#define WS_PORT          81
#define HTTP_PORT        80
#define SERIAL_BAUD      115200
#define DEBOUNCE_MS      50
#define LONGPRESS_MS     1500
#define EEPROM_SIZE      512
#define EEPROM_MAGIC     0xA5
#define NUM_FANS         2
#define CURVE_POINTS    7

enum FanID    : uint8_t { FAN_CPU = 0, FAN_GPU = 1 };
enum CtrlMode : uint8_t { MODE_AUTO = 0, MODE_MANUAL = 1, MODE_GAME = 2, MODE_FAILSAFE = 3 };

struct FanState {
  uint8_t  percent = 50;
  CtrlMode mode = MODE_AUTO;
};

struct FanCurve {
  uint8_t temps[CURVE_POINTS]    = {30, 40, 50, 60, 70, 80, 90};
  uint8_t percents[CURVE_POINTS]= {20, 30, 40, 55, 75, 90, 100};
  uint8_t numPoints = 7;
};

FanState  fans[NUM_FANS];
FanCurve  curves[NUM_FANS];
uint8_t   lastTemps[NUM_FANS] = {40, 40};
uint8_t   activeProfile = 1;
bool      gameMode = false;
bool      autoMode = true;  // AUTO mode enabled by default
bool      usbFallback = false;  // True when USB serial is active (no WiFi)
unsigned long lastPCContact = 0;
unsigned long lastButtonPress = 0;
bool      lastButtonState = HIGH;

// RPM counting (tach pulses via interrupt)
volatile unsigned int tachCounts[NUM_FANS] = {0, 0};
unsigned long lastRPMCheck = 0;
uint16_t fanRPM[NUM_FANS] = {0, 0};

ESP8266WebServer http(HTTP_PORT);
WebSocketsServer  ws(WS_PORT);

// ============================================================
//  TACH INTERRUPT HANDLERS (RPM measurement)
// ============================================================
// PC fan tachometer: 2 pulses per revolution
// We count pulses, then RPM = (pulses / 2) * (60 / time_window_sec)
// Standard: pulses in 1 second / 2 = RPS, * 60 = RPM

void IRAM_ATTR cpuTachISR() {
  tachCounts[FAN_CPU]++;
}

void IRAM_ATTR gpuTachISR() {
  tachCounts[FAN_GPU]++;
}

void updateRPM() {
  // Called periodically to compute RPM from pulse counts
  unsigned long now = millis();
  if (now - lastRPMCheck < 1000) return;  // 1 second window
  unsigned long elapsed = now - lastRPMCheck;
  lastRPMCheck = now;

  // Disable interrupts briefly to read counts
  noInterrupts();
  unsigned int cpuCount = tachCounts[FAN_CPU];
  unsigned int gpuCount = tachCounts[FAN_GPU];
  tachCounts[FAN_CPU] = 0;
  tachCounts[FAN_GPU] = 0;
  interrupts();

  // RPM = (pulses / 2) * (60000 / elapsed_ms)
  // Most PC fans: 2 pulses per revolution
  fanRPM[FAN_CPU] = (uint16_t)((cpuCount * 60000UL) / (2UL * elapsed));
  fanRPM[FAN_GPU] = (uint16_t)((gpuCount * 60000UL) / (2UL * elapsed));

  Serial.printf("[RPM] CPU=%u  GPU=%u\n", fanRPM[FAN_CPU], fanRPM[FAN_GPU]);
}

// ============================================================
//  SETUP
// ============================================================
void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(200);
  Serial.println(F("\n[BOOT] ESP8266 Fan Controller v3.0"));

  pinMode(FAN_CPU_PIN, OUTPUT);
  pinMode(FAN_GPU_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(STATUS_LED, OUTPUT);

  // Tach pins (input with pullup - tach signal is open-collector)
  pinMode(FAN_CPU_TACH, INPUT_PULLUP);
  pinMode(FAN_GPU_TACH, INPUT_PULLUP);
  // Attach interrupts for RPM measurement (FALLING edge = 1 pulse per rev on most fans)
  attachInterrupt(digitalPinToInterrupt(FAN_CPU_TACH), cpuTachISR, FALLING);
  attachInterrupt(digitalPinToInterrupt(FAN_GPU_TACH), gpuTachISR, FALLING);
  lastRPMCheck = millis();

  analogWriteFreq(PWM_FREQ_HZ);
  analogWriteRange(PWM_RANGE);

  // Initial 50% to ensure fans are spinning
  setFanPercent(FAN_CPU, 50);
  setFanPercent(FAN_GPU, 50);
  digitalWrite(STATUS_LED, HIGH);   // LED OFF (active low)

  EEPROM.begin(EEPROM_SIZE);
  loadEEPROM();

  // Start WiFi AP
  Serial.printf("[AP] Starting hotspot '%s'...\n", AP_SSID);
  WiFi.mode(WIFI_AP);
  WiFi.softAPConfig(AP_IP, AP_GATEWAY, AP_SUBNET);

  bool apOK;
  if (strlen(AP_PASSWORD) >= 8) {
    apOK = WiFi.softAP(AP_SSID, AP_PASSWORD, AP_CHANNEL, false, AP_MAX_CLIENTS);
  } else {
    apOK = WiFi.softAP(AP_SSID, NULL, AP_CHANNEL, false, AP_MAX_CLIENTS);
  }

  if (apOK) {
    Serial.print(F("[AP] Hotspot started! IP="));
    Serial.println(WiFi.softAPIP());
    Serial.printf("[AP] SSID='%s'  Pass='%s'\n", AP_SSID, AP_PASSWORD);

    http.on("/",      []() {
      http.send(200, "text/plain",
        "ESP8266 Fan Controller v3.0\n"
        "Endpoints: /status /set?fan=cpu&percent=80&mode=manual\n"
        "WebSocket: port 81\n");
    });
    http.on("/status", handleStatus);
    http.on("/set",   handleSetFan);
    http.onNotFound([]() { http.send(404, "text/plain", "404"); });
    http.begin();

    ws.begin();
    ws.onEvent(handleWebSocket);

    if (MDNS.begin("fanctrl")) {
      MDNS.addService("http", "tcp", 80);
    }

    // Blink LED 3 times to confirm AP is up
    for (uint8_t i = 0; i < 3; i++) {
      digitalWrite(STATUS_LED, LOW);  delay(100);
      digitalWrite(STATUS_LED, HIGH); delay(100);
    }
    Serial.println(F("[BOOT] ready - connect PC to WiFi 'FanController'"));
  } else {
    Serial.println(F("[AP] FAILED - check config"));
  }
}

// ============================================================
//  LOOP
// ============================================================
void loop() {
  http.handleClient();
  ws.loop();
  processSerial();
  checkButton();
  checkWatchdog();
  updateRPM();  // Update RPM every 1 second
}

// ============================================================
//  FAN CONTROL
// ============================================================
void setFanPercent(uint8_t fan, uint8_t percent) {
  percent = constrain(percent, 0, 100);
  fans[fan].percent = percent;
  uint16_t duty = PERCENT_TO_DUTY(percent);
  if (percent > 0 && duty < PWM_MIN_DUTY) duty = PWM_MIN_DUTY;
  if (fan == FAN_CPU) analogWrite(FAN_CPU_PIN, duty);
  else                analogWrite(FAN_GPU_PIN, duty);
}

uint8_t evalCurve(uint8_t fan, uint8_t temp) {
  FanCurve& c = curves[fan];
  if (c.numPoints == 0) return 50;
  if (temp <= c.temps[0]) return c.percents[0];
  if (temp >= c.temps[c.numPoints - 1]) return c.percents[c.numPoints - 1];
  for (uint8_t i = 0; i < c.numPoints - 1; i++) {
    if (temp >= c.temps[i] && temp <= c.temps[i + 1]) {
      float slope = (float)(c.percents[i + 1] - c.percents[i]) /
                    (float)(c.temps[i + 1]   - c.temps[i]);
      float pct = c.percents[i] + slope * (temp - c.temps[i]);
      return (uint8_t)constrain((int)pct, 0, 100);
    }
  }
  return c.percents[c.numPoints - 1];
}

void applyProfile(uint8_t p) {
  activeProfile = p;
  switch (p) {
    case 0: // Silent
      for (uint8_t i = 0; i < NUM_FANS; i++)
        curves[i] = { {30,40,50,60,70,80,90}, {15,25,35,50,65,80,95}, 7 };
      break;
    case 1: // Balanced
      for (uint8_t i = 0; i < NUM_FANS; i++)
        curves[i] = { {30,40,50,60,70,80,90}, {20,30,40,55,70,85,100}, 7 };
      break;
    case 2: // Performance
      for (uint8_t i = 0; i < NUM_FANS; i++)
        curves[i] = { {30,40,50,60,65,70,80}, {30,45,60,75,85,95,100}, 7 };
      break;
    case 3: // Game (min 60%)
      for (uint8_t i = 0; i < NUM_FANS; i++)
        curves[i] = { {30,40,50,60,70,80,90}, {60,70,80,90,95,100,100}, 7 };
      break;
  }
  saveEEPROM();
  Serial.printf("[PROFILE] #%d applied\n", p);
}

void setGameMode(bool on) {
  gameMode = on;
  if (on) {
    applyProfile(3);
    setFanPercent(FAN_CPU, 100);
    setFanPercent(FAN_GPU, 100);
    fans[FAN_CPU].mode = MODE_GAME;
    fans[FAN_GPU].mode = MODE_GAME;
    digitalWrite(STATUS_LED, LOW);  // LED ON
    Serial.println(F("[GAME] ON - 100%"));
  } else {
    fans[FAN_CPU].mode = MODE_AUTO;
    fans[FAN_GPU].mode = MODE_AUTO;
    digitalWrite(STATUS_LED, HIGH);
    Serial.println(F("[GAME] OFF - back to auto"));
  }
  saveEEPROM();
  sendStateToClients();
}

// ============================================================
//  WEBSOCKET
// ============================================================
void handleWebSocket(uint8_t num, WStype_t type, uint8_t *payload, size_t length) {
  if (type == WStype_CONNECTED) {
    Serial.printf("[WS] client %u connected\n", num);
    sendStateToClients();
  } else if (type == WStype_TEXT) {
    StaticJsonDocument<512> doc;
    if (deserializeJson(doc, (const char*)payload)) return;
    const char* cmd = doc["cmd"] | "";

    if (strcmp(cmd, "temps") == 0) {
      // PC pushes current CPU/GPU temps
      lastTemps[FAN_CPU] = doc["cpu"] | lastTemps[FAN_CPU];
      lastTemps[FAN_GPU] = doc["gpu"] | lastTemps[FAN_GPU];
      lastPCContact = millis();
      Serial.printf("[TEMP] CPU=%u GPU=%u\n", lastTemps[FAN_CPU], lastTemps[FAN_GPU]);
      // Auto-adjust fans if in AUTO mode and not in GAME mode
      if (autoMode && !gameMode) {
        uint8_t cpuPct = evalCurve(FAN_CPU, lastTemps[FAN_CPU]);
        uint8_t gpuPct = evalCurve(FAN_GPU, lastTemps[FAN_GPU]);
        setFanPercent(FAN_CPU, cpuPct);
        setFanPercent(FAN_GPU, gpuPct);
        Serial.printf("[AUTO] CPU->%u%% GPU->%u%%\n", cpuPct, gpuPct);
      }
      sendStateToClients();
    }
    else if (strcmp(cmd, "set") == 0) {
      const char* fanStr = doc["fan"] | "cpu";
      uint8_t fan = (strcmp(fanStr, "gpu") == 0) ? FAN_GPU : FAN_CPU;
      uint8_t pct = doc["percent"] | 50;
      const char* mode = doc["mode"] | "manual";
      if (strcmp(mode, "auto") == 0) {
        fans[fan].mode = MODE_AUTO;
        Serial.printf("[SET] %s AUTO\n", fanStr);
      } else if (strcmp(mode, "game") == 0) {
        fans[fan].mode = MODE_GAME;
        setFanPercent(fan, 100);
        Serial.printf("[SET] %s GAME\n", fanStr);
        saveEEPROM();
        sendStateToClients();
        return;
      } else {
        fans[fan].mode = MODE_MANUAL;
        setFanPercent(fan, pct);
        Serial.printf("[SET] %s %u%% MANUAL\n", fanStr, pct);
      }
      saveEEPROM();
      sendStateToClients();
    }
    else if (strcmp(cmd, "game") == 0) {
      setGameMode(doc["on"] | true);
    }
    else if (strcmp(cmd, "auto") == 0) {
      // Toggle auto mode globally
      autoMode = doc["on"] | true;
      Serial.printf("[AUTO] mode %s\n", autoMode ? "ON" : "OFF");
      if (!autoMode && !gameMode) {
        // If auto disabled, hold current fan speeds
        Serial.println(F("[AUTO] holding current speeds"));
      }
      saveEEPROM();
      sendStateToClients();
    }
    else if (strcmp(cmd, "profile") == 0) {
      uint8_t pid = doc["id"] | 1;
      applyProfile(pid);
      if (autoMode && !gameMode) {
        setFanPercent(FAN_CPU, evalCurve(FAN_CPU, lastTemps[FAN_CPU]));
        setFanPercent(FAN_GPU, evalCurve(FAN_GPU, lastTemps[FAN_GPU]));
      }
      sendStateToClients();
    }
    else if (strcmp(cmd, "curve") == 0) {
      uint8_t fan = (strcmp(doc["fan"] | "cpu", "gpu") == 0) ? FAN_GPU : FAN_CPU;
      JsonArray t = doc["temps"].as<JsonArray>();
      JsonArray p = doc["percents"].as<JsonArray>();
      uint8_t n = min((uint8_t)t.size(), (uint8_t)CURVE_POINTS);
      for (uint8_t i = 0; i < n; i++) {
        curves[fan].temps[i]    = t[i];
        curves[fan].percents[i] = p[i];
      }
      curves[fan].numPoints = n;
      saveEEPROM();
      Serial.printf("[CURVE] %s updated (%u pts)\n", fan==FAN_CPU?"CPU":"GPU", n);
      sendStateToClients();
    }
    else if (strcmp(cmd, "status") == 0) {
      sendStateToClients();
    }
  }
}

void sendStateToClients() {
  StaticJsonDocument<512> doc;
  doc["type"]      = "status";
  doc["cpu_pct"]   = fans[FAN_CPU].percent;
  doc["gpu_pct"]   = fans[FAN_GPU].percent;
  doc["cpu_temp"]  = lastTemps[FAN_CPU];
  doc["gpu_temp"]  = lastTemps[FAN_GPU];
  doc["cpu_rpm"]   = fanRPM[FAN_CPU];
  doc["gpu_rpm"]   = fanRPM[FAN_GPU];
  doc["cpu_mode"]  = (uint8_t)fans[FAN_CPU].mode;
  doc["gpu_mode"]  = (uint8_t)fans[FAN_GPU].mode;
  doc["profile"]   = activeProfile;
  doc["game"]      = gameMode;
  doc["auto"]      = autoMode;
  String out;
  serializeJson(doc, out);
  ws.broadcastTXT(out);
  // Also send via USB serial if connected
  if (usbFallback) {
    serializeJson(doc, Serial);
    Serial.println();
  }
}

// ============================================================
//  HTTP REST
// ============================================================
void handleStatus() {
  String json;
  StaticJsonDocument<512> doc;
  doc["cpu_pct"]  = fans[FAN_CPU].percent;
  doc["gpu_pct"]  = fans[FAN_GPU].percent;
  doc["cpu_temp"] = lastTemps[FAN_CPU];
  doc["gpu_temp"] = lastTemps[FAN_GPU];
  doc["cpu_rpm"]  = fanRPM[FAN_CPU];
  doc["gpu_rpm"]  = fanRPM[FAN_GPU];
  doc["cpu_mode"] = (uint8_t)fans[FAN_CPU].mode;
  doc["gpu_mode"] = (uint8_t)fans[FAN_GPU].mode;
  doc["profile"]  = activeProfile;
  doc["game"]     = gameMode;
  doc["auto"]     = autoMode;
  doc["ip"]       = WiFi.softAPIP().toString();
  doc["uptime"]   = millis() / 1000;
  serializeJson(doc, json);
  http.send(200, "application/json", json);
}

void handleSetFan() {
  String fanStr = http.arg("fan");
  String pctStr = http.arg("percent");
  String modeStr = http.arg("mode");
  uint8_t fan = (fanStr == "gpu") ? FAN_GPU : FAN_CPU;
  uint8_t pct = pctStr.toInt();
  if (modeStr == "auto") {
    fans[fan].mode = MODE_AUTO;
  } else if (modeStr == "game") {
    fans[fan].mode = MODE_GAME;
    setFanPercent(fan, 100);
    http.send(200, "application/json", "{\"ok\":true}");
    saveEEPROM();
    sendStateToClients();
    return;
  } else {
    fans[fan].mode = MODE_MANUAL;
    setFanPercent(fan, pct);
  }
  saveEEPROM();
  sendStateToClients();
  http.send(200, "application/json", "{\"ok\":true}");
}

// ============================================================
//  USB SERIAL (fallback)
// ============================================================
void processSerial() {
  static String buffer;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (buffer.length() > 0) {
        StaticJsonDocument<512> doc;
        if (!deserializeJson(doc, buffer)) {
          const char* cmd = doc["cmd"] | "";
          if (strcmp(cmd, "temps") == 0) {
            lastTemps[FAN_CPU] = doc["cpu"] | lastTemps[FAN_CPU];
            lastTemps[FAN_GPU] = doc["gpu"] | lastTemps[FAN_GPU];
            lastPCContact = millis();
            if (autoMode && !gameMode) {
              setFanPercent(FAN_CPU, evalCurve(FAN_CPU, lastTemps[FAN_CPU]));
              setFanPercent(FAN_GPU, evalCurve(FAN_GPU, lastTemps[FAN_GPU]));
            }
          } else if (strcmp(cmd, "status") == 0) {
            StaticJsonDocument<512> s;
            s["type"] = "status";
            s["cpu_pct"] = fans[FAN_CPU].percent;
            s["gpu_pct"] = fans[FAN_GPU].percent;
            s["cpu_temp"] = lastTemps[FAN_CPU];
            s["gpu_temp"] = lastTemps[FAN_GPU];
            s["game"] = gameMode;
            s["auto"] = autoMode;
            serializeJson(s, Serial);
            Serial.println();
          }
        }
        buffer = "";
      }
    } else {
      buffer += c;
      if (buffer.length() > 512) buffer = "";
    }
  }
}

// ============================================================
//  BUTTON
// ============================================================
void checkButton() {
  bool now = digitalRead(BUTTON_PIN);
  if (now != lastButtonState) {
    delay(DEBOUNCE_MS);
    now = digitalRead(BUTTON_PIN);
  }
  if (lastButtonState == HIGH && now == LOW) {
    lastButtonPress = millis();
  } else if (lastButtonState == LOW && now == HIGH) {
    unsigned long held = millis() - lastButtonPress;
    if (held > 50 && held < LONGPRESS_MS) {
      setGameMode(!gameMode);
    } else if (held >= LONGPRESS_MS) {
      setGameMode(false);
      applyProfile(0);
      if (autoMode) {
        setFanPercent(FAN_CPU, evalCurve(FAN_CPU, lastTemps[FAN_CPU]));
        setFanPercent(FAN_GPU, evalCurve(FAN_GPU, lastTemps[FAN_GPU]));
      }
      sendStateToClients();
    }
  }
  lastButtonState = now;
}

// ============================================================
//  WATCHDOG
// ============================================================
void checkWatchdog() {
  static unsigned long lastCheck = 0;
  if (millis() - lastCheck < 5000) return;
  lastCheck = millis();

  // Lost contact for >30s -> failsafe 70%
  if (millis() - lastPCContact > 30000) {
    if (fans[FAN_CPU].mode != MODE_FAILSAFE) {
      fans[FAN_CPU].mode = MODE_FAILSAFE;
      fans[FAN_GPU].mode = MODE_FAILSAFE;
      setFanPercent(FAN_CPU, 70);
      setFanPercent(FAN_GPU, 70);
      Serial.println(F("[FAILSAFE] No PC contact >30s -> 70%"));
    }
  } else if (fans[FAN_CPU].mode == MODE_FAILSAFE && millis() - lastPCContact < 5000) {
    fans[FAN_CPU].mode = MODE_AUTO;
    fans[FAN_GPU].mode = MODE_AUTO;
    Serial.println(F("[FAILSAFE] recovered"));
  }

  // Print client count
  static uint8_t lastClientCount = 99;
  uint8_t clientCount = WiFi.softAPgetStationNum();
  if (clientCount != lastClientCount) {
    Serial.printf("[AP] clients: %u\n", clientCount);
    lastClientCount = clientCount;
  }
}

// ============================================================
//  EEPROM
// ============================================================
struct EEPROMLayout {
  uint8_t  magic;
  uint8_t  activeProfile;
  uint8_t  gameMode;
  uint8_t  autoMode;
  FanCurve curves[NUM_FANS];
};

void loadEEPROM() {
  EEPROMLayout data;
  EEPROM.get(0, data);
  if (data.magic != EEPROM_MAGIC) {
    Serial.println(F("[EEPROM] fresh init"));
    applyProfile(1);
    saveEEPROM();
    return;
  }
  activeProfile = data.activeProfile;
  gameMode      = data.gameMode;
  autoMode      = data.autoMode ? true : false;
  memcpy(curves, data.curves, sizeof(curves));
  Serial.printf("[EEPROM] loaded profile=%u game=%u auto=%u\n",
                 activeProfile, gameMode, autoMode);
  applyProfile(activeProfile);
}

void saveEEPROM() {
  EEPROMLayout data;
  data.magic         = EEPROM_MAGIC;
  data.activeProfile = activeProfile;
  data.gameMode      = gameMode;
  data.autoMode      = autoMode ? 1 : 0;
  memcpy(data.curves, curves, sizeof(curves));
  EEPROM.put(0, data);
  EEPROM.commit();
}
