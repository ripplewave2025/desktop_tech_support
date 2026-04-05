# Zora — Manual Test Plan

This is the guide you use to verify Zora actually works, feature by feature. Each section has **what to do**, **what to expect**, and a **pass / fail** checkbox you can copy into a tracking doc.

**Total sections: 9. Plan on 20–30 minutes for a full pass.**

---

## Prerequisites

Before you start:
- [ ] Backend is running (`python launcher.py` or the .exe)
- [ ] Browser is open to **http://127.0.0.1:8000**
- [ ] An AI provider is configured (green "Active: ollama" or similar in Settings)

---

## 0. Automated test suite — sanity baseline

**Goal:** confirm nothing is broken before you touch the UI.

```powershell
.venv\Scripts\activate
python -m unittest tests.test_multi_agent_stack -v
```

**Expected output (abbreviated):**
```
test_redacted_snapshot_hides_secrets ............... ok
test_secrets_are_obfuscated_on_disk ................ ok
test_turn_off_lights_hydrates_toggle_playbook ...... ok
test_unlock_door_is_manual_gated_by_policy ......... ok
test_no_backend_configured_returns_onboarding_hint . ok
test_turn_off_lights_routes_to_smart_home .......... ok
test_unlock_door_routes_to_smart_home .............. ok
test_set_thermostat_routes_to_smart_home ........... ok
test_connect_home_assistant_routes_to_smart_home ... ok
test_bluetooth_still_routes_to_windows ............. ok
...
Ran 26 tests in 9.078s

OK
```

- [ ] 26 tests, all OK

---

## 1. Router smoke test

**Goal:** confirm the right specialist handles each kind of request.

In the chat, send each of these. Don't worry about the full response — you're just verifying the **agent name** in the "working..." indicator.

| Say this | Expected agent |
|---|---|
| `pair my bluetooth headphones` | `WindowsAgent` |
| `where is my tax PDF` | `FilesAgent` |
| `join my Zoom meeting` | `BrowserSupportAgent` |
| `what's on my screen right now` | `DesktopNavigationAgent` |
| `check my Dell for updates` | `OEMAgent` |
| `prepare a support ticket about my printer` | `SupportCaseAgent` |
| `turn off the lights` | `SmartHomeAgent` |
| `unlock the front door` | `SmartHomeAgent` |

You can peek at the routing decision in the tool indicator — it flashes the agent name briefly before the plan runs.

- [ ] All 8 requests routed to the expected agent
- [ ] "turn off the lights" does **not** get stolen by `SupportCaseAgent`
- [ ] "pair bluetooth" does **not** get stolen by `SmartHomeAgent`

---

## 2. Consent gate — the safety net

**Goal:** confirm Zora stops and asks before doing something scary.

### 2a. Installer confirmation

1. Say: `install ZoomInstaller.exe from Downloads`
2. **Expected:** a consent card appears titled like _"About to run an installer from Downloads"_ with **Confirm** and **Cancel** buttons
3. Click **Cancel**

- [ ] Consent card appeared
- [ ] Clicking Cancel stops the plan (system message says "Cancelled.")
- [ ] Nothing was launched

### 2b. Unlock door — double gate (policy upgrade)

This test only fires the consent card, not an actual unlock. You don't need a real lock configured — the gate fires at plan time.

1. Say: `unlock the front door`
2. **Expected:**
   - First, an `ask_user` card asking which lock ("Which lock should I unlock?")
   - Type any placeholder like `front_door_lock` and submit
   - Then a consent card appears titled something like _"Unlock the front door"_ with an explicit irreversibility warning
3. Click **Cancel**

- [ ] ask_user card appeared and accepted the input
- [ ] Consent card appeared with "unlock" wording
- [ ] Status showed it was manual-gated
- [ ] Clicking Cancel stopped the plan

---

## 3. Knowledge playbooks — 11 smart-home recipes

**Goal:** confirm every smart-home playbook hydrates correctly, even without real hardware.

Send each of these. Each should produce either an `ask_user` card or a `consent` card (or both). You're testing the **plan shape**, not the execution.

| Say | Expected first interaction |
|---|---|
| `turn on the living room lights` | ask_user: which device? |
| `dim the bedroom lamp to 30%` | ask_user: which device? then percentage |
| `set thermostat to 68 degrees` | ask_user: which thermostat? |
| `activate movie mode` | ask_user: which scene? |
| `is the garage door closed` | ask_user: which device? |
| `lock the front door` | ask_user: which lock? |
| `unlock the front door` | ask_user + manual gate |
| `arm the alarm` | ask_user + select mode + manual gate |
| `connect my Home Assistant` | ask_user: URL then token |
| `connect my Philips Hue bridge` | discover or ask_user: bridge IP |
| `connect my MQTT broker` | ask_user: host then credentials |

- [ ] All 11 recipes produced the expected first interaction
- [ ] Cancel at any step returns control to a normal chat state

---

## 4. Voice layer — hear Zora, talk to Zora

**Goal:** confirm the voice UI works end-to-end.

### 4a. Voice output (TTS)

1. Click **⚙ Settings**
2. Scroll to the **Voice** section — you should see **"Read Zora's replies aloud"** with a toggle
3. Flip the toggle **on**
4. Click **Test voice output**
5. **Expected:** you hear Zora say _"Hello. I am Zora. If you can hear me, voice mode is working."_
6. Close Settings
7. Back in chat, send any message
8. **Expected:** Zora's reply is spoken aloud automatically

- [ ] "Test voice output" speaks the line
- [ ] Every Zora reply in chat is read aloud when voice mode is on
- [ ] The Volume2 icon in the chat shows **Voice on** when enabled
- [ ] Flipping the toggle off silences future replies

### 4b. Voice input (STT)

1. With voice mode on, the **🎤 mic button** should appear next to the send button
2. Click the mic — it turns red and pulses
3. Speak: `"turn off the lights"`
4. Pause — the mic stops automatically after ~1 second of silence
5. **Expected:** your spoken text appears in the chat history as if you had typed it, and Zora responds

- [ ] Mic button is visible
- [ ] Clicking it starts listening (red, pulsing)
- [ ] Speech is transcribed and sent as a message
- [ ] Zora responds to the spoken message

### 4c. Barge-in (interrupt)

1. Ask Zora something that generates a long reply (e.g. `"explain what a driver is"`)
2. While Zora is speaking, click the mic
3. **Expected:** Zora stops speaking immediately; you can start a new utterance

- [ ] Speech interrupts on mic tap
- [ ] Clicking the mic while Zora is speaking cleanly stops TTS

**If voice doesn't work:**
- Check the browser — Edge and Chrome work best on Windows; Firefox does not support Web Speech API
- Check mic permissions in `chrome://settings/content/microphone`
- See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) § Voice

---

## 5. Smart home settings panel

**Goal:** confirm the Settings modal loads and shows the redacted snapshot.

1. Click **⚙ Settings**
2. Scroll to the **Smart Home** section
3. **Expected:** three rows — **Home Assistant**, **Philips Hue**, **MQTT** — each showing a state pill: **Connected** (green) or **Not set up** (gray)
4. Below: four buttons — **Set up Home Assistant**, **Set up Hue**, **Set up MQTT**, and (if any backend is configured) **List my devices**

- [ ] All three backends listed
- [ ] State pills show correctly
- [ ] Setup buttons appear

### 5a. Triggering a setup recipe from the panel

1. Click **Set up Home Assistant**
2. **Expected:** the Settings modal closes, and the chat starts the Home Assistant setup playbook (first ask_user: URL)
3. Cancel when you're done testing

- [ ] Clicking a setup button closes the modal
- [ ] The setup recipe starts in the chat immediately

### 5b. Credential redaction (if you already have HA configured)

If you have Home Assistant set up with a real token:

1. Open **http://127.0.0.1:8000/api/smart_home/status** in a new tab
2. **Expected:** the JSON shows `"token": "***"` — the real token is **never** echoed through the API

- [ ] `/api/smart_home/status` returns `token: "***"` (not plaintext)

---

## 6. Follow-up scheduler (Phase 4b)

**Goal:** confirm the follow-up pill appears when a case is due.

You need an open case with a past-due follow-up. The easiest way is to seed one via the orchestrator:

```powershell
.venv\Scripts\python.exe -c "
import sys, os
sys.path.insert(0, os.getcwd())
from ai.orchestrator import TaskOrchestrator
import datetime as dt
orch = TaskOrchestrator()
case_id = orch.create_support_case('Printer not working', 'The spooler crashes')
orch.add_follow_up(case_id, 'Check spooler status', dt.datetime(2020, 1, 1).isoformat())
print('Seeded case:', case_id)
"
```

Then reload the Zora UI.

- [ ] A bell pill appears at the top of the chat showing **"1 follow-up due"**
- [ ] Clicking **Review** starts a conversation about that case

**Cleanup:** delete `storage/zora.db` and restart to clear test cases.

---

## 7. Knowledge version endpoint

**Goal:** confirm Zora reports the right playbook inventory.

Visit **http://127.0.0.1:8000/api/knowledge/version**.

- [ ] Response lists at least 2 packs: `builtin-support-pack` and `smart-home-pack`
- [ ] Total playbook count is **26**

---

## 8. Smart-home tool dispatch (internal)

**Goal:** confirm the 8 new smart-home tool handlers are registered.

```powershell
.venv\Scripts\python.exe -c "
from ai.tool_executor import ToolExecutor
exec = ToolExecutor()
handlers = sorted([m for m in dir(exec) if m.startswith('_tool_smart_home') or m.startswith('_tool_mqtt')])
for h in handlers:
    print(' ', h)
print('Total:', len(handlers))
"
```

Expected output:
```
  _tool_mqtt_publish
  _tool_mqtt_subscribe
  _tool_smart_home_call
  _tool_smart_home_discover_hue
  _tool_smart_home_list_entities
  _tool_smart_home_query
  _tool_smart_home_set_alias
  _tool_smart_home_setup
Total: 8
```

- [ ] All 8 handlers present

---

## 9. The "grandma test" — the one that matters most

**Goal:** confirm a non-technical person can ride through a complete interaction without touching the keyboard.

With voice mode on, say each of these **out loud** (don't type):

1. `"Hello Zora"` — expect a warm greeting spoken back
2. `"What can you do for me"` — expect a plain-English overview
3. `"Turn off the lights"` — expect ask_user spoken: "Which device should I toggle?"
4. `"Bedroom"` — expect Zora to continue the plan
5. `"Cancel"` — expect cancellation confirmed

**This is the real test.** If you can do the whole thing hands-free, with spoken prompts, and everything feels like a conversation with a knowledgeable friend — Zora is working as intended.

- [ ] Full hands-free loop works
- [ ] Every reply is spoken audibly and intelligibly
- [ ] Cancellation by voice is respected
- [ ] The experience feels conversational, not commandish

---

## What passing looks like

**All green:**
- 26/26 automated tests
- 8/8 router cases
- 2/2 consent gates
- 11/11 playbooks
- 3/3 voice sub-tests
- Smart Home panel loads and works
- Knowledge endpoint reports 26 playbooks
- The grandma test works end-to-end

If any section fails, grab the error from the browser devtools console and the tail of `logs/zora.log`, then check [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

## Reporting a bug

When filing an issue, include:

1. **Section number** from this test plan
2. **What you said** (exact words)
3. **What Zora did** (exact words or screenshot)
4. **What you expected**
5. **Browser** (Edge 123, Chrome 124, etc.)
6. **Windows version** (`winver`)
7. **AI provider** (Ollama / Claude / OpenAI / ...)
8. **Tail of `logs/zora.log`** (last 40 lines)
9. **Backend logs** from the PowerShell where launcher is running

That's enough for anyone to reproduce and fix.
