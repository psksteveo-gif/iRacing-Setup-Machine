# -*- mode: python ; coding: utf-8 -*-
#
# optimal_sector.spec — PyInstaller build spec for Optimal Sector
#
# Build command:
#   pyinstaller optimal_sector.spec
#
# For encrypted bytecode (obfuscates .pyc from casual extraction):
#   pyinstaller optimal_sector.spec --key=<32-char-random-key>
#   Generate key: python -c "import secrets; print(secrets.token_hex(16))"
#
# Distribution:
#   dist/OptimalSector/OptimalSector.exe  (Windows)
#   dist/OptimalSector/OptimalSector      (Linux/macOS)
#
# Security notes:
#   - --key flag encrypts .pyc bytecode (AES-256) — raises the bar for
#     reverse engineering but is NOT unbreakable. Determined attackers with
#     the binary can still extract logic. This protects casual inspection.
#   - Knowledge base text (core/knowledge_base.py) will be visible in the
#     binary without additional obfuscation. This is acceptable — it contains
#     publicly available racing engineering knowledge, not trade secrets.
#   - Subscription key validation logic is compiled but visible with tools
#     like uncompyle6. Accept this — server-side validation is the real gate.
#   - All credentials go through OS keyring, never embedded in the binary.

import sys, os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None  # set via --key flag at build time

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Include track corner database and any data files
        ('data/',          'data/'),
        ('core/',          'core/'),
    ],
    hiddenimports=[
        # CustomTkinter and tkinter
        'customtkinter',
        'tkinter',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'tkinter.simpledialog',
        # Anthropic SDK
        'anthropic',
        'httpx',
        'httpcore',
        'anyio',
        # Crypto
        'cryptography',
        'cryptography.fernet',
        'cryptography.hazmat.primitives.ciphers',
        # Keyring backends (all — Windows/macOS/Linux)
        'keyring',
        'keyring.backends.Windows',
        'keyring.backends.macOS',
        'keyring.backends.SecretService',
        'keyring.backends.fail',
        # Data
        'numpy',
        'numpy.core',
        'scipy',
        'scipy.signal',
        # Audio
        'pyttsx3',
        'pyttsx3.drivers',
        'pyttsx3.drivers.sapi5',
        # iRacing
        'irsdk',
        # Requests
        'requests',
        'urllib3',
        'certifi',
        # Utils
        'PIL',
        'PIL.Image',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude dev/test tools
        'pytest',
        'IPython',
        'jupyter',
        'notebook',
        'black',
        'pylint',
        'mypy',
        # Large unused stdlib
        'distutils',
        'lib2to3',
        'xmlrpc',
        'doctest',
        'pdb',
    ],
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
    upx=True,               # UPX compression — reduces binary size ~30-40%
    upx_exclude=[
        # Exclude DLLs that break under UPX
        'vcruntime140.dll',
        'python3*.dll',
        '_tkinter*.pyd',
    ],
    console=False,           # No console window (GUI app)
    disable_windowed_traceback=True,  # Don't show Python tracebacks to users
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if os.path.exists('assets/icon.ico') else None,
    version='version_info.txt' if os.path.exists('version_info.txt') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=['vcruntime140.dll', 'python3*.dll', '_tkinter*.pyd'],
    name='OptimalSector',
)
