# ESP8266 Dual PWM Fan Controller

پروژه کامل برای کنترل سرعت دو فن ۴-پین PWM کامپیوتر با ESP8266 از طریق دمای CPU و GPU.

## 📂 ساختار پروژه

```
esp8266_fan_controller/
├── esp8266_firmware/
│   └── esp8266_firmware.ino        ← آپلود روی NodeMCU با Arduino IDE
├── pc_app/
│   ├── main.py                     ← نقطه شروع اپ ویندوز
│   ├── config.py                   ← ذخیره تنظیمات
│   ├── hardware_monitor.py         ← خواندن دما با LibreHardwareMonitor
│   ├── esp_client.py               ← ارتباط با ESP (WebSocket/HTTP/USB)
│   ├── profiles.py                 ← مدیریت پروفایل‌های چندگانه
│   ├── tray.py                     ← آیکون System Tray
│   ├── gui.py                      ← پنجره اصلی با نمودار دما
│   ├── hotkey.py                   ← Ctrl+Shift+G
│   ├── make_shortcut.py            ← ساخت شورتکات دسکتاپ
│   ├── test_esp.py                 ← تست اتصال
│   └── requirements.txt
└── README.md
```

## 🚀 نصب سریع

### ۱. فلش ESP8266
1. Arduino IDE رو نصب کنید
2. در `File → Preferences → Additional Board Manager URLs` اضافه کنید:
   `https://arduino.esp8266.com/stable/package_esp8266com_index.json`
3. کتابخانه‌های `WebSockets` (by Links2004) و `ArduinoJson` v6 رو نصب کنید
4. فایل `esp8266_firmware.ino` رو باز کنید
5. SSID و رمز وای‌فای رو در ابتدای فایل وارد کنید
6. روی NodeMCU آپلود کنید

### ۲. نصب اپ ویندوز
```powershell
cd pc_app
pip install -r requirements.txt
# فایل‌های LibreHardwareMonitorLib.dll رو از GitHub‌اش دانلود و در همین پوشه بذارید
python main.py    # به‌صورت ادمین اجرا کنید
```

### ۳. ساخت شورتکات دسکتاپ
```powershell
python make_shortcut.py --ip 192.168.1.200
```

### ۴. تست
```powershell
python test_esp.py --ip 192.168.1.200
```

## 🎮 ویژگی‌ها

- ✅ خواندن دمای CPU/GPU از ویندوز با LibreHardwareMonitor
- ✅ WebSocket real-time + HTTP + USB fallback
- ✅ ۲ فن مستقل ۴-پین PWM با فرکانس ۲۵ کیلوهرتز
- ✅ ۴ پروفایل (Silent / Balanced / Performance / Game)
- ✅ منحنی دما-به-سرعت قابل تنظیم (۷ نقطه)
- ✅ قانون خودکار GPU > 70°C → 100%
- ✅ دکمه فیزیکی Game Mode روی کیس (با تشخیص short/long press)
- ✅ Hotkey Ctrl+Shift+G
- ✅ شورتکات دسکتاپ
- ✅ System Tray
- ✅ نمودار زنده دما (CPU/GPU)
- ✅ حالت Failsafe اگه ارتباط قطع بشه (۷۰٪)

## ⚠️ نکته مهم درباره اتصال سخت‌افزاری

ESP8266 رو **نمی‌شه مستقیم به هدر فن مادربرد وصل کرد**. به جاش:
- فن‌ها رو به یک **Fan Hub** وصل کنید که ۱۲V از PSU می‌گیره
- پین PWM فن رو مستقیم به خروجی ESP8266 وصل کنید
- GND مشترک بین ESP، PSU و مادربرد ضروریه
- مقاومت ۱۰kΩ pull-down روی هر پین PWM اضافه کنید

## 🔧 شماتیک سخت‌افزار

```
PSU 12V ──┬──[Fan1]──┐
          │          │
          └──[Fan2]──┤
                     │
ESP8266:              │
  D1 (GPIO5) ──[10k]──┤  (CPU fan PWM)
  D2 (GPIO4) ──[10k]──┘  (GPU fan PWM)
  D5 (GPIO14) ──── Button ─── GND  (Game Mode)
  D4 (GPIO2) ──── LED (active low, Game Mode indicator)
  Vin ─── 5V (USB or PSU)
  GND ─── Common with PSU GND (CRITICAL)
```

## 🛡️ ایمنی

- حداقل سرعت فن ۱۰٪ (هرگز ۰٪ نخواهد بود)
- در قطع WiFi، فن‌ها خودکار ۷۰٪ می‌شن (Failsafe)
- دکمه فیزیکی حتی بدون WiFi کار می‌کنه

ساخته‌شده با ❤️
