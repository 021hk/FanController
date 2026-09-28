# -*- mode: python ; coding: utf-8 -*-
"""
fan_controller.spec - PyInstaller build configuration.
"""

import os
import sys
import logging
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

block_cipher = None

# Collect all submodules for libraries that use dynamic imports
hiddenimports = []
hiddenimports += collect_submodules('PyQt6')
hiddenimports += collect_submodules('pystray')
hiddenimports += collect_submodules('PIL')
hiddenimports += collect_submodules('websocket')
hiddenimports += collect_submodules('serial')
hiddenimports += ['keyboard._winkeyboard', 'keyboard._nixkeyboard']
hiddenimports += ['serial.tools.list_ports', 'serial.serialcli']

# Include LibreHardwareMonitor.exe + ALL its DLL dependencies
# We launch LHM.exe as a background process to expose WMI sensors
datas = []
lhm_files_to_bundle = [
    'LibreHardwareMonitor.exe',
    'LibreHardwareMonitor.exe.config',
    'LibreHardwareMonitorLib.dll',
    'HidSharp.dll',
]
# Add LHM exe + all .dll files in current directory
for f in lhm_files_to_bundle:
    if os.path.exists(f):
        datas.append((f, '.'))

# Also add any other .dll files that might be LHM dependencies
for f in os.listdir('.'):
    if f.lower().endswith('.dll') and f not in lhm_files_to_bundle:
        datas.append((f, '.'))
        log.info(f'Bundling additional DLL: {f}')

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
