#!/usr/bin/env python3
"""
Zora Desktop Launcher
First-run: guides user through Ollama setup wizard.
Normal run: starts FastAPI backend (serves React UI) and opens browser.
This is the entry point for the PyInstaller .exe build.
"""
import sys
import os

# Single source of truth lives in core/version.py; we re-export it here so
# legacy callers that do ``from launcher import ZORA_VERSION`` keep working.
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from core.version import ZORA_VERSION  # noqa: F401
except Exception:
    ZORA_VERSION = "0.0.0"

# ── Fix for windowed mode (console=False in PyInstaller) ──────────
# When built as a windowed .exe, sys.stdout/stderr are None.
# Uvicorn's log formatter calls .isatty() on them and crashes.
# Redirect to a log file so everything still works.
#
# We open the log file directly (so print() and uvicorn's stream writers
# both land somewhere), AND we attach a RotatingFileHandler to the root
# logger so structured logging.* calls also rotate. Both write to the same
# file path so the user sees one combined log.
if sys.stdout is None or sys.stderr is None:
    _log_dir = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Zora"
    )
    os.makedirs(_log_dir, exist_ok=True)
    _log_file = open(os.path.join(_log_dir, "zora.log"), "a", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = _log_file
    if sys.stderr is None:
        sys.stderr = _log_file

import time
import threading
import webbrowser
import socket
import subprocess
import shutil
import json
from pathlib import Path

# Fix paths for PyInstaller bundle. Done BEFORE the crash-reporter import
# below so `from core.crash_reporter ...` resolves whether we're frozen,
# launched from project root, or launched via a desktop shortcut whose cwd
# is somewhere else entirely.
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
    os.environ["ZORA_BASE_DIR"] = BASE_DIR
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# ── Crash reporter + rotating log ─────────────────────────────────
# As early as possible (right after path setup) so import-time exceptions
# in the rest of launcher.py / the main app are captured to disk.
try:
    _zora_data = Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / "Zora"
    from core.crash_reporter import (
        install_crash_handlers as _install_crash_handlers,
        attach_rotating_log as _attach_rotating_log,
    )
    _install_crash_handlers(version=ZORA_VERSION,
                            crash_dir=_zora_data / "crashes")
    _attach_rotating_log(log_path=_zora_data / "zora.log")
except Exception as _crash_setup_err:
    # Don't take the launcher down if the crash reporter itself can't
    # set up — just complain and continue.
    print(f"[Zora] Crash reporter setup skipped: {_crash_setup_err}",
          file=sys.stderr)

PORT = 8000
URL = f"http://127.0.0.1:{PORT}"
ZORA_DATA = Path(os.environ.get("LOCALAPPDATA", "C:/Users/Public")) / "Zora"
SETUP_MARKER = ZORA_DATA / ".setup_complete"

BANNER = r"""
   ███████╗ ██████╗ ██████╗  █████╗
   ╚══███╔╝██╔═══██╗██╔══██╗██╔══██╗
     ███╔╝ ██║   ██║██████╔╝███████║
    ███╔╝  ██║   ██║██╔══██╗██╔══██║
   ███████╗╚██████╔╝██║  ██║██║  ██║
   ╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝
      AI Desktop Companion v2.0
"""


# ─── Utility ──────────────────────────────────────────
def clear():
    os.system("cls" if os.name == "nt" else "clear")


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def is_ollama_installed() -> bool:
    return shutil.which("ollama") is not None


def is_ollama_running() -> bool:
    try:
        import urllib.request
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3)
        return True
    except Exception:
        return False


def get_installed_models() -> list:
    try:
        import urllib.request
        data = urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5).read()
        return [m["name"] for m in json.loads(data).get("models", [])]
    except Exception:
        return []


def start_ollama():
    """Ensure Ollama server is running."""
    if is_ollama_running():
        return True
    try:
        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NO_WINDOW
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
    except Exception:
        pass
    for _ in range(10):
        if is_ollama_running():
            return True
        time.sleep(1)
    return False


# ─── First-Run Setup ─────────────────────────────────
def _download_progress(block_count, block_size, total_size):
    downloaded = block_count * block_size
    if total_size > 0:
        pct = min(100, downloaded * 100 // total_size)
        mb = downloaded / (1024 * 1024)
        total_mb = total_size / (1024 * 1024)
        bar = "█" * (pct // 3) + "░" * (33 - pct // 3)
        print(f"\r  [{bar}] {pct}% ({mb:.1f}/{total_mb:.1f} MB)", end="", flush=True)


def run_setup():
    """First-run setup wizard — installs Ollama + pulls models + creates shortcuts."""
    clear()
    print(BANNER)
    print("  Welcome! Let's get Zora set up on your PC.\n")
    print("  What I'll do:")
    print("  1. Install Ollama (the local AI engine — free, no account needed)")
    print("  2. Download AI models (~2GB, one-time)")
    print("  3. Create a desktop shortcut\n")
    print("  Takes about 5-10 minutes depending on your internet.\n")
    input("  Press Enter to start...")

    ZORA_DATA.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Ollama ──
    clear()
    print(BANNER)
    print("  [Step 1/3] Installing Ollama\n")

    if is_ollama_installed():
        print("  ✅ Ollama is already installed!\n")
    else:
        print("  Downloading Ollama installer...\n")
        installer_path = ZORA_DATA / "OllamaSetup.exe"
        try:
            import urllib.request
            urllib.request.urlretrieve(
                "https://ollama.com/download/OllamaSetup.exe",
                str(installer_path),
                _download_progress,
            )
            print("\n\n  Running installer... A setup window will pop up.")
            print("  Just click through it and come back here when done!\n")
            subprocess.run([str(installer_path)], check=False)
            print("  Waiting for Ollama to be ready...", end="", flush=True)
            for _ in range(30):
                if is_ollama_running():
                    print(" ✅")
                    break
                time.sleep(2)
                print(".", end="", flush=True)
            else:
                print("\n  Ollama installed. You may need to restart your PC.")
        except Exception as e:
            print(f"\n  Couldn't auto-install Ollama: {e}")
            print("  Please install manually from: https://ollama.com")
            input("\n  Press Enter to continue...")

    # ── Step 2: Models ──
    clear()
    print(BANNER)
    print("  [Step 2/3] Downloading AI Models\n")

    start_ollama()

    for model in ["qwen2.5:3b", "moondream"]:
        installed = get_installed_models()
        base = model.split(":")[0]
        if any(base in m for m in installed):
            label = "(chat brain)" if "qwen" in model else "(vision)"
            print(f"  ✅ {model} {label} — already downloaded\n")
            continue

        label = "chat brain — lets Zora think" if "qwen" in model else "vision — lets Zora see your screen"
        print(f"  📦 Downloading {model} ({label})...")
        print(f"     This may take a few minutes...\n")
        try:
            subprocess.run(["ollama", "pull", model], check=False)
            print(f"\n  ✅ {model} ready!\n")
        except Exception:
            print(f"  ⚠️ Couldn't download {model}. Run 'ollama pull {model}' later.\n")

    # ── Step 3: Shortcut ──
    clear()
    print(BANNER)
    print("  [Step 3/3] Creating Shortcuts\n")

    exe_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
    desktop = Path(os.environ.get("USERPROFILE", "~")) / "Desktop"

    try:
        ps_cmd = f'''
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("{desktop / 'Zora.lnk'}")
$sc.TargetPath = "{exe_path}"
$sc.WorkingDirectory = "{Path(exe_path).parent}"
$sc.Description = "Zora AI Desktop Companion"
$sc.Save()
'''
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, creationflags=flags)
        print("  ✅ Desktop shortcut created")
    except Exception:
        print("  ⚠️ Couldn't create shortcut (not critical)")

    # Start Menu
    try:
        sm = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs"
        ps_cmd2 = f'''
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("{sm / 'Zora.lnk'}")
$sc.TargetPath = "{exe_path}"
$sc.WorkingDirectory = "{Path(exe_path).parent}"
$sc.Description = "Zora AI Desktop Companion"
$sc.Save()
'''
        subprocess.run(["powershell", "-Command", ps_cmd2], capture_output=True, creationflags=flags)
        print("  ✅ Start Menu shortcut created")
    except Exception:
        pass

    # Mark complete
    SETUP_MARKER.write_text(time.strftime("%Y-%m-%d %H:%M:%S"))

    clear()
    print(BANNER)
    print("  ✅ Setup Complete!\n")
    print("  Everything's ready. Zora will now launch in your browser.")
    print("  From now on, just double-click 'Zora' on your desktop!\n")
    input("  Press Enter to launch Zora...")


# ─── Main App Launch ─────────────────────────────────
def open_browser_when_ready(port: int):
    """Wait for the server to be ready on `port`, then open the browser."""
    target_url = f"http://127.0.0.1:{port}"
    for _ in range(30):
        time.sleep(0.5)
        if is_port_in_use(port):
            webbrowser.open(target_url)
            return
    print(f"[Zora] Server didn't start in time. Open {target_url} manually.")


def start_tray_icon(url: str):
    """Start system tray icon (best-effort — silently skips if pystray missing)."""
    try:
        from tray.tray_icon import ZoraTray
        tray = ZoraTray(url=url, on_quit=lambda: os._exit(0))
        tray.start()
        print("  ✅ System tray icon active\n")
        return tray
    except ImportError:
        print("  ℹ️  No tray icon (install pystray for system tray support)\n")
    except Exception as e:
        print(f"  ⚠️ Tray icon failed: {e}\n")
    return None


def main():
    # ── Single-instance enforcement ─────────────────────
    # If another Zora is already running, don't spawn a second uvicorn.
    # Open the existing UI for the user and exit cleanly.
    from core.single_instance import (
        acquire_lock,
        find_free_port,
        write_instance_metadata,
        read_running_instance,
    )

    lock = acquire_lock()
    if lock is None:
        existing = read_running_instance()
        if existing:
            print(BANNER)
            print(f"  Zora is already running at {existing['url']}.")
            print("  Opening it for you...\n")
            try:
                webbrowser.open(existing["url"])
            except Exception:
                pass
        else:
            # Lock held but no reachable instance — likely starting up or
            # crashed mid-launch. Tell the user instead of silently dying.
            print(BANNER)
            print("  Another Zora is starting up. Try again in a few seconds.\n")
        sys.exit(0)

    # First-run setup
    if not SETUP_MARKER.exists() or "--setup" in sys.argv:
        run_setup()

    clear()
    print(BANNER)

    # ── Pick a port ────────────────────────────────────
    # Prefer 8000; if it's taken (by another app, NOT another Zora — the
    # mutex above would have caught that), walk up to find a free one.
    try:
        chosen_port = find_free_port(preferred=PORT, max_tries=20)
    except RuntimeError:
        print(f"  ❌ No free port between {PORT} and {PORT + 19}.")
        print("     Close some apps and try again.\n")
        sys.exit(1)

    if chosen_port != PORT:
        print(f"  ⚠️  Port {PORT} was busy. Using {chosen_port} instead.")
    chosen_url = f"http://127.0.0.1:{chosen_port}"
    print(f"  Starting Zora on {chosen_url}")
    print("  Press Ctrl+C to stop.\n")

    # Record where we're running so future double-launches know the URL.
    write_instance_metadata(chosen_port)

    # Ensure Ollama is up
    if is_ollama_installed():
        start_ollama()
        models = get_installed_models()
        if models:
            print(f"  ✅ Ollama running — Models: {', '.join(models)}\n")
        else:
            print("  ⚠️ Ollama running but no models found.")
            print("     Run: ollama pull qwen2.5:7b\n")
    else:
        print("  ⚠️ Ollama not found — running in basic mode.")
        print("     Install from https://ollama.com for AI features.\n")

    # Start system tray icon (uses the dynamic URL so right-click → Open
    # Zora opens the right port).
    tray = start_tray_icon(chosen_url)

    # Open browser
    threading.Thread(
        target=open_browser_when_ready, args=(chosen_port,), daemon=True
    ).start()

    # Start uvicorn (the watcher is started inside server.py on_event("startup"))
    import uvicorn
    uvicorn.run(
        "api.server:app",
        host="127.0.0.1",
        port=chosen_port,
        log_level="info",
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Zora signing off. See you next time! 👋")
        sys.exit(0)
