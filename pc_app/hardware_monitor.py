"""
hardware_monitor.py - Read CPU / GPU temperatures on Windows 10/11.

Strategy (most reliable):
  1. Bundle LibreHardwareMonitor.exe (the full app) with our installer
  2. Launch it as a background process at startup (it self-elevates to admin)
  3. It creates a WMI namespace "LibreHardwareMonitor" exposing all sensors
  4. We query WMI via PowerShell (no pythonnet/CLR needed!)

Fallbacks:
  - nvidia-smi.exe for NVIDIA GPUs
  - WMI MSAcpi_ThermalZoneTemperature for CPU (works on some systems)
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
    """Get all possible locations for bundled executables (dev + PyInstaller)."""
    paths = []
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        paths.append(meipass)
    if getattr(sys, 'frozen', False):
        paths.append(os.path.dirname(sys.executable))
        paths.append(os.path.join(os.path.dirname(sys.executable), "_internal"))
    paths.append(os.path.dirname(os.path.abspath(__file__)))
    for p in list(paths):
        paths.append(os.path.join(p, "lib"))
        paths.append(os.path.join(p, "LibreHardwareMonitor"))
    seen = set()
    unique = []
    for p in paths:
        if p and p not in seen and os.path.isdir(p):
            seen.add(p)
            unique.append(p)
    return unique


def _find_lhm_exe() -> Optional[str]:
    """Find LibreHardwareMonitor.exe in any of the search paths."""
    for p in _get_search_paths():
        candidate = os.path.join(p, "LibreHardwareMonitor.exe")
        if os.path.exists(candidate):
            return candidate
    return None


@dataclass
class Temps:
    cpu: float = 0.0
    gpu: float = 0.0
    cpu_name: str = ""
    gpu_name: str = ""
    cpu_sensor_path: str = ""
    gpu_sensor_path: str = ""


class HardwareMonitor:
    """Reads CPU/GPU temperatures via LibreHardwareMonitor (launched as subprocess)."""

    def __init__(self, cpu_sensor: str = "", gpu_sensor: str = ""):
        self.cpu_sensor_filter = cpu_sensor
        self.gpu_sensor_filter = gpu_sensor
        self._lhm_process: Optional[subprocess.Popen] = None
        self._initialized = False
        self._init_error = ""
        self._lock = threading.Lock()

        # Log environment info
        log.info(f"Python: {sys.version}")
        log.info(f"Frozen: {getattr(sys, 'frozen', False)}")
        log.info(f"_MEIPASS: {getattr(sys, '_MEIPASS', 'N/A')}")
        log.info(f"Search paths: {_get_search_paths()}")

        # Find and launch LibreHardwareMonitor.exe
        self._init_lhm_process()

        if self._initialized:
            log.info("LHM process launched, WMI should be available")
        else:
            log.warning(f"LHM not available ({self._init_error}), using nvidia-smi fallback")

    def _init_lhm_process(self):
        """Find and launch LibreHardwareMonitor.exe as a background process."""
        self._init_error = ""

        lhm_exe = _find_lhm_exe()
        if lhm_exe is None:
            self._init_error = "LibreHardwareMonitor.exe not found in search paths"
            log.warning(self._init_error)
            log.warning(f"Searched in: {_get_search_paths()}")
            return

        log.info(f"Found LHM at: {lhm_exe}")

        try:
            # Launch LHM.exe with hidden window (it self-elevates to admin)
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            creationflags = 0x08000000  # CREATE_NO_WINDOW

            # Start LHM.exe in background - it will:
            # 1. Self-elevate to admin (UAC prompt only first time)
            # 2. Create WMI namespace "LibreHardwareMonitor"
            # 3. Run silently (we hide its window)
            self._lhm_process = subprocess.Popen(
                [lhm_exe, "--run"],
                startupinfo=startupinfo,
                creationflags=creationflags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log.info(f"LHM process started (PID={self._lhm_process.pid})")

            # Give it a few seconds to initialize WMI
            time.sleep(3)
            self._initialized = True

        except Exception as e:
            self._init_error = f"LHM launch failed: {e}"
            log.error(self._init_error, exc_info=True)
            self._initialized = False

    def read(self) -> Temps:
        """Read CPU/GPU temps. Try LHM via WMI first, then nvidia-smi fallback."""
        t = Temps()

        if self._initialized:
            try:
                t = self._read_wmi_lhm()
                if t.cpu > 0 or t.gpu > 0:
                    log.debug(f"LHM-WMI: CPU={t.cpu:.1f}°C GPU={t.gpu:.1f}°C")
                    return t
            except Exception as e:
                log.debug(f"LHM WMI read failed: {e}")

        # Fallback: nvidia-smi for GPU, WMI thermal zone for CPU
        log.debug("Using nvidia-smi/WMI fallback")
        return self._read_nvidia_smi_and_wmi()

    def _read_wmi_lhm(self) -> Temps:
        """Query LibreHardwareMonitor WMI namespace for sensor data."""
        t = Temps()
        if os.name != "nt":
            return t

        # PowerShell script to query LHM WMI namespace
        # Returns: temp|sensor_name|hardware_name per line
        ps_script = (
            'try { '
            '  $sensors = Get-CimInstance -Namespace "root/LibreHardwareMonitor" '
            '    -ClassName Sensor -ErrorAction Stop | '
            '    Where-Object { $_.SensorType -eq "Temperature" }; '
            '  foreach ($s in $sensors) { '
            '    Write-Output ($s.Value.ToString() + "|" + $s.Name + "|" + $s.Parent); '
            '  } '
            '} catch { '
            '  Write-Output "ERROR:" + $_.Exception.Message; '
            '}'
        )

        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            creationflags = 0x08000000

            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", ps_script],
                stderr=subprocess.DEVNULL, timeout=5,
                startupinfo=startupinfo,
                creationflags=creationflags,
            ).decode(errors="replace").strip()

            if not out or out.startswith("ERROR:"):
                log.debug(f"LHM WMI not ready or error: {out[:200]}")
                return t

            cpu_temps = []
            gpu_temps = []

            for line in out.splitlines():
                line = line.strip()
                if not line or "|" not in line:
                    continue
                parts = line.split("|", 2)
                if len(parts) < 2:
                    continue
                try:
                    val = float(parts[0])
                except ValueError:
                    continue
                if val <= 0 or val > 200:
                    continue
                sensor_name = parts[1].lower() if len(parts) > 1 else ""
                hw_parent = parts[2].lower() if len(parts) > 2 else ""

                # Categorize: CPU
                if any(k in sensor_name for k in ["cpu", "core", "package", "tdie"]) or \
                   any(k in hw_parent for k in ["cpu", "amdcpu", "intelcpu"]):
                    cpu_temps.append((val, parts[1] if len(parts) > 1 else "", parts[2] if len(parts) > 2 else ""))
                # GPU
                elif any(k in sensor_name for k in ["gpu", "hot spot", "memory"]) or \
                     any(k in hw_parent for k in ["gpu", "nvidiagpu", "amdgpu", "intelgpu"]):
                    gpu_temps.append((val, parts[1] if len(parts) > 1 else "", parts[2] if len(parts) > 2 else ""))

            # Pick the highest temperature (most representative)
            if cpu_temps:
                cpu_temps.sort(key=lambda x: -x[0])
                t.cpu = cpu_temps[0][0]
                t.cpu_name = cpu_temps[0][2] if cpu_temps[0][2] else cpu_temps[0][1]
                t.cpu_sensor_path = "LHM-WMI"
            if gpu_temps:
                gpu_temps.sort(key=lambda x: -x[0])
                t.gpu = gpu_temps[0][0]
                t.gpu_name = gpu_temps[0][2] if gpu_temps[0][2] else gpu_temps[0][1]
                t.gpu_sensor_path = "LHM-WMI"

        except subprocess.TimeoutExpired:
            log.debug("PowerShell LHM query timed out")
        except Exception as e:
            log.debug(f"LHM WMI query failed: {e}")

        return t

    def _read_nvidia_smi_and_wmi(self) -> Temps:
        """Fallback: nvidia-smi for GPU + WMI thermal zone for CPU."""
        t = Temps()

        if os.name != "nt":
            return t

        startupinfo = None
        creationflags = 0
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            creationflags = 0x08000000
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
                log.info(f"nvidia-smi found: {exe}")
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
                    log.info(f"nvidia-smi GPU: {t.gpu}°C ({t.gpu_name})")
        except Exception as e:
            log.debug(f"nvidia-smi failed: {e}")

        # Try WMI MSAcpi_ThermalZoneTemperature for CPU
        if t.cpu == 0:
            t.cpu = self._read_wmi_thermal_zone(startupinfo, creationflags)
            if t.cpu > 0:
                log.info(f"WMI thermal zone CPU: {t.cpu}°C")

        return t

    @staticmethod
    def _read_wmi_thermal_zone(startupinfo=None, creationflags=0) -> float:
        """Read CPU temp from WMI MSAcpi_ThermalZoneTemperature (no admin needed)."""
        try:
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

    def close(self):
        """Terminate the LHM background process."""
        if self._lhm_process:
            try:
                self._lhm_process.terminate()
                self._lhm_process.wait(timeout=3)
                log.info("LHM process terminated")
            except Exception as e:
                log.warning(f"LHM terminate failed: {e}")
                try:
                    self._lhm_process.kill()
                except Exception:
                    pass
            self._lhm_process = None


# ============================================================
# Admin check helper
# ============================================================
def is_admin() -> bool:
    """Check if running as administrator."""
    if os.name != "nt":
        return os.geteuid() == 0
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def relaunch_as_admin() -> None:
    """Relaunch the current process as administrator (will exit current process)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        params = " ".join(f'"{a}"' for a in sys.argv)
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        sys.exit(0)
    except Exception as e:
        log.error(f"Failed to relaunch as admin: {e}")
