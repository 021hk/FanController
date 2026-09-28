"""
hardware_monitor.py - Read CPU / GPU temperatures on Windows 10/11.

Strategy (no LHM.exe, no admin requirement):
  1. nvidia-smi.exe for NVIDIA GPU temp (no admin needed)
  2. WMI MSAcpi_ThermalZoneTemperature for CPU (works on most systems, no admin)
  3. OpenHardwareMonitor / LibreHardwareMonitor WMI namespace (if user has it
     installed and running - exposes temps to root/OpenHardwareMonitor or
     root/LibreHardwareMonitor)

For CPU, we read ALL available temperature sensors and pick the HIGHEST
(which represents the hottest core - "Core Max" / "Tctl" / "Package").
"""

from __future__ import annotations
import os
import sys
import time
import subprocess
import threading
import logging
log = logging.getLogger(__name__)
from typing import Optional, Tuple, Callable, List
from dataclasses import dataclass


@dataclass
class Temps:
    cpu: float = 0.0       # Highest CPU core temperature
    gpu: float = 0.0
    cpu_name: str = ""
    gpu_name: str = ""
    cpu_sensor_path: str = ""
    gpu_sensor_path: str = ""


def _startupinfo():
    """Build a STARTUPINFO that hides any subprocess console window."""
    if os.name != "nt":
        return None
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        return si
    except AttributeError:
        return None


def _creationflags():
    """CREATE_NO_WINDOW flag to suppress console for subprocesses."""
    if os.name == "nt":
        return 0x08000000
    return 0


def _ps_query(script: str, timeout: int = 5) -> str:
    """Run a PowerShell script and return its stdout (window hidden)."""
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            stderr=subprocess.DEVNULL, timeout=timeout,
            startupinfo=_startupinfo(),
            creationflags=_creationflags(),
        )
        return out.decode(errors="replace").strip()
    except subprocess.TimeoutExpired:
        log.debug(f"PowerShell timed out: {script[:80]}")
        return ""
    except Exception as e:
        log.debug(f"PowerShell failed: {e}")
        return ""


class HardwareMonitor:
    """Reads CPU (hottest core) + GPU temps without admin requirement."""

    def __init__(self, cpu_sensor: str = "", gpu_sensor: str = ""):
        self.cpu_sensor_filter = cpu_sensor
        self.gpu_sensor_filter = gpu_sensor
        self._lock = threading.Lock()
        # Detect available sources
        self._has_nvidia_smi = self._detect_nvidia_smi()
        self._has_ohm_wmi = self._detect_ohm_wmi()  # OpenHardwareMonitor / LHM namespace

        log.info(f"Hardware monitor initialized:")
        log.info(f"  nvidia-smi: {'yes' if self._has_nvidia_smi else 'no'}")
        log.info(f"  OHM/LHM WMI: {'yes' if self._has_ohm_wmi else 'no'}")
        log.info(f"  Admin: {'yes' if self._is_admin() else 'no'}")

    @staticmethod
    def _is_admin() -> bool:
        if os.name != "nt":
            return os.geteuid() == 0
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    def _detect_nvidia_smi(self) -> bool:
        """Check if nvidia-smi.exe is available."""
        candidates = [
            r"C:\Windows\System32\nvidia-smi.exe",
            r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
        ]
        for c in candidates:
            if os.path.exists(c):
                log.info(f"nvidia-smi found: {c}")
                return True
        # Try 'where'
        out = _ps_query("(Get-Command nvidia-smi -ErrorAction SilentlyContinue).Source")
        if out and os.path.exists(out):
            log.info(f"nvidia-smi found via where: {out}")
            return True
        return False

    def _detect_ohm_wmi(self) -> bool:
        """Check if OpenHardwareMonitor or LibreHardwareMonitor WMI namespace exists."""
        # Try LibreHardwareMonitor namespace
        out = _ps_query(
            'try { (Get-CimInstance -Namespace "root/LibreHardwareMonitor" '
            '-ClassName Sensor -ErrorAction Stop | Measure-Object).Count } '
            'catch { "0" }'
        )
        if out and out != "0":
            log.info("LibreHardwareMonitor WMI namespace available")
            return True
        # Try OpenHardwareMonitor namespace
        out = _ps_query(
            'try { (Get-CimInstance -Namespace "root/OpenHardwareMonitor" '
            '-ClassName Sensor -ErrorAction Stop | Measure-Object).Count } '
            'catch { "0" }'
        )
        if out and out != "0":
            log.info("OpenHardwareMonitor WMI namespace available")
            return True
        return False

    def read(self) -> Temps:
        """Read CPU (hottest core) + GPU temperatures."""
        t = Temps()

        # 1. Try OpenHardwareMonitor / LibreHardwareMonitor WMI (most accurate)
        if self._has_ohm_wmi:
            try:
                t = self._read_ohm_wmi()
                if t.cpu > 0 or t.gpu > 0:
                    log.debug(f"OHM/LHM WMI: CPU={t.cpu:.1f}°C GPU={t.gpu:.1f}°C")
                    return t
            except Exception as e:
                log.debug(f"OHM/LHM WMI read failed: {e}")

        # 2. Fallback: nvidia-smi for GPU + WMI thermal zone for CPU
        t = self._read_fallbacks()
        log.debug(f"Fallback: CPU={t.cpu:.1f}°C GPU={t.gpu:.1f}°C")
        return t

    def _read_ohm_wmi(self) -> Temps:
        """Query OpenHardwareMonitor / LibreHardwareMonitor WMI namespace.
        Picks the HIGHEST CPU core temperature (hottest core)."""
        t = Temps()
        # Query both namespaces; LHM is preferred
        namespaces = ["root/LibreHardwareMonitor", "root/OpenHardwareMonitor"]
        cpu_temps: List[Tuple[float, str, str]] = []  # (value, name, parent)
        gpu_temps: List[Tuple[float, str, str]] = []

        for ns in namespaces:
            ps_script = (
                f'try {{ '
                f'  $sensors = Get-CimInstance -Namespace "{ns}" '
                f'    -ClassName Sensor -ErrorAction Stop | '
                f'    Where-Object {{ $_.SensorType -eq "Temperature" -and $_.Value -gt 0 }}; '
                f'  foreach ($s in $sensors) {{ '
                f'    Write-Output ($s.Value.ToString() + "|" + $s.Name + "|" + $s.Parent); '
                f'  }} '
                f'}} catch {{ }}'
            )
            out = _ps_query(ps_script, timeout=4)
            if not out:
                continue
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
                sensor_name = parts[1] if len(parts) > 1 else ""
                parent = parts[2] if len(parts) > 2 else ""
                sn_lower = sensor_name.lower()
                parent_lower = parent.lower()

                # CPU sensors: cores, package, Tctl, Tdie
                is_cpu = any(k in sn_lower for k in [
                    "cpu", "core", "package", "tdie", "tctl", "cpu package",
                    "cpu graphics"
                ]) or any(k in parent_lower for k in [
                    "cpu", "amdcpu", "intelcpu"
                ])
                # GPU sensors
                is_gpu = any(k in sn_lower for k in [
                    "gpu", "hot spot", "hotspot", "memory junction", "gpu hotspot"
                ]) or any(k in parent_lower for k in [
                    "gpu", "nvidiagpu", "amdgpu", "intelgpu"
                ])

                if is_cpu:
                    cpu_temps.append((val, sensor_name, parent))
                elif is_gpu:
                    gpu_temps.append((val, sensor_name, parent))

            if cpu_temps or gpu_temps:
                break  # Got data from this namespace, no need to try the other

        # Pick the HIGHEST temperature (hottest core for CPU, hot spot for GPU)
        if cpu_temps:
            cpu_temps.sort(key=lambda x: -x[0])
            t.cpu = cpu_temps[0][0]
            t.cpu_name = cpu_temps[0][2] or cpu_temps[0][1]
            t.cpu_sensor_path = "OHM-WMI"
            log.debug(f"CPU: picked {t.cpu:.1f}°C from {cpu_temps[0][1]} "
                      f"({len(cpu_temps)} cores available)")
        if gpu_temps:
            gpu_temps.sort(key=lambda x: -x[0])
            t.gpu = gpu_temps[0][0]
            t.gpu_name = gpu_temps[0][2] or gpu_temps[0][1]
            t.gpu_sensor_path = "OHM-WMI"

        return t

    def _read_fallbacks(self) -> Temps:
        """Fallback: nvidia-smi for GPU + WMI thermal zone for CPU."""
        t = Temps()

        # GPU via nvidia-smi (no admin needed)
        if self._has_nvidia_smi:
            try:
                out = _ps_query(
                    '& "nvidia-smi" --query-gpu=temperature.gpu,name '
                    '--format=csv,noheader,nounits'
                )
                if out:
                    line = out.splitlines()[0]
                    temp_str, name = line.split(",", 1)
                    t.gpu = float(temp_str.strip())
                    t.gpu_name = name.strip()
                    t.gpu_sensor_path = "nvidia-smi"
            except Exception as e:
                log.debug(f"nvidia-smi read failed: {e}")

        # CPU via WMI MSAcpi_ThermalZoneTemperature (no admin needed)
        if t.cpu == 0:
            out = _ps_query(
                'try { '
                '  $t = Get-CimInstance -Namespace root/wmi '
                '    -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction Stop | '
                '    Select-Object -First 1; '
                '  if ($t) { $t.CurrentTemperature } '
                '} catch { }'
            )
            if out and out.isdigit():
                # WMI returns temp in tenths of Kelvin
                temp_k = int(out) / 10.0
                temp_c = temp_k - 273.15
                if 0 < temp_c < 150:
                    t.cpu = temp_c
                    t.cpu_name = "ACPI Thermal Zone"
                    t.cpu_sensor_path = "WMI-ACPI"
                    log.debug(f"CPU: {t.cpu:.1f}°C from ACPI thermal zone")

        return t

    def poll_loop(self, interval: float, callback: Callable[[Temps], None]):
        while True:
            t = self.read()
            callback(t)
            time.sleep(interval)

    def close(self):
        """Nothing to clean up (no background processes)."""
        pass


# ============================================================
# Admin check helper (kept for compatibility)
# ============================================================
def is_admin() -> bool:
    if os.name != "nt":
        return os.geteuid() == 0
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False
