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


def _get_search_paths() -> list:
    """Get all possible DLL search locations (dev + PyInstaller bundle)."""
    paths = []
    # 1. PyInstaller _MEIPASS (onedir or onefile temp extraction)
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        paths.append(meipass)
    # 2. Directory of the executable (frozen)
    if getattr(sys, 'frozen', False):
        paths.append(os.path.dirname(sys.executable))
    # 3. Directory of this script (dev mode)
    paths.append(os.path.dirname(os.path.abspath(__file__)))
    # 4. Subdirectories
    for p in list(paths):
        paths.append(os.path.join(p, "lib"))
        paths.append(os.path.join(p, "LibreHardwareMonitor"))
        paths.append(os.path.join(p, "_internal"))
    # Deduplicate
    seen = set()
    unique = []
    for p in paths:
        if p and p not in seen and os.path.isdir(p):
            seen.add(p)
            unique.append(p)
    return unique


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
        self._init_error = ""
        # Log environment info for debugging
        log.info(f"Python: {sys.version}")
        log.info(f"Frozen: {getattr(sys, 'frozen', False)}")
        log.info(f"_MEIPASS: {getattr(sys, '_MEIPASS', 'N/A')}")
        log.info(f"Search paths: {_get_search_paths()}")
        # Initialize LHM
        self._init_librehardware()
        if not self._initialized:
            log.warning(f"LHM not available ({self._init_error}), will try nvidia-smi fallback")
        else:
            log.info("LHM initialized successfully")

    def _init_librehardware(self):
        self._init_error = ""
        try:
            import clr
        except ImportError:
            self._init_error = "pythonnet not installed"
            log.error(self._init_error)
            return

        # Search for the DLL in all possible locations
        dll_path = None
        for p in _get_search_paths():
            candidate = os.path.join(p, "LibreHardwareMonitorLib.dll")
            log.info(f"  Checking: {candidate} -> exists={os.path.exists(candidate)}")
            if os.path.exists(candidate):
                dll_path = candidate
                break

        if dll_path is None:
            self._init_error = "LibreHardwareMonitorLib.dll not found in any search path"
            log.warning(self._init_error)
            return

        log.info(f"Found DLL at: {dll_path}")
        try:
            # Add DLL directory to sys.path AND use AddReferenceToFileAndPath
            dll_dir = os.path.dirname(dll_path)
            if dll_dir not in sys.path:
                sys.path.insert(0, dll_dir)

            # Try multiple ways to load the reference
            try:
                clr.AddReference("LibreHardwareMonitorLib")
            except Exception:
                log.info("AddReference by name failed, trying by file path...")
                clr.AddReferenceToFileAndPath(dll_path)

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
            log.info("LibreHardwareMonitor initialized successfully")
        except Exception as e:
            self._init_error = f"LHM init failed: {e}"
            log.error(self._init_error, exc_info=True)
            self._initialized = False

    def read(self) -> Temps:
        if self._initialized:
            t = self._read_lhm()
            if t.cpu > 0 or t.gpu > 0:
                return t
            log.debug("LHM returned 0 temps, trying nvidia-smi fallback")
        else:
            log.debug(f"LHM not initialized ({self._init_error}), using nvidia-smi")
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

        # Try nvidia-smi for GPU
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
            if exe:
                log.info(f"nvidia-smi found at: {exe}")
                out = subprocess.check_output(
                    [exe, "--query-gpu=temperature.gpu,name",
                     "--format=csv,noheader,nounits"],
                    stderr=subprocess.DEVNULL, timeout=4,
                    startupinfo=startupinfo,
                    creationflags=creationflags,
                ).decode(errors="replace").strip()
                if out:
                    line = out.splitlines()[0]
                    temp_str, name = line.split(",", 1)
                    t.gpu = float(temp_str.strip())
                    t.gpu_name = name.strip()
                    t.gpu_sensor_path = "nvidia-smi"
                    log.info(f"nvidia-smi GPU temp: {t.gpu}°C ({t.gpu_name})")
        except Exception as e:
            log.debug(f"nvidia-smi failed: {e}")

        # Try WMI for CPU temp (OpenHardwareMonitor-compatible approach)
        if t.cpu == 0:
            try:
                t.cpu = HardwareMonitor._read_wmi_cpu_temp()
                if t.cpu > 0:
                    log.info(f"WMI CPU temp: {t.cpu}°C")
            except Exception as e:
                log.debug(f"WMI CPU temp failed: {e}")

        return t

    @staticmethod
    def _read_wmi_cpu_temp() -> float:
        """Read CPU temperature from WMI MSAcpi_ThermalZoneTemperature.
        Note: This only works on some systems and may return 0."""
        if os.name != "nt":
            return 0.0
        try:
            import ctypes
            import struct
            # Use WMI via subprocess to avoid pywin32 dependency issues
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            creationflags = 0x08000000

            # PowerShell query for CPU temp via WMI
            ps_cmd = (
                "(Get-CimInstance -Namespace root/wmi -ClassName "
                "MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue | "
                "Select-Object -First 1).CurrentTemperature"
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                stderr=subprocess.DEVNULL, timeout=5,
                startupinfo=startupinfo,
                creationflags=creationflags,
            ).decode(errors="replace").strip()
            if out and out.isdigit():
                # WMI returns temp in tenths of Kelvin
                temp_k = int(out) / 10.0
                temp_c = temp_k - 273.15
                if 0 < temp_c < 150:
                    return temp_c
        except Exception as e:
            log.debug(f"WMI thermal zone failed: {e}")
        return 0.0

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
