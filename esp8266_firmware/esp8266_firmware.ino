/* ============================================================
 *  ESP8266 Dual PWM Fan Controller - v2.0 (matched with PC GUI v1.3.8)
 *  ----------------------------------------------------------
 *  Target  : ESP8266 (NodeMCU v1.0 / Wemos D1 Mini)
 *  Board   : "NodeMCU 1.0 (ESP-12E Module)"
 *  Library : ESP8266 Arduino Core >= 3.0
 *            + WebSocketsServer (Links2004/arduinoWebSockets)
 *            + ArduinoJson 6.x
 *
 *  WiFi Mode: AP (Hotspot)
 *    SSID:     FanController
 *    Password: 12345678
 *    IP:       192.168.4.1
 *    WS Port:  81
 *    HTTP:     80
 *
 *  Protocol (JSON over WebSocket):
 *    PC -> ESP:
 *      {"cmd":"temps","cpu":52,"gpu":68}      // push current temps
 *      {"cmd":"set","fan":"cpu","percent":80,"mode":"manual"}
 *      {"cmd":"game","on":true}
 *      {"cmd":"profile","id":2}                // 0=Silent 1=Balanced 2=Performance 3=Game
 *      {"cmd":"curve","fan":"cpu","temps":[30,50,70,90],"percents":[20,40,75,100]}
 *      {"cmd":"status"}                        // request current state
 *    ESP -> PC:
 *      {"type":"status","cpu_pct":55,"gpu_pct":100,"cpu_temp":52,"gpu_temp":68,
 *       "cpu_mode":0,"gpu_mode":2,"profile":3,"game":true}
 *
 *  Modes: 0=Auto (use curve), 1=Manual, 2=Game (100%), 3=Failsafe (70%)
 * ============================================================
 */

#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <WebSocketsServer.h>
#include <ArduinoJson.h>
#include <EEPROM.h>

// ============================================================
//  USER CONFIG - EDIT THESE BEFORE FIRST FLASH
// ============================================================
const char* AP_SSID      = "FanController";
const char* AP_PASSWORD   = "12345678";   // min 8 chars, or "" for open AP

IPAddress AP_IP      (192, 168, 4, 1);
IPAddress AP_GATEWAY (192, 168, 4, 1);
IPAddress AP_SUBNET  (255, 255, 255, 0);

#define AP_CHANNEL     1
#define AP_MAX_CLIENTS 4

// ============================================================
//  PIN MAPPING (NodeMCU D1 Mini)
//  D1 = GPIO5  -> CPU fan PWM (4-pin header pin 4)
//  D2 = GPIO4  -> GPU fan PWM (4-pin header pin 4)
//  D5 = GPIO14 -> Game Mode push button (active low, to GND)
//  D4 = GPIO2  -> Onboard LED (active low - shows Game Mode status)
//  D6 = GPIO12 -> USB VBUS detect (optional, via voltage divider)
//  Vin        -> 5V from USB or PSU
//  GND        -> Common ground with PSU (CRITICAL!)
// ============================================================
#define FAN_CPU_PIN     5   // D1
#define FAN_GPU_PIN     4   // D2
#define BUTTON_PIN      14  // D5
#define STATUS_LED      2   // D4
#define USB_DETECT_PIN  12  // D6

// ============================================================
//  CONSTANTS
// ============================================================
#define PWM_FREQ_HZ      25000UL    // Intel PC fan spec: 25 kHz
#define PWM_RANGE        1023       // 10-bit
#define PWM_MIN_DUTY     102        // 10% minimum (keep fan spinning)
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
  uint8_t  percent = 30;
  uint8_t  manualPercent = 50;
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
bool      usbFallback = false;
unsigned long lastPCContact = 0;
unsigned long lastButtonPress = 0;
bool      lastButtonState = HIGH;

ESP8266WebServer http(HTTP_PORT);
WebSocketsServer  ws(WS_PORT);

// ============================================================
//  FORWARD DECLARATIONS
// ============================================================
void setFanPercent(uint8_t fan, uint8_t percent);
uint8_t evalCurve(uint8_t fan, uint8_t temp);
void handleWebSocket(uint8_t num, WStype_t type, uint8_t *payload, size_t length);
void handleRoot();
void handleStatus();
void handleSetFan();
void sendStateToClients();
void processSerial();
void checkButton();
void checkWiFi();
void loadEEPROM();
void saveEEPROM();
void applyProfile(uint8_t p);
void setGameMode(bool on);

// ============================================================
//  SETUP
// ============================================================
void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(200);
  Serial.println(F("\n[BOOT] ESP8266 Fan Controller v2.0"));

  pinMode(FAN_CPU_PIN, OUTPUT);
  pinMode(FAN_GPU_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(STATUS_LED, OUTPUT);
  pinMode(USB_DETECT_PIN, INPUT_PULLUP);

  analogWriteFreq(PWM_FREQ_HZ);
  analogWriteRange(PWM_RANGE);

  // Initial safe output (50% so fans are spinning)
  setFanPercent(FAN_CPU, 50);
  setFanPercent(FAN_GPU, 50);
  digitalWrite(STATUS_LED, LOW);   // ON during boot

  EEPROM.begin(EEPROM_SIZE);
  loadEEPROM();

  // ----- AP MODE (HOTSPOT) -----
  Serial.printf("[AP] Starting hotspot '%s' on channel %d...\n",
                 AP_SSID, AP_CHANNEL);

  WiFi.mode(WIFI_AP);
  WiFi.softAPConfig(AP_IP, AP_GATEWAY, AP_SUBNET);

  bool apOK;
  if (strlen(AP_PASSWORD) >= 8) {
    apOK = WiFi.softAP(AP_SSID, AP_PASSWORD, AP_CHANNEL, false, AP_MAX_CLIENTS);
  } else {
    apOK = WiFi.softAP(AP_SSID, NULL, AP_CHANNEL, false, AP_MAX_CLIENTS);
  }

  if (apOK) {
    usbFallback = false;
    Serial.print(F("[AP] Hotspot started! IP="));
    Serial.println(WiFi.softAPIP());
    Serial.printf("[AP] SSID='%s'  Pass='%s'  Clients(max)=%d\n",
                   AP_SSID,
                   (strlen(AP_PASSWORD) >= 8 ? AP_PASSWORD : "(open)"),
                   AP_MAX_CLIENTS);

    http.on("/",      handleRoot);
    http.on("/status",handleStatus);
    http.on("/set",   handleSetFan);
    http.onNotFound([]() { http.send(404, "text/plain", "404"); });
    http.begin();

    ws.begin();
    ws.onEvent(handleWebSocket);

    if (MDNS.begin("fanctrl")) {
      MDNS.addService("http", "tcp", 80);
      Serial.println(F("[mDNS] fanctrl.local"));
    }

    // Blink LED 3 times to indicate AP is up
    for (uint8_t i = 0; i < 3; i++) {
      digitalWrite(STATUS_LED, LOW);  delay(100);
      digitalWrite(STATUS_LED, HIGH); delay(100);
    }
  } else {
    usbFallback = true;
    Serial.println(F("[AP] FAILED to start hotspot -> USB fallback"));
  }

  digitalWrite(STATUS_LED, HIGH);
  Serial.println(F("[BOOT] ready"));
  Serial.println(F("=========================================="));
  Serial.println(F("WiFi Hotspot:"));
  Serial.printf("  SSID: %s\n", AP_SSID);
  Serial.printf("  Pass: %s\n", AP_PASSWORD);
  Serial.print  (F("  IP:   ")); Serial.println(WiFi.softAPIP());
  Serial.println(F("  WS Port: 81  HTTP Port: 80"));
  Serial.println(F("=========================================="));
  Serial.println(F("Connect PC to WiFi 'FanController'"));
  Serial.println(F("Then run FanController.exe on PC"));
  Serial.println(F("=========================================="));
}

// ============================================================
//  LOOP
// ============================================================
void loop() {
  if (!usbFallback) {
    http.handleClient();
    ws.loop();
  }
  processSerial();
  checkButton();
  checkWiFi();
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
    case 1: // Balanced (default)
      for (uint8_t i = 0; i < NUM_FANS; i++)
        curves[i] = { {30,40,50,60,70,80,90}, {20,30,40,55,70,85,100}, 7 };
      break;
    case 2: // Performance
      for (uint8_t i = 0; i < NUM_FANS; i++)
        curves[i] = { {30,40,50,60,65,70,80}, {30,45,60,75,85,95,100}, 7 };
      break;
    case 3: // Game (boosted, min 60%)
      for (uint8_t i = 0; i < NUM_FANS; i++)
        curves[i] = { {30,40,50,60,70,80,90}, {60,70,80,90,95,100,100}, 7 };
      break;
  }
  saveEEPROM();
  Serial.printf("[PROFILE] applied #%d\n", p);
}

void setGameMode(bool on) {
  gameMode = on;
  if (on) {
    applyProfile(3);
    setFanPercent(FAN_CPU, 100);
    setFanPercent(FAN_GPU, 100);
    fans[FAN_CPU].mode = MODE_GAME;
    fans[FAN_GPU].mode = MODE_GAME;
    digitalWrite(STATUS_LED, LOW);  // LED ON = game mode
    Serial.println(F("[GAME] ON - all fans 100%"));
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
//  WEBSOCKET HANDLER
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
      Serial.printf("[TEMP] CPU=%u°C GPU=%u°C\n", lastTemps[FAN_CPU], lastTemps[FAN_GPU]);
      if (!gameMode) {
        uint8_t cpuPct = evalCurve(FAN_CPU, lastTemps[FAN_CPU]);
        uint8_t gpuPct = evalCurve(FAN_GPU, lastTemps[FAN_GPU]);
        setFanPercent(FAN_CPU, cpuPct);
        setFanPercent(FAN_GPU, gpuPct);
        Serial.printf("[FAN] CPU->%u%% GPU->%u%%\n", cpuPct, gpuPct);
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
        Serial.printf("[SET] %s -> AUTO\n", fanStr);
      } else if (strcmp(mode, "game") == 0) {
        fans[fan].mode = MODE_GAME;
        setFanPercent(fan, 100);
        Serial.printf("[SET] %s -> GAME (100%%)\n", fanStr);
        saveEEPROM();
        return;
      } else {
        fans[fan].mode = MODE_MANUAL;
        fans[fan].manualPercent = pct;
        setFanPercent(fan, pct);
        Serial.printf("[SET] %s -> %u%% (MANUAL)\n", fanStr, pct);
      }
      saveEEPROM();
      sendStateToClients();
    }
    else if (strcmp(cmd, "game") == 0) {
      setGameMode(doc["on"] | true);
    }
    else if (strcmp(cmd, "profile") == 0) {
      uint8_t pid = doc["id"] | 1;
      applyProfile(pid);
      if (!gameMode) {
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
      Serial.printf("[CURVE] %s updated (%u points)\n",
                     fan == FAN_CPU ? "CPU" : "GPU", n);
      sendStateToClients();
    }
    else if (strcmp(cmd, "status") == 0) {
      sendStateToClients();
    }
  }
}

void sendStateToClients() {
  if (usbFallback) return;
  StaticJsonDocument<512> doc;
  doc["type"]     = "status";
  doc["cpu_pct"]  = fans[FAN_CPU].percent;
  doc["gpu_pct"]  = fans[FAN_GPU].percent;
  doc["cpu_temp"] = lastTemps[FAN_CPU];
  doc["gpu_temp"] = lastTemps[FAN_GPU];
  doc["cpu_mode"] = (uint8_t)fans[FAN_CPU].mode;
  doc["gpu_mode"] = (uint8_t)fans[FAN_GPU].mode;
  doc["profile"]  = activeProfile;
  doc["game"]     = gameMode;
  String out;
  serializeJson(doc, out);
  ws.broadcastTXT(out);
}

// ============================================================
//  HTTP (fallback)
// ============================================================
void handleRoot() {
  http.send(200, "text/plain",
    "ESP8266 Dual Fan Controller v2.0\n"
    "================================\n"
    "WiFi Hotspot: FanController\n"
    "IP: 192.168.4.1\n"
    "WS: port 81\n"
    "HTTP: /status /set?fan=cpu&percent=80&mode=manual\n");
}

void handleStatus() {
  String json;
  StaticJsonDocument<512> doc;
  doc["cpu_pct"]  = fans[FAN_CPU].percent;
  doc["gpu_pct"]  = fans[FAN_GPU].percent;
  doc["cpu_temp"] = lastTemps[FAN_CPU];
  doc["gpu_temp"] = lastTemps[FAN_GPU];
  doc["cpu_mode"] = (uint8_t)fans[FAN_CPU].mode;
  doc["gpu_mode"] = (uint8_t)fans[FAN_GPU].mode;
  doc["profile"]  = activeProfile;
  doc["game"]     = gameMode;
  doc["wifi"]     = (WiFi.status() == WL_CONNECTED);
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
    return;
  } else {
    fans[fan].mode = MODE_MANUAL;
    fans[fan].manualPercent = pct;
    setFanPercent(fan, pct);
  }
  saveEEPROM();
  sendStateToClients();
  http.send(200, "application/json", "{\"ok\":true}");
}

// ============================================================
//  USB SERIAL (fallback when WiFi down)
// ============================================================
void processSerial() {
  static String buffer;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (buffer.length() > 0) {
        // Process same as WebSocket
        StaticJsonDocument<512> doc;
        if (!deserializeJson(doc, buffer)) {
          const char* cmd = doc["cmd"] | "";
          if (strcmp(cmd, "temps") == 0) {
            lastTemps[FAN_CPU] = doc["cpu"] | lastTemps[FAN_CPU];
            lastTemps[FAN_GPU] = doc["gpu"] | lastTemps[FAN_GPU];
            lastPCContact = millis();
            if (!gameMode) {
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
//  PHYSICAL BUTTON (Game Mode toggle)
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
      // Short press: toggle game mode
      setGameMode(!gameMode);
    } else if (held >= LONGPRESS_MS) {
      // Long press: reset to Silent profile
      setGameMode(false);
      applyProfile(0);
      setFanPercent(FAN_CPU, evalCurve(FAN_CPU, lastTemps[FAN_CPU]));
      setFanPercent(FAN_GPU, evalCurve(FAN_GPU, lastTemps[FAN_GPU]));
      sendStateToClients();
    }
  }
  lastButtonState = now;
}

// ============================================================
//  AP WATCHDOG
// ============================================================
void checkWiFi() {
  static unsigned long lastCheck = 0;
  if (millis() - lastCheck < 5000) return;
  lastCheck = millis();

  // Lost contact for > 30s -> failsafe 70%
  if (!usbFallback && millis() - lastPCContact > 30000) {
    if (digitalRead(USB_DETECT_PIN) == LOW) {
      usbFallback = true;
      Serial.println(F("[AP] PC lost, switching to USB"));
      return;
    }
    if (fans[FAN_CPU].mode != MODE_FAILSAFE) {
      fans[FAN_CPU].mode = MODE_FAILSAFE;
      fans[FAN_GPU].mode = MODE_FAILSAFE;
      setFanPercent(FAN_CPU, 70);
      setFanPercent(FAN_GPU, 70);
      Serial.println(F("[FAILSAFE] No PC contact for 30s -> 70%"));
    }
  } else if (!usbFallback && fans[FAN_CPU].mode == MODE_FAILSAFE
             && millis() - lastPCContact < 5000) {
    fans[FAN_CPU].mode = MODE_AUTO;
    fans[FAN_GPU].mode = MODE_AUTO;
    Serial.println(F("[FAILSAFE] recovered"));
  }

  // Print client count periodically
  static uint8_t lastClientCount = 0;
  uint8_t clientCount = WiFi.softAPgetStationNum();
  if (clientCount != lastClientCount) {
    Serial.printf("[AP] Connected clients: %u\n", clientCount);
    lastClientCount = clientCount;
  }
}

// ============================================================
//  EEPROM PERSISTENCE
// ============================================================
struct EEPROMLayout {
  uint8_t  magic;
  uint8_t  activeProfile;
  uint8_t  gameMode;
  FanCurve curves[NUM_FANS];
};

void loadEEPROM() {
  EEPROMLayout data;
  EEPROM.get(0, data);
  if (data.magic != EEPROM_MAGIC) {
    Serial.println(F("[EEPROM] fresh init -> Balanced profile"));
    applyProfile(1);
    saveEEPROM();
    return;
  }
  activeProfile = data.activeProfile;
  gameMode      = data.gameMode;
  memcpy(curves, data.curves, sizeof(curves));
  Serial.printf("[EEPROM] loaded profile=%u game=%u\n", activeProfile, gameMode);
  applyProfile(activeProfile);
}

void saveEEPROM() {
  EEPROMLayout data;
  data.magic         = EEPROM_MAGIC;
  data.activeProfile = activeProfile;
  data.gameMode      = gameMode;
  memcpy(data.curves, curves, sizeof(curves));
  EEPROM.put(0, data);
  EEPROM.commit();
}
