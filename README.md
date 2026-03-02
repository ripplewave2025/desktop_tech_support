# Zora — AI Desktop Companion

**Your personal Windows tech support assistant.** Zora diagnoses and fixes common PC problems using local AI — no cloud, no subscriptions, no data leaves your machine.

---

## Get Started

### Option A: Download the .exe (easiest)
1. Download `Zora.exe` from [Releases](https://github.com/ripplewave2025/desktop_tech_support/releases)
2. Double-click it — the setup wizard installs everything automatically
3. Zora opens in your browser at `http://127.0.0.1:8000`

### Option B: Run from source
```powershell
git clone https://github.com/ripplewave2025/desktop_tech_support.git
cd desktop_tech_support
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Install & start Ollama (free local AI)
# Download from https://ollama.com then:
ollama pull qwen2.5:7b
ollama pull moondream

# Start Zora
python launcher.py
```

### Option C: Use a cloud API instead of Ollama
Zora supports multiple AI providers. Set your preferred provider in Settings:

| Provider | Model | Env Variable | Cost |
|----------|-------|-------------|------|
| **Ollama** (default) | qwen2.5:7b | — | Free (local) |
| **Claude** | claude-sonnet-4-20250514 | `ANTHROPIC_API_KEY` | Paid |
| **OpenAI** | gpt-4o | `OPENAI_API_KEY` | Paid |
| **Grok** | grok-3-latest | `XAI_API_KEY` | Paid |
| **Groq** | llama-3.3-70b-versatile | `GROQ_API_KEY` | Free tier |
| **Custom** | any | — | Varies |

Set your API key as an environment variable or paste it in the Settings panel.

---

## What Zora Can Do

### 24 AI Tools
| Category | Tools |
|----------|-------|
| **Diagnostics** | Run 8 diagnostic modules (internet, audio, printer, display, hardware, software, files, security) |
| **Computer Use** | Screenshot + vision analysis, mouse/keyboard control, screen highlight, OCR |
| **Flow Diagnostics** | 5 decision-tree flows that branch like real tech support |
| **Remediation** | 52 structured Windows fixes with risk levels, rollback, and verification |
| **Monitoring** | Background CPU/RAM/disk/temp alerts, crash loop detection |
| **System** | Process manager, PowerShell execution, window management, web search |
| **Self-Upgrade** | Download tools from trusted GitHub repos at runtime |

### 8 Diagnostic Categories
| Category | What it checks |
|----------|---------------|
| **Internet** | Adapters, DNS, ping, bandwidth, WiFi signal, top network processes |
| **Audio** | Sound devices, Windows Audio service, volume, endpoints |
| **Printer** | Installed printers, status, queue, Print Spooler, default printer |
| **Display** | Monitors, resolution, DPI, graphics adapter/driver |
| **Hardware** | CPU, RAM, disk (all drives), temperature, battery, uptime |
| **Software** | Frozen apps, Windows Update, startup programs, temp files |
| **Files** | Downloads size, Desktop clutter, Recycle Bin, large files |
| **Security** | Defender, firewall, suspicious processes/ports, UAC |

### 52 Remediation Fixes
Structured fixes across 7 categories: Network (15), Audio (8), Display (6), Software (8), Hardware (5), Security (5), Printer (5). Each fix has risk level, verification, and rollback commands.

---

## Architecture

```
Layer 1: PERCEPTION           Layer 2: UNDERSTANDING       Layer 3: REASONING
  screen_capture.py             agent.py SYSTEM_PROMPT       agent.py (tool loop)
  tool_executor.py              tools.py (tool matching)     flow_engine.py (YAML trees)
  monitoring/watcher.py

Layer 4: ACTION               Layer 5: LEARNING (planned)
  tool_executor.py              SQLite memory (v3.0)
  flow_actions.py
  remediation/library.py
```

## Project Structure

```
desktop_tech_support/
  ai/                    # AI providers + agent logic
    agent.py               Tool-calling chat loop
    tools.py               24 tool definitions
    tool_executor.py       Tool handlers (1600+ lines)
    provider_factory.py    6-provider factory (Ollama/Claude/OpenAI/Grok/Groq/Custom)
    ollama_provider.py     Ollama integration
    claude_provider.py     Anthropic Claude
    openai_provider.py     OpenAI + compatible APIs
  api/                   # FastAPI backend
    server.py              REST + SSE streaming endpoints
  core/                  # Automation framework
    automation.py          Unified controller API
    safety.py              Emergency stop, rate limiter, blacklist
    window_manager.py      Find/focus/resize windows
    input_controller.py    Mouse + keyboard simulation
    screen_capture.py      Screenshots + OCR
    process_manager.py     Process lifecycle + system info
  diagnostics/           # Diagnostic modules
    base.py                BaseDiagnostic + narrator
    internet.py, audio.py, printer.py, display.py,
    hardware.py, software.py, files.py, security.py
    flow_engine.py         YAML decision tree engine
    flow_actions.py        23 reusable flow action functions
    flows/                 5 YAML diagnostic trees
  monitoring/            # Background system watcher
    watcher.py             CPU/RAM/disk/temp/crash alerts
    alerts.py              Alert model
  remediation/           # Fix library
    library.py             52 structured fixes
  tray/                  # System tray
    tray_icon.py           pystray icon + alert badges
  ui/                    # React frontend (Vite)
    src/App.jsx            Floating glassmorphism widget
    src/components/        ChatWidget, SettingsPanel, AlertsPanel
  launcher.py            # Entry point — setup wizard + server
  config.json            # User configuration
  Zora.spec              # PyInstaller build spec
  installer/             # Inno Setup installer script
  tests/                 # 158+ passing tests
```

---

## Development

```powershell
# Backend
cd desktop_tech_support
.venv\Scripts\activate
python -m uvicorn api.server:app --host 127.0.0.1 --port 8000 --reload

# Frontend (separate terminal)
cd ui
npm install
npm run dev

# Tests
pytest tests/ -k "not TestDiagnosticTools" -v

# Build .exe
python -m PyInstaller Zora.spec --noconfirm
```

## Safety System

- **Emergency Stop**: `Ctrl+Alt+Esc` halts all automation instantly
- **Rate Limiting**: 100 actions/minute (configurable)
- **Blacklist**: System32, critical processes protected
- **Confirmation Prompts**: High-risk actions require user permission
- **Audit Logging**: Every action logged to `logs/automation_log.jsonl`
- **Trusted Repos**: Tool downloads restricted to allowlisted GitHub repos

## Requirements

- **Windows 10/11**
- **Python 3.8+** (for running from source)
- **~4GB free space** (for Ollama models)
- **Internet** for first-time setup only (Ollama + model download)
- Optional: API key for Claude/OpenAI/Grok/Groq

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). We need help with:
- Bluetooth & VPN diagnostics
- Manufacturer-specific fix integration (Dell, HP, Lenovo CLI wrappers)
- ShowUI 2B vision integration
- Voice I/O (whisper.cpp + Windows SAPI)
- Multi-agent routing (specialist agents per category)
- Plugin system
- Localization

## Roadmap

See [Iterationplan.md](Iterationplan.md) for the full tracker.

| Version | Status | Highlights |
|---------|--------|------------|
| v1.0 | Done | CLI .exe, 8 diagnostics, safety system |
| v1.5 | Done | AI chat, React UI, Computer Use tools |
| v2.0 | Done | Flow diagnostics, monitoring, remediation, installer |
| v2.1 | Done | 6 AI providers, GitHub tool download |
| v3.0 | Planned | ShowUI vision, voice I/O, multi-agent, SQLite memory |
| v4.0 | Planned | OEM integration, family dashboard, plugins |

## License

MIT
