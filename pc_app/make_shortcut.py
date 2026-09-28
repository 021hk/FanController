"""
make_shortcut.py - Creates desktop shortcuts for "Game Mode".
"""

from __future__ import annotations
import os
import sys
import argparse
import urllib.request
import urllib.parse
import json
from pathlib import Path


def esp_url(ip: str, http_port: int, path: str) -> str:
    return f"http://{ip}:{http_port}{path}"


def make_bat(bat_path: Path, ip: str, port: int,
              game_mode: bool, label: str) -> None:
    cmd = (
        f"@echo off\r\n"
        f"echo {'Activating' if game_mode else 'Disabling'} Game Mode...\r\n"
        f"curl -s \"{esp_url(ip, port, '/set?fan=gpu&percent=100&mode=game')}\" > nul\r\n"
        f"curl -s \"{esp_url(ip, port, '/set?fan=cpu&percent=100&mode=game')}\" > nul\r\n"
        f"timeout /t 1 > nul\r\n"
        f"echo Done.\r\n"
        f"exit\r\n"
    ) if game_mode else (
        f"@echo off\r\n"
        f"echo Resetting fans to Auto...\r\n"
        f"curl -s \"{esp_url(ip, port, '/set?fan=gpu&percent=0&mode=auto')}\" > nul\r\n"
        f"curl -s \"{esp_url(ip, port, '/set?fan=cpu&percent=0&mode=auto')}\" > nul\r\n"
        f"timeout /t 1 > nul\r\n"
        f"echo Done.\r\n"
        f"exit\r\n"
    )
    bat_path.write_text(cmd, encoding="ascii")
    print(f"Wrote {bat_path}")


def make_lnk(target: Path, link: Path, icon: str = "", desc: str = "") -> None:
    if os.name != "nt":
        print(f"Skipping .lnk creation on non-Windows; target={target}")
        return
    try:
        import pythoncom
        from win32com.shell import shell, shellcon
    except ImportError:
        print("pywin32 not installed, skipping .lnk creation.")
        return
    shortcut = pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink, None,
        pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink
    )
    shortcut.SetPath(str(target))
    shortcut.SetDescription(desc or target.name)
    if icon:
        shortcut.SetIconLocation(icon, 0)
    persist = shortcut.QueryInterface(pythoncom.IID_IPersistFile)
    persist.Save(str(link), True)
    print(f"Created shortcut: {link}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ip", default="192.168.4.1")
    p.add_argument("--port", type=int, default=80)
    p.add_argument("--desktop-dir",
                   default=str(Path.home() / "Desktop"))
    args = p.parse_args()

    desktop = Path(args.desktop_dir)
    if not desktop.exists():
        desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)

    bat_on  = desktop / "GameMode_ON.bat"
    bat_off = desktop / "GameMode_OFF.bat"

    make_bat(bat_on, args.ip, args.port, game_mode=True,
             label="Game Mode: ON (all fans 100%)")
    make_bat(bat_off, args.ip, args.port, game_mode=False,
             label="Game Mode: OFF (auto)")

    try:
        make_lnk(bat_on, desktop / "Game Mode ON.lnk",
                 desc="Activate Game Mode (fans 100%)")
        make_lnk(bat_off, desktop / "Game Mode OFF.lnk",
                 desc="Reset to automatic fan control")
    except Exception as e:
        print(f"LNK creation skipped: {e}")

    print("\nDone! Two shortcuts created on your desktop:")
    print(f"  - {bat_on.name}  (or 'Game Mode ON.lnk')")
    print(f"  - {bat_off.name} (or 'Game Mode OFF.lnk')")
    print(f"\nTarget: http://{args.ip}:{args.port}")
    print("Make sure ESP8266 is reachable from this PC.")


if __name__ == "__main__":
    main()
