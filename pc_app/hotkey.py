"""
hotkey.py - Global keyboard shortcut listener.
"""

from __future__ import annotations
import logging
import threading
from typing import Callable, Optional

log = logging.getLogger(__name__)


class HotkeyManager:
    def __init__(self, hotkey: str, callback: Callable[[], None]):
        self.hotkey = hotkey
        self.callback = callback
        self._listener = None

    def start(self) -> None:
        try:
            import keyboard
        except ImportError:
            log.error("`keyboard` not installed; hotkeys disabled")
            return
        try:
            keyboard.add_hotkey(self.hotkey, self._fire, suppress=False)
            log.info(f"Hotkey registered: {self.hotkey}")
        except Exception as e:
            log.error(f"Hotkey registration failed: {e}")

    def stop(self) -> None:
        try:
            import keyboard
            keyboard.remove_hotkey(self.hotkey)
        except Exception:
            pass

    def _fire(self) -> None:
        log.info(f"Hotkey {self.hotkey} fired")
        threading.Thread(target=self._safe_call, daemon=True).start()

    def _safe_call(self) -> None:
        try:
            self.callback()
        except Exception as e:
            log.exception(e)
