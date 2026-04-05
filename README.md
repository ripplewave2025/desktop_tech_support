# Zora — Your Talking Desktop Assistant

**A Windows tech support and smart-home companion you can talk to.** Zora is built for people who have never used a computer. You tell it what you need — by voice or by typing — and it figures out the rest. It asks before doing anything scary. It remembers what you like. It works offline if you want it to.

> **Mission:** Make a computer usable by someone who has never touched one, just by talking to it.

---

## What Zora can do

| Category | What you say | What Zora does |
|---|---|---|
| **Smart home** | "Turn off the bedroom lamp" | Finds the device, toggles it, confirms back |
| **Smart home** | "Unlock the front door" | **Asks you first** — unlocking is never automatic |
| **Smart home** | "Connect my Philips Hue" | Discovers the bridge, walks you through the button press |
| **Windows** | "Pair my Bluetooth headphones" | Opens Settings to the right page, walks you through |
| **Windows** | "My internet isn't working" | Runs a diagnostic, proposes a fix, asks before applying |
| **Files** | "Where is my tax PDF?" | Searches, lists candidates, opens the one you pick |
| **Browser** | "Join my Zoom meeting" | Opens Zoom in the right browser with the right link |
| **OEM** | "Check my Dell for updates" | Detects your laptop, uses Dell SupportAssist |
| **Tickets** | "Prepare a support case about my printer" | Builds a ticket with system info + follow-up tracking |

Zora has **7 specialist agents**, **26 guided playbooks**, and a **policy engine** that refuses to do irreversible things without your explicit permission.

---

## What's new in this build

- **Voice layer** — tap the mic and speak. Zora speaks back when voice mode is on.
- **Smart home** — Home Assistant, Philips Hue, and MQTT support with obfuscated credential storage and a dedicated settings panel.
- **Multi-agent orchestrator** — 7 specialists, each with their own tools.
- **Guided playbooks** — 26 step-by-step recipes. Recipes can ask you questions mid-flight.
- **Consent gates** — every irreversible action (unlock, disarm, install, credential write) requires your explicit yes.
- **Follow-up scheduler** — Zora remembers open cases and surfaces them when they're due.
- **Word-boundary knowledge matching** — "lock" and "unlock" no longer collide.

**26/26 tests green.** See [TESTING.md](TESTING.md) for the full manual test plan.

---

## Quick start (5 minutes)

### 1. Install

```powershell
git clone https://github.com/ripplewave2025/desktop_tech_support.git
cd desktop_tech_support
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Install Ollama (free, local AI — recommended)

Download Ollama from [https://ollama.com](https://ollama.com), then:

```powershell
ollama pull qwen2.5:7b
ollama pull moondream     # optional, for vision
```

**Or** use a cloud provider (Claude, OpenAI, Grok, Groq) — paste your API key in Settings after launching.

### 3. Launch

```powershell
python launcher.py
```

Zora opens at `http://127.0.0.1:8000`. That's it.

### 4. Try it

Click the 🎤 mic button or just type:

- `"turn off the lights"` — Smart home
- `"pair my bluetooth headphones"` — Windows
- `"where is my tax PDF"` — Files
- `"my wifi is slow"` — Diagnostics

For voice mode, click **Settings → Voice → Read Zora's replies aloud**. Then the mic button becomes push-to-talk and Zora reads every reply.

See **[SETUP.md](SETUP.md)** for full installation and first-run walkthrough.
See **[TESTING.md](TESTING.md)** for the manual test plan.
See **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** when something goes wrong.

---

## The architecture in one picture

```
  You (voice or text)
        │
        ▼
  ┌─────────────┐
  │   Router    │  ← decides which specialist handles the request
  └─────────────┘
        │
        ▼
  ┌──────────────────────────────────────────────────────┐
  │  7 specialist agents                                 │
  │  WindowsAgent · FilesAgent · BrowserSupportAgent     │
  │  DesktopNavigationAgent · OEMAgent · SupportCaseAgent│
  │  SmartHomeAgent ← new                                │
  └──────────────────────────────────────────────────────┘
        │
        ▼
  ┌─────────────┐        ┌────────────────┐
  │  Knowledge  │───────►│  Orchestrator  │  ← hydrates recipes with {user.*} slots
  │  26 recipes │        │                │
  └─────────────┘        └────────────────┘
                                 │
                                 ▼
                         ┌───────────────┐
                         │    Policy     │  ← upgrades dangerous steps to require confirmation
                         │    engine     │
                         └───────────────┘
                                 │
                                 ▼
                         ┌───────────────┐
                         │  Consent gate │  ← plain-English preview, big Yes / No
                         │     (UI)      │
                         └───────────────┘
                                 │
                                 ▼
                         ┌───────────────┐        ┌─────────┐
                         │ Tool executor │───────►│ SQLite  │  ← everything logged
                         └───────────────┘        │ memory  │
                                                  └─────────┘
```

### Design principles

1. **Never assume knowledge.** Playbooks read like a human walking you through it on the phone.
2. **Never silently do scary things.** Unlock, disarm, install, credential write → consent gate.
3. **Never strand the user.** No backend configured → onboarding hint, not a stack trace.
4. **Never make the user remember.** Aliases, profiles, follow-ups, SQLite memory.
5. **Never mix concerns.** Seven specialist agents, one router. Add a new agent to add new powers.

---

## Project structure

```
desktop_tech_support/
├── ai/
│   ├── agents/              # 7 specialists (Router / Windows / Files / Browser / Desktop / OEM / SupportCase / SmartHome)
│   ├── orchestrator.py      # Hydrates recipes, runs steps, emits SSE events
│   ├── policy.py            # Consent-gate upgrade logic
│   ├── knowledge.py         # Playbook matcher with word-boundary tag scoring
│   ├── router.py            # Keyword → specialist dispatch
│   ├── tool_executor.py     # 30+ tool handlers (incl. 8 smart-home tools)
│   └── smart_home/          # HA / Hue / MQTT clients + obfuscated credential store
├── knowledge/packs/
│   ├── builtin-support-pack/    # 15 core recipes
│   └── smart-home/              # 11 smart-home recipes
├── api/
│   └── server.py            # FastAPI + SSE streaming + voice endpoints
├── ui/                      # React + Vite floating widget
│   └── src/
│       ├── hooks/useVoice.js    # Browser Web Speech API with server fallback
│       ├── components/ChatWidget.jsx
│       └── components/SettingsPanel.jsx
├── tests/
│   └── test_multi_agent_stack.py   # 26 tests covering all phases
└── docs/
    └── MULTI_AGENT_IMPLEMENTATION.md
```

---

## Voice layer details

**Primary path: browser Web Speech API.**
- Works in Edge, Chrome, Safari 14.5+ on Windows 10/11.
- Zero install, zero latency, microphone permission handled by the browser.
- No audio ever leaves your machine for the common path.

**Fallback path: server-side Whisper + pyttsx3.**
- If your browser doesn't support Web Speech API, Zora records a blob and POSTs it to `/api/voice/transcribe`.
- Install `faster-whisper` (recommended) or `openai-whisper` to enable.
- Server TTS via `pyttsx3` uses Windows SAPI voices offline.

**Endpoints:**
- `GET  /api/voice/capabilities` — report what's installed
- `POST /api/voice/transcribe` — audio bytes → text (optional, needs Whisper)
- `POST /api/voice/speak` — text → WAV stream (optional, needs pyttsx3)

---

## Smart home details

**Supported backends:**

| Backend | Protocol | Setup |
|---|---|---|
| **Home Assistant** | REST (`/api/states`, `/api/services/*`) | URL + long-lived access token |
| **Philips Hue** | LAN JSON API + mDNS discovery + physical button pairing | Bridge IP + username (auto-created) |
| **MQTT** | paho-mqtt (Zigbee2MQTT, Tasmota, etc.) | Host + port + credentials |

**Credential storage:**
- Stored in `storage/smart_home.json`
- Secrets XOR+base64 obfuscated with a module-level key
- **NOT cryptography** — but prevents screenshot/grep/sync spillage
- `redacted_snapshot()` never echoes tokens to the UI or API

**Policy gates that fire automatically:**
- Saving any credential → confirmation required
- First publish to a new MQTT topic → confirmation required (remembered after first success)
- Unlock / disarm / open_garage / arm_* → manual gate + confirmation
- Temperature changes → confirmation required

**Endpoints:**
- `GET /api/smart_home/status` — redacted snapshot (tokens → `***`)

---

## Testing

See **[TESTING.md](TESTING.md)** for the full walkthrough. Quick version:

```powershell
# Automated tests (26/26)
.venv\Scripts\python.exe -m unittest tests.test_multi_agent_stack -v

# Backend smoke test
.venv\Scripts\python.exe -c "from api.server import app; print('OK')"

# Frontend build
cd ui && npm run build
```

---

## Requirements

- **Windows 10 or 11**
- **Python 3.10+**
- **Node.js 18+** (for frontend dev)
- **~4 GB disk** (for Ollama models)
- **Microphone** (optional, for voice)
- **Speakers** (optional, for voice)
- **Modern browser** (Edge or Chrome for best Web Speech API support)

Optional for smart home:
- Home Assistant instance (Nabu Casa, local, or Supervisor)
- Philips Hue bridge on the same LAN
- An MQTT broker (Mosquitto, HiveMQ, AWS IoT)

Optional for server-side voice:
- `pip install faster-whisper` (STT)
- `pip install pyttsx3` (TTS)

---

## License

MIT. See [LICENSE](LICENSE).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Acknowledgements

Built with Claude, FastAPI, React, Vite, Ollama, Home Assistant, paho-mqtt, faster-whisper, and pyttsx3.
