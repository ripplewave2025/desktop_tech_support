# Zora Implementation Plan & Tracker

> **Living document.** Check items off as they're completed. Any agent can update this.
> Last updated: Mar 2, 2026

---

## v1.0 — Foundation (COMPLETE)

- [x] Python codebase with 8 diagnostic modules
- [x] CLI interface (`cli/main.py`)
- [x] Core modules: process_manager, automation, window_manager, screen_capture, input_controller, safety
- [x] 48 passing tests
- [x] First .exe build (`dist/ZoraTechSupport.exe` — 67MB CLI-only)
- [x] README, CONTRIBUTING.md, LIMITATIONS.md, LICENSE
- [x] Git repo + GitHub push

## v1.5 — AI + UI (COMPLETE)

- [x] AI module: agent.py, tools.py, tool_executor.py
- [x] Provider system: ollama, claude, openai providers
- [x] React frontend (Vite) — ChatPanel, SystemStats, DiagnosticsPanel, SettingsPanel
- [x] FastAPI backend with `/api/chat/stream` SSE endpoint
- [x] Tauri v2 project scaffolded (not compiled — needs Rust)
- [x] 8 Computer Use tools (screenshot+vision, mouse, highlight, settings, tickets)
- [x] Smart tool selection (small models get 8 core, big models get all)
- [x] Floating glassmorphism chat widget (380x560, draggable)
- [x] Grok-style witty personality
- [x] 93 passing tests

## v2.0 — Flow Diagnostics + Monitoring (COMPLETE)

- [x] Flow-based diagnostics — 5 YAML decision trees
  - [x] internet_slow.yaml (8 steps, 4 branches)
  - [x] no_sound.yaml (7 steps, 3 branches)
  - [x] printer_not_working.yaml (6 steps, 3 branches)
  - [x] slow_pc.yaml (9 steps, 5 branches)
  - [x] wifi_disconnects.yaml (6 steps, 3 branches)
- [x] Flow engine (diagnostics/flow_engine.py)
- [x] 23 flow action functions (diagnostics/flow_actions.py)
- [x] Remediation library — 52 fixes across 7 categories
- [x] Proactive monitoring (monitoring/watcher.py) — CPU, RAM, disk, uptime, temp, crash loops
- [x] System tray icon (tray/tray_icon.py) — pystray with alert badges
- [x] Real web search — DuckDuckGo (replaced stub)
- [x] Chat streaming fix — removed double-call in agent.py
- [x] Inno Setup installer (installer/zora_setup.iss)
- [x] Windowed .exe fix — stdout/stderr redirect for console=False mode
- [x] 158 passing tests
- [x] Full git commit + push (`0a6f7d4`)

## v2.1 — Multi-API + Tool Download (COMPLETE)

- [x] Multi-provider support — 6 providers
- [x] Updated provider_factory.py, openai_provider.py, SettingsPanel.jsx, server.py
- [x] Tool auto-download from GitHub (trusted repos, releases API, ZIP extract)
- [x] React UI rebuilt, .exe rebuilt, git commit + push
- [x] GitHub Release v2.1.0 created with .exe

## v2.2 — Full Desktop Assistant (COMPLETE)

- [x] Merged Codex security PR (CORS, runtime API keys, PS allowlist)
- [x] Expanded PowerShell allowlist (18 → 80+ commands)
- [x] Desktop assistant tools — 6 new tools (30 total):
  - [x] `send_email` — Outlook COM or mailto: fallback
  - [x] `manage_files` — list/move/copy/rename/find/delete/get_size/organize_by_type
  - [x] `open_url` — Open URLs in default browser
  - [x] `clipboard` — Read/write system clipboard
  - [x] `remember` — Persistent notes/reminders/follow-ups (JSON)
  - [x] `notify` — Windows toast notifications
- [x] Rewritten agent system prompt for full desktop assistant
- [x] Repo cleanup — removed local config, old specs from tracking
- [x] All tests passing, UI rebuilt, .exe rebuilt (78MB)
- [x] Updated docs (WHATS_DONE.md, Antigravitywork.md, this file)
- [ ] Git commit + push v2.2

## v3.0 — Intelligence Upgrade (PLANNED)

- [ ] Vision upgrade — ShowUI 2B via Ollama (replace moondream)
  - [ ] vision/ module with provider abstraction
  - [ ] moondream_provider.py (extract from tool_executor)
  - [ ] showui_provider.py
  - [ ] `locate_and_click` tool
- [ ] Voice I/O
  - [ ] whisper.cpp STT (subprocess call to whisper.exe)
  - [ ] Windows SAPI TTS (built-in, zero dep)
  - [ ] Microphone capture (sounddevice)
  - [ ] `/api/voice/transcribe` + `/api/voice/speak` endpoints
  - [ ] Mic button in ChatWidget.jsx
- [ ] Multi-agent routing
  - [ ] ai/router.py — intent classifier + specialist dispatch
  - [ ] NetworkAgent, AudioAgent, SecurityAgent, PerformanceAgent
  - [ ] Only for large models (13b+, Claude, GPT)
- [ ] SQLite memory
  - [ ] storage/db.py — user_profile, fix_history, hardware_profile, conversation_log
  - [ ] Auto-detect OEM, model, CPU, GPU, RAM via WMI
  - [ ] "I remember fixing this before" capability
- [ ] Tauri native build (real floating window — needs Rust toolchain)

## v4.0 — Enterprise & Ecosystem (PLANNED)

- [ ] OEM tool integration (Dell SupportAssist, HP HPIA, Lenovo ThinInstaller)
- [ ] Family dashboard (monitor multiple PCs on LAN)
- [ ] Plugin system (YAML manifest + tools.py per plugin)
- [ ] B2B/MSP features (remote diagnostics, ticket system, batch remediation)

---

## Quick Reference

| Version | Status | Key Milestone |
|---------|--------|---------------|
| v1.0 | DONE | CLI .exe with 8 diagnostic modules |
| v1.5 | DONE | AI chat + React UI + Computer Use tools |
| v2.0 | DONE | Flow diagnostics, monitoring, remediation, installer |
| v2.1 | DONE | Multi-API (6 providers), GitHub tool download |
| v2.2 | DONE | Desktop assistant: email, files, clipboard, memory, notifications |
| v3.0 | PLANNED | ShowUI vision, voice I/O, multi-agent, SQLite memory |
| v4.0 | PLANNED | OEM integration, family dashboard, plugins |
