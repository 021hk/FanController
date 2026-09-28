# ساخت نسخه نصبی ویندوز (.exe)

این راهنما توضیح میده چطور از کد پایتون، یه **installer ویندوزی** با پسوند `.exe` بسازید که قابل نصب روی هر کامپیوتر ویندوز ۱۰/۱۱ x64 باشه.

---

## 📋 پیش‌نیازها (روی کامپیوتر توسعه)

۱. **Python 3.10+** — [python.org/downloads](https://python.org/downloads)
   (تیک "Add Python to PATH" رو حتماً بزنید)

۲. **Inno Setup 6** (رایگان) — [jrsoftware.org/isdl.php](https://jrsoftware.org/isdl.php)

۳. **LibreHardwareMonitor DLLs** — از [GitHub release](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases) آخرین نسخه رو دانلود کنید و این فایل‌ها رو در پوشه `pc_app/` کپی کنید:
   - `LibreHardwareMonitorLib.dll`
   - `LibreHardwareMonitorLib.dll.config`
   - `HidSharp.dll`
   - پوشه `LibreHardwareMonitorLib.resources/` (اختیاری)

۴. (اختیاری) آیکون آماده در پوشه هست (`icon.ico`) ولی اگه خواستید بسازید:
   ```powershell
   python icon_generator.py
   ```

---

## 🚀 ساخت Installer (یک کلیک)

کافیست فایل `build_installer.bat` رو دابل‌کلیک کنید. اسکریپت خودش این کارها رو می‌کنه:

1. ✅ Python و pip رو چک می‌کنه
2. ✅ وابستگی‌های پایتون + PyInstaller + pywin32 رو نصب می‌کنه
3. ✅ `LibreHardwareMonitorLib.dll` رو چک می‌کنه
4. ✅ بیلدهای قبلی رو پاک می‌کنه
5. ✅ با PyInstaller، فایل `.exe` می‌سازه
6. ✅ با Inno Setup، installer نهایی رو می‌سازه

**خروجی نهایی:**
```
dist/FanController-Setup-v1.0.0.exe   ← Installer قابل نصب
dist/FanController/                    ← نسخه portable (بدون نصب)
```

---

## 📦 محتویات Installer

وقتی installer رو اجرا می‌کنید:

- در `C:\Program Files\ESP8266 Fan Controller\` نصب می‌شه
- در Start Menu این شورتکات‌ها ساخته می‌شه:
  - **ESP8266 Fan Controller** (اپ اصلی)
  - **Game Mode ON** (شورتکات سریع)
  - **Game Mode OFF** (شورتکات سریع)
  - **Uninstall**
- (اختیاری) شورتکات روی Desktop
- (اختیاری) اجرای خودکار در استارتاپ ویندوز

---

## 🔧 ساخت دستی (اگه build_installer.bat کار نکرد)

### مرحله ۱: نصب وابستگی‌ها

```powershell
cd pc_app
pip install -r requirements.txt
pip install pyinstaller pywin32
```

### مرحله ۲: بیلد exe با PyInstaller

```powershell
python -m PyInstaller fan_controller.spec --noconfirm --clean
```

خروجی: `dist/FanController/FanController.exe`

### مرحله ۳: کپی DLLهای LibreHardwareMonitor

```powershell
copy LibreHardwareMonitorLib.dll dist\FanController\
copy LibreHardwareMonitorLib.dll.config dist\FanController\
copy HidSharp.dll dist\FanController\
```

### مرحله ۴: ساخت installer با Inno Setup

یا با GUI:
- Inno Setup Compiler رو باز کنید
- فایل `installer.iss` رو باز کنید
- `Build → Compile` (یا Ctrl+F7)

یا با خط فرمان:
```powershell
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

خروجی: `dist/FanController-Setup-v1.0.0.exe`

---

## 🐛 عیب‌یابی

| مشکل | راه‌حل |
|------|------|
| "PyInstaller not found" | `pip install pyinstaller` |
| "ISCC.exe not found" | Inno Setup 6 رو از سایت رسمی نصب کنید |
| Installer بدون LHM | `LibreHardwareMonitorLib.dll` رو دانلود و در پوشه بذارید |
| آنتی‌ویروس warning | PyInstaller گاهی false-positive میده — فایل رو whitelist کنید |
| exe اجرا نمی‌شه | روی فایل installer راست‌کلیک → Run as administrator |
| Python در PATH نیست | Python رو reinstall و تیک "Add to PATH" رو بزنید |
| PyQt6 باگ میده | `pip install --upgrade PyQt6 PyQt6-Qt6 PyQt6-sip` |

---

## 📤 توزیع

فایل `FanController-Setup-v1.0.0.exe` رو می‌تونید:
- روی فلش مموری بذارید و روی هر کامپیوتر اجرا کنید
- در GitHub Releases آپلود کنید
- به دوستان بدید

حجم نهایی حدود ۸۰-۱۲۰ مگابایت (شامل PyQt6 و وابستگی‌ها).

---

## 🔐 کد‌گزاری دیجیتال (اختیاری)

اگه می‌خواید هشدار "Unknown Publisher" ویندوز برطرف شه:

1. یه گواهی کد‌گزاری بخرید (از DigiCert, Sectigo, و...)
2. با `signtool.exe` گواهی رو به exe بزنید:
   ```powershell
   signtool sign /a /tr http://timestamp.digicert.com /td sha256 /fd sha256 dist\FanController-Setup-v1.0.0.exe
   ```

یا از sigstore استفاده کنید (رایگان، open source):
```powershell
sigstore sign dist\FanController-Setup-v1.0.0.exe
```

برای پروژه‌های شخصی، نیازی به این کار نیست — فقط روی warning کلیک "More info → Run anyway" بزنید.
