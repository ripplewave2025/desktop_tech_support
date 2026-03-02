# 🧠 Zora — Shared Agent Memory

> **READ THIS FIRST, EVERY SESSION.**
> This file is the shared memory between all AI agents working on this project (Antigravity/Gemini, Claude Code, any future agent). When you start a session, read this file to know what's been done. When you finish work, add your entry at the bottom with a timestamp, what you did, and what files you changed. Write in plain language. This is how we talk to each other across sessions.

---

## Project: Zora Desktop Tech Support

**What it is:** A Windows desktop AI companion that helps normal people fix their computer problems. It runs locally using Ollama (free, no cloud, no API keys). It has a floating glassmorphism chat widget UI, 23 AI tools, diagnostics, remediation, monitoring, and a setup wizard that installs everything automatically.

**Owner:** Upesh Bishwakarma (FaradaysCage007)
**Repo:** https://github.com/ripplewave2025/desktop_tech_support
**Stack:** Python (FastAPI backend) + React (Vite frontend) + Ollama (local AI) + Tauri (planned native desktop)

---

## Timeline — What Was Done, By Whom, When

### Feb 24, 2026 — Initial Foundation (Claude Code)
- Built the initial Python codebase: 8 diagnostic modules (audio, internet, printer, display, hardware, software, files, security)
- Created CLI interface (`cli/main.py`)
- Added `core/` modules: process_manager, automation, window_manager, screen_capture, input_controller, safety
- Set up `tests/` with 48 passing tests
- Created README, CONTRIBUTING.md, LIMITATIONS.md, LICENSE
- First git commit: `835ec55` — "Initial release: Desktop tech support with safety system, 48 passing tests"
- Pushed to GitHub

### Feb 27, 2026 — AI Integration (Claude Code)
- Added full `ai/` module: agent.py, tools.py, tool_executor.py
- Created provider system: ollama_provider.py, claude_provider.py, openai_provider.py, provider_factory.py
- Updated config.json with AI settings
- Added requirements.txt dependencies (anthropic, openai, httpx)
- Audio diagnostic debugging session (pycaw per-app scanning, microphone privacy checks)

### Feb 27, 2026 — First .exe Build (Antigravity/Gemini)
- Built `dist/ZoraTechSupport.exe` — 67MB CLI-only single file
- Fixed sys.stdout double-wrap crash in frozen exe (cli/main.py + diagnostics/base.py)
- Verified: --sysinfo, --diagnose hardware, --diagnose audio all working

### Feb 28, 2026 — React UI + FastAPI Backend (Antigravity + Claude)
- Scaffolded React frontend with Vite (`ui/`)
- Created ChatPanel.jsx, SystemStats.jsx, DiagnosticsPanel.jsx, SettingsPanel.jsx
- Created useChat.js (SSE streaming), useSystemStats.js, useTauri.js hooks
- Set up Tauri v2 project (`ui/src-tauri/`) — not compiled yet (needs Rust)
- FastAPI backend (`api/server.py`) with `/api/chat/stream` SSE endpoint
- Tests grew to 93 passing

### Mar 1, 2026 ~2PM — Computer Use Tools (Claude Code)
- Added 8 new Computer Use tools to Zora:
  - screenshot_and_analyze (vision via moondream model)
  - find_text_on_screen (OCR text location)
  - mouse_click / mouse_move / mouse_scroll (input control)
  - highlight_screen_area (Win32 GDI colored rectangles)
  - change_windows_setting (12 safe PowerShell commands)
  - create_support_ticket (JSON ticket + MS support link)
- Updated ai/agent.py system prompt
- Updated ai/tools.py (8 new tool definitions)
- Updated ai/tool_executor.py (8 new handlers)
- Updated ChatWidget.jsx quick action chips
- Smart tool selection: small models get 8 core tools, big models get all 23

### Mar 1, 2026 ~4PM — Floating Widget UI Redesign (Antigravity/Gemini)
- Replaced full-screen 1280x800 dashboard with compact 380x560 floating chat widget
- Created ChatWidget.jsx — compact chat with welcome state, quick actions, tool details
- Created PinMenu.jsx — pin-to-edge dropdown (top/bottom/left/right)
- Rewrote index.css — glassmorphism, typing dots, thinking spinners, custom scrollbar
- Rewrote App.jsx — floating widget shell
- Rewrote SettingsPanel.jsx — compact modal, Ollama as default
- Updated useChat.js — tool history tracking, emoji labels
- Updated useTauri.js — pinToEdge, setAlwaysOnTop commands
- Updated tauri.conf.json — 400x600, transparent, always-on-top
- Updated lib.rs — pin_to_edge Tauri command
- Changed config.json default provider to Ollama
- Dev server verified working, no console errors

### Mar 1, 2026 ~7:30PM — Full .exe Build + Setup Wizard (Claude Code)
- Created launcher.py (320 lines) — entry point with 3-step setup wizard:
  1. Auto-downloads & installs Ollama from ollama.com
  2. Pulls qwen2.5:3b + moondream models
  3. Creates desktop + Start Menu shortcuts
- Created Zora.spec — PyInstaller spec bundling React UI + FastAPI + AI + diagnostics + monitoring
- Built dist/Zora.exe — 92MB single file, self-contained
- Personality rewrite: English with Grok-style humor (replaced Hinglish)
- console=False — runs as windowed app, no terminal popup

### Mar 1, 2026 — v2.0 Enhancements (Claude Code)
- Flow-based diagnostics — 5 YAML decision trees (diagnostics/flows/):
  - internet_slow.yaml (8 steps, 4 branches)
  - no_sound.yaml (7 steps, 3 branches)
  - printer_not_working.yaml (6 steps, 3 branches)
  - slow_pc.yaml (9 steps, 5 branches)
  - wifi_disconnects.yaml (6 steps, 3 branches)
- 23 flow action functions (diagnostics/flow_actions.py)
- Remediation library — 52 structured Windows fixes across 7 categories (remediation/library.py):
  - Network (15), Audio (8), Display (6), Software (8), Hardware (5), Security (5), Printer (5)
  - Each fix has: risk level, commands, verification, rollback, reboot flag
- Proactive monitoring (monitoring/watcher.py):
  - CPU >90% sustained 2min, RAM >90%, disk <5GB, uptime >7 days, temp >85C
  - Crash loop detection, alert de-duplication, reduced polling on battery
- System tray icon (tray/tray_icon.py) — pystray with alert badges
- Real web search — DuckDuckGo search (replaced stub)
- Inno Setup installer (installer/zora_setup.iss)
- Tests grew to 158 passing

### Mar 2, 2026 — Audit + Git Commit (Antigravity/Gemini)
- Audited full codebase, found ALL v2.0 work was uncommitted
- Updated .gitignore (added .venv/, node_modules/, Tauri target, .pytest_cache)
- Committed everything as `0a6f7d4` — 82 files changed, 14,060 insertions
- Pushed to GitHub
- Created this Antigravitywork.md shared memory file

---

## Current State (as of Mar 2, 2026)

### What works
- dist/Zora.exe (92MB) — double-click, setup wizard runs, chat works in browser
- dist/ZoraTechSupport.exe (67MB) — CLI-only older version
- 23 AI tools (13 original + 8 Computer Use + run_flow_diagnostic + apply_remediation)
- Floating glassmorphism chat widget (React, dev mode via npm run dev)
- FastAPI backend with SSE streaming
- Ollama integration (qwen2.5:7b chat, moondream vision)
- 5 YAML diagnostic flows, 52 remediation fixes, proactive monitoring
- System tray icon, first-run setup wizard
- 158 tests passing

### What's NOT done yet
- [ ] provider_factory.py — graceful Ollama auto-detect (partially done)
- [ ] Tauri native build (needs Rust toolchain installed)
- [ ] Thinking/action indicators not verified with live AI
- [ ] ShowUI 2B vision (better screen understanding, replaces moondream)
- [ ] Voice I/O (whisper.cpp STT + Windows SAPI TTS)
- [ ] Multi-agent routing (specialist agents per category)
- [ ] SQLite memory (user profile, past fixes, conversation history)
- [ ] OEM integration (Dell SupportAssist, HP HPIA, Lenovo ThinInstaller)
- [ ] Family dashboard (monitor multiple PCs on LAN)
- [ ] Plugin system (YAML manifest + tools.py)

### How to run (dev mode)
```powershell
# Terminal 1: Backend
cd c:\Users\FaradaysCage007\Desktop\desktop_tech_support
.venv\Scripts\python.exe -m uvicorn api.server:app --host 127.0.0.1 --port 8000

# Terminal 2: Frontend
cd c:\Users\FaradaysCage007\Desktop\desktop_tech_support\ui
npm run dev

# Terminal 3: Ollama (if not auto-started)
ollama serve
```

---

## 📝 Agent Instructions

**When you start a session:** Read this file first. It tells you what's been done and what needs doing.

**When you finish work:** Add a new entry at the bottom of the Timeline section. Include:
- Date and approximate time
- Your name (Claude Code / Antigravity-Gemini / other)
- What you did in plain language
- What files you created or changed
- What's still broken or unfinished

**Keep it simple.** No fancy formatting. Just tell the next agent what happened.
