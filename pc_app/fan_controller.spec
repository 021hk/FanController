# -*- mode: python ; coding: utf-8 -*-
"""
fan_controller.spec - PyInstaller build configuration.

Builds the ESP8266 Fan Controller as a standalone Windows .exe
with all dependencies bundled (PyQt6, pystray, websocket-client, etc.).

Usage:
    python -m PyInstaller fan_controller.spec --noconfirm --clean

Output:
    dist/FanController/FanController.exe
    dist/FanController/_internal/  (DLLs, Qt plugins, etc.)
"""

import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Collect all submodules for libraries that use dynamic imports
hiddenimports = []
hiddenimports += collect_submodules('PyQt6')
hiddenimports += collect_submodules('pystray')
hiddenimports += collect_submodules('PIL')
hiddenimports += ['keyboard._winkeyboard', 'keyboard._nixkeyboard']
hiddenimports += ['serial.tools.list_ports', 'serial.serialcli']
hiddenimports += ['LibreHardwareMonitor', 'LibreHardwareMonitor.Hardware']
hiddenimports += ['clr']

# Include LibreHardwareMonitor DLLs if present
datas = []
for dll in ['LibreHardwareMonitorLib.dll',
            'LibreHardwareMonitorLib.dll.config',
            'HidSharp.dll']:
    if os.path.exists(dll):
        datas.append((dll, '.'))

# Include LHM resources folder if present
if os.path.isdir('LibreHardwareMonitorLib.resources'):
    for root, dirs, files in os.walk('LibreHardwareMonitorLib.resources'):
        for f in files:
            src = os.path.join(root, f)
            dst = os.path.relpath(root, '.')
            datas.append((src, dst))

# PyQt6 plugins
datas += collect_data_files('PyQt6')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'test', 'unittest', 'pydoc', 'doctest',
              'distutils', 'setuptools', 'pip'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FanController',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # GUI app, no console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico' if os.path.exists('icon.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FanController',
)
