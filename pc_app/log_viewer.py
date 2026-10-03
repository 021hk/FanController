"""
log_viewer.py - In-app log viewer dialog.

Shows the contents of %APPDATA%/FanController/app.log directly
in the app, with copy-to-clipboard and "open folder" buttons.
"""

from __future__ import annotations
import os
import sys
import logging
import platform
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QTextCursor, QGuiApplication
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QCheckBox, QApplication, QMessageBox
)

log = logging.getLogger(__name__)


def _log_file_path() -> Path:
    """Get the path to the app.log file."""
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / "FanController" / "app.log"
    return Path.home() / ".config" / "FanController" / "app.log"


def _stdout_log_path() -> Path:
    """Get the path to the stdout.log file."""
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / "FanController" / "stdout.log"
    return Path.home() / ".config" / "FanController" / "stdout.log"


def _collect_system_info() -> str:
    """Collect system info for debugging (helps diagnose issues)."""
    info = []
    info.append("=" * 60)
    info.append("SYSTEM INFO")
    info.append("=" * 60)
    info.append(f"OS: {platform.system()} {platform.release()} ({platform.machine()})")
    info.append(f"Python: {platform.python_version()}")
    info.append(f"Frozen: {getattr(sys, 'frozen', False)}")
    if getattr(sys, 'frozen', False):
        info.append(f"Executable: {sys.executable}")
        info.append(f"_MEIPASS: {getattr(sys, '_MEIPASS', 'N/A')}")
    info.append(f"Log file: {_log_file_path()}")
    info.append(f"Log exists: {_log_file_path().exists()}")
    info.append("")
    return "\n".join(info)


class LogViewerDialog(QDialog):
    """Dialog that shows app.log + system info with copy/share buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📋 لاگ برنامه - عیب‌یابی")
        self.setMinimumSize(700, 500)
        self.setStyleSheet("""
            QDialog {
                background-color: #121212;
                color: #ffffff;
                font-family: Tahoma, 'Segoe UI', Arial, sans-serif;
            }
            QLabel#Title {
                color: #00d2ff;
                font-size: 16px;
                font-weight: bold;
            }
            QLabel#Subtitle {
                color: #aaaaaa;
                font-size: 11px;
            }
            QTextEdit {
                background-color: #1a1a1a;
                color: #e0e0e0;
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 8px;
                padding: 8px;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 11px;
            }
            QPushButton {
                background-color: rgba(255,255,255,0.06);
                color: #ffffff;
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(255,255,255,0.12);
            }
            QPushButton#Primary {
                background-color: #00d2ff;
                color: #121212;
                border: none;
                font-weight: bold;
            }
            QPushButton#Primary:hover {
                background-color: #00b8d9;
            }
            QCheckBox {
                color: #aaaaaa;
                font-size: 11px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
        """)

        self._build_ui()
        self._refresh_log()

        # Auto-refresh every 3 seconds while open
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_log)
        self._timer.start(3000)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header
        title = QLabel("📋 لاگ برنامه")
        title.setObjectName("Title")
        layout.addWidget(title)

        subtitle = QLabel(
            "این فایل شامل تمام فعالیت‌های برنامه است. "
            "اگه مشکلی دارید، محتوای زیر رو کپی کنید و بفرستید."
        )
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Path label
        self.lbl_path = QLabel(f"📁 مسیر فایل: {_log_file_path()}")
        self.lbl_path.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(self.lbl_path)

        # Log text area
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFont(QFont("Consolas", 10))
        layout.addWidget(self.txt_log, stretch=1)

        # Auto-refresh checkbox
        self.chk_refresh = QCheckBox("🔄 تازه‌سازی خودکار (هر ۳ ثانیه)")
        self.chk_refresh.setChecked(True)
        self.chk_refresh.stateChanged.connect(self._on_refresh_toggled)
        layout.addWidget(self.chk_refresh)

        # Buttons
        btn_row = QHBoxLayout()

        btn_open_folder = QPushButton("📁 باز کردن پوشه")
        btn_open_folder.clicked.connect(self._open_folder)
        btn_row.addWidget(btn_open_folder)

        btn_refresh = QPushButton("🔄 تازه‌سازی")
        btn_refresh.clicked.connect(self._refresh_log)
        btn_row.addWidget(btn_refresh)

        btn_row.addStretch()

        btn_copy = QPushButton("📋 کپی برای ارسال")
        btn_copy.setObjectName("Primary")
        btn_copy.clicked.connect(self._copy_to_clipboard)
        btn_row.addWidget(btn_copy)

        btn_close = QPushButton("✕ بستن")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

    def _refresh_log(self):
        """Reload log file content into text area."""
        try:
            # System info first
            content = _collect_system_info()

            # Add a TEMP DIAGNOSTIC section - test the temperature reading
            content += "\n" + "=" * 60 + "\n"
            content += "TEMPERATURE DIAGNOSTIC (live test)\n"
            content += "=" * 60 + "\n"
            try:
                from hardware_monitor import HardwareMonitor, _find_lhm_exe, _get_search_paths
                content += f"LHM.exe found: {_find_lhm_exe() or 'NOT FOUND'}\n"
                content += f"Search paths checked: {_get_search_paths()}\n"

                # Run a real temp read
                import time
                start = time.time()
                hm = HardwareMonitor()
                t = hm.read()
                elapsed = time.time() - start
                content += f"Read took: {elapsed:.2f}s\n"
                content += f"nvidia-smi detected: {hm._has_nvidia_smi}\n"
                content += f"OHM/LHM WMI detected: {hm._has_ohm_wmi}\n"
                content += f"Admin: {hm._is_admin()}\n"
                content += f"\nRESULT:\n"
                content += f"  CPU: {t.cpu:.1f}°C ({t.cpu_name or 'unknown'})\n"
                content += f"  CPU sensor: {t.cpu_sensor_path or 'none'}\n"
                content += f"  GPU: {t.gpu:.1f}°C ({t.gpu_name or 'unknown'})\n"
                content += f"  GPU sensor: {t.gpu_sensor_path or 'none'}\n"
                hm.close()
            except Exception as e:
                content += f"Diagnostic failed: {e}\n"

            # Main log file
            log_path = _log_file_path()
            if log_path.exists():
                try:
                    log_text = log_path.read_text(encoding="utf-8", errors="replace")
                    # Take last 8000 chars to avoid huge text
                    if len(log_text) > 8000:
                        log_text = "...[truncated, showing last 8000 chars]...\n" + log_text[-8000:]
                    content += "\n" + "=" * 60 + "\n"
                    content += "APP LOG (most recent at bottom)\n"
                    content += "=" * 60 + "\n"
                    content += log_text
                except Exception as e:
                    content += f"\nError reading app.log: {e}\n"
            else:
                content += "\napp.log file does not exist yet.\n"

            # stdout.log if exists (catches CLR/keyboard output)
            stdout_path = _stdout_log_path()
            if stdout_path.exists():
                try:
                    stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace")
                    if len(stdout_text) > 3000:
                        stdout_text = "...[truncated]...\n" + stdout_text[-3000:]
                    content += "\n" + "=" * 60 + "\n"
                    content += "STDOUT LOG\n"
                    content += "=" * 60 + "\n"
                    content += stdout_text
                except Exception as e:
                    content += f"\nError reading stdout.log: {e}\n"

            self.txt_log.setPlainText(content)
            # Scroll to bottom (most recent)
            self.txt_log.moveCursor(QTextCursor.MoveOperation.End)
        except Exception as e:
            self.txt_log.setPlainText(f"Error loading log: {e}")

    def _on_refresh_toggled(self, state):
        if self.chk_refresh.isChecked():
            self._timer.start(3000)
        else:
            self._timer.stop()

    def _copy_to_clipboard(self):
        """Copy log content to clipboard."""
        text = self.txt_log.toPlainText()
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(text)
        # Show confirmation
        btn = self.sender()
        original_text = btn.text()
        btn.setText("✓ کپی شد!")
        QTimer.singleShot(2000, lambda: btn.setText(original_text))

    def _open_folder(self):
        """Open the log folder in Windows Explorer."""
        log_path = _log_file_path()
        folder = log_path.parent
        try:
            if sys.platform == "win32":
                # Open Explorer with file selected
                import subprocess
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                subprocess.Popen(
                    ["explorer", "/select,", str(log_path)],
                    startupinfo=startupinfo,
                    creationflags=0x08000000,
                )
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as e:
            QMessageBox.information(self, "مسیر", f"مسیر فایل:\n{log_path}\n\nخطا: {e}")

    def closeEvent(self, e):
        self._timer.stop()
        super().closeEvent(e)
