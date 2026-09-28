"""
main.py - Entry point for the ESP8266 Fan Controller PC app.
"""

from __future__ import annotations
import sys
import os
import time
import signal
import logging
import logging.handlers
import threading
from pathlib import Path

# ============================================================
# CRITICAL: Redirect stdout/stderr BEFORE any imports.
# This prevents CMD windows from flashing when subprocess calls are made
# or when libraries like pythonnet/keyboard write to stdout.
# We redirect to a log file in APPDATA so we can still debug issues.
# ============================================================
def _redirect_stdio_to_file():
    """Redirect sys.stdout/stderr to a log file - called before any other imports."""
    if sys.platform != "win32":
        return
    try:
        log_dir = Path(os.environ.get("APPDATA", str(Path.home()))) / "FanController"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "stdout.log"
        # Open in append mode with line buffering
        f = open(log_file, "a", encoding="utf-8", buffering=1)
        sys.stdout = f
        sys.stderr = f
    except Exception:
        # Fallback: discard output completely (no console window)
        try:
            sys.stdout = open(os.devnull, "w")
            sys.stderr = sys.stdout
        except Exception:
            pass

# Apply redirect FIRST
_redirect_stdio_to_file()

# Also patch subprocess on Windows to never show console windows
if sys.platform == "win32":
    import subprocess as _sp
    _orig_check_output = _sp.check_output
    _orig_Popen = _sp.Popen

    def _patched_check_output(*args, **kwargs):
        if 'startupinfo' not in kwargs or kwargs.get('startupinfo') is None:
            try:
                si = _sp.STARTUPINFO()
                si.dwFlags |= _sp.STARTF_USESHOWWINDOW
                si.wShowWindow = 0  # SW_HIDE
                kwargs['startupinfo'] = si
            except AttributeError:
                pass
        if 'creationflags' not in kwargs:
            kwargs['creationflags'] = 0x08000000  # CREATE_NO_WINDOW
        return _orig_check_output(*args, **kwargs)

    class _PatchedPopen(_orig_Popen):
        def __init__(self, *args, **kwargs):
            if kwargs.get('startupinfo') is None:
                try:
                    si = _sp.STARTUPINFO()
                    si.dwFlags |= _sp.STARTF_USESHOWWINDOW
                    si.wShowWindow = 0
                    kwargs['startupinfo'] = si
                except (AttributeError, KeyError):
                    pass
            if not kwargs.get('creationflags'):
                kwargs['creationflags'] = 0x08000000  # CREATE_NO_WINDOW
            super().__init__(*args, **kwargs)

    _sp.check_output = _patched_check_output
    _sp.Popen = _PatchedPopen

# ============================================================
# Logging setup - write to file AND console (if available)
# ============================================================
def setup_logging():
    """Configure logging to write to %APPDATA%/FanController/app.log"""
    if sys.platform == "win32":
        log_dir = Path(os.environ.get("APPDATA", str(Path.home()))) / "FanController"
    else:
        log_dir = Path.home() / ".config" / "FanController"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    # Rotating file handler (max 1MB, keep 3 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)

    # Also try console (will silently fail in --noconsole mode, which is fine)
    try:
        if sys.stdout is not None:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
            ))
            root_logger.addHandler(console_handler)
    except Exception:
        pass

    return logging.getLogger("main")

log = setup_logging()
log.info("=" * 50)
log.info("Fan Controller starting up...")
log.info("=" * 50)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def ensure_admin():
    """Force the app to run as Administrator.
    
    If not admin, relaunch elevated and exit current instance.
    This is required for LibreHardwareMonitor to access hardware sensors.
    """
    if os.name != "nt":
        return True
    try:
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin():
            log.info("Running as Administrator (sensors available)")
            return True
    except Exception:
        pass

    log.info("Not running as admin. Relaunching elevated...")
    try:
        import ctypes
        # Build command line with all original args
        params = " ".join(f'"{a}"' for a in sys.argv)
        # ShellExecuteW with "runas" verb triggers UAC prompt
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 0  # 0 = SW_HIDE
        )
        # ShellExecuteW returns > 32 on success
        if result <= 32:
            log.error(f"ShellExecuteW failed with code {result}")
            return False
        log.info("Elevated instance launched. Exiting current instance.")
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:
        log.error(f"Failed to elevate: {e}")
        return False


def main():
    # Force admin - LHM sensors require admin rights
    if not ensure_admin():
        log.warning("Could not elevate to admin. Continuing with limited functionality.")
    
    from config import Config, CONFIG_FILE
    from hardware_monitor import HardwareMonitor
    from esp_client import ESPClient, ConnState
    from profiles import push_all_curves, get_profile
    from tray import TrayController
    from hotkey import HotkeyManager

    config = Config.load()
    log.info(f"Config loaded from {CONFIG_FILE}")

    monitor = HardwareMonitor(
        cpu_sensor=config.cpu_sensor,
        gpu_sensor=config.gpu_sensor,
    )

    client = ESPClient(
        esp_ip=config.esp_ip,
        ws_port=config.ws_port,
        http_port=config.http_port,
        usb_port=config.usb_port,
        usb_baud=config.usb_baud,
        use_wifi=config.use_wifi,
    )

    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.QtGui import QFont
    app = QApplication(sys.argv)
    
    # Set Persian-friendly default font
    font = QFont("Tahoma", 10)
    app.setFont(font)
    
    app.setQuitOnLastWindowClosed(False)
    gui = None

    game_mode_state = {"on": False}

    def toggle_game_mode(on: bool):
        log.info(f"Game Mode -> {on}")
        game_mode_state["on"] = on
        if client.set_game_mode(on):
            if tray:
                tray.update_icon(game_mode=on, state="ok")
        else:
            log.warning("set_game_mode failed")

    def set_profile(pid: int):
        log.info(f"Profile -> {pid} ({get_profile(pid).name})")
        config.active_profile = pid
        config.save()
        try:
            client.set_profile(pid)
            push_all_curves(client, config)
        except Exception as e:
            log.warning(f"set_profile failed: {e}")

    def set_fan(fan: str, percent: int):
        mode = "auto" if percent == 0 else "manual"
        log.info(f"Fan {fan} -> {percent}% ({mode})")
        try:
            client.set_fan(fan, percent, mode)
        except Exception as e:
            log.warning(f"set_fan failed: {e}")

    def show_gui():
        nonlocal gui
        try:
            if gui is None:
                from gui import FanControllerGUI
                gui = FanControllerGUI(config, client,
                                       toggle_game_mode, set_profile, set_fan)
                # Pass hardware monitor to GUI so it can display local temps
                gui.set_hardware_monitor(monitor)
            gui.show()
            gui.raise_()
            gui.activateWindow()
        except Exception as e:
            log.exception(f"GUI failed to show: {e}")
            QMessageBox.critical(None, "خطا در اجرای برنامه",
                                  f"امکان نمایش پنجره وجود ندارد:\n\n{e}\n\n"
                                  f"لطفاً لاگ برنامه را بررسی کنید.")

    tray = TrayController(
        on_show_gui=show_gui,
        on_game_mode=toggle_game_mode,
        on_set_profile=set_profile,
        on_set_fan=set_fan,
        on_quit=lambda: app.quit(),
    )
    tray.start()

    hk = HotkeyManager(config.hotkey_game_mode,
                       lambda: toggle_game_mode(not game_mode_state["on"]))
    hk.start()

    client.start()
    time.sleep(1.0)
    try:
        set_profile(config.active_profile)
    except Exception as e:
        log.warning(f"Initial profile set failed: {e}")

    # Show GUI immediately on startup (don't make user click the tray icon)
    show_gui()

    stop_event = threading.Event()

    def poll_loop():
        last_send = 0.0
        while not stop_event.is_set():
            t = monitor.read()
            log.debug(f"CPU={t.cpu:.1f}C  GPU={t.gpu:.1f}C")
            now = time.time()
            if now - last_send >= config.poll_interval_sec:
                if t.gpu >= config.gpu_boost_temp and not game_mode_state["on"]:
                    client.set_fan("gpu", config.gpu_boost_percent, "manual")
                elif t.cpu >= config.cpu_boost_temp and not game_mode_state["on"]:
                    client.set_fan("cpu", 100, "manual")
                elif not game_mode_state["on"]:
                    client.set_fan("cpu", 0, "auto")
                    client.set_fan("gpu", 0, "auto")
                client.send_temps(t.cpu, t.gpu)
                last_send = now
            stop_event.wait(0.5)

    poll_thread = threading.Thread(target=poll_loop, daemon=True)
    poll_thread.start()

    log.info("Fan Controller started. Tray icon ready.")

    def shutdown(*_):
        log.info("Shutting down...")
        stop_event.set()
        try:
            hk.stop()
        except Exception:
            pass
        try:
            tray.stop()
        except Exception:
            pass
        try:
            client.stop()
        except Exception:
            pass
        try:
            monitor.close()
        except Exception:
            pass
        app.quit()
    signal.signal(signal.SIGINT, shutdown)
    try:
        app.exec()
    finally:
        shutdown()


if __name__ == "__main__":
    main()
