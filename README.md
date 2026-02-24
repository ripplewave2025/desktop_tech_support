# Desktop Tech Support

**Windows Troubleshooting & Automation System**

A standalone tech support engine for Windows that diagnoses and fixes common issues across 8 categories. Designed for non-technical users with a friendly narrator system.

---

## Quick Start

```powershell
# 1. Install dependencies
python setup.py

# 2. Run tech support
python -m cli.main
```

## Features

| Category | What it checks |
|----------|---------------|
| **Printer** | Installed printers, default printer, status, queue, Print Spooler service |
| **Internet** | Network adapters, DNS, ping, bandwidth, top network processes, WiFi signal |
| **Software** | Frozen apps, Windows Update, startup programs, pending reboots, temp files |
| **Hardware** | CPU, RAM, disk space (all drives), temperature, battery, uptime |
| **Files** | Downloads folder size, Desktop clutter, Recycle Bin, large files (>500 MB) |
| **Display** | Monitor detection, resolution, DPI scaling, graphics adapter/driver |
| **Audio** | Sound devices, Windows Audio service, volume, AudioEndpointBuilder |
| **Security** | Windows Defender, firewall, suspicious processes, suspicious ports, UAC |

## CLI Usage

```powershell
# Interactive menu
python -m cli.main

# Run specific diagnostic
python -m cli.main --diagnose printer
python -m cli.main --diagnose internet
python -m cli.main --diagnose hardware

# Run all diagnostics
python -m cli.main --diagnose all

# Auto-fix mode (still asks permission per fix)
python -m cli.main --diagnose all --auto-fix

# JSON output for scripting
python -m cli.main --diagnose hardware --json

# System info only
python -m cli.main --sysinfo
```

## Python API

```python
from core.automation import AutomationController

ctrl = AutomationController()

# System info
info = ctrl.get_system_info()
print(f"CPU: {info.cpu_percent}%, RAM: {info.memory_percent}%")

# Window management
windows = ctrl.list_windows()
win = ctrl.find_window(title="Notepad")
win.focus()

# Process control
procs = ctrl.list_processes(name_filter="chrome")
ctrl.kill_process("notepad.exe")

# Screen capture + OCR
img = ctrl.capture_screen()
text = ctrl.read_text()

# Input simulation
ctrl.type_text("Hello World")
ctrl.hotkey("ctrl", "s")
```

## Safety System

- **Emergency Stop**: `Ctrl+Alt+Esc` halts all automation instantly
- **Rate Limiting**: 100 actions/minute (configurable)
- **Blacklist**: System32, critical processes protected
- **Confirmation Prompts**: High-risk actions require user permission
- **Audit Logging**: Every action logged to `logs/automation_log.jsonl`

## Running Tests

```powershell
# All tests
python -m unittest discover -s tests -v

# Specific test
python -m unittest tests.test_safety -v
python -m unittest tests.test_smoke -v
```

## Project Structure

```
desktop_tech_support/
  core/               # Core automation framework
    automation.py      #   Main controller (unified API)
    safety.py          #   Emergency stop, rate limiter, blacklist
    window_manager.py  #   Find, focus, resize windows
    input_controller.py#   Mouse + keyboard simulation
    screen_capture.py  #   Screenshots + OCR
    process_manager.py #   Process lifecycle + system info
  diagnostics/         # Tech support diagnostic modules
    base.py            #   Narrator + BaseDiagnostic
    printer.py         #   Printer troubleshooting
    internet.py        #   Network diagnostics
    software.py        #   App issues + updates
    hardware.py        #   Performance + disk
    files.py           #   File management
    display.py         #   Monitor + resolution
    audio.py           #   Sound devices
    security.py        #   Defender + firewall
  cli/                 # Command-line interface
    main.py            #   Entry point + interactive menu
  tests/               # Test suite (5 files)
  setup.py             # One-click installer
  config.json          # Configuration
  requirements.txt     # Dependencies
```

## Documentation

| Document | What it covers |
|----------|---------------|
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to add diagnostics, code style, safety rules, areas needing help |
| [LIMITATIONS.md](LIMITATIONS.md) | Known limitations per diagnostic, platform constraints, what this tool is NOT |
| [SUPPORT_RESOURCES.md](docs/SUPPORT_RESOURCES.md) | Official support links for Dell, HP, Lenovo, ASUS, Acer, Surface, Samsung, MSI + printer brands |

### Manufacturer Support Quick Links

| Manufacturer | Support Site | Diagnostic Tool |
|-------------|-------------|-----------------|
| **Dell** | [support.dell.com](https://support.dell.com) | SupportAssist |
| **HP** | [support.hp.com](https://support.hp.com) | HP Support Assistant |
| **Lenovo** | [support.lenovo.com](https://support.lenovo.com) | Lenovo Vantage |
| **ASUS** | [asus.com/support](https://www.asus.com/support/) | MyASUS |
| **Acer** | [acer.com/support](https://www.acer.com/us-en/support) | Acer Care Center |
| **Surface** | [support.microsoft.com/surface](https://support.microsoft.com/en-us/surface) | Surface Diagnostic Toolkit |

> **Tip:** Run `python -m cli.main --sysinfo` or `Get-CimInstance Win32_ComputerSystem` in PowerShell to identify your manufacturer.

## Requirements

- **Python 3.8+** on Windows 10/11
- Dependencies: pywinauto, pynput, mss, pytesseract, opencv-python, psutil, pywin32, Pillow
- Optional: [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) for text recognition

## Known Limitations

See [LIMITATIONS.md](LIMITATIONS.md) for full details. Key points:
- Windows only (no macOS/Linux)
- Some fixes require Administrator privileges
- Security scan is heuristic-based, NOT a replacement for antivirus
- Hardware diagnostics are software-level only (use manufacturer tools for hardware-level testing)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Areas we need help with:
- Bluetooth & VPN diagnostics
- Manufacturer-specific fix integration
- Localization (narrator messages in other languages)
- Zora avatar overlay (Phase 2)

## License

MIT
