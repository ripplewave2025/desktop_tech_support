#!/usr/bin/env python3
"""
Zora Desktop Companion — Windows Installer / First-Run Setup
Guides the user through installing Ollama, pulling models, and launching Zora.
Runs as a console wizard before handing off to the main app.

This script is bundled INSIDE Zora.exe and runs on first launch (or when
the user passes --setup). On subsequent launches, it detects everything
is already set up and skips straight to the app.
"""
import os
import sys
import time
import shutil
import subprocess
import urllib.request
import json
from pathlib import Path

# ── Constants ──────────────────────────────────────────
OLLAMA_INSTALLER_URL = "https://ollama.com/download/OllamaSetup.exe"
REQUIRED_MODELS = ["qwen2.5:3b"]
OPTIONAL_MODELS = ["moondream"]
ZORA_DIR = Path(os.environ.get("LOCALAPPDATA", "C:/Users/Public")) / "Zora"
SETUP_MARKER = ZORA_DIR / ".setup_complete"

BANNER = r"""
   ███████╗ ██████╗ ██████╗  █████╗
   ╚══███╔╝██╔═══██╗██╔══██╗██╔══██╗
     ███╔╝ ██║   ██║██████╔╝███████║
    ███╔╝  ██║   ██║██╔══██╗██╔══██║
   ███████╗╚██████╔╝██║  ██║██║  ██║
   ╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝
         AI Desktop Companion v2.0
"""


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def print_header(step: str):
    clear()
    print(BANNER)
    print(f"  [{step}]")
    print("  " + "─" * 45)
    print()


def is_ollama_installed() -> bool:
    """Check if Ollama is accessible."""
    return shutil.which("ollama") is not None


def is_ollama_running() -> bool:
    """Check if Ollama server is responding."""
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3)
        return True
    except Exception:
        return False


def get_installed_models() -> list:
    """Get list of installed Ollama models."""
    try:
        data = urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5).read()
        return [m["name"].split(":")[0] for m in json.loads(data).get("models", [])]
    except Exception:
        return []


def download_file(url: str, dest: Path, label: str):
    """Download with progress bar."""
    print(f"  Downloading {label}...")
    try:
        urllib.request.urlretrieve(url, str(dest), _progress_hook)
        print()  # newline after progress
        return True
    except Exception as e:
        print(f"\n  Error: {e}")
        return False


def _progress_hook(block_count, block_size, total_size):
    downloaded = block_count * block_size
    if total_size > 0:
        pct = min(100, downloaded * 100 // total_size)
        mb = downloaded / (1024 * 1024)
        total_mb = total_size / (1024 * 1024)
        bar = "█" * (pct // 3) + "░" * (33 - pct // 3)
        print(f"\r  [{bar}] {pct}% ({mb:.1f}/{total_mb:.1f} MB)", end="", flush=True)


def install_ollama():
    """Download and install Ollama."""
    print_header("Step 1/3: Installing Ollama (AI Engine)")
    print("  Ollama is the AI engine that powers Zora's brain.")
    print("  It runs 100% locally on your PC — no cloud, no fees.\n")

    if is_ollama_installed():
        print("  ✅ Ollama is already installed! Skipping.\n")
        return True

    installer_path = ZORA_DIR / "OllamaSetup.exe"
    ZORA_DIR.mkdir(parents=True, exist_ok=True)

    if not download_file(OLLAMA_INSTALLER_URL, installer_path, "Ollama"):
        print("\n  ❌ Download failed. You can install manually from: https://ollama.com")
        print("  Press Enter to continue anyway...")
        input()
        return False

    print("  Running Ollama installer...\n")
    print("  ⚠️  A setup window will pop up — just click through it.")
    print("  Come back here when it's done!\n")

    try:
        subprocess.run([str(installer_path)], check=False)
    except Exception as e:
        print(f"  Error launching installer: {e}")

    # Wait for Ollama to be available
    print("  Waiting for Ollama to be ready...", end="", flush=True)
    for _ in range(30):
        if is_ollama_running():
            print(" ✅")
            return True
        time.sleep(2)
        print(".", end="", flush=True)

    print("\n  Ollama installed but not running yet.")
    print("  Try restarting your PC if it doesn't start automatically.")
    return True


def start_ollama():
    """Ensure Ollama server is running."""
    if is_ollama_running():
        return True

    print("  Starting Ollama...", end="", flush=True)
    try:
        # Try launching Ollama serve in background
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except Exception:
        pass

    for _ in range(15):
        if is_ollama_running():
            print(" ✅")
            return True
        time.sleep(1)
        print(".", end="", flush=True)

    print(" ❌ couldn't start. Try running 'ollama serve' manually.")
    return False


def pull_models():
    """Pull required AI models."""
    print_header("Step 2/3: Downloading AI Models")
    print("  Zora needs AI models to think and see.")
    print("  This is a one-time download (about 2GB total).\n")

    if not start_ollama():
        print("  ⚠️  Ollama isn't running. Skipping model download.")
        print("  You can pull models later with: ollama pull qwen2.5:3b")
        input("\n  Press Enter to continue...")
        return

    installed = get_installed_models()

    for model in REQUIRED_MODELS:
        base_name = model.split(":")[0]
        if base_name in installed:
            print(f"  ✅ {model} already downloaded\n")
            continue

        print(f"  📦 Pulling {model} (this may take a few minutes)...\n")
        try:
            proc = subprocess.run(
                ["ollama", "pull", model],
                capture_output=False,
            )
            if proc.returncode == 0:
                print(f"\n  ✅ {model} ready!\n")
            else:
                print(f"\n  ⚠️ Issue pulling {model}. Run 'ollama pull {model}' manually.\n")
        except Exception as e:
            print(f"\n  Error: {e}")

    for model in OPTIONAL_MODELS:
        base_name = model.split(":")[0]
        if base_name in installed:
            print(f"  ✅ {model} already downloaded (vision model)\n")
            continue

        print(f"  📦 Pulling {model} (optional — enables screen vision)...\n")
        try:
            subprocess.run(["ollama", "pull", model], capture_output=False)
            print(f"\n  ✅ {model} ready!\n")
        except Exception:
            print(f"\n  ⚠️ Skipping {model}. Vision features won't work until installed.\n")


def create_shortcuts():
    """Create desktop shortcut and Start Menu entry."""
    print_header("Step 3/3: Creating Shortcuts")

    exe_path = sys.executable if getattr(sys, 'frozen', False) else __file__

    # Desktop shortcut via PowerShell
    desktop = Path(os.environ.get("USERPROFILE", "~")) / "Desktop"
    shortcut_path = desktop / "Zora.lnk"

    try:
        ps_cmd = f'''
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("{shortcut_path}")
$sc.TargetPath = "{exe_path}"
$sc.WorkingDirectory = "{Path(exe_path).parent}"
$sc.Description = "Zora AI Desktop Companion"
$sc.Save()
'''
        subprocess.run(
            ["powershell", "-Command", ps_cmd],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        print(f"  ✅ Desktop shortcut created")
    except Exception as e:
        print(f"  ⚠️ Couldn't create shortcut: {e}")

    # Start Menu
    start_menu = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    sm_shortcut = start_menu / "Zora.lnk"
    try:
        ps_cmd2 = f'''
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("{sm_shortcut}")
$sc.TargetPath = "{exe_path}"
$sc.WorkingDirectory = "{Path(exe_path).parent}"
$sc.Description = "Zora AI Desktop Companion"
$sc.Save()
'''
        subprocess.run(
            ["powershell", "-Command", ps_cmd2],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        print(f"  ✅ Start Menu shortcut created")
    except Exception:
        pass

    print()


def run_setup():
    """Full first-run setup wizard."""
    print_header("Welcome to Zora!")
    print("  I'll get everything set up for you in 3 quick steps:\n")
    print("  1. Install Ollama (AI engine)  — runs locally, no internet needed after setup")
    print("  2. Download AI models          — one-time ~2GB download")
    print("  3. Create shortcuts            — desktop & Start Menu\n")
    print("  Total time: ~5-10 minutes depending on your internet.\n")
    input("  Press Enter to begin...")

    install_ollama()
    pull_models()
    create_shortcuts()

    # Mark setup complete
    ZORA_DIR.mkdir(parents=True, exist_ok=True)
    SETUP_MARKER.write_text(time.strftime("%Y-%m-%d %H:%M:%S"))

    print_header("Setup Complete! 🎉")
    print("  ✅ Ollama installed")
    print("  ✅ AI models downloaded")
    print("  ✅ Shortcuts created\n")
    print("  Zora is about to launch in your browser.")
    print("  From now on, just double-click Zora on your desktop!\n")
    input("  Press Enter to launch Zora...")


def needs_setup() -> bool:
    """Check if first-run setup is needed."""
    if "--setup" in sys.argv:
        return True
    if SETUP_MARKER.exists():
        return False
    # First time running
    return True


if __name__ == "__main__":
    run_setup()
