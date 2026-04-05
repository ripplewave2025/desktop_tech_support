# Zora — Troubleshooting Guide

Common problems and fixes. Organized by symptom, not by subsystem.

---

## Zora won't start

### `ModuleNotFoundError: No module named '...'`
You didn't activate the virtualenv, or requirements aren't installed.

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
```

### `Address already in use` / port 8000 busy
Something else is using port 8000. Kill it or change the port:

```powershell
# Find the process on port 8000
Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess
# Then: taskkill /F /PID <pid>

# Or run Zora on a different port
python -m uvicorn api.server:app --host 127.0.0.1 --port 8123
```

### `python: command not found`
Python isn't on PATH. Either reinstall with **"Add Python to PATH"** checked, or use the full path:

```powershell
C:\Python310\python.exe -m venv .venv
```

### `launcher.py` hangs on startup
Ollama may be initializing for the first time. Wait 60 seconds. If it's still hanging, launch Ollama manually:

```powershell
ollama serve
```

Leave that running in its own window, then start Zora in a second window.

---

## The AI isn't responding

### "Active: none" in Settings
Your provider isn't connected. Options:

1. **Ollama:** make sure it's running (`ollama list` should show models)
2. **Claude/OpenAI/etc:** paste your API key in Settings → Save & Connect
3. Check the backend log (`logs/zora.log`) for `Provider init failed: ...`

### Ollama says "model not found"
You need to pull the model:

```powershell
ollama pull qwen2.5:7b
```

### Responses are really slow
- **Ollama** on CPU-only: first response is 10–60s. Subsequent ones are much faster.
- **Ollama** with GPU: should be under 5s. If not, `ollama run --verbose` to see what's happening.
- **Cloud providers:** check your API key and your network.

### "Sorry, I ran into an issue: ..." in the chat
Check the backend logs. Common causes:
- API key expired or rate-limited (cloud providers)
- Ollama crashed (restart it)
- Network blocked by firewall or proxy

---

## Voice doesn't work

### No mic button
- The `Voice` section in Settings must be supported. If the section is missing, your browser doesn't support Web Speech API **and** the server-side voice backends aren't installed.
- Check browser: **Edge and Chrome work best on Windows**. Firefox does not support Web Speech API.
- If you need Firefox support, install `faster-whisper` and `pyttsx3` (see [SETUP.md](SETUP.md) step 2).

### Mic turns red, then immediately stops
- Browser denied microphone permission. Fix it:
  - **Edge:** `edge://settings/content/microphone`
  - **Chrome:** `chrome://settings/content/microphone`
  - Add `http://127.0.0.1:8000` to the allow list
- Or: the OS blocked the mic. Check **Windows Settings → Privacy → Microphone → Allow apps to access your microphone**.

### Mic hears me but nothing happens
- Open browser devtools (F12) → Console tab. Look for errors like `STT error: no-speech` or `network`.
- The most common cause is **ambient noise too low** — Web Speech API needs clear speech. Try speaking louder / closer to the mic.

### Zora speaks in a robotic voice
- That's the default Windows SAPI voice (David or Zira). To change it:
  - **Windows 10/11:** Settings → Time & Language → Speech → Manage voices → Add voices → install a natural voice like "Aria" or "Jenny"
  - The browser picks up new voices automatically

### No sound from Zora's replies
- Check system volume and output device
- Check the **Voice → Read Zora's replies aloud** toggle in Settings
- Click **Test voice output** — if that's silent, your browser or OS has blocked audio for localhost
- Try a different browser

### Server-side voice: `503 Server-side transcription unavailable`
You asked for server STT but Whisper isn't installed. Either:

```powershell
pip install faster-whisper
```

Or switch to the browser path (use Edge/Chrome).

---

## Smart home problems

### "No smart-home hub connected yet"
Normal on first run. Click **Settings → Smart Home → Set up Home Assistant** (or Hue / MQTT) to configure a backend.

### Home Assistant: `401 Unauthorized`
Your long-lived access token is wrong or expired. Create a new one:

1. In Home Assistant, click your profile (bottom-left)
2. **Security** tab → scroll to **Long-Lived Access Tokens**
3. **Create Token** — give it a name like "Zora"
4. Copy the token immediately (it's shown once)
5. In Zora, say: `reconnect Home Assistant` and paste the new token

### Home Assistant: `Connection refused` / `Name or service not known`
- Check the URL — is it `http://homeassistant.local:8123` or an IP like `http://192.168.1.50:8123`?
- Test it in a browser first. If it doesn't load there, it won't load in Zora either.
- If you're using Nabu Casa: the URL should be `https://yourid.ui.nabu.casa`

### Philips Hue: "Bridge not found"
Zora's discovery path tries (in order):
1. `discovery.meethue.com` (needs internet)
2. mDNS via zeroconf on your LAN

If both fail:
- Confirm the bridge has a solid blue light (not flashing)
- Confirm your PC is on the same LAN as the bridge
- Find the bridge IP manually: check your router's DHCP leases
- Say: `connect my Hue bridge` and enter the IP when asked

### Philips Hue: "Link button not pressed"
You need to physically press the round button on **top** of the Hue bridge, **then** within 30 seconds confirm in Zora.

### MQTT: "Connection refused"
- Check host, port, and credentials
- Test with `mosquitto_pub` or MQTT Explorer first
- If the broker requires TLS on port 8883, Zora doesn't currently support that — use port 1883 with plaintext on a trusted network

### "This MQTT topic is new — confirm?"
**That's intentional.** The first time Zora publishes to any topic, you get a confirmation gate. After the first successful publish, that topic is remembered and future publishes go straight through.

### I set up a device but Zora still asks "which device?"
Zora uses aliases. Tell it once:

```
Say: "call the kitchen downlights 'kitchen'"
```

Or use the full entity ID (`light.kitchen_downlight_01`) the first time.

---

## The consent gate won't let me do X

### "Why is Zora asking me to confirm?"
Because one of these triggered:

- The step is on the **irreversible actions** list: `unlock`, `disarm`, `open_garage`, `arm_*`, `set_temperature`, credential writes, first-use MQTT topic, installer execution, registry writes, service stops
- The step is marked `requires_confirmation: true` in its playbook
- The runtime policy engine upgraded it based on the arguments

**This is a feature, not a bug.** The whole point of Zora is to never do scary things silently.

### I keep hitting the consent gate for something safe
If a specific tool call keeps gating and it's actually routine in your environment, you can:

1. File an issue with the exact tool name and args
2. Or (advanced): edit `ai/policy.py` to exempt the specific pattern

Do **not** disable the consent gate globally.

---

## Tests fail

### `ImportError: No module named 'ai.smart_home'`
You're running tests from the wrong directory or the venv isn't active.

```powershell
cd C:\Users\<you>\Desktop\desktop_tech_support
.venv\Scripts\activate
python -m unittest tests.test_multi_agent_stack -v
```

### `AssertionError: expected an unlock smart_home_call step`
This should not happen in the current build — the lock/unlock collision was fixed via word-boundary regex matching in `ai/knowledge.py`. If you see this, your local copy of `ai/knowledge.py` may be stale. Pull the latest.

### Any test hangs forever
Windows Defender sometimes inspects subprocess launches. Either:
- Add the Zora folder to Defender exclusions
- Run tests with a timeout: `python -m unittest tests.test_multi_agent_stack -v -f` (fail fast)

---

## The UI looks broken

### Blank white page
Frontend wasn't built. Run:

```powershell
cd ui
npm install
npm run build
```

Then reload the page.

### Styles are missing / no glass effect
Your browser is too old. Chrome ≥ 76, Edge ≥ 79, Safari ≥ 15, Firefox ≥ 103. Update your browser.

### Buttons don't respond
Open devtools (F12) → Console. Look for JavaScript errors. Copy the full stack and file an issue.

---

## Credentials and privacy

### Are my HA tokens safe?
- Stored in `storage/smart_home.json` with XOR + base64 obfuscation
- **This is NOT cryptography** — a determined attacker with filesystem access can recover them
- It **does** prevent casual exposure via screenshots, grep, file sync, or tech-support screen shares
- If you need true encryption, use OS-level file encryption (BitLocker) on the Zora folder

### Is my voice sent to the cloud?
- **Browser Web Speech API (the default):** depends on your browser. Chrome and Edge send audio to Google/Microsoft servers by default. Safari uses on-device recognition for supported languages.
- **Server-side Whisper fallback:** 100% local, nothing leaves your machine.

If privacy matters, install the Whisper fallback and disable the browser mic in your browser settings so Zora uses the local path.

### Does Zora log what I say?
- Tool calls and their arguments are logged to `storage/zora.db` (SQLite)
- Raw audio is **never** stored
- Full chat history is kept in browser memory (cleared on refresh unless you're logged into the session)

To clear: delete `storage/zora.db` and restart.

---

## Still stuck?

1. Check `logs/zora.log` — search for `ERROR` or `WARNING`
2. Open browser devtools (F12) — check Console and Network tabs
3. Run the automated tests to narrow it down:
   ```powershell
   python -m unittest tests.test_multi_agent_stack -v
   ```
4. File an issue with the reproduction steps from [TESTING.md](TESTING.md)

Include the section number from TESTING.md, your browser, your OS version, and the last 40 lines of `logs/zora.log`.
