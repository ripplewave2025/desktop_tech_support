# Zora — Production Build Diary

> A running log of every build, request, fix, and improvement.
> Maintained by the dev team (human + AI collaborators).

---

## Build #001 — CLI-Only PyInstaller
**Date:** 2026-02-27 ~18:00 IST
**Requested by:** Developer
**Built by:** Antigravity (Gemini)

### What was built
- First PyInstaller single-file .exe (`ZoraTechSupport.exe`)
- CLI-only — text interface in terminal
- Core diagnostics: audio, internet, printer, display, hardware, software, files, security
- Ollama integration for AI chat (qwen2.5:3b)

### Output
- `dist/ZoraTechSupport.exe` — 66MB
- Tested working on dev machine

### Notes
- No GUI — runs in command prompt
- Ollama must be installed separately
- Basic keyword fallback when Ollama is offline

---

## Build #002 — Floating Widget UI (Dev Only)
**Date:** 2026-02-28 ~15:00 IST
**Requested by:** Developer
**Built by:** Antigravity (Gemini) + Claude

### What was built
- React frontend with glassmorphism floating widget design
- ChatWidget.jsx, PinMenu.jsx, SettingsPanel.jsx
- FastAPI backend with SSE streaming (`/api/chat/stream`)
- Tauri v2 project scaffolded (not built — needs Rust)
- 93 Python tests passing

### Components
- `ui/src/components/ChatWidget.jsx` — main chat widget
- `ui/src/hooks/useChat.js` — SSE streaming hook
- `ui/src/hooks/useTauri.js` — desktop window management
- `api/server.py` — FastAPI backend

### Notes
- Dev mode only (npm run dev + uvicorn)
- No standalone .exe yet for the UI version
- Frontend: Vite + React 19, 210KB JS bundle

---

## Build #003 — Computer Use Upgrade
**Date:** 2026-03-01 ~14:00 IST
**Requested by:** Developer
**Request:** "Full Computer Use capabilities — see screen, move mouse, click, type, scroll. Keep everything local-first."

### What was built
- 8 new Computer Use tools added to Zora:
  - `screenshot_and_analyze` — vision via moondream model
  - `find_text_on_screen` — OCR text location
  - `mouse_click` / `mouse_move` / `mouse_scroll` — input control
  - `highlight_screen_area` — Win32 GDI colored rectangles
  - `change_windows_setting` — 12 safe PowerShell commands
  - `create_support_ticket` — JSON ticket + MS support link
- Hinglish elder brother personality (later changed — see Build #004)
- Updated quick actions in UI

### Files modified
- `ai/agent.py` — full system prompt rewrite
- `ai/tools.py` — 8 new tool definitions
- `ai/tool_executor.py` — 8 new handler methods
- `ui/src/hooks/useChat.js` — tool labels
- `ui/src/components/ChatWidget.jsx` — quick action chips

### Verification
- 93 tests pass
- Frontend builds clean (210KB)
- Tested via API: vision worked, diagnostics worked, streaming worked

---

## Build #004 — Full Desktop .exe + Installer + Personality Rework
**Date:** 2026-03-01 ~19:30 IST
**Requested by:** Developer
**Request:** "Make an .exe I can send to friends. They should be able to install and use it easily. Also fix the language — simple English with Grok-like puns, not Hinglish. And make a production diary."

### Problems fixed
1. **Browser showed raw JSON at root URL** — `@app.get("/")` returned API status JSON instead of the React app. Fixed by moving it to `/api/status` so the SPA catch-all serves `index.html` at `/`.
2. **Personality was Hinglish** — Rewrote system prompt to simple English with witty, Grok-style humor. Proactive, humble, occasionally funny.
3. **No installer experience** — Friends had to manually install Ollama, pull models, etc. Created a first-run setup wizard built into the .exe.

### What was built
- **`launcher.py`** — Entry point with setup wizard + server launcher
  - First run: 3-step wizard (install Ollama → pull models → create shortcuts)
  - Normal run: starts backend, auto-opens browser
  - Creates desktop + Start Menu shortcuts
  - Detects and auto-starts Ollama
- **`Zora.spec`** — PyInstaller spec bundling everything:
  - React frontend (ui/dist)
  - FastAPI backend (api/)
  - AI modules (ai/)
  - Core automation (core/)
  - Diagnostics (diagnostics/)
  - Config (config.json)
- **Static file serving in server.py** — FastAPI serves built React app
- **New personality** — English, witty, pun-friendly:
  - "Your Wi-Fi's back! Guess it just needed some connection therapy."
  - "Found 47GB of temp files. Your PC was hoarding digital dust bunnies."

### Output
- `dist/Zora.exe` — 78MB single file
- Self-contained: backend + frontend + AI + diagnostics
- First-run wizard handles Ollama installation

### User experience
1. Friend downloads `Zora.exe`
2. Double-clicks it → Setup wizard runs (first time only)
3. Wizard installs Ollama + downloads AI models
4. Creates desktop shortcut
5. Launches Zora in browser → floating chat widget
6. Next time: just double-click, opens instantly

### Known requirements for end users
- Windows 10/11
- Internet connection (first-time model download only)
- ~4GB free disk space (Ollama + models)
- Ollama runs locally — no cloud, no API keys, no accounts

### Improvement ideas (future)
- [ ] Proactive learning — track user habits in local JSON profile
- [ ] 24h ticket follow-up reminders
- [ ] System tray icon (minimize to tray instead of taskbar)
- [ ] Auto-update mechanism
- [ ] Tauri native build (when Rust is installed) for true desktop app
- [ ] Voice input/output
- [ ] Screen recording for support tickets

---

## Architecture Overview (as of Build #004)

```
Zora.exe (PyInstaller)
├── launcher.py          — Setup wizard + server launcher
├── api/server.py        — FastAPI backend (serves UI + API)
├── ai/
│   ├── agent.py         — Agent loop + system prompt
│   ├── tools.py         — 21 tool definitions
│   ├── tool_executor.py — Tool handlers (vision, mouse, etc.)
│   ├── providers.py     — AI provider abstraction
│   ├── ollama_provider  — Ollama integration
│   ├── claude_provider  — Claude API (optional)
│   └── openai_provider  — OpenAI API (optional)
├── core/
│   ├── automation.py    — Screen capture + OCR
│   ├── input_controller — Mouse/keyboard control
│   ├── window_manager   — Window listing/focus
│   ├── process_manager  — System info + process mgmt
│   └── safety.py        — Rate limiter + blacklist
├── diagnostics/         — 8 diagnostic modules
├── ui/dist/             — Built React frontend
│   ├── index.html
│   └── assets/          — JS + CSS bundles
└── config.json          — Runtime configuration
```

---

*This diary is updated with every production build.*
