"""
esp_client.py - Communication with the ESP8266 fan controller.
"""

from __future__ import annotations
import json
import time
import threading
import logging
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger(__name__)


class ConnState(Enum):
    DISCONNECTED = 0
    WS = 1
    HTTP = 2
    USB = 3


@dataclass
class ESPStatus:
    cpu_pct: int = 0
    gpu_pct: int = 0
    cpu_temp: float = 0.0
    gpu_temp: float = 0.0
    cpu_rpm: int = 0   # NEW: RPM from tach sensor
    gpu_rpm: int = 0   # NEW: RPM from tach sensor
    cpu_mode: int = 0
    gpu_mode: int = 0
    profile: int = 1
    game: bool = False
    auto_mode: bool = True  # NEW: auto mode state
    raw: Dict[str, Any] = field(default_factory=dict)


class ESPClient:
    RECONNECT_DELAY = 3.0
    POLL_INTERVAL = 2.0
    USB_READ_TIMEOUT = 1.0

    def __init__(self,
                 esp_ip: str = "192.168.4.1",
                 ws_port: int = 81,
                 http_port: int = 80,
                 usb_port: str = "",
                 usb_baud: int = 115200,
                 use_wifi: bool = True,
                 on_status: Optional[Callable[[ESPStatus], None]] = None,
                 on_state_change: Optional[Callable[[ConnState], None]] = None):
        self.esp_ip = esp_ip
        self.ws_port = ws_port
        self.http_port = http_port
        self.usb_port = usb_port
        self.usb_baud = usb_baud
        self.use_wifi = use_wifi
        self.on_status = on_status
        self.on_state_change = on_state_change
        self._state: ConnState = ConnState.DISCONNECTED
        self._ws = None
        self._ws_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._http_session = None
        self._serial = None
        self._serial_lock = threading.Lock()
        self._last_status: Optional[ESPStatus] = None
        # Auto-reconnect flag
        self._auto_reconnect = True
        self._reconnect_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop_event.clear()
        # PRIORITY: Try USB first (more reliable, no network needed)
        log.info("Starting ESPClient - trying USB first...")
        if self._connect_usb():
            log.info("USB connected! Using USB serial mode.")
        else:
            log.info("USB not available, falling back to WiFi.")
            if self.use_wifi:
                self._start_ws_thread()
            else:
                log.warning("WiFi disabled and USB failed - no connection")
        # Start auto-reconnect watchdog
        self._reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
        self._reconnect_thread.start()

    def reconnect(self) -> None:
        """Manually trigger a reconnect."""
        log.info("Manual reconnect triggered")
        # Close existing connections
        if self._ws:
            try: self._ws.close()
            except: pass
        if self._serial:
            try: self._serial.close()
            except: pass
            self._serial = None
        self.usb_port = ""  # Force re-detection
        # Restart
        self._stop_event.set()
        time.sleep(0.5)
        self._stop_event.clear()
        if self.use_wifi:
            self._start_ws_thread()
        else:
            self._connect_usb()

    def _reconnect_loop(self):
        """Watchdog that reconnects if state is DISCONNECTED for too long.
        Tries USB first, then WiFi."""
        while not self._stop_event.is_set():
            time.sleep(5)
            if self._state == ConnState.DISCONNECTED and self._auto_reconnect:
                log.info("Auto-reconnect: trying USB first...")
                try:
                    if self._connect_usb():
                        log.info("Auto-reconnect: USB connected!")
                        continue
                except Exception as e:
                    log.debug(f"Auto-reconnect USB failed: {e}")
                # If USB failed, try WiFi
                if self.use_wifi:
                    log.info("Auto-reconnect: trying WiFi...")
                    try:
                        self._start_ws_thread()
                    except Exception as e:
                        log.debug(f"Auto-reconnect WiFi failed: {e}")

    def stop(self) -> None:
        self._stop_event.set()
        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=2)
        if self._ws:
            try: self._ws.close()
            except: pass
        if self._http_session:
            try: self._http_session.close()
            except: pass
        if self._serial:
            try: self._serial.close()
            except: pass
        self._set_state(ConnState.DISCONNECTED)

    @property
    def state(self) -> ConnState:
        return self._state

    @property
    def last_status(self) -> Optional[ESPStatus]:
        return self._last_status

    def _start_ws_thread(self) -> None:
        self._ws_thread = threading.Thread(target=self._ws_loop, daemon=True)
        self._ws_thread.start()

    def _ws_loop(self) -> None:
        try:
            import websocket
        except ImportError:
            log.error("websocket-client not installed; using HTTP fallback")
            self._http_fallback_loop()
            return
        url = f"ws://{self.esp_ip}:{self.ws_port}/"
        while not self._stop_event.is_set():
            try:
                self._ws = websocket.WebSocketApp(
                    url,
                    on_open=self._ws_on_open,
                    on_message=self._ws_on_message,
                    on_error=self._ws_on_error,
                    on_close=self._ws_on_close,
                )
                self._ws.run_forever(ping_interval=10, ping_timeout=5)
            except Exception as e:
                log.warning(f"WS exception: {e}")
            self._set_state(ConnState.DISCONNECTED)
            if self._stop_event.is_set():
                return
            if not self._try_http_then_usb():
                self._stop_event.wait(self.RECONNECT_DELAY)

    def _ws_on_open(self, ws):
        log.info(f"WS connected to {self.esp_ip}")
        self._set_state(ConnState.WS)

    def _ws_on_message(self, ws, data: str):
        try:
            msg = json.loads(data)
        except Exception:
            return
        if msg.get("type") == "status":
            self._update_status(msg)

    def _ws_on_error(self, ws, error):
        log.warning(f"WS error: {error}")

    def _ws_on_close(self, ws, code, reason):
        log.info(f"WS closed: code={code} reason={reason}")

    def _try_http_then_usb(self) -> bool:
        if self._http_poll_once():
            self._http_fallback_loop()
            return True
        if self._connect_usb():
            self._set_state(ConnState.USB)
            return True
        return False

    def _http_fallback_loop(self) -> None:
        if self._http_session is None:
            try:
                import requests
                self._http_session = requests.Session()
            except ImportError:
                log.error("requests not installed; cannot use HTTP")
                return
        self._set_state(ConnState.HTTP)
        while not self._stop_event.is_set():
            if not self._http_poll_once():
                break
            self._stop_event.wait(self.POLL_INTERVAL)
        self._set_state(ConnState.DISCONNECTED)

    def _http_poll_once(self) -> bool:
        if not self._http_session:
            return False
        try:
            r = self._http_session.get(
                f"http://{self.esp_ip}:{self.http_port}/status",
                timeout=2)
            if r.status_code == 200:
                self._update_status(r.json())
                return True
        except Exception as e:
            log.debug(f"HTTP poll failed: {e}")
        return False

    def _connect_usb(self) -> bool:
        if not self.usb_port:
            self.usb_port = self._auto_detect_port()
            if not self.usb_port:
                log.warning("No USB serial port detected")
                log.warning("If ESP8266 is connected via USB:")
                log.warning("  1. Close Arduino IDE and Serial Monitor (they lock the port)")
                log.warning("  2. Check Device Manager > Ports (COM & LPT)")
                log.warning("  3. Look for 'USB-SERIAL CH340' or similar")
                log.warning("  4. Note the COM port number (e.g. COM3)")
                log.warning("  5. Set it in config or pass --port COM3")
                return False

        log.info(f"Trying USB serial port: {self.usb_port}")

        try:
            import serial
            with self._serial_lock:
                if self._serial is None:
                    # Try to open with exclusive access
                    self._serial = serial.Serial(
                        self.usb_port,
                        self.usb_baud,
                        timeout=1,
                        write_timeout=2,
                        exclusive=True  # Prevent other apps from using it
                    )
                    # Test connection by sending a status request
                    self._serial.write(b'{"cmd":"status"}\n')
                    time.sleep(0.5)
            log.info(f"USB serial opened: {self.usb_port} @ {self.usb_baud} baud")
            self._set_state(ConnState.USB)
            # Start USB read loop
            threading.Thread(target=self._usb_read_loop, daemon=True).start()
            return True
        except Exception as e:
            err_str = str(e)
            log.error(f"USB open failed: {e}")
            if "PermissionError" in err_str or "Access is denied" in err_str:
                log.error(">>> PORT IS LOCKED BY ANOTHER APPLICATION <<<")
                log.error("Common causes:")
                log.error("  - Arduino IDE Serial Monitor is open")
                log.error("  - Another serial terminal (PuTTY, TeraTerm) is using the port")
                log.error("  - The port is being used for programming")
                log.error("Solution: Close all serial applications, then restart FanController")
            elif "FileNotFoundError" in err_str:
                log.error(">>> PORT DOES NOT EXIST <<<")
                log.error("The COM port may have changed. Try re-plugging the ESP8266.")
            elif "cannot configure" in err_str.lower():
                log.error(">>> CANNOT CONFIGURE PORT <<<")
                log.error("This usually means:")
                log.error("  - The port is in use by another application")
                log.error("  - The CH340 driver needs reinstallation")
                log.error("  - The USB cable is data-only (some cables are power-only)")
            # Clear usb_port so we re-detect next time
            self.usb_port = ""
            return False

    @staticmethod
    def _auto_detect_port() -> str:
        try:
            from serial.tools import list_ports
            for p in list_ports.comports():
                if p.vid in (0x1A86, 0x10C4, 0x1D50):
                    return p.device
            for p in list_ports.comports():
                return p.device
        except Exception:
            pass
        return ""

    def _usb_read_loop(self) -> None:
        self._set_state(ConnState.USB)
        while not self._stop_event.is_set():
            try:
                line = self._serial.readline().decode(errors="replace").strip()
                if line and line.startswith("{"):
                    msg = json.loads(line)
                    if msg.get("type") == "status":
                        self._update_status(msg)
            except Exception as e:
                log.warning(f"USB read error: {e}")
                self._set_state(ConnState.DISCONNECTED)
                return

    def _update_status(self, msg: Dict[str, Any]) -> None:
        s = ESPStatus(
            cpu_pct=int(msg.get("cpu_pct", 0)),
            gpu_pct=int(msg.get("gpu_pct", 0)),
            cpu_temp=float(msg.get("cpu_temp", 0)),
            gpu_temp=float(msg.get("gpu_temp", 0)),
            cpu_rpm=int(msg.get("cpu_rpm", 0)),
            gpu_rpm=int(msg.get("gpu_rpm", 0)),
            cpu_mode=int(msg.get("cpu_mode", 0)),
            gpu_mode=int(msg.get("gpu_mode", 0)),
            profile=int(msg.get("profile", 1)),
            game=bool(msg.get("game", False)),
            auto_mode=bool(msg.get("auto", True)),
            raw=msg,
        )
        self._last_status = s
        if self.on_status:
            try: self.on_status(s)
            except Exception as e: log.exception(e)

    def _set_state(self, state: ConnState) -> None:
        if state == self._state:
            return
        log.info(f"ConnState: {self._state.name} -> {state.name}")
        self._state = state
        if self.on_state_change:
            try: self.on_state_change(state)
            except Exception as e: log.exception(e)

    def send_temps(self, cpu_temp: float, gpu_temp: float) -> bool:
        cmd = {"cmd": "temps", "cpu": int(cpu_temp), "gpu": int(gpu_temp)}
        return self._send(cmd)

    def set_fan(self, fan: str, percent: int, mode: str = "manual") -> bool:
        cmd = {"cmd": "set", "fan": fan, "percent": int(percent), "mode": mode}
        return self._send(cmd)

    def set_game_mode(self, on: bool) -> bool:
        cmd = {"cmd": "game", "on": bool(on)}
        ok = self._send(cmd)
        if ok:
            self._update_status({"game": on, "cpu_pct": 100, "gpu_pct": 100,
                                  "cpu_mode": 2, "gpu_mode": 2,
                                  "cpu_temp": 0, "gpu_temp": 0,
                                  "profile": 3, "type": "status",
                                  **(self._last_status.raw if self._last_status else {})})
        return ok

    def set_profile(self, profile_id: int) -> bool:
        cmd = {"cmd": "profile", "id": int(profile_id)}
        return self._send(cmd)

    def set_curve(self, fan: str, temps: list, percents: list) -> bool:
        cmd = {"cmd": "curve", "fan": fan, "temps": temps, "percents": percents}
        return self._send(cmd)

    def request_status(self) -> bool:
        return self._send({"cmd": "status"})

    def _send(self, cmd: Dict[str, Any]) -> bool:
        msg = json.dumps(cmd)
        if self._state == ConnState.WS and self._ws:
            try:
                self._ws.send(msg)
                return True
            except Exception as e:
                log.warning(f"WS send failed: {e}")
        if self._state == ConnState.HTTP and self._http_session:
            try:
                if cmd["cmd"] == "set":
                    r = self._http_session.get(
                        f"http://{self.esp_ip}:{self.http_port}/set",
                        params={"fan": cmd["fan"], "percent": cmd["percent"],
                                "mode": cmd["mode"]},
                        timeout=2)
                    return r.status_code == 200
            except Exception as e:
                log.warning(f"HTTP send failed: {e}")
        if self._state == ConnState.USB or (self._serial is None and self._connect_usb()):
            try:
                with self._serial_lock:
                    self._serial.write((msg + "\n").encode())
                if self._state != ConnState.USB:
                    self._set_state(ConnState.USB)
                return True
            except Exception as e:
                log.warning(f"USB send failed: {e}")
        log.warning(f"Send dropped: {cmd['cmd']}")
        return False
