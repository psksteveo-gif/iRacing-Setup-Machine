# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Optimal Sector
Run: pyinstaller OptimalSector.spec
"""

import os
import sys
import customtkinter

block_cipher = None

# Path to customtkinter package (needs its themes/assets bundled)
ctk_path = os.path.dirname(customtkinter.__file__)

# Path to tkinterdnd2 package (needs its platform libs bundled)
try:
    import tkinterdnd2
    dnd_path = os.path.dirname(tkinterdnd2.__file__)
    dnd_datas = [(dnd_path, 'tkinterdnd2')]
    dnd_imports = ['tkinterdnd2']
except ImportError:
    dnd_datas = []
    dnd_imports = []

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Bundle customtkinter themes and assets
        (ctk_path, 'customtkinter'),
        # Bundle app data and version
        ('core', 'core'),
        ('ui', 'ui'),
        ('data', 'data'),
        ('version.py', '.'),
        ('LICENSE', '.'),
        ('THIRD_PARTY_NOTICES.md', '.'),
    ] + dnd_datas,
    hiddenimports=[
        'customtkinter',
        'tkinter',
        'numpy',
        'matplotlib',
        'matplotlib.backends.backend_tkagg',
        'matplotlib.figure',
        'matplotlib.pyplot',
        'matplotlib.patches',
        'matplotlib.colormaps',
        'anthropic',
        'keyring',
        'keyring.backends',
        'keyring.backends.Windows',
        'jaraco.classes',
        'jaraco.functools',
        'jaraco.context',
        'reportlab',
        'reportlab.lib',
        'reportlab.lib.pagesizes',
        'reportlab.platypus',
        'reportlab.lib.styles',
        'reportlab.lib.units',
        'winreg',
        'core',
        'core.ibt_parser',
        'core.analysis_engine',
        'core.advanced_analysis',
        'core.driving_style',
        'core.setup_parser',
        'core.ai_advisor',
        'core.pdf_report',
        'core.car_classifier',
        'core.file_watcher',
        'core.cloud_sync',
        'core.race_engineer',
        'data',
        'data.templates',
        'data.templates.track_templates',
    ] + dnd_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='OptimalSector',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window — GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OptimalSector',
)
