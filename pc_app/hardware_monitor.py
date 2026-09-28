"""
hardware_monitor.py - Read CPU / GPU temperatures on Windows 10/11.
"""

from __future__ import annotations
import os
import sys
import time
import subprocess
import threading
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
        self._init_librehardware()
        if not self._initialized:
            print("[monitor] LHM not available, will try nvidia-smi fallback")

    def _init_librehardware(self):
        try:
            import clr
        except ImportError:
            print("[monitor] pythonnet not installed: pip install pythonnet")
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
            print("[monitor] LibreHardwareMonitorLib.dll not found")
            return
        try:
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
            print("[monitor] LibreHardwareMonitor initialized")
        except Exception as e:
            print(f"[monitor] LHM init failed: {e}")
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
                print(f"[monitor] read error: {e}")
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
        t = Temps()
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
                    out = subprocess.check_output(["where", "nvidia-smi"],
                                                  stderr=subprocess.DEVNULL,
                                                  timeout=3).decode().strip()
                    if out:
                        exe = out.splitlines()[0]
                except Exception:
                    pass
            if exe is None:
                return t
            out = subprocess.check_output(
                [exe, "--query-gpu=temperature.gpu,name",
                 "--format=csv,noheader,nounits"],
                stderr=subprocess.DEVNULL, timeout=4
            ).decode(errors="replace").strip()
            line = out.splitlines()[0]
            temp_str, name = line.split(",", 1)
            t.gpu = float(temp_str.strip())
            t.gpu_name = name.strip()
            t.gpu_sensor_path = "nvidia-smi"
        except Exception:
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
        print(f"CPU={t.cpu:.1f}C [{t.cpu_name}]  GPU={t.gpu:.1f}C [{t.gpu_name}]")
        time.sleep(2)
