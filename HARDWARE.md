# 🔌 شماتیک سخت‌افزاری کامل - ESP8266 Fan Controller

این فایل شامل تمام اطلاعات سخت‌افزاری برای ساخت کنترلر فن با ESP8266 هست.

---

## 📦 قطعات مورد نیاز

### قطعات اصلی

| قطعه | تعداد | مدل پیشنهادی | قیمت تقریبی |
|------|------|-------------|------------|
| میکروکنترلر | ۱ | NodeMCU v1.0 (ESP-12E) یا Wemos D1 Mini | ۵۰-۱۰۰ هزار تومان |
| فن ۴-پین PWM | ۲ | Arctic P12 / Noctua NF-A12x25 | هر کدام ۱۰۰-۳۰۰ هزار |
| مقاومت ۱۰kΩ | ۲ | ۱/۴ وات، کربنی | ۵۰۰ تومان |
| دکمه فشاری | ۱ | ۶×۶mm، ۴ پایه | ۱۰۰۰ تومان |
| سیم DuPont | ۲۰ | ماده-ماده و ماده-والد | ۵۰۰۰ تومان |
| کابل USB Micro | ۱ | برای برنامه‌ریزی و تغذیه | ۵۰۰۰ تومان |

### قطعات اختیاری (برای حرفه‌ای‌تر)

| قطعه | تعداد | کاربرد |
|------|------|------|
| Fan Hub ۴-پین | ۱ | اگه چند فن موازی می‌خواید |
| خازن ۱۰۰nF | ۲ | نویزگیری PWM |
| LED ۳mm | ۱ | نشانگر Game Mode (اختیاری) |
| مقاومت ۲۲۰Ω | ۱ | برای LED |
| هدر ۴-پین | ۲ | برای اتصال فن‌ها به راحتی |
| کابل آداپتور USB-to-TTL | ۱ | اگه NodeMCU ندارید (برای پروگرم) |

---

## 🎯 نمودار اتصالات (Wiring Diagram)

### نمای کلی

```
                    ┌──────────────────────────────────────┐
                    │           کامپیوتر (PC)               │
                    │                                      │
                    │  ┌─────────────┐  ┌──────────────┐  │
                    │  │   CPU Cooler │  │  GPU Cooler  │  │
                    │  │   (4-pin fan)│  │  (4-pin fan)  │  │
                    │  └──────┬──────┘  └──────┬───────┘  │
                    │         │                │           │
                    │         │ 4-pin          │ 4-pin     │
                    │         ▼                ▼           │
                    │  ┌─────────────────────────────────┐ │
                    │  │     Fan Hub / Splitter          │ │
                    │  │  (یا اتصال مستقیم به فن‌ها)      │ │
                    │  └─────────────────────────────────┘ │
                    │         │                │           │
                    │         │ 12V (Yellow)   │           │
                    │         │ GND (Black)    │           │
                    │         │ PWM (Blue)     │           │
                    │         │ Tach (Green)   │           │
                    │         │                │           │
                    │  ┌──────┴────────────────┴──────┐    │
                    │  │   PSU (Power Supply Unit)    │    │
                    │  │   12V from Molex/SATA        │    │
                    │  └──────────────────────────────┘    │
                    │                                      │
                    │  ┌──────────────────────────────────┐ │
                    │  │   ESP8266 (NodeMCU)              │ │
                    │  │   ┌────────────────┐             │ │
                    │  │   │     USB ────┐  │             │ │
                    │  │   │              ▼ │             │ │
                    │  │   │  [NodeMCU]    PC USB port     │ │
                    │  │   │              (برای تغذیه +   │ │
                    │  │   │              fallback سریال)   │ │
                    │  │   └────────────────┘             │ │
                    │  └──────────────────────────────────┘   │
                    └──────────────────────────────────────┘
```

### اتصالات ESP8266 (NodeMCU pinout)

```
                    NodeMCU v1.0 (ESP-12E)
                    ┌────────────────────┐
              3V3 ──┤                    ├── 5V (Vin)  ←── 5V from USB or PSU
              GND ──┤                    ├── GND       ←── Common GND (CRITICAL!)
              EN  ──┤                    ├── D1 (GPIO5)──→ CPU fan PWM
         GPIO16 ──┤ D0              D2 ├── (GPIO4)  ──→ GPU fan PWM
         GPIO5  ──┤ D1              D3 ├── (GPIO0)
         GPIO4  ──┤ D2              D4 ├── (GPIO2)  ←── Onboard LED (Game Mode)
         GPIO0  ──┤ D3              3V3 ├──
         GPIO2  ──┤ D4              GND ├──
         GPIO14 ──┤ D5              D5 ├── (GPIO14) ──← Game Mode button
         GPIO12 ──┤ D6              D6 ├── (GPIO12) ──← USB detect (optional)
         GPIO13 ──┤ D7              D7 ├── (GPIO13)
         GPIO15 ──┤ D8              D8 ├── (GPIO15)
                    │                    │
                    │  [USB Micro]       │
                    └─────────┬──────────┘
                              │
                              ▼
                    Computer USB port
                    (تغذیه + fallback سریال)
```

### اتصالات فن (Fan Pinout)

فن استاندارد PC ۴-پین:

```
                    فن ۴-پین (نمای بالا)
                    ┌─────────────────────┐
                    │  1    2    3    4   │
                    │  │    │    │    │   │
                    │ GND  12V  Tach PWM  │
                    │ │    │    │    │   │
                    └─┴────┴────┴────┴───┘
                       │    │         │
                       │    │         │
                       │    │         └── ESP8266 D1 (CPU) or D2 (GPU)
                       │    │              با مقاومت ۱۰kΩ pull-down
                       │    │
                       │    └── PSU 12V (Yellow wire, Molex pin 1 or SATA pin 2)
                       │
                       └── Common GND (PSU GND, ESP GND)
```

---

## 🔧 شماتیک مدار (Circuit Schematic)

### بخش ۱: اتصال فن به ESP8266

```
PSU 12V ────────┬──────────────────────┐
  (Yellow)      │                      │
                │                      │
                │   ┌──────────────┐   │
                │   │   CPU Fan    │   │
                │   │   (4-pin)    │   │
                │   │              │   │
                │   │  12V (red) ──┤   │
                │   │  GND (blk) ──┤   │
                │   │  Tach (grn) ─┤   │  ← (اختیاری، برای خواندن RPM)
                │   │  PWM (blu) ──┤   │
                │   └──────┬───────┘   │
                │          │           │
                │          │ 10kΩ      │
                │          │ pull-down │
                │          │           │
                │          └── ESP8266 D1 (GPIO5)
                │
                │
                │   ┌──────────────┐
                │   │   GPU Fan    │
                │   │   (4-pin)    │
                │   │              │
                │   │  12V (red) ──┤
                │   │  GND (blk) ──┤
                │   │  Tach (grn) ─┤   ← (اختیاری)
                │   │  PWM (blu) ──┤
                │   └──────┬───────┘
                │          │
                │          │ 10kΩ pull-down
                │          │
                │          └── ESP8266 D2 (GPIO4)

PSU GND ────────┴──────────┬───────────────
                           │
                           │   ESP8266 GND
                           │
                           └── Common Ground (ضروری!)
```

### بخش ۲: دکمه Game Mode فیزیکی

```
                    ESP8266
                      D5 (GPIO14)
                         │
                         │
                         ├── 10kΩ pull-up (داخلی NodeMCU فعال است)
                         │
                       ┌─┴─┐
                       │   │  دکمه فشاری
                       │   │  (Push button, 6×6mm)
                       └─┬─┘
                         │
                         │
                        GND

      رفتار دکمه:
      - کوتاه فشار (< 1.5 ثانیه): Game Mode را تغییر بده
      - بلند فشار (> 1.5 ثانیه): به پروفایل Silent برگرد
```

### بخش ۳: LED نشانگر Game Mode (اختیاری)

```
                    ESP8266
                      D4 (GPIO2)
                         │
                         │
                       ┌─┴─┐
                       │   │  LED 3mm
                       │   │
                       └─┬─┘
                         │
                         │ 220Ω
                         │
                        GND

      رفتار:
      - Game Mode OFF: LED خاموش
      - Game Mode ON:  LED روشن
      - Boot در حال:    LED چشمک می‌زنه
```

### بخش ۴: تشخیص USB (اختیاری)

```
                    USB 5V
                       │
                       │
                     ┌─┴─┐
                     │   │  مقاومت ۱kΩ
                     │   │
                     └─┬─┘
                       │
                       ├────── ESP8266 D6 (GPIO12)
                       │
                     ┌─┴─┐
                     │   │  مقاومت ۲kΩ
                     │   │
                     └─┬─┘
                       │
                      GND

      (تقسیم ولتاژ: 5V → 3.3V برای GPIO امن)
      وقتی USB وصل باشه، D6 = HIGH
      وقتی USB قطع باشه، D6 = LOW (به GND pull-down می‌شه)
```

---

## ⚠️ نکات حیاتی سخت‌افزاری

### ۱. GND مشترک ضروری است!

```
PSU GND ────┬──── ESP8266 GND
            │
            └──── Fan GND

اگر GND مشترک نباشه:
- PWM نویزی می‌شه
- فن‌ها ممکنه کار نکنن
- ESP ممکنه ریست بشه
```

### ۲. ولتاژ ۱۲ ولت از PSU

```
PSU Molex Connector:
┌─────────────────┐
│  │   │   │   │  │
│  │   │   │   │  │
│  Y   B   B   R  │
│  │   │   │   │  │
│ 12V GND GND 5V  │
└─────────────────┘

Yellow = 12V (برای فن‌ها)
Red    = 5V  (برای ESP از طریق رگولاتور onboard)
Black  = GND  (مشترک)
```

### ۳. مقاومت Pull-Down روی PWM

هر پین PWM فن باید یه مقاومت ۱۰kΩ به GND داشته باشه:

```
ESP8266 D1 ──┬── Fan PWM
             │
             │
             ┌─┐
             │ │ 10kΩ
             │ │
             └─┘
              │
             GND
```

**علت:** وقتی ESP ریست می‌شه یا در حال boot هست، پین‌ها در حالت high-impedance هستن. بدون pull-down، فن ممکنه با سرعت کامل روشن بشه.

---

## 🛠️ مراحل مونتاژ

### مرحله ۱: آماده‌سازی NodeMCU

۱. NodeMCU رو با کابل USB به کامپیوتر وصل کنید
۲. در Device Manager ویندوز، مطمئن بشید پورت COM شناسایی شده (مثلاً COM3)
۳. اگر شناسایی نشده، درایور CH340 رو از [سایت سازنده](https://sparks.gogo.co.nz/ch340.html) نصب کنید

### مرحله ۲: برنامه‌ریزی ESP8266

۱. Arduino IDE رو نصب کنید
۲. در `File → Preferences` این URL رو اضافه کنید:
   ```
   https://arduino.esp8266.com/stable/package_esp8266com_index.json
   ```
۳. در `Tools → Board → Boards Manager` پکیج `esp8266` رو نصب کنید
۴. کتابخانه‌های زیر رو از `Sketch → Include Library → Manage Libraries` نصب کنید:
   - **WebSockets** by Markus Sattler (Links2004)
   - **ArduinoJson** by Benoit Blanchon (نسخه ۶.x)
۵. فایل `esp8266_firmware.ino` رو باز کنید
۶. تنظیمات WiFi رو در ابتدای فایل تغییر بدید (اگه می‌خواید):
   ```cpp
   const char* AP_SSID      = "FanController";
   const char* AP_PASSWORD   = "12345678";
   ```
۷. در `Tools`:
   - Board: **NodeMCU 1.0 (ESP-12E Module)**
   - Port: **COM3** (یا هر پورت که NodeMCU وصله)
۸. دکمه **Upload** رو بزنید

### مرحله ۳: تست ESP8266

۱. Arduino IDE → Tools → Serial Monitor (یا `Ctrl+Shift+M`)
۲. Baud rate رو روی `115200` تنظیم کنید
۳. دکمه RST روی NodeMCU رو بزنید
۴. باید این خروجی رو ببینید:

```
[BOOT] ESP8266 Fan Controller v2.0
[AP] Starting hotspot 'FanController' on channel 1...
[AP] Hotspot started! IP=192.168.4.1
[AP] SSID='FanController'  Pass='12345678'  Clients(max)=4
[mDNS] fanctrl.local
[BOOT] ready
==========================================
WiFi Hotspot:
  SSID: FanController
  Pass: 12345678
  IP:   192.168.4.1
  WS Port: 81  HTTP Port: 80
==========================================
Connect PC to WiFi 'FanController'
Then run FanController.exe on PC
==========================================
```

### مرحله ۴: اتصال فن‌ها

۱. **PSU رو از برق بکشید** (احتیاط!)
۲. صبر کنید تا خازن‌های PSU خالی بشن (۳۰ ثانیه)
۳. سیم ۱۲ ولت زرد رو از یه Molex یا SATA power بگیرید
۴. سیم GND مشکی رو هم از همون Molex بگیرید
۵. اتصالات رو طبق شماتیک بالا انجام بدید:
   - PSU 12V → Fan 12V (هر دو فن)
   - PSU GND → Fan GND → ESP GND
   - ESP D1 → Fan CPU PWM (با مقاومت ۱۰kΩ pull-down)
   - ESP D2 → Fan GPU PWM (با مقاومت ۱۰kΩ pull-down)
۶. دکمه رو بین D5 و GND وصل کنید

### مرحله ۵: تست نهایی

۱. PSU رو به برق وصل کنید
۲. کامپیوتر رو روشن کنید
۳. به وای‌فای `FanController` وصل بشید (رمز: `12345678`)
۴. اپ FanController رو اجرا کنید
۵. باید دما و سرعت فن‌ها رو ببینید
۶. دکمه Game Mode فیزیکی رو تست کنید — باید LED روشن بشه و فن‌ها ۱۰۰٪ بشن

---

## 🔍 عیب‌یابی سخت‌افزاری

| مشکل | علت احتمالی | راه‌حل |
|------|------------|------|
| فن‌ها نمی‌چرخن | GND مشترک نیست | GND مشترک بین ESP و PSU |
| فن‌ها ۱۰۰٪ می‌چرخن | مقاومت pull-down نصب نشده | ۱۰kΩ بین PWM و GND اضافه کنید |
| فن‌ها نویزی هستن | کابل PWM طولانی | کابل کمتر از ۳۰cm |
| ESP ریست می‌شه | منبع تغذیه ضعیف | از شارژر تلفن ۲A استفاده کنید |
| دکمه کار نمی‌کنه | Polarite دکمه اشتباه | دکمه ۴ پایه رو ۹۰ درجه بچرخونید |
| LED روشن نمی‌شه | LED معکوس وصل شده | پایه‌های LED رو عوض کنید |
| PWM کار نمی‌کنه | پین اشتباه | D1 و D2 فقط (نه D0 یا D8) |

---

## 📐 اندازه‌ها و ابعاد

| قطعه | ابعاد |
|------|------|
| NodeMCU v1.0 | ۵۸×۳۱ mm |
| Wemos D1 Mini | ۳۴×۲۵ mm |
| فن ۱۲۰mm | ۱۲۰×۱۲۰×۲۵ mm |
| فن ۹۲mm | ۹۲×۹۲×۲۵ mm |
| دکمه ۶×۶ | ۶×۶ mm |

---

## 🔥 جایگزین‌ها

### اگه NodeMCU ندارید:
- **Wemos D1 Mini** (کوچک‌تر، ارزون‌تر، همون پین‌ها)
- **ESP-12F با آداپتور USB** (نیاز به پروگرم‌کننده USB-TTL)

### اگه فن ۳-پین دارید:
- نمی‌تونید PWM کنید
- باید ولتاژ ۱۲ ولت رو با MOSFET (مثل IRLZ44N) PWM کنید
- فرکانس PWM باید ۱-۵ کیلوهرتز باشه (نه ۲۵kHz)
- کد فریمور رو تغییر بدید

### اگه چند فن موازی می‌خواید:
- از **Fan Hub** استفاده کنید
- Fan Hub یک ورودی PWM می‌گیره و به چند فن توزیع می‌کنه
- هر Fan Hub می‌تونه ۴-۸ فن رو هندل کنه

---

## 📚 منابع

- [ESP8266 Arduino Core](https://github.com/esp8266/Arduino)
- [WebSockets Library](https://github.com/Links2004/arduinoWebSockets)
- [ArduinoJson](https://arduinojson.org/)
- [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor)
- [Intel PWM Fan Spec](https://www.intel.com/content/www/us/en/products/docs/boards-and-kits/desktop-platforms/four-wire-pwm-spec.html)

---

ساخته‌شده با ❤️. اگه سوالی بود، بپرسید!
