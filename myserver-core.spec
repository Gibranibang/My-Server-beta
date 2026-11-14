# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

ROOT_DIR = SPECPATH

datas = []
binaries = []
hiddenimports = ['clr', 'pythonnet', 'winreg', 'syncthing_manager', 'config_manager', 'logger_manager']
for pkg in ['webview', 'paramiko', 'cryptography', 'bcrypt', 'nacl']:
    try:
        t = collect_all(pkg)
        datas += t[0]
        binaries += t[1]
        hiddenimports += t[2]
    except Exception as e:
        pass

a = Analysis(
    [os.path.join(ROOT_DIR, 'myserver_core_service.py')],
    pathex=[ROOT_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# Exclude Windows Universal CRT & API-set stubs so the host OS System32 DLLs are used
a.binaries = [
    x for x in a.binaries
    if not os.path.basename(x[0]).lower().startswith(('api-ms-win-', 'ucrtbase'))
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='myserver-core',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
