# 🚀 روش سریع: بیلد خودکار در GitHub Actions (بدون نصب چیزی)

اگه نمی‌خواید Python و Inno Setup رو نصب کنید، **GitHub Actions** خودش نسخه نصبی رو می‌سازه.

---

## ✅ مراحل (۳ دقیقه)

### ۱. یه اکانت GitHub بسازید (اگه ندارید)

به [github.com/signup](https://github.com/signup) برید و یه اکانت رایگان بسازید.

### ۲. یه ریپو خالی بسازید

1. به [github.com/new](https://github.com/new) برید
2. **Repository name:** `FanController`
3. **Public** یا **Private** (هر دو کار می‌کنن)
4. ❌ **مهم:** هیچ تیکی نزنید (نه README، نه .gitignore، نه license)
5. **Create repository** بزنید

### ۳. فایل ZIP رو اکسترکت کنید

فایل `esp8266_fan_controller.zip` رو در یه پوشه اکسترکت کنید.

### ۴. اسکریپت push رو اجرا کنید

در پوشه `pc_app/`:

```
دابل‌کلیک روی: push_to_github.bat
```

اسکریپت از شما می‌خواد:
- نام کاربری و ایمیل GitHub (برای commit)
- URL ریپو (از مرحله ۲)

بعد از چند ثانیه، کد در GitHub آپلود می‌شه.

### ۵. بیلد خودکار رو تماشا کنید

1. به صفحه ریپو برید: `https://github.com/YOUR_USERNAME/FanController`
2. روی تب **Actions** کلیک کنید
3. یه workflow به نام **"Build Windows Installer"** در حال اجرا می‌بینید
4. حدود ۳-۵ دقیقه طول می‌کشه

### ۶. دانلود installer

وقتی workflow تموم شد:

1. روی اجرای موفق (علامت ✓ سبز) کلیک کنید
2. در پایین صفحه، بخش **Artifacts** رو پیدا کنید
3. روی **`FanController-Setup-v1.0.0`** کلیک کنید
4. فایل ZIP رو دانلود کنید
5. در داخلش `FanController-Setup-v1.0.0.exe` هست — **همون نسخه نصبی!**

---

## 🔄 بیلد نسخه جدید (Release)

اگه می‌خواید یه نسخه رسمی با tag بسازید:

```bash
git tag v1.0.0
git push origin v1.0.0
```

GitHub خودش یه **Release** می‌سازه و فایل `.exe` رو به‌عنوان دانلود attach می‌کنه. اینطوری کاربران می‌تونن به‌جای Actions artifacts، از تب Releases دانلود کنن.

---

## 🆘 عیب‌یابی

| مشکل | راه‌حل |
|------|------|
| `push failed - authentication` | یه **Personal Access Token** بسازید: GitHub Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token → تیک `repo` → از token به‌جای رمز عبور استفاده کنید |
| `Actions tab خالی` | فایل `.github/workflows/build.yml` رو چک کنید — باید داخل ریپو باشه |
| `Build failed` | روی اجرای fail شده کلیک کنید، log رو بخونید. معمولاً مشکل از نبودن یه فایل هست |
| `Artifacts not visible` | باید login باشید به GitHub. artifacts برای کاربران ناشناس قابل دیدن نیست |

---

## 💡 روش جایگزین: بیلد محلی (در ویندوز)

اگه نمی‌خواید از GitHub Actions استفاده کنید، می‌تونید خودتون بیلد کنید:

1. **Python 3.10+** — [python.org](https://python.org/downloads)
2. **Inno Setup 6** — [jrsoftware.org/isdl.php](https://jrsoftware.org/isdl.php)
3. در پوشه `pc_app`، فایل `build_installer.bat` رو دابل‌کلیک کنید

این روش طولانی‌تره ولی نتایج یکسانی می‌ده.

---

## 📂 فایل‌های مهم

| فایل | کاربرد |
|------|------|
| `.github/workflows/build.yml` | تنظیمات GitHub Actions workflow |
| `pc_app/push_to_github.bat` | اسکریپت یک‌کلیکی برای push به GitHub |
| `pc_app/build_installer.bat` | اسکریپت بیلد محلی (در ویندوز) |
| `pc_app/fan_controller.spec` | تنظیمات PyInstaller |
| `pc_app/installer.iss` | تنظیمات Inno Setup |

---

سوالی بود، بپرسید! 🎮
