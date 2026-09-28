"""
main.py - Entry point for the ESP8266 Fan Controller PC app.
"""

from __future__ import annotations
import sys
import os
import time
import signal
import logging
import threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("main")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def ensure_admin():
    if os.name != "nt":
        return
    try:
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin():
            return
    except Exception:
        return
    log.info("Requesting admin privileges for hardware sensor access...")
    params = " ".join(f'"{a}"' for a in sys.argv)
    import ctypes
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    sys.exit(0)


def main():
    ensure_admin()

    from config import Config
    from hardware_monitor import HardwareMonitor
    from esp_client import ESPClient, ConnState
    from profiles import push_all_curves, get_profile
    from tray import TrayController
    from hotkey import HotkeyManager

    config = Config.load()
    log.info(f"Config loaded from {Config.CONFIG_FILE}")

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

    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
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
        client.set_profile(pid)
        push_all_curves(client, config)

    def set_fan(fan: str, percent: int):
        mode = "auto" if percent == 0 else "manual"
        log.info(f"Fan {fan} -> {percent}% ({mode})")
        client.set_fan(fan, percent, mode)

    def show_gui():
        nonlocal gui
        if gui is None:
            from gui import FanControllerGUI
            gui = FanControllerGUI(config, client,
                                   toggle_game_mode, set_profile, set_fan)
        gui.show()
        gui.raise_()

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
    set_profile(config.active_profile)

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
        hk.stop()
        tray.stop()
        client.stop()
        app.quit()
    signal.signal(signal.SIGINT, shutdown)
    try:
        app.exec()
    finally:
        shutdown()


if __name__ == "__main__":
    main()
