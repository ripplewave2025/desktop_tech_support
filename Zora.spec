# -*- mode: python ; coding: utf-8 -*-
# Zora Desktop Companion v2.0 — Full build with UI + AI + Diagnostics + Monitoring

import os

# Check if icon exists
icon_path = 'assets/zora_icon.ico'
if not os.path.exists(icon_path):
    icon_path = None

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Config
        ('config.json', '.'),
        # Backend modules
        ('diagnostics', 'diagnostics'),
        ('core', 'core'),
        ('cli', 'cli'),
        ('ai', 'ai'),
        ('api', 'api'),
        # v2.0 modules
        ('monitoring', 'monitoring'),
        ('remediation', 'remediation'),
        ('tray', 'tray'),
        # Diagnostic flows (YAML)
        ('diagnostics/flows', 'diagnostics/flows'),
        # Built React frontend
        ('ui/dist', 'ui/dist'),
    ],
    hiddenimports=[
        # Diagnostics
        'diagnostics.printer', 'diagnostics.audio', 'diagnostics.internet',
        'diagnostics.hardware', 'diagnostics.display', 'diagnostics.files',
        'diagnostics.security', 'diagnostics.software', 'diagnostics.base',
        'diagnostics.flow_engine', 'diagnostics.flow_actions',
        # Core automation
        'core.process_manager', 'core.automation', 'core.window_manager',
        'core.screen_capture', 'core.input_controller', 'core.safety',
        # AI
        'ai.agent', 'ai.tools', 'ai.tool_executor', 'ai.provider_factory',
        'ai.providers', 'ai.providers.ollama_provider',
        'ai.providers.claude_provider', 'ai.providers.openai_provider',
        # API
        'api.server',
        # v2.0 modules
        'monitoring', 'monitoring.alerts', 'monitoring.watcher',
        'remediation', 'remediation.library',
        'tray', 'tray.tray_icon',
        # Win32
        'comtypes', 'win32api', 'win32con', 'win32gui',
        # FastAPI / Uvicorn
        'uvicorn', 'uvicorn.logging', 'uvicorn.loops',
        'uvicorn.loops.auto', 'uvicorn.protocols',
        'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan', 'uvicorn.lifespan.on',
        'fastapi', 'starlette', 'starlette.routing',
        'starlette.staticfiles', 'starlette.responses',
        'anyio._backends._asyncio',
        'httpx', 'httpcore',
        # v2.0 dependencies
        'yaml', 'pystray', 'PIL._tkinter_finder',
        'duckduckgo_search',
        # Other
        'PIL', 'mss', 'psutil', 'pynput',
        'multiprocessing',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy.testing', 'scipy', 'pandas'],
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
    name='Zora',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,   # v2.0: Windowed app (tray icon, no console)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
    version='file_version_info.txt' if os.path.exists('file_version_info.txt') else None,
)
