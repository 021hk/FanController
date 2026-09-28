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
        """Start listening for hotkey. Silently fail if keyboard lib unavailable."""
        try:
            import keyboard
        except ImportError:
            log.warning("`keyboard` not installed; hotkeys disabled")
            return
        try:
            # On Windows, keyboard library may need admin rights to work globally
            # If it fails, we just skip the hotkey - app still works via tray
            keyboard.add_hotkey(self.hotkey, self._fire, suppress=False)
            self._started = True
            log.info(f"Hotkey registered: {self.hotkey}")
        except Exception as e:
            log.warning(f"Hotkey registration failed (needs admin?): {e}")

    def stop(self) -> None:
        if not getattr(self, "_started", False):
            return
        try:
            import keyboard
            keyboard.remove_hotkey(self.hotkey)
            self._started = False
        except Exception as e:
            log.debug(f"Hotkey removal failed: {e}")

    def _fire(self) -> None:
        log.info(f"Hotkey {self.hotkey} fired")
        threading.Thread(target=self._safe_call, daemon=True).start()

    def _safe_call(self) -> None:
        try:
            self.callback()
        except Exception as e:
            log.exception(e)
