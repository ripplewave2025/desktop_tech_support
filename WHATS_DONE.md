# Zora v2.1 — What's Done, What's Next

> **Living doc.** Updated every session so all agents stay in sync.
> Last updated: Mar 2, 2026

## What's Built (Working Now)

### v1.0 Foundation
- **Single .exe** (`dist/Zora.exe` — 93MB) — double-click, browser opens, chat works
- **First-run setup wizard** — auto-installs Ollama, pulls AI models, creates desktop shortcut
- **Glassmorphism floating chat widget** — React frontend served by FastAPI
- **8 Computer Use tools** — screenshot+vision, mouse control, screen highlight, Windows settings, support tickets
- **13 original tools** — diagnostics, process manager, PowerShell, OCR, window management
- **Smart tool selection** — small models (3b/7b) get 8 core tools, big models get all 23
- **Auto-retry without tools** — if Ollama chokes on tool schemas, falls back to plain chat
- **Ollama local AI** — qwen2.5:7b for chat, moondream for vision. Zero cloud, zero cost
- **Witty Grok-style personality** — puns, emojis, short punchy messages

### v2.0 Enhancements
- **Flow-based diagnostics** — 5 YAML decision trees that branch like real tech support
  - Internet Slow (8 steps, 4 branches)
  - No Sound (7 steps, 3 branches)
  - Printer Not Working (6 steps, 3 branches)
  - PC Running Slow (9 steps, 5 branches)
  - WiFi Disconnects (6 steps, 3 branches)
- **23 flow action functions** — reusable checks for network, audio, printer, performance
- **Remediation library** — 52 structured Windows fixes across 7 categories
  - Network (15), Audio (8), Display (6), Software (8), Hardware (5), Security (5), Printer (5)
  - Each fix has: risk level, commands, verification, rollback, reboot flag
- **Proactive monitoring** — background SystemWatcher thread
  - CPU >90% sustained 2min, RAM >90%, disk <5GB, uptime >7 days, temp >85C
  - Crash loop detection (3 crashes in 5 minutes)
  - Alert de-duplication within 10-minute windows
  - Reduced polling on battery (2min vs 30s on AC)
- **System tray icon** — pystray-based with alert badges, context menu
- **Real web search** — DuckDuckGo search (replaced stub)
- **Chat streaming fix** — removed double-call inefficiency in agent.py
- **Inno Setup installer** — professional Windows installer with:
  - Program Files installation + uninstaller
  - Optional Ollama auto-download during setup
  - Optional startup entry
  - Firewall exception for localhost:8000
- **23 AI tools** (up from 21) — added `run_flow_diagnostic` and `apply_remediation`
- **158 tests passing** (up from 93)

### v2.1 Enhancements (NEW — Mar 2, 2026)
- **Multi-provider AI support** — 6 providers now:
  - **Ollama** (local, free, default)
  - **Claude** (Anthropic API — needs ANTHROPIC_API_KEY)
  - **OpenAI** (GPT-4o — needs OPENAI_API_KEY)
  - **Grok** (xAI — needs XAI_API_KEY, OpenAI-compatible)
  - **Groq** (fast inference — needs GROQ_API_KEY, OpenAI-compatible)
  - **Custom** (any OpenAI-compatible endpoint — needs api_key + base_url)
- **Provider factory** rewritten — all OpenAI-compatible providers share one code path
- **Settings UI updated** — dropdown with all 6 providers, smart placeholders per provider
- **Tool auto-download from GitHub** — Zora can download missing tools at runtime
  - Trusted repo allowlist for security
  - GitHub Releases API integration
  - Auto-extract ZIPs to %LOCALAPPDATA%\Zora\tools\
- **24 AI tools** (up from 23) — added `download_tool`
- **Windowed .exe fix** — stdout/stderr redirect to log file when console=False

### v2.2 Desktop Assistant (NEW — Mar 2, 2026)
- **Merged Codex security PR** — CORS lockdown, runtime-only API keys, PowerShell allowlist
- **6 new desktop assistant tools** (30 AI tools total):
  - **send_email** — Draft emails via Outlook COM or mailto: fallback (never auto-sends)
  - **manage_files** — List, move, copy, rename, find, delete, get_size, organize_by_type
  - **open_url** — Open websites in default browser
  - **clipboard** — Read/write system clipboard
  - **remember** — Persistent notes, reminders, follow-ups across sessions
  - **notify** — Windows toast notifications
- **Expanded PowerShell allowlist** — 80+ commands covering all remediation, diagnostics, and assistant needs
- **Rewritten system prompt** — covers full desktop assistant use cases, guides AI for non-tech users
- **Repo cleanup** — removed local config, old specs, dev diaries from git tracking

## Architecture

```
Layer 1: PERCEPTION        Layer 2: UNDERSTANDING     Layer 3: REASONING
  screen_capture.py          agent.py SYSTEM_PROMPT     agent.py (tool loop)
  tool_executor.py           tools.py (tool matching)   flow_engine.py (YAML trees)
  monitoring/watcher.py

Layer 4: ACTION            Layer 5: MEMORY
  tool_executor.py           remember tool → notes.json
  flow_actions.py            (%LOCALAPPDATA%\Zora\memory\)
  remediation/library.py     (planned: SQLite upgrade)
```

## File Count
- 27+ Python backend files
- 11 React frontend files
- 5 YAML diagnostic flow files
- 11 test files
- 1 Inno Setup installer script

## For Your Friend
1. Send them `dist/Zora.exe` (93MB)
2. They double-click it -> setup wizard runs (installs Ollama + models)
3. After setup, Zora opens in browser at `http://127.0.0.1:8000`
4. System tray icon stays in background
5. Requirements: Windows 10/11, ~4GB free space, internet for first setup only
6. **Cloud AI option:** Set provider to Claude/OpenAI/Grok in Settings (needs API key)

## What Changed in v2.1

| File | Change |
|------|--------|
| `ai/provider_factory.py` | Rewritten — 6 providers, PROVIDER_DEFAULTS dict |
| `ai/openai_provider.py` | Added `base_url` param for Grok/Groq/Custom |
| `ai/tools.py` | Added `download_tool` definition (24 tools total) |
| `ai/tool_executor.py` | Added TRUSTED_REPOS + `_tool_download_tool()` handler |
| `api/server.py` | Updated providers list + env var checks |
| `ui/src/components/SettingsPanel.jsx` | 6 providers in dropdown |
| `launcher.py` | stdout/stderr fix for windowed .exe mode |

## What's Next (v3.0 Roadmap)
1. **ShowUI 2B vision** — better screen understanding via Ollama (replaces moondream)
2. **Voice I/O** — whisper.cpp for speech-to-text, Windows SAPI for text-to-speech
3. **Multi-agent routing** — specialist agents for network, audio, security, performance
4. **SQLite memory** — remember user profile, past fixes, conversation history
5. **OEM integration** — Dell SupportAssist, HP HPIA, Lenovo ThinInstaller CLI wrappers
6. **Family dashboard** — monitor multiple PCs on local network
7. **Plugin system** — YAML manifest + tools.py for extensibility
