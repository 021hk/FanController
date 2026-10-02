# -*- mode: python ; coding: utf-8 -*-
"""fan_controller.spec - PyInstaller build configuration."""

import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

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
hiddenimports += ['log_viewer', 'settings_dialog']  # local modules

# Data files - bundle LibreHardwareMonitor.exe + all DLLs + get_log.bat
datas = []
for f in os.listdir('.'):
    if f.lower().endswith(('.exe', '.dll', '.config', '.bat')):
        datas.append((f, '.'))
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
