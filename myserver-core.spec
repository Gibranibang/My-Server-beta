# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

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
    ['D:/Projek/MyServer/Beta/myserver_core_service.py'],
    pathex=['D:/Projek/MyServer/Beta'],
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
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
