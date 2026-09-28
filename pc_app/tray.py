"""
tray.py - System tray icon + right-click menu.
"""

from __future__ import annotations
import threading
import logging
from typing import Callable, Optional

from PIL import Image, ImageDraw

log = logging.getLogger(__name__)


def make_icon(game_mode: bool = False, state: str = "ok") -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if state == "ok":
        color = (60, 200, 120, 255)
    elif state == "warn":
        color = (240, 200, 60, 255)
    else:
        color = (230, 80, 80, 255)
    d.ellipse([4, 4, 60, 60], fill=color, outline=(20, 20, 20, 255), width=2)
    blade = (255, 255, 255, 230)
    d.pieslice([14, 14, 50, 50], 0,   90, fill=blade)
    d.pieslice([14, 14, 50, 50], 90, 180, fill=blade)
    d.pieslice([14, 14, 50, 50], 180, 270, fill=blade)
    d.pieslice([14, 14, 50, 50], 270, 360, fill=blade)
    d.ellipse([26, 26, 38, 38], fill=color, outline=(20, 20, 20, 255))
    if game_mode:
        d.ellipse([36, 36, 62, 62], fill=(220, 30, 30, 255),
                  outline=(255, 255, 255, 255), width=2)
        try:
            from PIL import ImageFont
            font = ImageFont.truetype("arial.ttf", 22)
        except Exception:
            font = ImageFont.load_default()
        bbox = d.textbbox((0, 0), "G", font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        d.text((49 - w // 2, 49 - h // 2), "G", fill=(255, 255, 255, 255), font=font)
    return img


class TrayController:
    def __init__(self,
                 on_show_gui: Callable[[], None],
                 on_game_mode: Callable[[bool], None],
                 on_set_profile: Callable[[int], None],
                 on_set_fan: Callable[[str, int], None],
                 on_quit: Callable[[], None]):
        self._on_show_gui = on_show_gui
        self._on_game_mode = on_game_mode
        self._on_set_profile = on_set_profile
        self._on_set_fan = on_set_fan
        self._on_quit = on_quit
        self._game_mode = False
        self._state = "ok"
        self._icon = None

    def update_icon(self, game_mode: bool, state: str = "ok") -> None:
        self._game_mode = game_mode
        self._state = state
        if self._icon:
            try:
                self._icon.icon = make_icon(game_mode, state)
            except Exception as e:
                log.warning(f"icon update failed: {e}")

    def start(self) -> None:
        import pystray
        self._icon = pystray.Icon(
            "FanController",
            make_icon(False, "ok"),
            "Fan Controller",
            menu=self._build_menu(),
        )
        threading.Thread(target=self._icon.run, daemon=True).start()

    def stop(self) -> None:
        if self._icon:
            try: self._icon.stop()
            except: pass

    def _build_menu(self):
        import pystray
        from profiles import PROFILES

        profile_items = [
            pystray.MenuItem(
                p.name,
                lambda _, _pid=p.id: self._on_set_profile(_pid),
                radio=True,
                checked=lambda _, _pid=p.id: False
            ) for p in PROFILES
        ]

        return pystray.Menu(
            pystray.MenuItem("Show window", self._on_show_gui, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Game Mode",
                lambda _: self._on_game_mode(not self._game_mode),
                checked=lambda _: self._game_mode
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Profiles", pystray.Menu(*profile_items)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("CPU Fan", pystray.Menu(
                pystray.MenuItem("100%", lambda _: self._on_set_fan("cpu", 100)),
                pystray.MenuItem("75%",  lambda _: self._on_set_fan("cpu", 75)),
                pystray.MenuItem("50%",  lambda _: self._on_set_fan("cpu", 50)),
                pystray.MenuItem("Auto", lambda _: self._on_set_fan("cpu", 0)),
            )),
            pystray.MenuItem("GPU Fan", pystray.Menu(
                pystray.MenuItem("100%", lambda _: self._on_set_fan("gpu", 100)),
                pystray.MenuItem("75%",  lambda _: self._on_set_fan("gpu", 75)),
                pystray.MenuItem("50%",  lambda _: self._on_set_fan("gpu", 50)),
                pystray.MenuItem("Auto", lambda _: self._on_set_fan("gpu", 0)),
            )),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit),
        )
