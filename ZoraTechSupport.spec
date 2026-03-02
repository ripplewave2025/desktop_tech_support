# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['zora.py'],
    pathex=[],
    binaries=[],
    datas=[('config.json', '.'), ('diagnostics', 'diagnostics'), ('core', 'core'), ('cli', 'cli')],
    hiddenimports=['diagnostics.printer', 'diagnostics.audio', 'diagnostics.internet', 'diagnostics.hardware', 'diagnostics.display', 'diagnostics.files', 'diagnostics.security', 'diagnostics.software', 'diagnostics.base', 'core.process_manager', 'core.automation', 'core.window_manager', 'core.screen_capture', 'core.input_controller', 'core.safety', 'comtypes', 'win32api', 'win32con', 'win32gui'],
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
    name='ZoraTechSupport',
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
