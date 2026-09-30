"""
settings_dialog.py - Settings dialog for fan curve configuration.

Allows user to define custom rules:
  - When CPU temp reaches X°C → CPU fan percent should be Y%
  - When GPU temp reaches X°C → GPU fan percent should be Y%

These rules override the auto curve (when triggered).
Curve is sent to ESP8266 firmware on apply.
"""

from __future__ import annotations
import logging
from typing import List, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPen, QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QGroupBox, QFrame, QWidget
)

log = logging.getLogger(__name__)

# Theme colors (must match gui.py)
PRIMARY_COLOR = "#00d2ff"
BG_COLOR = "#121212"
CARD_BG = "#1e1e1e"
TEXT_COLOR = "#ffffff"
TEXT_MUTED = "#aaaaaa"
SUCCESS_COLOR = "#4caf50"
DANGER_COLOR = "#ff5252"


SETTINGS_QSS = f"""
QDialog {{
    background-color: {BG_COLOR};
    color: {TEXT_COLOR};
    font-family: Tahoma, 'Segoe UI', Arial, sans-serif;
}}
QLabel {{
    background: transparent;
    color: {TEXT_COLOR};
}}
QLabel#Title {{
    color: {PRIMARY_COLOR};
    font-size: 18px;
    font-weight: 700;
}}
QLabel#Subtitle {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}
QGroupBox {{
    background-color: {CARD_BG};
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    margin-top: 14px;
    padding-top: 14px;
    color: {TEXT_COLOR};
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: {PRIMARY_COLOR};
}}
QTableWidget {{
    background-color: rgba(255,255,255,0.03);
    color: {TEXT_COLOR};
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 8px;
    gridline-color: rgba(255,255,255,0.05);
    selection-background-color: {PRIMARY_COLOR};
    selection-color: {BG_COLOR};
}}
QHeaderView::section {{
    background-color: rgba(255,255,255,0.06);
    color: {PRIMARY_COLOR};
    border: none;
    padding: 8px;
    font-weight: 600;
}}
QTableWidget::item {{
    padding: 6px 10px;
}}
QPushButton {{
    background-color: rgba(255,255,255,0.06);
    color: {TEXT_COLOR};
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 12px;
}}
QPushButton:hover {{
    background-color: rgba(255,255,255,0.12);
}}
QPushButton#Primary {{
    background-color: {PRIMARY_COLOR};
    color: {BG_COLOR};
    border: none;
    font-weight: bold;
}}
QPushButton#Primary:hover {{
    background-color: #00b8d9;
}}
QPushButton#Danger {{
    background-color: rgba(255,82,82,0.15);
    color: {DANGER_COLOR};
    border: 1px solid rgba(255,82,82,0.3);
}}
QPushButton#Danger:hover {{
    background-color: rgba(255,82,82,0.25);
}}
"""


class SettingsDialog(QDialog):
    """Modal dialog to edit fan curves (temp → fan %)."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("⚙️ تنظیمات منحنی دما-فن")
        self.setMinimumWidth(620)
        self.setMinimumHeight(560)
        self.setStyleSheet(SETTINGS_QSS)
        self._build_ui()
        self._load_curves()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header
        title = QLabel("⚙️ تنظیمات منحنی دما-فن")
        title.setObjectName("Title")
        layout.addWidget(title)

        subtitle = QLabel(
            "تعیین سرعت فن بر اساس دما — هر ردیف یه نقطه روی منحنی است\n"
            "مثال: اگه CPU به ۷۰°C برسه، فن CPU باید ۸۰٪ بشه"
        )
        subtitle.setObjectName("Subtitle")
        layout.addWidget(subtitle)

        # CPU curve table
        cpu_group = QGroupBox("🔄 فن CPU (مبتنی بر دمای CPU)")
        cpu_layout = QVBoxLayout(cpu_group)
        self.tbl_cpu = self._make_curve_table()
        cpu_layout.addWidget(self.tbl_cpu)
        cpu_btns = QHBoxLayout()
        btn_add_cpu = QPushButton("+ افزودن ردیف")
        btn_add_cpu.clicked.connect(lambda: self._add_row(self.tbl_cpu))
        cpu_btns.addWidget(btn_add_cpu)
        btn_del_cpu = QPushButton("− حذف ردیف")
        btn_del_cpu.setObjectName("Danger")
        btn_del_cpu.clicked.connect(lambda: self._del_row(self.tbl_cpu))
        cpu_btns.addWidget(btn_del_cpu)
        cpu_btns.addStretch()
        cpu_layout.addLayout(cpu_btns)
        layout.addWidget(cpu_group)

        # GPU curve table
        gpu_group = QGroupBox("🎯 فن GPU (مبتنی بر دمای GPU)")
        gpu_layout = QVBoxLayout(gpu_group)
        self.tbl_gpu = self._make_curve_table()
        gpu_layout.addWidget(self.tbl_gpu)
        gpu_btns = QHBoxLayout()
        btn_add_gpu = QPushButton("+ افزودن ردیف")
        btn_add_gpu.clicked.connect(lambda: self._add_row(self.tbl_gpu))
        gpu_btns.addWidget(btn_add_gpu)
        btn_del_gpu = QPushButton("− حذف ردیف")
        btn_del_gpu.setObjectName("Danger")
        btn_del_gpu.clicked.connect(lambda: self._del_row(self.tbl_gpu))
        gpu_btns.addWidget(btn_del_gpu)
        gpu_btns.addStretch()
        gpu_layout.addLayout(gpu_btns)
        layout.addWidget(gpu_group)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("انصراف")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("✓ ذخیره و اعمال")
        btn_save.setObjectName("Primary")
        btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(btn_save)

        layout.addLayout(btn_row)

    def _make_curve_table(self) -> QTableWidget:
        tbl = QTableWidget(0, 2)
        tbl.setHorizontalHeaderLabels(["دماتر (°C)", "سرعت فن (%)"])
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tbl.verticalHeader().setVisible(False)
        tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        return tbl

    def _add_row(self, tbl: QTableWidget, temp: int = 50, pct: int = 50):
        row = tbl.rowCount()
        tbl.insertRow(row)
        tbl.setItem(row, 0, QTableWidgetItem(str(temp)))
        tbl.setItem(row, 1, QTableWidgetItem(str(pct)))

    def _del_row(self, tbl: QTableWidget):
        rows = {r.row() for r in tbl.selectedItems()}
        if not rows:
            if tbl.rowCount() > 0:
                tbl.removeRow(tbl.rowCount() - 1)
            return
        for r in sorted(rows, reverse=True):
            tbl.removeRow(r)

    def _load_curves(self):
        """Load current curves from config into tables."""
        try:
            temps, pcts = self.config.get_curve(self.config.active_profile, "cpu")
            for t, p in zip(temps, pcts):
                self._add_row(self.tbl_cpu, t, p)
        except Exception as e:
            log.warning(f"Load CPU curve failed: {e}")

        try:
            temps, pcts = self.config.get_curve(self.config.active_profile, "gpu")
            for t, p in zip(temps, pcts):
                self._add_row(self.tbl_gpu, t, p)
        except Exception as e:
            log.warning(f"Load GPU curve failed: {e}")

        # Ensure at least 3 rows
        if self.tbl_cpu.rowCount() < 3:
            for default in [(30, 20), (50, 40), (70, 75), (90, 100)]:
                if self.tbl_cpu.rowCount() < 4:
                    self._add_row(self.tbl_cpu, *default)
        if self.tbl_gpu.rowCount() < 3:
            for default in [(30, 20), (50, 40), (70, 75), (90, 100)]:
                if self.tbl_gpu.rowCount() < 4:
                    self._add_row(self.tbl_gpu, *default)

    def _read_table(self, tbl: QTableWidget) -> Tuple[List[int], List[int]]:
        temps: List[int] = []
        pcts: List[int] = []
        for r in range(tbl.rowCount()):
            t_item = tbl.item(r, 0)
            p_item = tbl.item(r, 1)
            if t_item is None or p_item is None:
                continue
            t_text = t_item.text().strip()
            p_text = p_item.text().strip()
            if not t_text or not p_text:
                continue
            try:
                t = int(t_text)
                p = int(p_text)
                if not (0 <= t <= 150):
                    raise ValueError(f"Temp {t} out of range")
                if not (0 <= p <= 100):
                    raise ValueError(f"Percent {p} out of range")
                temps.append(t)
                pcts.append(p)
            except ValueError as e:
                raise ValueError(f"ردیف {r+1}: {e}")
        if not temps:
            raise ValueError("هیچ ردیف معتبری وجود ندارد")
        # Sort by temperature
        paired = sorted(zip(temps, pcts))
        temps = [p[0] for p in paired]
        pcts = [p[1] for p in paired]
        return temps, pcts

    def _on_save(self):
        try:
            cpu_temps, cpu_pcts = self._read_table(self.tbl_cpu)
            gpu_temps, gpu_pcts = self._read_table(self.tbl_gpu)
        except ValueError as e:
            QMessageBox.warning(self, "خطا در ورودی", str(e))
            return

        # Save to config
        self.config.set_curve(self.config.active_profile, "cpu", cpu_temps, cpu_pcts)
        self.config.set_curve(self.config.active_profile, "gpu", gpu_temps, gpu_pcts)

        # Return curves to caller via accepted signal
        self._saved_curves = {
            "cpu": (cpu_temps, cpu_pcts),
            "gpu": (gpu_temps, gpu_pcts),
        }
        log.info(f"Curves saved: CPU={len(cpu_temps)}pts, GPU={len(gpu_temps)}pts")
        self.accept()

    def get_curves(self):
        return getattr(self, "_saved_curves", None)
