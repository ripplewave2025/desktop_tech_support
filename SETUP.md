# Zora — Setup Guide

Step-by-step installation for Windows 10 / 11. Plan on **10 to 15 minutes** for a first run.

---

## 1. Prerequisites

Before you start, install these (if you don't already have them):

| Tool | Why | Link |
|---|---|---|
| **Python 3.10 or newer** | Backend runtime | [python.org/downloads](https://www.python.org/downloads/) |
| **Git** | To clone the repo | [git-scm.com](https://git-scm.com/download/win) |
| **Node.js 18 or newer** | Frontend build tools | [nodejs.org](https://nodejs.org/) |
| **Ollama** (recommended) | Free local AI — no API keys needed | [ollama.com](https://ollama.com) |

> **Note**: during Python install, **check "Add Python to PATH"**. It saves headaches later.

---

## 2. Clone and install

Open **PowerShell** (not Command Prompt) and run:

```powershell
cd ~\Desktop
git clone https://github.com/ripplewave2025/desktop_tech_support.git
cd desktop_tech_support
python -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

The last command installs about 30 Python packages. Expect **2 to 5 minutes**.

### Optional — server-side voice backends

If you want transcription and TTS **without** a browser Web Speech API (e.g. for a Tauri shell or a locked-down corporate browser), install:

```powershell
pip install faster-whisper    # STT, CPU-friendly (~150 MB model first run)
pip install pyttsx3           # TTS, offline Windows SAPI voices
```

Skip this if you're using Edge or Chrome — the browser handles voice for free.

---

## 3. Install a local AI model (Ollama)

Ollama gives you a free, local, offline AI. No data leaves your machine.

```powershell
# 1. Download and install from https://ollama.com/download
# 2. Then pull the models Zora prefers:
ollama pull qwen2.5:7b
ollama pull moondream          # optional — vision model for screen analysis
```

**Don't want Ollama?** You can use a cloud provider instead. Zora supports:

| Provider | Free tier? | Get a key |
|---|---|---|
| **Claude** (Anthropic) | Free credits for new accounts | [console.anthropic.com](https://console.anthropic.com) |
| **OpenAI** | Pay-as-you-go | [platform.openai.com](https://platform.openai.com) |
| **Grok** (xAI) | Paid | [x.ai](https://x.ai) |
| **Groq** | Generous free tier, very fast | [console.groq.com](https://console.groq.com) |

You'll paste your API key into the Settings panel after launching. It's stored in memory only for the session — not written to disk.

---

## 4. Launch Zora

```powershell
python launcher.py
```

You should see:

```
╔════════════════════════════════════════╗
║  Zora Desktop v2.3 — starting up...   ║
╚════════════════════════════════════════╝
...
✓ Ollama provider ready
✓ Task orchestrator initialized
✓ System watcher started
✓ Follow-up scheduler started (30-min interval)
✓ Listening on http://127.0.0.1:8000
```

Open your browser to **http://127.0.0.1:8000**. You'll see the Zora floating widget.

---

## 5. First run — say hi

Type or click one of the quick actions:

- `"What is on screen?"` — takes a screenshot and describes it
- `"Check WiFi"` — runs network diagnostics
- `"Where is my PDF file?"` — searches recent files
- `"Run OEM check"` — detects your laptop brand and vendor tools

If you installed Ollama, the first response takes 10 to 30 seconds while the model warms up. After that, responses stream in real time.

---

## 6. Enable voice (optional but recommended)

Zora's north star is voice-first. Here's how to enable it:

1. Click the **⚙ Settings** button in the title bar
2. Scroll to the **Voice** section
3. Click the toggle next to **Read Zora's replies aloud**
4. Click **Test voice output** — you should hear Zora's voice immediately

**Once voice mode is on:**

- A **🎤 mic button** appears next to the send button
- Tap the mic, speak, and your words are sent as a message
- Every reply from Zora is read aloud automatically
- Tap the mic a second time to interrupt Zora mid-sentence

> **Browser matters.** The built-in Web Speech API works best in **Microsoft Edge** and **Google Chrome** on Windows. Firefox does not support it — you'll need the optional server-side voice backend (step 2 above) if you prefer Firefox.

---

## 7. Connect a smart home (optional)

If you have **Home Assistant**, **Philips Hue**, or an **MQTT broker**, you can tell Zora to turn lights on, unlock doors (with confirmation), check thermostats, activate scenes, and more.

1. Click **⚙ Settings → Smart Home**
2. Pick a backend and click its **Set up** button
3. Zora will ask for the details it needs, step by step

### Home Assistant
You'll need:
- **URL** (e.g. `http://homeassistant.local:8123` or `https://yourid.ui.nabu.casa`)
- **Long-lived access token** — create one in HA under **Profile → Security → Long-Lived Access Tokens**

### Philips Hue
- Zora auto-discovers your bridge via `discovery.meethue.com` and mDNS
- When prompted, **press the round button on top of the Hue bridge**, then hit continue
- Zora stores a username credential locally — no cloud account needed

### MQTT
You'll need:
- **Host** (e.g. `homeassistant.local` or `192.168.1.50`)
- **Port** (default `1883`)
- **Username** and **Password** if your broker requires auth

**Credentials are obfuscated at rest** in `storage/smart_home.json` — not encrypted, but not plaintext either. The settings panel never echoes tokens back to you; it shows `Connected` or `Not set up` only.

---

## 8. Verify everything works

Run the automated test suite:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_multi_agent_stack -v
```

You should see:

```
Ran 26 tests in ~10s
OK
```

If any test fails, open [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

## 9. (Optional) Run the frontend in dev mode

If you want to edit the UI and see changes live:

```powershell
# Terminal 1 — backend
.venv\Scripts\activate
python -m uvicorn api.server:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2 — frontend
cd ui
npm install
npm run dev
```

The dev server runs at **http://localhost:5173** with hot reload. It proxies `/api/*` to the backend on port 8000.

---

## 10. (Optional) Build a standalone .exe

```powershell
.venv\Scripts\activate
cd ui && npm install && npm run build && cd ..
python -m PyInstaller Zora.spec --noconfirm
```

The `.exe` lands in `dist/Zora/Zora.exe`. Double-click it — Zora launches without needing Python installed. Ship this to non-technical users.

---

## What's next?

- **[TESTING.md](TESTING.md)** — walk through every feature and verify it works
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — common problems and fixes
- **[README.md](README.md)** — architecture and design principles

---

## Getting help

- Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md) first
- File an issue at [github.com/ripplewave2025/desktop_tech_support/issues](https://github.com/ripplewave2025/desktop_tech_support/issues)
- Include: Windows version, Python version, the error message, and the tail of `logs/zora.log`
