"""
config.py - Persistent configuration for the Fan Controller PC app.
"""

from __future__ import annotations
import json
import os
import sys
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Tuple
from pathlib import Path

log = logging.getLogger(__name__)

if sys.platform == "win32":
    APPDATA = Path(os.environ.get("APPDATA", str(Path.home())))
else:
    APPDATA = Path.home() / ".config"

CONFIG_DIR = APPDATA / "FanController"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CURVE_SILENT = {"temps": [30, 40, 50, 60, 70, 80, 90],
                        "percents": [15, 25, 35, 50, 65, 80, 95]}
DEFAULT_CURVE_BALANCED = {"temps": [30, 40, 50, 60, 70, 80, 90],
                          "percents": [20, 30, 40, 55, 70, 85, 100]}
DEFAULT_CURVE_PERFORMANCE = {"temps": [30, 40, 50, 60, 65, 70, 80],
                             "percents": [30, 45, 60, 75, 85, 95, 100]}
DEFAULT_CURVE_GAME = {"temps": [30, 40, 50, 60, 70, 80, 90],
                      "percents": [60, 70, 80, 90, 95, 100, 100]}

PROFILE_NAMES = {0: "Silent", 1: "Balanced", 2: "Performance", 3: "Game"}


@dataclass
class Config:
    # ESP8266 in AP (Hotspot) mode - default IP is 192.168.4.1
    # After connecting PC to "FanController" WiFi, ESP is at 192.168.4.1
    esp_ip: str = "192.168.4.1"
    ws_port: int = 81
    http_port: int = 80
    use_wifi: bool = True
    usb_port: str = ""
    usb_baud: int = 115200
    poll_interval_sec: float = 2.0
    gpu_boost_temp: int = 70
    gpu_boost_percent: int = 100
    cpu_boost_temp: int = 85
    active_profile: int = 1
    hotkey_game_mode: str = "ctrl+shift+g"
    autostart_with_windows: bool = False
    minimize_to_tray_on_close: bool = True
    window_width: int = 760
    window_height: int = 560
    window_x: int = 100
    window_y: int = 100
    profiles: Dict[int, Dict[str, Dict]] = field(default_factory=lambda: {
        0: {"cpu": DEFAULT_CURVE_SILENT,       "gpu": DEFAULT_CURVE_SILENT},
        1: {"cpu": DEFAULT_CURVE_BALANCED,     "gpu": DEFAULT_CURVE_BALANCED},
        2: {"cpu": DEFAULT_CURVE_PERFORMANCE,  "gpu": DEFAULT_CURVE_PERFORMANCE},
        3: {"cpu": DEFAULT_CURVE_GAME,         "gpu": DEFAULT_CURVE_GAME},
    })
    cpu_sensor: str = ""
    gpu_sensor: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        c = cls()
        for k, v in d.items():
            if hasattr(c, k):
                if k == "profiles":
                    merged = {0: {"cpu": DEFAULT_CURVE_SILENT,    "gpu": DEFAULT_CURVE_SILENT},
                              1: {"cpu": DEFAULT_CURVE_BALANCED,  "gpu": DEFAULT_CURVE_BALANCED},
                              2: {"cpu": DEFAULT_CURVE_PERFORMANCE,"gpu": DEFAULT_CURVE_PERFORMANCE},
                              3: {"cpu": DEFAULT_CURVE_GAME,      "gpu": DEFAULT_CURVE_GAME}}
                    for pid, fans in v.items():
                        pid_int = int(pid)
                        if pid_int in merged and isinstance(fans, dict):
                            for fan in ("cpu", "gpu"):
                                if fan in fans and isinstance(fans[fan], dict):
                                    merged[pid_int][fan] = fans[fan]
                    c.profiles = merged
                else:
                    setattr(c, k, v)
        return c

    def save(self) -> None:
        try:
            CONFIG_FILE.write_text(json.dumps(self.to_dict(), indent=2),
                                   encoding="utf-8")
        except Exception as e:
            log.warning(f"[config] save failed: {e}")

    @classmethod
    def load(cls) -> "Config":
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                return cls.from_dict(data)
            except Exception as e:
                log.warning(f"[config] load failed ({e}), using defaults")
        cfg = cls()
        cfg.save()
        return cfg

    def get_curve(self, profile_id: int, fan: str) -> Tuple[List[int], List[int]]:
        fan = fan.lower()
        if fan not in ("cpu", "gpu"):
            raise ValueError(f"fan must be 'cpu' or 'gpu', got {fan}")
        curve = self.profiles.get(profile_id, {}).get(fan, DEFAULT_CURVE_BALANCED)
        return list(curve["temps"]), list(curve["percents"])

    def set_curve(self, profile_id: int, fan: str,
                  temps: List[int], percents: List[int]) -> None:
        if fan not in ("cpu", "gpu"):
            raise ValueError(f"fan must be 'cpu' or 'gpu'")
        if profile_id not in self.profiles:
            self.profiles[profile_id] = {"cpu": DEFAULT_CURVE_BALANCED,
                                          "gpu": DEFAULT_CURVE_BALANCED}
        self.profiles[profile_id][fan] = {"temps": list(temps),
                                            "percents": list(percents)}
        self.save()
