"""
gui.py - Main GUI window built with PyQt6.
"""

from __future__ import annotations
import logging
import collections
import time
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QPainter, QColor, QPen, QFont
from PyQt6.QtWidgets import (
    QWidget, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QProgressBar, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QGroupBox
)

from config import Config, PROFILE_NAMES
from esp_client import ESPClient, ESPStatus, ConnState
from profiles import PROFILES

log = logging.getLogger(__name__)


class TempChartWidget(QWidget):
    def __init__(self, parent=None, window_sec: int = 300):
        super().__init__(parent)
        self.window_sec = window_sec
        self.setMinimumHeight(160)
        self.cpu_data: collections.deque = collections.deque()
        self.gpu_data: collections.deque = collections.deque()
        self._cpu_color = QColor(60, 180, 240)
        self._gpu_color = QColor(230, 100, 100)

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

    def clear(self) -> None:
        self.cpu_data.clear()
        self.gpu_data.clear()
        self.update()

    def paintEvent(self, _evt) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        p.fillRect(0, 0, w, h, QColor(245, 245, 250))
        p.setPen(QPen(QColor(220, 220, 230), 1, Qt.PenStyle.DashLine))
        for i in range(1, 5):
            y = h * i // 5
            p.drawLine(0, y, w, y)
        for i in range(1, 10):
            x = w * i // 10
            p.drawLine(x, 0, x, h)
        p.setPen(QColor(120, 120, 130))
        p.setFont(QFont("Arial", 8))
        for i in range(5):
            t = 100 - i * 25
            y = h * (i + 1) // 5
            p.drawText(2, y - 2, f"{t}C")
        if len(self.cpu_data) < 2:
            return
        now = time.time()
        x0 = now - self.window_sec
        max_temp = 100.0

        def to_xy(samples):
            xs, ys = [], []
            for t, v in samples:
                x = (t - x0) / self.window_sec * w
                y = h - (min(v, max_temp) / max_temp) * h
                xs.append(x); ys.append(y)
            return xs, ys

        for samples, color in ((self.cpu_data, self._cpu_color),
                                (self.gpu_data, self._gpu_color)):
            xs, ys = to_xy(samples)
            pen = QPen(color, 2)
            p.setPen(pen)
            for i in range(1, len(xs)):
                p.drawLine(int(xs[i-1]), int(ys[i-1]), int(xs[i]), int(ys[i]))
        p.setPen(self._cpu_color)
        p.drawText(w - 130, 18, "CPU")
        p.setPen(self._gpu_color)
        p.drawText(w - 80,  18, "GPU")


class FanControllerGUI(QMainWindow):
    status_signal = pyqtSignal(dict)
    state_signal = pyqtSignal(int)

    def __init__(self, config: Config, client: ESPClient,
                 on_game_mode, on_set_profile, on_set_fan):
        super().__init__()
        self.config = config
        self.client = client
        self._on_game_mode = on_game_mode
        self._on_set_profile = on_set_profile
        self._on_set_fan = on_set_fan
        self.setWindowTitle("ESP8266 Fan Controller")
        self.resize(config.window_width, config.window_height)
        self.move(config.window_x, config.window_y)
        self._setup_ui()
        self.client.on_status = self._on_status
        self.client.on_state_change = self._on_state_change
        self.status_signal.connect(self._apply_status)
        self.state_signal.connect(self._apply_state)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_once)
        self._timer.start(int(config.poll_interval_sec * 1000))

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        top = QHBoxLayout()
        top.addWidget(QLabel("Connection:"))
        self.lbl_conn = QLabel("Disconnected")
        self.lbl_conn.setStyleSheet("font-weight: bold; color: #888;")
        top.addWidget(self.lbl_conn)
        top.addStretch()
        top.addWidget(QLabel("Profile:"))
        self.cmb_profile = QComboBox()
        for p in PROFILES:
            self.cmb_profile.addItem(p.name, p.id)
        self.cmb_profile.setCurrentIndex(self.config.active_profile)
        self.cmb_profile.currentIndexChanged.connect(self._on_profile_changed)
        top.addWidget(self.cmb_profile)
        v.addLayout(top)

        for fan in ("CPU", "GPU"):
            grp = QGroupBox(f"{fan}")
            h = QHBoxLayout()
            lbl_t = QLabel(f"{fan} Temp:")
            h.addWidget(lbl_t)
            bar_t = QProgressBar(); bar_t.setRange(0, 100); bar_t.setFixedWidth(180)
            h.addWidget(bar_t)
            lbl_f = QLabel("Fan: 0%")
            lbl_f.setStyleSheet("font-weight: bold;")
            h.addWidget(lbl_f)
            lbl_m = QLabel("Mode: Auto")
            h.addWidget(lbl_m)
            h.addStretch()
            btn100 = QPushButton("Force 100%")
            btn100.clicked.connect(lambda _, f=fan.lower(): self._on_force(f, 100))
            h.addWidget(btn100)
            btn0 = QPushButton("Auto")
            btn0.clicked.connect(lambda _, f=fan.lower(): self._on_force(f, 0))
            h.addWidget(btn0)
            grp.setLayout(h)
            v.addWidget(grp)
            if fan == "CPU":
                self.cpu_bar = bar_t
                self.cpu_fan_lbl = lbl_f
                self.cpu_mode_lbl = lbl_m
            else:
                self.gpu_bar = bar_t
                self.gpu_fan_lbl = lbl_f
                self.gpu_mode_lbl = lbl_m

        gm = QHBoxLayout()
        self.btn_game = QPushButton("Activate Game Mode  (all fans 100%)")
        self.btn_game.setStyleSheet(
            "QPushButton { background-color: #d33; color: white;"
            " font-weight: bold; padding: 8px 16px; }"
            "QPushButton:hover { background-color: #c00; }"
        )
        self.btn_game.clicked.connect(self._toggle_game_mode)
        gm.addWidget(self.btn_game)
        v.addLayout(gm)

        self.tables = {}
        for fan in ("CPU", "GPU"):
            grp = QGroupBox(f"{fan} Fan Curve (active profile)")
            h = QHBoxLayout()
            tbl = QTableWidget(7, 2)
            tbl.setHorizontalHeaderLabels(["Temp (C)", "Fan %"])
            tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            for row in range(7):
                tbl.setItem(row, 0, QTableWidgetItem("0"))
                tbl.setItem(row, 1, QTableWidgetItem("0"))
            tbl.cellChanged.connect(lambda r, c, f=fan.lower(): self._on_curve_edit(f, r, c))
            h.addWidget(tbl)
            btn_apply = QPushButton("Apply")
            btn_apply.clicked.connect(lambda _, f=fan.lower(): self._on_apply_curve(f))
            h.addWidget(btn_apply)
            grp.setLayout(h)
            v.addWidget(grp)
            self.tables[fan.lower()] = tbl

        self.chart = TempChartWidget(window_sec=300)
        v.addWidget(self.chart, stretch=1)
        self._reload_curves_from_config()

    def _on_status(self, s: ESPStatus) -> None:
        self.status_signal.emit({
            "cpu_pct": s.cpu_pct, "gpu_pct": s.gpu_pct,
            "cpu_temp": s.cpu_temp, "gpu_temp": s.gpu_temp,
            "cpu_mode": s.cpu_mode, "gpu_mode": s.gpu_mode,
            "profile": s.profile, "game": s.game,
        })

    def _on_state_change(self, state: ConnState) -> None:
        self.state_signal.emit(int(state))

    def _apply_status(self, d: dict) -> None:
        self.cpu_bar.setValue(int(d.get("cpu_temp", 0)))
        self.cpu_bar.setFormat(f"{d.get('cpu_temp', 0):.0f} C")
        self.cpu_fan_lbl.setText(f"Fan: {d.get('cpu_pct', 0)}%")
        self.cpu_mode_lbl.setText(f"Mode: {self._mode_str(d.get('cpu_mode', 0))}")
        self.gpu_bar.setValue(int(d.get("gpu_temp", 0)))
        self.gpu_bar.setFormat(f"{d.get('gpu_temp', 0):.0f} C")
        self.gpu_fan_lbl.setText(f"Fan: {d.get('gpu_pct', 0)}%")
        self.gpu_mode_lbl.setText(f"Mode: {self._mode_str(d.get('gpu_mode', 0))}")
        self.chart.push(d.get("cpu_temp", 0), d.get("gpu_temp", 0))
        game = bool(d.get("game", False))
        self.btn_game.setText(
            "Disable Game Mode" if game else
            "Activate Game Mode  (all fans 100%)"
        )
        self.btn_game.setStyleSheet(
            "QPushButton { background-color: #2a8; color: white;"
            " font-weight: bold; padding: 8px 16px; }"
            "QPushButton:hover { background-color: #196; }"
            if game else
            "QPushButton { background-color: #d33; color: white;"
            " font-weight: bold; padding: 8px 16px; }"
            "QPushButton:hover { background-color: #c00; }"
        )

    def _apply_state(self, state_int: int) -> None:
        state = ConnState(state_int)
        colors = {
            ConnState.DISCONNECTED: ("Disconnected", "#c33"),
            ConnState.WS:           (f"WebSocket @ {self.config.esp_ip}", "#2a8"),
            ConnState.HTTP:         (f"HTTP @ {self.config.esp_ip}", "#d80"),
            ConnState.USB:          (f"USB @ {self.config.usb_port}", "#06c"),
        }
        text, color = colors[state]
        self.lbl_conn.setText(text)
        self.lbl_conn.setStyleSheet(f"font-weight: bold; color: {color};")

    def _toggle_game_mode(self) -> None:
        is_on = "Disable" in self.btn_game.text()
        self._on_game_mode(not is_on)

    def _on_force(self, fan: str, percent: int) -> None:
        if percent == 0:
            self._on_set_fan(fan, 0)
        else:
            self._on_set_fan(fan, percent)

    def _on_profile_changed(self, idx: int) -> None:
        pid = self.cmb_profile.itemData(idx)
        self.config.active_profile = pid
        self.config.save()
        self._on_set_profile(pid)
        self._reload_curves_from_config()

    def _reload_curves_from_config(self) -> None:
        for fan in ("cpu", "gpu"):
            temps, percents = self.config.get_curve(
                self.config.active_profile, fan)
            tbl = self.tables[fan]
            tbl.blockSignals(True)
            for i in range(7):
                tbl.item(i, 0).setText(str(temps[i]) if i < len(temps) else "")
                tbl.item(i, 1).setText(str(percents[i]) if i < len(percents) else "")
            tbl.blockSignals(False)

    def _on_curve_edit(self, fan: str, row: int, col: int) -> None:
        pass

    def _on_apply_curve(self, fan: str) -> None:
        tbl = self.tables[fan]
        temps, percents = [], []
        for r in range(tbl.rowCount()):
            t = tbl.item(r, 0).text().strip()
            p = tbl.item(r, 1).text().strip()
            if t == "" or p == "":
                continue
            try:
                temps.append(int(t))
                percents.append(int(p))
            except ValueError:
                QMessageBox.warning(self, "Invalid input",
                                    f"Row {r+1}: must be integers")
                return
        self.config.set_curve(self.config.active_profile, fan, temps, percents)
        self.client.set_curve(fan, temps, percents)

    def _poll_once(self) -> None:
        pass

    def closeEvent(self, e) -> None:
        self.config.window_width = self.width()
        self.config.window_height = self.height()
        self.config.window_x = self.x()
        self.config.window_y = self.y()
        self.config.save()
        if self.config.minimize_to_tray_on_close:
            self.hide()
            e.ignore()
        else:
            super().closeEvent(e)

    @staticmethod
    def _mode_str(m: int) -> str:
        return {0: "Auto", 1: "Manual", 2: "Game", 3: "Failsafe"}.get(m, "Unknown")
