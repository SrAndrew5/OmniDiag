# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['auditoria_kilometraje.py'],
    pathex=[],
    binaries=[('libusb-1.0.dll', '.')],
    datas=[],
    hiddenimports=[
        'can.interfaces.gs_usb',
        'can.interfaces.slcan',
        'can.interfaces.virtual',
        'gs_usb',
        'usb',
        'usb.core',
        'usb.backend.libusb1',
        'libusb_package',
        'isotp'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt6'],
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
    name='AuditoriaKm',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
