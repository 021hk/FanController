"""
gui.py - Main GUI window built with PyQt6 (Dark Dashboard Style).

Inspired by the reference HTML dashboard:
- Dark theme with cyan (#00d2ff) primary color
- Animated SVG fan blades that spin based on real fan speed %
- Slider + numeric input for percentage control
- Live RPM/PWM display
- Mini mode (floating compact widget) toggleable via minimize button
- 4 fan cards (CPU, GPU, Case1, Case2) in a responsive grid
- RTL layout with Persian font support
"""

from __future__ import annotations
import logging
import math
import collections
import time
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui import (QPainter, QColor, QPen, QBrush, QFont, QPainterPath,
                          QLinearGradient, QRadialGradient, QFontDatabase)
from PyQt6.QtWidgets import (
    QWidget, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QProgressBar, QSlider, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QGroupBox, QFrame, QSizePolicy, QApplication, QGridLayout, QDialog
)

from config import Config, PROFILE_NAMES
from esp_client import ESPClient, ESPStatus, ConnState
from profiles import PROFILES

log = logging.getLogger(__name__)

# ============================================================
# THEME - matches the reference HTML dashboard
# ============================================================
PRIMARY_COLOR = "#00d2ff"     # cyan
SECONDARY_COLOR = "#3a7bd5"   # blue
BG_COLOR = "#121212"
CARD_BG = "#1e1e1e"
CARD_BG_HOVER = "#252525"
TEXT_COLOR = "#ffffff"
TEXT_MUTED = "#aaaaaa"
INPUT_BG = "rgba(255,255,255,0.08)"
DANGER_COLOR = "#ff5252"
SUCCESS_COLOR = "#4caf50"
WARN_COLOR = "#ffc107"

# Persian font (IRANSans if available, fallback to Tahoma)
try:
    PERSIAN_FONT = "IRANSans"
    if PERSIAN_FONT not in QFontDatabase.families():
        PERSIAN_FONT = "Tahoma"
except Exception:
    PERSIAN_FONT = "Tahoma"

DARK_QSS = f"""
QWidget {{
    background-color: {BG_COLOR};
    color: {TEXT_COLOR};
    font-family: {PERSIAN_FONT}, 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}}

QMainWindow, QDialog {{
    background-color: {BG_COLOR};
}}

/* Card style */
QFrame#FanCard {{
    background-color: {CARD_BG};
    border-radius: 20px;
}}
QFrame#FanCard:hover {{
    background-color: {CARD_BG_HOVER};
}}

QFrame#Header {{
    background-color: transparent;
}}

QLabel#HeaderTitle {{
    color: {PRIMARY_COLOR};
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#HeaderSubtitle {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}

QLabel#FanLabel {{
    color: {TEXT_COLOR};
    font-size: 15px;
    font-weight: 600;
    background: transparent;
    border: none;
    border-bottom: 1px solid rgba(255,255,255,0.15);
    padding: 6px 0;
}}

QLabel#StatLabel {{
    color: {TEXT_MUTED};
    font-size: 11px;
    background: transparent;
}}
QLabel#StatValue {{
    color: {PRIMARY_COLOR};
    font-size: 18px;
    font-weight: 600;
    background: transparent;
}}

QLabel#ConnStatus {{
    font-size: 11px;
    font-weight: 600;
    padding: 4px 12px;
    border-radius: 10px;
    background: rgba(255,255,255,0.05);
}}

QFrame#StatBox {{
    background-color: rgba(255,255,255,0.04);
    border-radius: 12px;
    padding: 8px;
}}

QPushButton#GameButton {{
    background-color: #ff5252;
    color: white;
    font-weight: bold;
    font-size: 14px;
    padding: 10px 24px;
    border-radius: 12px;
    border: none;
}}
QPushButton#GameButton:hover {{
    background-color: #ff3030;
}}
QPushButton#GameButton:checked {{
    background-color: {SUCCESS_COLOR};
}}
QPushButton#GameButton:checked:hover {{
    background-color: #43a047;
}}

QPushButton#ModeButton {{
    background-color: rgba(255,255,255,0.06);
    color: {TEXT_COLOR};
    border: 1px solid rgba(255,255,255,0.1);
    padding: 6px 14px;
    border-radius: 10px;
    font-size: 12px;
}}
QPushButton#ModeButton:hover {{
    background-color: rgba(255,255,255,0.12);
}}
QPushButton#ModeButton:checked {{
    background-color: {PRIMARY_COLOR};
    color: {BG_COLOR};
}}

QPushButton#MiniButton {{
    background-color: rgba(255,255,255,0.06);
    color: {PRIMARY_COLOR};
    border: none;
    border-radius: 12px;
    font-size: 14px;
    padding: 6px 10px;
}}
QPushButton#MiniButton:hover {{
    background-color: rgba(0,210,255,0.15);
}}

QPushButton#CloseButton {{
    background-color: rgba(255,82,82,0.1);
    color: {DANGER_COLOR};
    border: none;
    border-radius: 12px;
    font-size: 14px;
    padding: 6px 10px;
}}
QPushButton#CloseButton:hover {{
    background-color: {DANGER_COLOR};
    color: white;
}}

QSlider::groove:horizontal {{
    height: 10px;
    background: #050505;
    border-radius: 5px;
}}
QSlider::handle:horizontal {{
    background: {PRIMARY_COLOR};
    width: 18px;
    height: 18px;
    margin: -5px 0;
    border-radius: 9px;
    border: 2px solid #0b0b0b;
}}
QSlider::sub-page:horizontal {{
    background: {PRIMARY_COLOR};
    border-radius: 5px;
}}

QSpinBox, QComboBox {{
    background-color: {INPUT_BG};
    color: {PRIMARY_COLOR};
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px;
    padding: 4px 8px;
    font-weight: 600;
}}
QComboBox QAbstractItemView {{
    background-color: {CARD_BG};
    color: {TEXT_COLOR};
    selection-background-color: {PRIMARY_COLOR};
    selection-color: {BG_COLOR};
    border: 1px solid rgba(255,255,255,0.1);
}}

QProgressBar {{
    background-color: rgba(255,255,255,0.04);
    border: none;
    border-radius: 6px;
    text-align: center;
    color: {TEXT_COLOR};
    font-size: 10px;
}}
QProgressBar::chunk {{
    background-color: {PRIMARY_COLOR};
    border-radius: 6px;
}}

QTableWidget {{
    background-color: {CARD_BG};
    color: {TEXT_COLOR};
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 12px;
    gridline-color: rgba(255,255,255,0.05);
}}
QHeaderView::section {{
    background-color: rgba(255,255,255,0.04);
    color: {PRIMARY_COLOR};
    border: none;
    padding: 6px;
    font-weight: 600;
}}
QTableWidget::item {{
    padding: 4px 8px;
}}
"""


# ============================================================
# Animated Fan Widget (SVG-style blades)
# ============================================================
class FanVisualizer(QWidget):
    """Widget that draws an animated fan with spinning blades."""

    def __init__(self, parent=None, size: int = 180):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._rotation = 0.0       # degrees
        self._percent = 0           # 0..100
        self._temp = 0              # °C for color hint
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)       # ~33 FPS
        self._last_tick = time.time()

    def set_percent(self, percent: int):
        self._percent = max(0, min(100, int(percent)))
        self.update()

    def set_temp(self, temp: float):
        self._temp = temp
        self.update()

    def _tick(self):
        # Spin speed proportional to percent
        # 0% -> 0 deg/sec; 100% -> ~720 deg/sec (2 revolutions/sec)
        deg_per_sec = self._percent * 7.2
        now = time.time()
        dt = now - self._last_tick
        self._last_tick = now
        self._rotation = (self._rotation + deg_per_sec * dt) % 360
        self.update()

    def paintEvent(self, _evt):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        cx, cy = w / 2, h / 2
        radius = min(w, h) / 2 - 6

        # Background circle gradient
        bg_grad = QRadialGradient(cx, cy, radius)
        bg_grad.setColorAt(0, QColor(30, 30, 30))
        bg_grad.setColorAt(1, QColor(20, 20, 20))
        p.setBrush(QBrush(bg_grad))
        p.setPen(QPen(QColor(SECONDARY_COLOR), 3))
        p.drawEllipse(QPointF(cx, cy), radius, radius)

        # Glow effect when fan is active
        if self._percent > 0:
            glow_color = QColor(0, 210, 255, int(40 + self._percent * 1.5))
            p.setBrush(QBrush(glow_color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(cx, cy), radius * 0.95, radius * 0.95)

        # Save state, translate to center, rotate
        p.save()
        p.translate(cx, cy)
        p.rotate(self._rotation)

        # Draw 3 blades (paths from reference HTML, scaled)
        blade_pen = QPen(QColor(PRIMARY_COLOR), 3)
        blade_color = QColor(0, 210, 255, 60)
        p.setPen(blade_pen)
        p.setBrush(QBrush(blade_color))

        r = radius * 0.85
        for i in range(3):
            p.save()
            p.rotate(i * 120)
            # Blade path - curved teardrop shape
            path = QPainterPath()
            path.moveTo(0, 0)
            path.cubicTo(-r * 0.4, -r * 0.6,  -r * 0.2, -r * 0.95,  0, -r * 0.95)
            path.cubicTo(r * 0.4, -r * 0.6,   r * 0.05, -r * 0.2,   0, 0)
            p.drawPath(path)
            p.restore()

        # Center hub
        p.setBrush(QBrush(QColor(243, 243, 243)))
        p.setPen(QPen(QColor(PRIMARY_COLOR), 3))
        p.drawEllipse(QPointF(0, 0), 14, 14)

        p.restore()


# ============================================================
# Temp Chart (compact line chart)
# ============================================================
class TempChartWidget(QWidget):
    def __init__(self, parent=None, window_sec: int = 180):
        super().__init__(parent)
        self.window_sec = window_sec
        self.setMinimumHeight(110)
        self.cpu_data = collections.deque()
        self.gpu_data = collections.deque()

    def push(self, cpu: float, gpu: float) -> None:
        now = time.time()
        self.cpu_data.append((now, cpu))
        self.gpu_data.append((now, gpu))
        cutoff = now - self.window_sec
        while self.cpu_data and self.cpu_data[0][0] < cutoff:
            self.cpu_data.popleft()
        while self.gpu_data and self.gpu_data[0][0] < cutoff:
            self.gpu_data.popleft()
        self.update()

    def paintEvent(self, _evt):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Background
        p.fillRect(0, 0, w, h, QColor(CARD_BG))

        # Grid
        p.setPen(QPen(QColor(255, 255, 255, 15), 1, Qt.PenStyle.DashLine))
        for i in range(1, 4):
            y = h * i // 4
            p.drawLine(0, y, w, y)

        # Axis labels
        p.setPen(QColor(TEXT_MUTED))
        p.setFont(QFont(PERSIAN_FONT, 8))
        for i in range(5):
            t = 100 - i * 25
            y = h * (i + 1) // 4
            p.drawText(4, y - 2, f"{t}°")

        if len(self.cpu_data) < 2:
            p.setPen(QColor(TEXT_MUTED))
            p.drawText(w // 2 - 50, h // 2, "Awaiting data...")
            return

        now = time.time()
        x0 = now - self.window_sec
        max_temp = 100.0

        def to_xy(samples):
            xs, ys = [], []
            for t, v in samples:
                xs.append((t - x0) / self.window_sec * w)
                ys.append(h - (min(v, max_temp) / max_temp) * h)
            return xs, ys

        for samples, color in ((self.cpu_data, QColor(0, 210, 255)),
                                (self.gpu_data, QColor(255, 82, 82))):
            xs, ys = to_xy(samples)
            p.setPen(QPen(color, 2))
            for i in range(1, len(xs)):
                p.drawLine(int(xs[i-1]), int(ys[i-1]), int(xs[i]), int(ys[i]))

        # Legend
        p.setPen(QColor(0, 210, 255))
        p.drawText(w - 100, 16, "CPU")
        p.setPen(QColor(255, 82, 82))
        p.drawText(w - 60, 16, "GPU")


# ============================================================
# Fan Card Widget
# ============================================================
class FanCard(QFrame):
    """One card per fan - shows visualizer + stats + slider."""

    def __init__(self, fan_name: str, parent=None):
        super().__init__(parent)
        self.setObjectName("FanCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._fan_name = fan_name
        self._percent = 0
        self._temp = 0
        self._rpm = 0
        self._mode = "Auto"

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Fan name (editable-looking label)
        self.lbl_name = QLabel(self._fan_name)
        self.lbl_name.setObjectName("FanLabel")
        self.lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_name)

        # Fan visualizer (animated)
        self.visualizer = FanVisualizer(self, size=160)
        vis_layout = QHBoxLayout()
        vis_layout.addStretch()
        vis_layout.addWidget(self.visualizer)
        vis_layout.addStretch()
        layout.addLayout(vis_layout)

        # Stats grid (Temp + RPM)
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(8)

        self.stat_temp_label = QLabel("دمما (°C)")
        self.stat_temp_label.setObjectName("StatLabel")
        self.stat_temp_value = QLabel("--")
        self.stat_temp_value.setObjectName("StatValue")
        self.stat_temp_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        temp_box = QVBoxLayout()
        temp_box.addWidget(self.stat_temp_label)
        temp_box.addWidget(self.stat_temp_value)
        temp_w = QFrame()
        temp_w.setObjectName("StatBox")
        temp_w.setLayout(temp_box)
        stats_layout.addWidget(temp_w)

        self.stat_rpm_label = QLabel("سرعت فن (%)")
        self.stat_rpm_label.setObjectName("StatLabel")
        self.stat_rpm_value = QLabel("--")
        self.stat_rpm_value.setObjectName("StatValue")
        self.stat_rpm_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rpm_box = QVBoxLayout()
        rpm_box.addWidget(self.stat_rpm_label)
        rpm_box.addWidget(self.stat_rpm_value)
        rpm_w = QFrame()
        rpm_w.setObjectName("StatBox")
        rpm_w.setLayout(rpm_box)
        stats_layout.addWidget(rpm_w)

        layout.addLayout(stats_layout)

        # Mode label
        self.lbl_mode = QLabel("حالت: Auto")
        self.lbl_mode.setObjectName("StatLabel")
        self.lbl_mode.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_mode)

        # Percentage display + spin box
        pct_row = QHBoxLayout()
        pct_row.addWidget(QLabel("درصد توان"))
        pct_row.addStretch()
        self.spinbox = QSpinBox()
        self.spinbox.setRange(0, 100)
        self.spinbox.setSuffix("%")
        self.spinbox.setFixedWidth(80)
        self.spinbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pct_row.addWidget(self.spinbox)
        layout.addLayout(pct_row)

        # Slider
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        layout.addWidget(self.slider)

        # Connect
        self.slider.valueChanged.connect(self._on_slider)
        self.spinbox.valueChanged.connect(self._on_spinbox)

    def _on_slider(self, v: int):
        self.spinbox.blockSignals(True)
        self.spinbox.setValue(v)
        self.spinbox.blockSignals(False)
        self._percent = v
        self.visualizer.set_percent(v)

    def _on_spinbox(self, v: int):
        self.slider.blockSignals(True)
        self.slider.setValue(v)
        self.slider.blockSignals(False)
        self._percent = v
        self.visualizer.set_percent(v)

    def update_temp_only(self, temp: float):
        """Update only the temperature display (from local hardware).
        Fan percent comes from ESP, so we don't touch slider/spinbox here."""
        try:
            temp = float(temp) if temp is not None else 0.0
        except (TypeError, ValueError):
            temp = 0.0
        self._temp = temp
        self.stat_temp_value.setText(f"{temp:.0f}°")
        self.visualizer.set_temp(temp)

    def update_status(self, temp: float, fan_pct: int, mode: int):
        # Handle None / NaN gracefully
        try:
            temp = float(temp) if temp is not None else 0.0
        except (TypeError, ValueError):
            temp = 0.0
        try:
            fan_pct = int(fan_pct) if fan_pct is not None else 0
        except (TypeError, ValueError):
            fan_pct = 0
        try:
            mode = int(mode) if mode is not None else 0
        except (TypeError, ValueError):
            mode = 0

        self._temp = temp
        self._percent = fan_pct
        self._mode = {0: "Auto", 1: "Manual", 2: "Game", 3: "Failsafe"}.get(mode, "?")
        self.stat_temp_value.setText(f"{temp:.0f}°")
        self.stat_rpm_value.setText(f"{fan_pct}%")
        self.lbl_mode.setText(f"حالت: {self._mode}")
        self.visualizer.set_percent(fan_pct)
        self.visualizer.set_temp(temp)

        # Block slider signals when status pushed (don't echo back)
        self.slider.blockSignals(True)
        self.spinbox.blockSignals(True)
        # Only update slider if mode is auto/game (don't override manual)
        if mode in (0, 2, 3):
            self.slider.setValue(fan_pct)
            self.spinbox.setValue(fan_pct)
        self.slider.blockSignals(False)
        self.spinbox.blockSignals(False)


# ============================================================
# Mini Spinning Fan Circle Widget (CPU and GPU)
# ============================================================
class MiniFanCircle(QWidget):
    """A single circular animated fan blade indicator for mini mode."""

    def __init__(self, label: str, color: str, parent=None, size: int = 70):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._rotation = 0.0
        self._percent = 0
        self._temp = 0
        self._label = label
        self._color = QColor(color)
        self._last_tick = time.time()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)  # ~33 FPS

    def set_percent(self, percent: int):
        self._percent = max(0, min(100, int(percent)))

    def set_temp(self, temp: float):
        self._temp = temp

    def _tick(self):
        # Spin speed proportional to percent (0 = stopped, 100 = ~720 deg/s)
        deg_per_sec = self._percent * 7.2
        now = time.time()
        dt = now - self._last_tick
        self._last_tick = now
        self._rotation = (self._rotation + deg_per_sec * dt) % 360
        self.update()

    def paintEvent(self, _evt):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        radius = min(w, h) / 2 - 4

        # Background circle
        bg = QRadialGradient(cx, cy, radius)
        bg.setColorAt(0, QColor(40, 40, 40))
        bg.setColorAt(1, QColor(20, 20, 20))
        p.setBrush(QBrush(bg))
        p.setPen(QPen(self._color.darker(150), 2))
        p.drawEllipse(QPointF(cx, cy), radius, radius)

        # Glow if active
        if self._percent > 0:
            glow = QColor(self._color)
            glow.setAlpha(int(30 + self._percent * 1.5))
            p.setBrush(QBrush(glow))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(cx, cy), radius * 0.95, radius * 0.95)

        # Rotating fan blades
        p.save()
        p.translate(cx, cy)
        p.rotate(self._rotation)

        blade_color = QColor(self._color)
        blade_color.setAlpha(140)
        p.setBrush(QBrush(blade_color))
        p.setPen(QPen(self._color, 1.5))

        r = radius * 0.85
        for i in range(3):
            p.save()
            p.rotate(i * 120)
            path = QPainterPath()
            path.moveTo(0, 0)
            path.cubicTo(-r * 0.4, -r * 0.6,  -r * 0.2, -r * 0.95,  0, -r * 0.95)
            path.cubicTo(r * 0.4, -r * 0.6,   r * 0.05, -r * 0.2,   0, 0)
            p.drawPath(path)
            p.restore()

        # Center hub
        p.setBrush(QBrush(QColor(243, 243, 243)))
        p.setPen(QPen(self._color, 2))
        p.drawEllipse(QPointF(0, 0), 8, 8)
        p.restore()

        # Label below
        p.setPen(self._color)
        p.setFont(QFont("Tahoma", 8, QFont.Weight.Bold))
        p.drawText(QRectF(0, h - 14, w, 14), Qt.AlignmentFlag.AlignCenter, self._label)


# ============================================================
# Mini Floating Widget (compact mode) - 2 spinning circles
# ============================================================
class MiniWidget(QWidget):
    """Compact floating widget with 2 spinning fan circles (CPU + GPU)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Window flags for a floating, frameless, always-on-top widget
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool  # don't show in taskbar
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setFixedSize(340, 280)

        # Apply dark theme styles
        self.setStyleSheet(f"""
            QWidget#MiniRoot {{
                background-color: {CARD_BG};
                border-radius: 18px;
                border: 1px solid rgba(0,210,255,0.4);
            }}
            QLabel {{
                background: transparent;
                color: {TEXT_COLOR};
                font-family: {PERSIAN_FONT}, 'Segoe UI', Arial, sans-serif;
            }}
        """)
        self.setObjectName("MiniRoot")

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        title = QLabel("🎮 Fan Controller")
        title.setStyleSheet(f"color: {PRIMARY_COLOR}; font-weight: bold; font-size: 13px;")
        header.addWidget(title)
        header.addStretch()
        self.btn_expand = QPushButton("⤢")
        self.btn_expand.setFixedSize(26, 26)
        self.btn_expand.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_expand.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,255,255,0.06);
                border: none; border-radius: 13px;
                color: {PRIMARY_COLOR};
                font-size: 14px;
            }}
            QPushButton:hover {{ background: rgba(0,210,255,0.2); }}
        """)
        self.btn_expand.setToolTip("بازگشت به حالت کامل")
        header.addWidget(self.btn_expand)
        layout.addLayout(header)

        # Connection status indicator
        self.lbl_conn = QLabel("● در حال اتصال...")
        self.lbl_conn.setStyleSheet(f"""
            font-size: 10px;
            color: {TEXT_MUTED};
            padding: 4px 8px;
            background: rgba(255,255,255,0.04);
            border-radius: 8px;
        """)
        layout.addWidget(self.lbl_conn)

        # Two spinning fan circles side by side, each with info BESIDE it
        circles_layout = QHBoxLayout()
        circles_layout.setSpacing(12)

        # CPU fan (circle on left, info on right)
        cpu_row = QHBoxLayout()
        cpu_row.setSpacing(8)
        self.cpu_circle = MiniFanCircle("CPU", PRIMARY_COLOR, size=90)
        cpu_row.addWidget(self.cpu_circle)
        cpu_info_box = QVBoxLayout()
        cpu_info_box.setSpacing(2)
        cpu_temp_lbl = QLabel("دماتر")
        cpu_temp_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; background: transparent;")
        cpu_temp_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        cpu_info_box.addWidget(cpu_temp_lbl)
        self.cpu_temp_value = QLabel("--°C")
        self.cpu_temp_value.setStyleSheet(f"""
            color: {PRIMARY_COLOR};
            font-size: 16px;
            font-weight: bold;
            background: transparent;
        """)
        self.cpu_temp_value.setAlignment(Qt.AlignmentFlag.AlignLeft)
        cpu_info_box.addWidget(self.cpu_temp_value)
        cpu_pct_lbl = QLabel("سرعت فن")
        cpu_pct_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; background: transparent;")
        cpu_pct_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        cpu_info_box.addWidget(cpu_pct_lbl)
        self.cpu_pct_value = QLabel("--%")
        self.cpu_pct_value.setStyleSheet(f"""
            color: {PRIMARY_COLOR};
            font-size: 16px;
            font-weight: bold;
            background: transparent;
        """)
        self.cpu_pct_value.setAlignment(Qt.AlignmentFlag.AlignLeft)
        cpu_info_box.addWidget(self.cpu_pct_value)
        cpu_info_box.addStretch()
        cpu_row.addLayout(cpu_info_box)
        circles_layout.addLayout(cpu_row)

        # GPU fan (circle on left, info on right)
        gpu_row = QHBoxLayout()
        gpu_row.setSpacing(8)
        self.gpu_circle = MiniFanCircle("GPU", "#ff5252", size=90)
        gpu_row.addWidget(self.gpu_circle)
        gpu_info_box = QVBoxLayout()
        gpu_info_box.setSpacing(2)
        gpu_temp_lbl = QLabel("دماتر")
        gpu_temp_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; background: transparent;")
        gpu_temp_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        gpu_info_box.addWidget(gpu_temp_lbl)
        self.gpu_temp_value = QLabel("--°C")
        self.gpu_temp_value.setStyleSheet("""
            color: #ff5252;
            font-size: 16px;
            font-weight: bold;
            background: transparent;
        """)
        self.gpu_temp_value.setAlignment(Qt.AlignmentFlag.AlignLeft)
        gpu_info_box.addWidget(self.gpu_temp_value)
        gpu_pct_lbl = QLabel("سرعت فن")
        gpu_pct_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; background: transparent;")
        gpu_pct_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        gpu_info_box.addWidget(gpu_pct_lbl)
        self.gpu_pct_value = QLabel("--%")
        self.gpu_pct_value.setStyleSheet("""
            color: #ff5252;
            font-size: 16px;
            font-weight: bold;
            background: transparent;
        """)
        self.gpu_pct_value.setAlignment(Qt.AlignmentFlag.AlignLeft)
        gpu_info_box.addWidget(self.gpu_pct_value)
        gpu_info_box.addStretch()
        gpu_row.addLayout(gpu_info_box)
        circles_layout.addLayout(gpu_row)

        layout.addLayout(circles_layout)

        layout.addStretch()

        # Quick Game Mode toggle
        self.btn_game = QPushButton("🎮  Game Mode")
        self.btn_game.setCheckable(True)
        self.btn_game.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_game.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255,82,82,0.15);
                color: {DANGER_COLOR};
                border: 1px solid rgba(255,82,82,0.3);
                border-radius: 10px;
                padding: 10px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: rgba(255,82,82,0.25);
            }}
            QPushButton:checked {{
                background-color: {SUCCESS_COLOR};
                color: white;
                border-color: {SUCCESS_COLOR};
            }}
        """)
        layout.addWidget(self.btn_game)

        # Drag handling
        self._drag_offset = None

    # ---------- Drag the floating widget ----------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            widget = self.childAt(event.position().toPoint())
            if widget is None:
                self._drag_offset = event.globalPosition().toPoint() - self.pos()
                event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_offset = None

    # ---------- Update content ----------
    def update_status(self, cpu_temp, gpu_temp, cpu_pct, gpu_pct, conn: str, game: bool):
        # Handle None / NaN values gracefully
        try:
            cpu_temp = float(cpu_temp) if cpu_temp is not None else 0.0
        except (TypeError, ValueError):
            cpu_temp = 0.0
        try:
            gpu_temp = float(gpu_temp) if gpu_temp is not None else 0.0
        except (TypeError, ValueError):
            gpu_temp = 0.0
        try:
            cpu_pct = int(cpu_pct) if cpu_pct is not None else 0
        except (TypeError, ValueError):
            cpu_pct = 0
        try:
            gpu_pct = int(gpu_pct) if gpu_pct is not None else 0
        except (TypeError, ValueError):
            gpu_pct = 0

        # Update spinning circles
        self.cpu_circle.set_percent(cpu_pct)
        self.cpu_circle.set_temp(cpu_temp)
        self.gpu_circle.set_percent(gpu_pct)
        self.gpu_circle.set_temp(gpu_temp)

        # Update info labels BESIDE the circles
        self.cpu_temp_value.setText(f"{cpu_temp:.0f}°C")
        self.cpu_pct_value.setText(f"{cpu_pct}%")
        self.gpu_temp_value.setText(f"{gpu_temp:.0f}°C")
        self.gpu_pct_value.setText(f"{gpu_pct}%")
        self.lbl_conn.setText(conn if conn else "● ...")
        self.btn_game.setChecked(bool(game))

    # ---------- Paint rounded background ----------
    def paintEvent(self, _event):
        from PyQt6.QtGui import QPainterPath, QBrush, QColor, QPainter
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 18, 18)
        p.fillPath(path, QBrush(QColor(CARD_BG)))
        from PyQt6.QtGui import QPen
        p.setPen(QPen(QColor(0, 210, 255, 100), 1))
        p.drawPath(path)


# ============================================================
# Main Window
# ============================================================
class FanControllerGUI(QMainWindow):
    status_signal = pyqtSignal(dict)
    state_signal = pyqtSignal(int)
    local_temp_signal = pyqtSignal(float, float)  # cpu_temp, gpu_temp from local hardware

    def __init__(self, config: Config, client: ESPClient,
                 on_game_mode, on_set_profile, on_set_fan):
        super().__init__()
        self.config = config
        self.client = client
        self._on_game_mode = on_game_mode
        self._on_set_profile = on_set_profile
        self._on_set_fan = on_set_fan

        self.setWindowTitle("ESP8266 Fan Controller")
        self.resize(920, 720)
        self.setStyleSheet(DARK_QSS)
        self.setWindowFlag(Qt.WindowType.Window, True)

        self._setup_ui()

        self.client.on_status = self._on_status
        self.client.on_state_change = self._on_state_change
        self.status_signal.connect(self._apply_status)
        self.state_signal.connect(self._apply_state)
        self.local_temp_signal.connect(self._apply_local_temp)

        # Local hardware temp polling timer (independent of ESP)
        # Reads CPU/GPU temps every 2 seconds from LibreHardwareMonitor / nvidia-smi
        # and displays them immediately (even without ESP connection)
        self._hw_timer = QTimer(self)
        self._hw_timer.timeout.connect(self._poll_local_hw)
        self._hw_timer.start(int(config.poll_interval_sec * 1000))

        # Mini mode widget - created lazily
        self._mini = None
        self._drag_offset = None

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(15)

        # ---------- Header ----------
        header_frame = QFrame()
        header_frame.setObjectName("Header")
        header = QHBoxLayout(header_frame)
        header.setContentsMargins(0, 0, 0, 0)

        title_block = QVBoxLayout()
        title = QLabel("Fan Controller Dashboard")
        title.setObjectName("HeaderTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("کنترل سرعت فن‌ها بر اساس دمای CPU/GPU")
        subtitle.setObjectName("HeaderSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        header.addLayout(title_block)

        # Window controls
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(6)

        # Settings button (gear icon)
        self.btn_settings = QPushButton("⚙ تنظیمات")
        self.btn_settings.setObjectName("MiniButton")
        self.btn_settings.setFixedHeight(32)
        self.btn_settings.setMinimumWidth(90)
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.clicked.connect(self._open_settings)
        ctrl_layout.addWidget(self.btn_settings)

        # Log viewer button (NEW - shows app.log in-app)
        self.btn_log = QPushButton("📋 لاگ")
        self.btn_log.setObjectName("MiniButton")
        self.btn_log.setFixedHeight(32)
        self.btn_log.setMinimumWidth(70)
        self.btn_log.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_log.setToolTip("نمایش لاگ برنامه برای عیب‌یابی")
        self.btn_log.clicked.connect(self._open_log_viewer)
        ctrl_layout.addWidget(self.btn_log)

        # Mini mode button (with text)
        self.btn_mini = QPushButton("🗗 مینی")
        self.btn_mini.setObjectName("MiniButton")
        self.btn_mini.setFixedHeight(32)
        self.btn_mini.setMinimumWidth(80)
        self.btn_mini.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mini.setToolTip("حالت کوچک (Mini mode) - پنجره شناور")
        self.btn_mini.clicked.connect(self._show_mini)
        ctrl_layout.addWidget(self.btn_mini)

        # Close button
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("CloseButton")
        self.btn_close.setFixedSize(32, 32)
        self.btn_close.setToolTip("بستن پنجره (به tray)")
        self.btn_close.clicked.connect(self.hide)
        ctrl_layout.addWidget(self.btn_close)

        header.addLayout(ctrl_layout)
        root.addWidget(header_frame)

        # ---------- Status bar (connection + profile) ----------
        status_row = QHBoxLayout()

        status_row.addWidget(QLabel("🔗 اتصال:"))
        self.lbl_conn = QLabel("در حال اتصال...")
        self.lbl_conn.setObjectName("ConnStatus")
        self.lbl_conn.setStyleSheet(f"color: {TEXT_MUTED};")
        status_row.addWidget(self.lbl_conn)
        status_row.addStretch()

        status_row.addWidget(QLabel("📊 پروفایل:"))
        self.cmb_profile = QComboBox()
        for p in PROFILES:
            self.cmb_profile.addItem(p.name, p.id)
        self.cmb_profile.setCurrentIndex(self.config.active_profile)
        self.cmb_profile.currentIndexChanged.connect(self._on_profile_changed)
        status_row.addWidget(self.cmb_profile)
        root.addLayout(status_row)

        # ---------- Game Mode button ----------
        self.btn_game = QPushButton("🎮  فعال‌سازی حالت گیم (همه فن‌ها ۱۰۰٪)")
        self.btn_game.setObjectName("GameButton")
        self.btn_game.setCheckable(True)
        self.btn_game.clicked.connect(self._toggle_game_mode)
        root.addWidget(self.btn_game)

        # ---------- Fan cards grid (2 fans: CPU + GPU) ----------
        cards_frame = QFrame()
        cards_layout = QGridLayout(cards_frame)
        cards_layout.setSpacing(12)

        # Only CPU + GPU fans
        self.cards = {}
        self.cards["cpu"] = FanCard("CPU Fan")
        self.cards["gpu"] = FanCard("GPU Fan")

        # Side by side
        cards_layout.addWidget(self.cards["cpu"], 0, 0)
        cards_layout.addWidget(self.cards["gpu"], 0, 1)
        root.addWidget(cards_frame)

        # Connect sliders
        self.cards["cpu"].slider.valueChanged.connect(
            lambda v: self._on_manual("cpu", v))
        self.cards["cpu"].spinbox.valueChanged.connect(
            lambda v: self._on_manual("cpu", v))
        self.cards["gpu"].slider.valueChanged.connect(
            lambda v: self._on_manual("gpu", v))
        self.cards["gpu"].spinbox.valueChanged.connect(
            lambda v: self._on_manual("gpu", v))

        # ---------- Live temp chart ----------
        chart_title = QLabel("📈 نمودار دما (۳ دقیقه اخیر)")
        chart_title.setStyleSheet(f"color: {PRIMARY_COLOR}; font-weight: bold; margin-top: 10px;")
        root.addWidget(chart_title)

        self.chart = TempChartWidget(window_sec=180)
        root.addWidget(self.chart, stretch=1)

    # ---------- Mini / Full mode ----------
    def _open_log_viewer(self):
        """Open the in-app log viewer for debugging."""
        try:
            from log_viewer import LogViewerDialog
            dlg = LogViewerDialog(parent=self)
            dlg.exec()
        except Exception as e:
            log.exception(f"Log viewer failed: {e}")
            QMessageBox.critical(self, "خطا", f"باز کردن لاگ ناموفق:\n{e}")

    def _open_settings(self):
        """Open the settings dialog to edit fan curves."""
        try:
            from settings_dialog import SettingsDialog
            dlg = SettingsDialog(self.config, parent=self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                curves = dlg.get_curves()
                if curves:
                    # Send new curves to ESP
                    if "cpu" in curves:
                        temps, pcts = curves["cpu"]
                        self.client.set_curve("cpu", temps, pcts)
                        log.info(f"CPU curve applied: {len(temps)} points")
                    if "gpu" in curves:
                        temps, pcts = curves["gpu"]
                        self.client.set_curve("gpu", temps, pcts)
                        log.info(f"GPU curve applied: {len(temps)} points")
        except Exception as e:
            log.exception(f"Settings dialog failed: {e}")

    def _show_mini(self):
        """Switch to compact floating mode."""
        try:
            if self._mini is None:
                log.info("Creating MiniWidget...")
                self._mini = MiniWidget()
                self._mini.btn_expand.clicked.connect(self._show_full)
                self._mini.btn_game.clicked.connect(self._toggle_game_mode)
                # Initial position: bottom-right of primary screen
                from PyQt6.QtGui import QGuiApplication
                screen = QGuiApplication.primaryScreen()
                if screen:
                    g = screen.availableGeometry()
                    x = g.x() + g.width() - self._mini.width() - 30
                    y = g.y() + g.height() - self._mini.height() - 30
                    self._mini.move(x, y)
                else:
                    self._mini.move(100, 100)
                log.info(f"MiniWidget created, moving to {self._mini.pos()}")

            # Hide main window
            self.hide()
            # Sync current status to mini widget
            self._mini.update_status(
                getattr(self, "_last_cpu_temp", 0.0),
                getattr(self, "_last_gpu_temp", 0.0),
                getattr(self, "_last_cpu_pct", 0),
                getattr(self, "_last_gpu_pct", 0),
                self.lbl_conn.text(),
                self.btn_game.isChecked()
            )
            # Show mini widget
            self._mini.show()
            self._mini.raise_()
            self._mini.activateWindow()
            log.info("Mini widget shown")
        except Exception as e:
            log.exception(f"Mini mode failed: {e}")
            # Fallback: just hide main window, don't show mini
            self.hide()
            log.warning("Mini widget failed, just hiding main window")

    def _show_full(self):
        """Switch from mini mode back to full window."""
        try:
            if self._mini is not None:
                self._mini.hide()
            self.show()
            self.raise_()
            self.activateWindow()
            log.info("Switched back to full mode")
        except Exception as e:
            log.exception(f"Full mode failed: {e}")

    # ---------- Game mode ----------
    def _toggle_game_mode(self):
        is_on = self.btn_game.isChecked()
        self._on_game_mode(is_on)

    # ---------- Manual fan control ----------
    def _on_manual(self, fan: str, value: int):
        # 0% on slider = auto, otherwise manual
        if value == 0:
            self._on_set_fan(fan, 0)   # auto
        else:
            self._on_set_fan(fan, value)

    # ---------- Profile change ----------
    def _on_profile_changed(self, idx: int):
        pid = self.cmb_profile.itemData(idx)
        self.config.active_profile = pid
        self.config.save()
        self._on_set_profile(pid)

    # ---------- Local hardware temperature polling ----------
    def set_hardware_monitor(self, monitor):
        """Set the hardware monitor so we can read local temps."""
        self._monitor = monitor

    def _poll_local_hw(self):
        """Read CPU/GPU temps directly from local hardware (not from ESP).
        This ensures temps display even when ESP isn't connected."""
        monitor = getattr(self, "_monitor", None)
        if monitor is None:
            return
        try:
            import threading
            def read_and_emit():
                try:
                    t = monitor.read()
                    log.debug(f"Local HW: CPU={t.cpu:.1f}C GPU={t.gpu:.1f}C")
                    self.local_temp_signal.emit(float(t.cpu), float(t.gpu))
                except Exception as e:
                    log.debug(f"Local HW read failed: {e}")
            threading.Thread(target=read_and_emit, daemon=True).start()
        except Exception as e:
            log.debug(f"HW poll error: {e}")

    def _apply_local_temp(self, cpu_temp: float, gpu_temp: float):
        """Update UI with local hardware temps (called via signal)."""
        self._last_cpu_temp = cpu_temp
        self._last_gpu_temp = gpu_temp
        # Update temp display in cards (fan % comes from ESP)
        self.cards["cpu"].update_temp_only(cpu_temp)
        self.cards["gpu"].update_temp_only(gpu_temp)
        # Update mini widget if visible
        if self._mini is not None and self._mini.isVisible():
            self._mini.update_status(
                cpu_temp, gpu_temp,
                getattr(self, "_last_cpu_pct", 0),
                getattr(self, "_last_gpu_pct", 0),
                self.lbl_conn.text(),
                self.btn_game.isChecked()
            )

    # ---------- Status from ESP ----------
    def _on_status(self, s: ESPStatus):
        self.status_signal.emit({
            "cpu_pct": s.cpu_pct, "gpu_pct": s.gpu_pct,
            "cpu_temp": s.cpu_temp, "gpu_temp": s.gpu_temp,
            "cpu_mode": s.cpu_mode, "gpu_mode": s.gpu_mode,
            "profile": s.profile, "game": s.game,
        })

    def _on_state_change(self, state: ConnState):
        self.state_signal.emit(int(state))

    def _apply_status(self, d: dict):
        cpu_temp = d.get("cpu_temp", 0)
        gpu_temp = d.get("gpu_temp", 0)
        cpu_pct = d.get("cpu_pct", 0)
        gpu_pct = d.get("gpu_pct", 0)
        cpu_mode = d.get("cpu_mode", 0)
        gpu_mode = d.get("gpu_mode", 0)

        # Cache for mini widget
        self._last_cpu_temp = cpu_temp
        self._last_gpu_temp = gpu_temp
        self._last_cpu_pct = cpu_pct
        self._last_gpu_pct = gpu_pct

        # Update cards
        self.cards["cpu"].update_status(cpu_temp, cpu_pct, cpu_mode)
        self.cards["gpu"].update_status(gpu_temp, gpu_pct, gpu_mode)

        # Chart
        self.chart.push(cpu_temp, gpu_temp)

        # Game mode button
        game = bool(d.get("game", False))
        self.btn_game.setChecked(game)
        self.btn_game.setText(
            "🎮  خاموش کردن حالت گیم" if game else
            "🎮  فعال‌سازی حالت گیم (همه فن‌ها ۱۰۰٪)")

        # Mini widget (if visible)
        if self._mini is not None and self._mini.isVisible():
            conn_text = self.lbl_conn.text()
            self._mini.update_status(cpu_temp, gpu_temp, cpu_pct, gpu_pct,
                                      conn_text, game)

    def _apply_state(self, state_int: int):
        state = ConnState(state_int)
        colors = {
            ConnState.DISCONNECTED: ("● قطع", DANGER_COLOR),
            ConnState.WS:           (f"● WebSocket @ {self.config.esp_ip}", SUCCESS_COLOR),
            ConnState.HTTP:         (f"● HTTP @ {self.config.esp_ip}", WARN_COLOR),
            ConnState.USB:          (f"● USB @ {self.config.usb_port}", PRIMARY_COLOR),
        }
        text, color = colors[state]
        self.lbl_conn.setText(text)
        self.lbl_conn.setStyleSheet(
            f"color: {color}; font-weight: bold; padding: 4px 12px;"
            f" border-radius: 10px; background: rgba(255,255,255,0.05);")
        self._mini.lbl_conn.setText(text)

    def _poll_once(self):
        pass

    # ---------- Window events ----------
    def closeEvent(self, e):
        self.config.window_width = self.width()
        self.config.window_height = self.height()
        self.config.window_x = self.x()
        self.config.window_y = self.y()
        self.config.save()
        if self.config.minimize_to_tray_on_close:
            if self._mini is not None:
                self._mini.hide()
            self.hide()
            e.ignore()
        else:
            super().closeEvent(e)

    # ---------- Mouse drag for mini mode ----------
    def mousePressEventMini(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self._mini.pos()

    def mouseMoveEventMini(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._mini.move(event.globalPosition().toPoint() - self._drag_offset)
