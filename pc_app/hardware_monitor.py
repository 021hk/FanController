"""
hardware_monitor.py - Read CPU / GPU temperatures on Windows 10/11.
"""

from __future__ import annotations
import os
import sys
import time
import subprocess
import threading
import logging
log = logging.getLogger(__name__)
from typing import Optional, Tuple, Callable
from dataclasses import dataclass


@dataclass
class Temps:
    cpu: float = 0.0
    gpu: float = 0.0
    cpu_name: str = ""
    gpu_name: str = ""
    cpu_sensor_path: str = ""
    gpu_sensor_path: str = ""


class HardwareMonitor:
    def __init__(self, cpu_sensor: str = "", gpu_sensor: str = ""):
        self.cpu_sensor_filter = cpu_sensor
        self.gpu_sensor_filter = gpu_sensor
        self._computer = None
        self._initialized = False
        self._lock = threading.Lock()
        # Initialize LHM in a way that doesn't spawn console windows
        self._init_librehardware()
        if not self._initialized:
            log.warning("[monitor] LHM not available, will try nvidia-smi fallback")

    def _init_librehardware(self):
        try:
            import clr
        except ImportError:
            log.error("pythonnet not installed: pip install pythonnet")
            return
        search_paths = [
            os.path.dirname(os.path.abspath(__file__)),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "LibreHardwareMonitor"),
        ]
        dll_path = None
        for p in search_paths:
            candidate = os.path.join(p, "LibreHardwareMonitorLib.dll")
            if os.path.exists(candidate):
                dll_path = candidate
                break
        if dll_path is None:
            log.warning("LibreHardwareMonitorLib.dll not found")
            return
        try:
            # Suppress .NET stdout (CLR may print messages)
            if os.name == "nt":
                try:
                    import ctypes
                    # Disable .NET's console output
                    ctypes.windll.kernel32.SetConsoleOutputCP(0)
                except Exception:
                    pass
            sys.path.insert(0, os.path.dirname(dll_path))
            clr.AddReference("LibreHardwareMonitorLib")
            from LibreHardwareMonitor import Hardware
            self._computer = Hardware.Computer(isCpuEnabled=True,
                                                isGpuEnabled=True,
                                                isMotherboardEnabled=False,
                                                isStorageEnabled=False,
                                                isBatteryEnabled=False,
                                                isMemoryEnabled=False,
                                                isNetworkEnabled=False,
                                                isControllerEnabled=False,
                                                isPsuEnabled=False)
            self._computer.Open()
            self._initialized = True
            log.info("LibreHardwareMonitor initialized")
        except Exception as e:
            log.error(f"LHM init failed: {e}")
            self._initialized = False

    def read(self) -> Temps:
        if self._initialized:
            t = self._read_lhm()
            if t.cpu > 0 or t.gpu > 0:
                return t
        return self._read_nvidia_smi()

    def _read_lhm(self) -> Temps:
        t = Temps()
        try:
            from LibreHardwareMonitor.Hardware import SensorType, HardwareType
        except Exception:
            return t
        with self._lock:
            try:
                for hw in self._computer.Hardware:
                    hw.Update()
                    name = hw.Name
                    htype = hw.HardwareType
                    if htype == HardwareType.Cpu:
                        t.cpu_name = name
                        best = self._find_best_temp(hw, self.cpu_sensor_filter)
                        if best is not None:
                            t.cpu, t.cpu_sensor_path = best
                    elif htype in (HardwareType.GpuNvidia,
                                   HardwareType.GpuAmd,
                                   HardwareType.GpuIntel):
                        t.gpu_name = name
                        best = self._find_best_temp(hw, self.gpu_sensor_filter)
                        if best is not None:
                            t.gpu, t.gpu_sensor_path = best
                    for sub in hw.SubHardware:
                        sub.Update()
                        if t.gpu == 0 and sub.HardwareType in (
                                HardwareType.GpuNvidia,
                                HardwareType.GpuAmd,
                                HardwareType.GpuIntel):
                            best = self._find_best_temp(sub, self.gpu_sensor_filter)
                            if best is not None:
                                t.gpu, t.gpu_name = best[0], name + " (sub)"
                                t.gpu_sensor_path = best[1]
            except Exception as e:
                log.warning(f"read error: {e}")
        return t

    @staticmethod
    def _find_best_temp(hw, filter_str: str = "") -> Optional[Tuple[float, str]]:
        from LibreHardwareMonitor.Hardware import SensorType
        candidates = []
        for s in hw.Sensors:
            if s.SensorType != SensorType.Temperature:
                continue
            val = s.Value
            if val is None or val <= 0:
                continue
            candidates.append((float(val), str(s.Identifier), s.Name))
        if not candidates:
            return None
        if filter_str:
            filtered = [c for c in candidates if filter_str.lower() in c[1].lower()]
            if filtered:
                candidates = filtered
        candidates.sort(key=lambda c: -c[0])
        return candidates[0][0], candidates[0][1]

    @staticmethod
    def _read_nvidia_smi() -> Temps:
        """Use nvidia-smi to read GPU temperature WITHOUT spawning a CMD window."""
        t = Temps()
        # Prepare subprocess kwargs to hide console window on Windows
        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            try:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE
                creationflags = 0x08000000  # CREATE_NO_WINDOW
            except AttributeError:
                pass

        try:
            candidates = [
                r"C:\Windows\System32\nvidia-smi.exe",
                r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
                "nvidia-smi",
            ]
            exe = None
            for c in candidates:
                if os.path.exists(c):
                    exe = c
                    break
            if exe is None:
                try:
                    out = subprocess.check_output(
                        ["where", "nvidia-smi"],
                        stderr=subprocess.DEVNULL, timeout=3,
                        startupinfo=startupinfo,
                        creationflags=creationflags,
                    ).decode().strip()
                    if out:
                        exe = out.splitlines()[0]
                except Exception:
                    pass
            if exe is None:
                return t
            out = subprocess.check_output(
                [exe, "--query-gpu=temperature.gpu,name",
                 "--format=csv,noheader,nounits"],
                stderr=subprocess.DEVNULL, timeout=4,
                startupinfo=startupinfo,
                creationflags=creationflags,
            ).decode(errors="replace").strip()
            line = out.splitlines()[0]
            temp_str, name = line.split(",", 1)
            t.gpu = float(temp_str.strip())
            t.gpu_name = name.strip()
            t.gpu_sensor_path = "nvidia-smi"
        except Exception:
            # Try WMI as last resort (also hide window)
            try:
                import wmi
                c = wmi.WMI()
                for tz in c.Win32_TemperatureProbe():
                    if tz.CurrentReading:
                        t.cpu = float(tz.CurrentReading) / 10.0
                        t.cpu_name = "WMI thermal zone"
                        break
            except Exception:
                pass
        return t

    def poll_loop(self, interval: float, callback: Callable[[Temps], None]):
        while True:
            t = self.read()
            callback(t)
            time.sleep(interval)


def is_admin() -> bool:
    if os.name != "nt":
        return os.geteuid() == 0
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def relaunch_as_admin() -> None:
    if os.name != "nt":
        return
    import ctypes
    params = " ".join(f'"{a}"' for a in sys.argv)
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    sys.exit(0)


if __name__ == "__main__":
    if os.name == "nt" and not is_admin():
        relaunch_as_admin()
    m = HardwareMonitor()
    for _ in range(5):
        t = m.read()
        log.info(f"CPU={t.cpu:.1f}C [{t.cpu_name}]  GPU={t.gpu:.1f}C [{t.gpu_name}]")
        time.sleep(2)
