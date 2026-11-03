# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Current working directory (tools/plot)
project_dir = os.path.abspath(os.getcwd())

# Add paths so PyInstaller resolves both local 'src' and parent 'tools' modules
pathex = [
    project_dir,
    os.path.abspath(os.path.join(project_dir, '..')),       # .../tools
    os.path.abspath(os.path.join(project_dir, '..', '..')), # .../mod/MnT-EU5
]

# Collect essential data files and dependencies
datas = []
for filename in ['key_configs.json', 'locations.csv', 'icon.png']:
    if os.path.exists(os.path.join(project_dir, filename)):
        datas.append((filename, '.'))

# Gather package metadata and assets for scientific/GUI libraries
datas += collect_data_files('matplotlib')
datas += collect_data_files('seaborn')
datas += collect_data_files('scipy')

# Hidden imports that dynamic loaders often miss
hiddenimports = [
    'unittest',
    'PyQt6',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'matplotlib.backends.backend_qtagg',
    'openpyxl',
    'openpyxl.cell._writer',
    'sklearn',
    'sklearn.utils._typedefs',
    'sklearn.neighbors._typedefs',
    'tools.shared',
    'tools.shared.fetch_logs',
]
hiddenimports += collect_submodules('sklearn')
hiddenimports += collect_submodules('openpyxl')
hiddenimports += collect_submodules('scipy')

icon_file = 'icon.png' if os.path.exists('icon.png') else None

a = Analysis(
    [os.path.join('src', 'MT_grapher.py')],
    pathex=pathex,
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'pytest'],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MT_grapher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Set to True if you want a command prompt window for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MT_grapher',
)