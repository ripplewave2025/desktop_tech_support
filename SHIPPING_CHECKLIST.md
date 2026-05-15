# Shipping Zora v2.3.1 — Step-by-Step

A checklist for cutting and publishing a Zora release. Run these in order
on your Windows machine. If anything reds out, stop and fix before moving
on — don't ship something half-broken.

## 0. Prereqs

- [ ] Windows 10 or 11
- [ ] Python 3.10+ in `.venv` at the project root
- [ ] Node.js 18+ on PATH
- [ ] [Inno Setup 6](https://jrsoftware.org/isinfo.php) installed (one-time)
- [ ] You're on the `main` branch with a clean working tree (`git status` shows nothing)

## 1. Sanity-check the version

The version lives in **one** place. Confirm:

```powershell
type core\version.py
```

You should see `ZORA_VERSION = "2.3.1"`. Also confirm `installer\zora_setup.iss`
has `#define MyAppVersion "2.3.1"` near the top.

If you're about to ship a NEW version (not 2.3.1), bump both files together.

## 2. Install dependencies

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
cd ui
npm install
cd ..
```

Watch for any new packages — `keyring>=24.0.0` was added in v2.3.1.

## 3. Run the full test suite

```powershell
.venv\Scripts\python.exe -m unittest discover tests -v
```

Expected: all green. The new test files added in v2.3.1 are:
- `test_safe_ops.py`
- `test_secret_store.py`
- `test_single_instance.py`
- `test_crash_reporter.py`
- `test_expert_mode.py`
- `test_deep_windows_tools.py`
- `test_updater.py`

If any test fails, fix it before continuing. Don't ship a red build.

## 4. Smoke-test the new features manually

Before building, give each new flow a real try.

- [ ] **Single-instance**: launch `python launcher.py` twice. Second one
      should print "Zora is already running at http://127.0.0.1:8000"
      and open it in the browser, then exit.
- [ ] **Port fallback**: with a Zora running, run
      `python -m http.server 8000` in a separate shell. Stop Zora, launch
      again — it should pick 8001.
- [ ] **DPAPI secrets**: enter a fake Claude API key in Settings → Save.
      Restart Zora. Reopen Settings — `has_api_key` should be true, but
      `type config.json` should NOT contain the key.
- [ ] **Expert mode**: toggle on. Verify the ⚡ Expert badge appears in
      the chat header within ~5s. Ask "what's running" — output should
      lean technical.
- [ ] **Diagnostics panel**: open Settings → expand Diagnostics. Should
      show empty crash list (good), BSOD list (may be empty if you've
      never blue-screened), and Event Log triage with at least a few
      entries.
- [ ] **Update checker**: open Settings. Should show "You're up to date"
      (since this IS the latest). Don't click Download yet — there's no
      release to download.

## 5. Build the frontend

```powershell
cd ui
npm run build
cd ..
```

This produces `ui\dist\`. Verify it exists and has an `index.html`.

## 6. Build the .exe with PyInstaller

```powershell
.venv\Scripts\python.exe -m PyInstaller Zora.spec --clean
```

Output: `dist\Zora.exe`. Should be ~80-95 MB. If size is way off,
something went sideways with the spec file.

Quick check:

```powershell
dist\Zora.exe
```

It should launch, run setup if first-run, open the browser.

## 7. Build the installer with Inno Setup

```powershell
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\zora_setup.iss
```

Output: `installer\output\ZoraSetup.exe`. **The filename must be exactly
"ZoraSetup.exe"** — the auto-updater looks for that name.

Smoke-test by running the installer on a clean VM or sandbox:

```powershell
installer\output\ZoraSetup.exe
```

Confirm:
- [ ] It installs to `C:\Program Files\Zora\`
- [ ] Start Menu + Desktop shortcuts work
- [ ] Uninstaller cleans up

## 8. Compute the SHA-256

```powershell
certutil -hashfile installer\output\ZoraSetup.exe SHA256
```

Copy the hex digest. You'll paste it into a `ZoraSetup.exe.sha256` file
in step 10.

## 9. Tag and push

```powershell
git add -A
git commit -m "Release v2.3.1"
git tag v2.3.1
git push origin main --tags
```

## 10. Create the GitHub Release

In the GitHub UI:

1. Releases → "Draft a new release"
2. Choose tag `v2.3.1`
3. Title: `Zora v2.3.1 — Hardening + Depth Release`
4. Body: paste the contents of `RELEASE_NOTES_2.3.1.md`
5. Attach files:
   - `installer\output\ZoraSetup.exe`
   - `ZoraSetup.exe.sha256` — a one-line text file:
     ```
     <hexdigest_from_step_8>  ZoraSetup.exe
     ```
6. Publish.

## 11. End-to-end auto-update smoke test

On a separate machine (or a fresh VM) that has v2.3.0 installed:

- [ ] Launch Zora → Settings → confirm "Update available: v2.3.1"
- [ ] Click "Download installer" — wait for it to finish
- [ ] Verify the SHA-256 row shows `✓ verified`
- [ ] Click "Restart and install" — Zora should close, the Inno installer
      should run silently, and Zora should relaunch on v2.3.1

If this works, **you've shipped a real product.** That's the moment to
actually breathe.

## 12. Post-release housekeeping

- [ ] Bump `core/version.py` and `installer/zora_setup.iss` to the next
      working version (e.g. `2.3.2-dev` or `2.4.0`)
- [ ] Push the bump as a fresh commit on `main`
- [ ] Update `WHATS_DONE.md` with a "Released" note for v2.3.1

## Troubleshooting

**PyInstaller picks up extra packages and the .exe balloons past 200 MB.**
Check `Zora.spec` for over-broad `hiddenimports`. Each provider's SDK
should only be bundled when you're shipping a release that supports it.

**Inno Setup compile fails.** Verify `assets\zora_icon.ico` exists at the
path the script references. If not, comment out `SetupIconFile=` and try
again.

**Auto-updater says "no asset named ZoraSetup.exe".** The Inno output
filename must be exactly that — no version suffix. Check
`OutputBaseFilename` in `zora_setup.iss`.

**SmartScreen "Unrecognized publisher" on first run.** Expected without a
signing cert. Users can click "More info" → "Run anyway". Code signing is
the next roadmap item.
