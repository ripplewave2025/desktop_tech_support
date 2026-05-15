# Zora v2.3.1 — Hardening + Depth Release

This release closes 8 of the top-10 engineering audit findings, adds the
features that make Zora actually replace a phone call to tech support, and
ships the first version that auto-updates itself.

If you're upgrading from v2.2 or earlier, **install this once manually** —
from v2.3.1 onward, Zora can update itself from Settings.

## Highlights

- **Auto-update.** Zora checks GitHub Releases on every Settings open. One
  click to download, one click to install. The installer takes care of
  closing and relaunching the app for you.
- **OS keystore for all secrets.** Your Claude / OpenAI / Grok / Groq API
  keys and your smart-home credentials now live in Windows Credential
  Manager (DPAPI-encrypted). They survive restarts and can't be stolen by
  another local user reading your project folder. **Legacy XOR-obfuscated
  smart-home secrets migrate automatically on first launch** — no action
  needed.
- **Power-user mode.** A new toggle in Settings flips Zora between plain-
  English novice mode and a technical "expert" mode (raw output, full tool
  catalog, deeper diagnostics, fewer "Anything else?" prompts). Safety
  gates still apply in both modes.
- **BSOD + Event Log triage.** Ask "why does my PC keep restarting" and
  Zora reads the System log, pulls bugcheck codes, and explains what
  IRQL_NOT_LESS_OR_EQUAL or DPC_WATCHDOG_VIOLATION actually means.
- **Silent OEM driver updates.** On Dell / HP / Lenovo, "update my
  drivers" delegates to Dell Command Update / HP Image Assistant / Lenovo
  Thin Installer in unattended mode. No Device Manager clicking.
- **Warranty lookup.** Zora reads your service tag from BIOS and builds
  the right vendor-warranty URL with it pre-filled.
- **Crash reporting.** Unhandled exceptions now write a structured dump
  to `%LOCALAPPDATA%\Zora\crashes\`. Settings → Diagnostics shows them
  and offers a one-click "Build support bundle" that ZIPs the dump plus
  the last 500 lines of the log.

## Security

- **PowerShell injection closed.** Free-form `run_powershell` is no
  longer the primary path. The agent uses a 25-operation `safe_op`
  catalog where every command is built server-side from a fixed template
  + validated parameters. Pipes, semicolons, subexpressions, and encoded
  payloads in the parameter slot all land as quoted args to a fixed
  cmdlet rather than being interpreted as shell syntax.
- **No more secrets on disk.** API keys are no longer in `config.json`.
  Smart-home tokens are no longer XOR'd in `storage/smart_home.json`.
  Both flows migrate transparently on first run, then wipe the file.
- **Single-instance enforcement.** Double-clicking Zora.exe a second
  time now opens the existing window instead of spawning a second
  uvicorn that crashes. Uses a Windows named mutex.
- **Port-conflict graceful fallback.** If port 8000 is taken, Zora walks
  up to 8019 looking for a free one. Tray icon and browser open to the
  chosen port.

## What's where (for the curious)

```
core/safe_ops.py            Named-operation catalog (security #1 fix)
core/secret_store.py        DPAPI / Windows Credential Manager wrapper
core/single_instance.py     Named mutex + port discovery
core/crash_reporter.py      File-based crash dumps + log rotation
core/bsod_analyzer.py       BSOD / bugcheck parser + 22-code explainer
core/event_log_triage.py    Grouped, annotated Event Log queries
core/updater.py             GitHub Releases poller + Inno installer
ai/oem_silent.py            Dell/HP/Lenovo silent CLI + warranty URLs
ai/agent.py                 Expert-mode prompt addendum
```

## Test coverage

This release adds ~80 new tests across:
- `tests/test_safe_ops.py` — injection rejection + dry-run argv
- `tests/test_secret_store.py` — DPAPI + legacy migration
- `tests/test_single_instance.py` — lock contention + port discovery
- `tests/test_crash_reporter.py` — install + write + prune + bundle
- `tests/test_expert_mode.py` — tool selection + prompt composition
- `tests/test_deep_windows_tools.py` — BSOD + Event Log + warranty
- `tests/test_updater.py` — version parsing + GitHub API + SHA verify

## Upgrading

If you're on v2.3.0 or earlier:

```powershell
git pull
.venv\Scripts\activate
pip install -r requirements.txt
.venv\Scripts\python.exe -m unittest discover tests -v
cd ui && npm run build && cd ..
```

Smart-home credentials migrate on first launch — no manual step needed.

## Known caveats

- **Code signing is still missing.** The .exe and installer aren't
  Authenticode-signed, so Windows SmartScreen will warn on first launch.
  This is a roadmap item once a cert is in place.
- **Auto-update relies on you tagging releases.** Tag as `v2.3.1`
  (with the `v` prefix), upload `ZoraSetup.exe` as the release asset,
  optionally upload `ZoraSetup.exe.sha256` (single line:
  `<hexdigest>  ZoraSetup.exe`).
- **The 2,400-line `ai/tool_executor.py` hasn't been split yet.** Works
  fine; just harder to navigate. Refactor is on the roadmap.

---

Closes audit items #1-#9 (see IMPROVEMENTS.md for the original audit).
