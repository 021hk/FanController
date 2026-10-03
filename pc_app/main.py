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
    """Check if running as admin. Don't force-elevate - just log a warning.
    
    The app will work without admin (using nvidia-smi + WMI fallbacks),
    but for full CPU temp coverage admin is recommended.
    """
    if os.name != "nt":
        return True
    try:
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin():
            log.info("Running as Administrator (full sensor access available)")
            return True
        log.warning(
            "Not running as Administrator - CPU temps may be limited. "
            "For full coverage, right-click → Run as administrator."
        )
        return False
    except Exception:
        return False


def main():
    # Force admin - LHM sensors require admin rights
    if not ensure_admin():
        log.warning("Could not elevate to admin. Continuing with limited functionality.")

    # CRITICAL: Catch ALL exceptions and show them in a dialog
    # so the app doesn't silently crash
    try:
        from config import Config, CONFIG_FILE
        log.info(f"Config loaded from {CONFIG_FILE}")

        from PyQt6.QtWidgets import QApplication, QMessageBox
        from PyQt6.QtGui import QFont
        app = QApplication(sys.argv)
        font = QFont("Tahoma", 10)
        app.setFont(font)
        app.setQuitOnLastWindowClosed(False)

        # Show a startup dialog so user knows app is loading
        log.info("=== Application starting ===")

        from hardware_monitor import HardwareMonitor
        from esp_client import ESPClient, ConnState
        from profiles import push_all_curves, get_profile
        from tray import TrayController
        from hotkey import HotkeyManager

        config = Config.load()
        log.info(f"Config: esp_ip={config.esp_ip}")

        # Create hardware monitor with try/except
        try:
            monitor = HardwareMonitor(
                cpu_sensor=config.cpu_sensor,
                gpu_sensor=config.gpu_sensor,
            )
        except Exception as e:
            log.exception("HardwareMonitor init failed")
            monitor = None

        # Create ESP client
        try:
            client = ESPClient(
                esp_ip=config.esp_ip,
                ws_port=config.ws_port,
                http_port=config.http_port,
                usb_port=config.usb_port,
                usb_baud=config.usb_baud,
                use_wifi=config.use_wifi,
            )
        except Exception as e:
            log.exception("ESPClient init failed")
            QMessageBox.critical(None, "خطا", f"ESPClient init failed:\n{e}")
            return

        gui = None
        game_mode_state = {"on": False}

        def toggle_game_mode(on: bool):
            log.info(f"Game Mode -> {on}")
            game_mode_state["on"] = on
            try:
                if client.set_game_mode(on):
                    if tray:
                        tray.update_icon(game_mode=on, state="ok")
            except Exception as e:
                log.warning(f"set_game_mode failed: {e}")

        def set_profile(pid: int):
            log.info(f"Profile -> {pid}")
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
                    log.info("Creating FanControllerGUI...")
                    gui = FanControllerGUI(config, client,
                                           toggle_game_mode, set_profile, set_fan)
                    log.info("GUI created, setting hardware monitor...")
                    if monitor:
                        gui.set_hardware_monitor(monitor)
                    log.info("GUI ready, showing...")
                gui.show()
                gui.raise_()
                gui.activateWindow()
                log.info("GUI shown")
            except Exception as e:
                log.exception(f"GUI failed to show: {e}")
                QMessageBox.critical(None, "خطا در اجرای برنامه",
                                      f"امکان نمایش پنجره وجود ندارد:\n\n{e}\n\n"
                                      f"لطفاً لاگ برنامه را بررسی کنید:\n"
                                      f"%APPDATA%\\FanController\\app.log")

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

        # Show GUI immediately
        show_gui()

        stop_event = threading.Event()

        def poll_loop():
            last_send = 0.0
            while not stop_event.is_set():
                if monitor:
                    try:
                        t = monitor.read()
                        now = time.time()
                        if now - last_send >= config.poll_interval_sec:
                            if t.gpu >= config.gpu_boost_temp and not game_mode_state["on"]:
                                try: client.set_fan("gpu", config.gpu_boost_percent, "manual")
                                except: pass
                            elif t.cpu >= config.cpu_boost_temp and not game_mode_state["on"]:
                                try: client.set_fan("cpu", 100, "manual")
                                except: pass
                            elif not game_mode_state["on"]:
                                try: client.set_fan("cpu", 0, "auto")
                                except: pass
                                try: client.set_fan("gpu", 0, "auto")
                                except: pass
                            try: client.send_temps(t.cpu, t.gpu)
                            except: pass
                            last_send = now
                    except Exception as e:
                        log.debug(f"Poll error: {e}")
                stop_event.wait(0.5)

        poll_thread = threading.Thread(target=poll_loop, daemon=True)
        poll_thread.start()

        log.info("=== Fan Controller started successfully ===")

        def shutdown(*_):
            log.info("Shutting down...")
            stop_event.set()
            for closer in [hk, tray, client, monitor]:
                try: closer.stop() if hasattr(closer, 'stop') else closer.close()
                except: pass
            app.quit()

        signal.signal(signal.SIGINT, shutdown)
        try:
            app.exec()
        finally:
            shutdown()

    except Exception as e:
        # LAST RESORT: catch any uncaught exception and show it
        log.exception("FATAL ERROR in main()")
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            app = QApplication(sys.argv)
            QMessageBox.critical(None, "خطای بحرانی",
                f"برنامه با خطا مواجه شد:\n\n{e}\n\n"
                f"لاگ کامل در:\n%APPDATA%\\FanController\\app.log")
            app.exec()
        except:
            # If even Qt fails, show in console
            import traceback
            traceback.print_exc()
            input("Press Enter to exit...")


if __name__ == "__main__":
    main()
