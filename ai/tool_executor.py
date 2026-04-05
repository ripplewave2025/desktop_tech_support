"""
Tool Executor — bridges AI tool calls to existing codebase capabilities.

Every tool handler routes through the existing AutomationController
(which enforces safety checks) or uses the diagnostic modules directly.
Includes Computer Use tools (vision, mouse, keyboard, screen highlight).
"""

import json
import subprocess
import asyncio
import base64
import os
import time
import threading
import datetime
from typing import Dict, Any, Optional, List
from io import BytesIO

from core.process_manager import ProcessManager


_SECRET_FIELD_HINTS = ("token", "password", "secret", "api_key", "apikey", "passphrase", "pin")


def _looks_secret(field: str) -> bool:
    """Return True if a user-profile field name looks like a credential.

    Used to redact secrets from tool results so tokens never land in plan
    summaries, chat transcripts, or the SQLite store.
    """
    if not field:
        return False
    lowered = field.lower()
    return any(hint in lowered for hint in _SECRET_FIELD_HINTS)


class ToolExecutor:
    """Executes tool calls from the AI agent, routing through safety system."""

    def __init__(self, automation=None):
        # Lazy-init AutomationController to avoid import issues in tests
        self._auto = automation
        self._pm = ProcessManager()

        # Playwright state — lazy, single persistent context so logins stick.
        # Created on the first browser_* call, reused thereafter, torn down
        # by browser_close.
        self._pw = None
        self._pw_context = None
        self._pw_page = None

        # PowerShell allowlist — commands Zora is permitted to run.
        # Covers diagnostics, remediation, flow actions, and desktop assistant tasks.
        self._powershell_allowlist = {
            # --- Read-only / info gathering ---
            "Get-Process", "Get-Service", "Get-ComputerInfo",
            "Get-NetAdapter", "Get-NetIPConfiguration", "Get-DnsClientServerAddress",
            "Get-Volume", "Get-PSDrive", "Get-WinEvent", "Get-EventLog",
            "Get-CimInstance", "Get-ItemProperty", "Get-Content",
            "Get-Printer", "Get-PrinterPort", "Get-PrintJob",
            "Get-NetIPAddress", "Get-NetRoute", "Get-NetFirewallProfile",
            "Get-MpComputerStatus", "Get-MpThreatDetection",
            "Get-ChildItem", "Get-Item", "Get-Date", "Get-Clipboard",
            "Get-AudioDevice", "Get-StartApps", "Get-AppxPackage",
            "Get-WindowsOptionalFeature", "Get-HotFix",
            "Test-NetConnection", "Test-Path", "Test-Connection",
            "Measure-Object", "Select-Object", "Where-Object",
            "Sort-Object", "Format-List", "Format-Table",
            "Out-File", "Out-String",
            "ipconfig", "ping", "nslookup", "tracert", "netstat",
            "tasklist", "whoami", "winget", "systeminfo", "hostname",
            "cmdkey", "klist",
            # --- Service management (for fixing audio, print, network) ---
            "Restart-Service", "Start-Service", "Stop-Service",
            # --- Remediation commands ---
            "Start-MpScan",                    # Defender scan
            "Set-DnsClientServerAddress",      # Fix DNS
            "Set-NetFirewallProfile",          # Firewall toggle
            "Set-ItemProperty",                # Registry tweaks (dark mode, proxy, UAC check)
            "Enable-NetAdapter", "Disable-NetAdapter",  # Network adapter reset
            "Start-Process",                   # Open settings pages / apps
            "Remove-Item",                     # Temp file cleanup (restricted by safety prompt)
            "Clear-DnsClientCache",            # DNS flush
            # --- System maintenance ---
            "sfc", "DISM", "chkdsk",           # System repair
            "cleanmgr", "wsreset.exe",         # Cleanup utilities
            "powercfg",                        # Power management
            "msdt.exe",                        # Built-in troubleshooters
            "rundll32",                        # Print test page, etc.
            "mmsys.cpl", "devmgmt.msc", "printmanagement.msc",  # Control panel applets
            "sndvol.exe", "taskmgr",           # System utilities
            # --- Network ---
            "netsh",                           # Network config (wlan, firewall, winsock)
            "rasdial",                         # VPN disconnect
            # --- Desktop assistant: file & app management ---
            "Copy-Item", "Move-Item", "Rename-Item", "New-Item",
            "Compress-Archive", "Expand-Archive",
            "Set-Clipboard",
            "Start-ScheduledTask", "Get-ScheduledTask",
            # --- Desktop assistant: email via Outlook COM ---
            "New-Object",                      # COM object creation (Outlook.Application)
            "Send-MailMessage",                # SMTP email
        }

        # Vision model for screen analysis
        self._vision_model = os.environ.get("ZORA_VISION_MODEL", "moondream")
        self._ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

    def _get_automation(self):
        """Lazy-load AutomationController."""
        if self._auto is None:
            from core.automation import AutomationController
            self._auto = AutomationController()
        return self._auto

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool call and return the result as a dict."""
        handler = getattr(self, f"_tool_{tool_name}", None)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}
        try:
            result = handler(arguments)
            # Support both sync and async handlers
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except Exception as e:
            return {"error": str(e), "tool": tool_name}

    # ─── Diagnostic Tools ────────────────────────────────────

    def _tool_run_diagnostic(self, args: Dict) -> Dict:
        """Run a diagnostic category using the existing diagnostic modules."""
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        from cli.main import DIAGNOSTIC_MODULES, load_diagnostic
        from diagnostics.base import TechSupportNarrator

        category = args["category"]
        if category not in DIAGNOSTIC_MODULES:
            return {"error": f"Unknown diagnostic category: {category}"}

        # Use a non-printing narrator to capture log
        narrator = TechSupportNarrator(verbose=False)
        DiagClass = load_diagnostic(category)
        diag = DiagClass(narrator=narrator)
        results = diag.diagnose()

        return {
            "category": category,
            "results": [
                {
                    "name": r.name,
                    "status": r.status,
                    "details": r.details,
                    "fix_available": r.fix_available,
                }
                for r in results
            ],
            "total_checks": len(results),
            "issues_found": sum(1 for r in results if r.status != "ok"),
        }

    def _tool_apply_fix(self, args: Dict) -> Dict:
        """Apply an auto-fix for a specific diagnostic issue."""
        import diagnostics.base
        from cli.main import DIAGNOSTIC_MODULES, load_diagnostic
        from diagnostics.base import TechSupportNarrator, DiagnosticResult

        category = args["category"]
        issue_name = args["issue_name"]

        if category not in DIAGNOSTIC_MODULES:
            return {"error": f"Unknown diagnostic category: {category}"}

        # Auto-approve for API context (UI already confirmed)
        original_ask = diagnostics.base.ask_permission
        diagnostics.base.ask_permission = lambda msg: True

        try:
            narrator = TechSupportNarrator(verbose=False)
            DiagClass = load_diagnostic(category)
            diag = DiagClass(narrator=narrator)

            dummy_result = DiagnosticResult(name=issue_name, status="warning")
            success = diag.apply_fix(dummy_result)

            return {
                "success": success,
                "issue_name": issue_name,
                "category": category,
                "narrator_log": narrator.log,
            }
        finally:
            diagnostics.base.ask_permission = original_ask

    # ─── System Info Tools ───────────────────────────────────

    def _tool_get_system_info(self, args: Dict) -> Dict:
        """Get system resource usage."""
        info = self._pm.get_system_info()
        return {
            "cpu_percent": info.cpu_percent,
            "cpu_count": info.cpu_count,
            "memory_percent": info.memory_percent,
            "memory_used_gb": round(info.memory_used_gb, 1),
            "memory_total_gb": round(info.memory_total_gb, 1),
            "disk_free_gb": round(info.disk_free_gb, 1),
            "disk_percent": info.disk_percent,
            "uptime_hours": round(info.uptime_hours, 1),
        }

    def _tool_list_processes(self, args: Dict) -> Dict:
        """List running processes."""
        name_filter = args.get("name_filter")
        procs = self._pm.list_processes(name_filter)
        return {
            "processes": [
                {
                    "pid": p.pid,
                    "name": p.name,
                    "cpu_percent": p.cpu_percent,
                    "memory_mb": round(p.memory_mb, 1),
                }
                for p in procs[:25]
            ],
            "total": len(procs),
        }

    def _tool_kill_process(self, args: Dict) -> Dict:
        """Kill a process by name or PID."""
        auto = self._get_automation()
        target = args["name_or_pid"]
        if target.isdigit():
            target = int(target)
        force = args.get("force", False)

        result = auto.kill_process(target, force=force)
        return {"killed": result, "target": str(args["name_or_pid"])}

    # ─── Screen & Window Tools ───────────────────────────────

    def _tool_read_screen(self, args: Dict) -> Dict:
        """Capture screenshot and OCR text."""
        auto = self._get_automation()
        region = None
        if args.get("region"):
            r = args["region"]
            region = (r["left"], r["top"], r["width"], r["height"])

        try:
            text = auto.read_text(region=region)
            return {"screen_text": text[:3000]}  # Truncate for context window
        except Exception as e:
            return {"error": f"OCR failed: {e}", "hint": "Tesseract may not be installed"}

    def _tool_list_windows(self, args: Dict) -> Dict:
        """List visible windows."""
        auto = self._get_automation()
        windows = auto.list_windows()
        return {
            "windows": [
                {"title": w.title, "handle": w.handle, "visible": w.visible}
                for w in windows[:30]
            ],
            "total": len(windows),
        }

    def _tool_focus_window(self, args: Dict) -> Dict:
        """Focus a window by title."""
        auto = self._get_automation()
        win = auto.find_window(title=args["title"])
        win.focus()
        return {"focused": win.title}

    # ─── App & Input Tools ───────────────────────────────────

    def _tool_launch_app(self, args: Dict) -> Dict:
        """Launch an application."""
        auto = self._get_automation()
        path = args["path"]
        app_args = args.get("args")

        result = auto.launch_process(path, app_args)
        return {
            "launched": True,
            "path": path,
            "pid": result.pid if result else None,
        }

    def _tool_type_text(self, args: Dict) -> Dict:
        """Type text into focused field."""
        auto = self._get_automation()
        text = args["text"]
        auto.type_text(text)
        return {"typed": True, "length": len(text)}

    def _tool_press_hotkey(self, args: Dict) -> Dict:
        """Press a keyboard shortcut."""
        auto = self._get_automation()
        keys = args["keys"]
        auto.hotkey(*keys)
        return {"pressed": keys}

    # ─── Computer Use: Vision Tools ─────────────────────────────

    async def _tool_screenshot_and_analyze(self, args: Dict) -> Dict:
        """Take screenshot, send to moondream vision model, get description."""
        auto = self._get_automation()
        prompt = args.get("prompt", "Describe what you see on screen")

        try:
            # Capture screenshot as PIL Image
            img = auto.capture_screen()

            # Convert to base64 PNG
            buf = BytesIO()
            img.save(buf, format="PNG")
            img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

            # Send to Ollama vision model
            import httpx
            payload = {
                "model": self._vision_model,
                "prompt": prompt,
                "images": [img_b64],
                "stream": False,
            }

            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self._ollama_url}/api/generate",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

            return {
                "description": data.get("response", "Could not analyze screenshot"),
                "screen_size": {"width": img.width, "height": img.height},
            }
        except Exception as e:
            return {"error": f"Vision analysis failed: {e}", "hint": "Is Ollama running with moondream model?"}

    def _tool_find_text_on_screen(self, args: Dict) -> Dict:
        """Find text location on screen via OCR."""
        auto = self._get_automation()
        text = args["text"]

        try:
            locations = auto.find_text(text)
            if not locations:
                return {"found": False, "text": text, "matches": []}

            return {
                "found": True,
                "text": text,
                "matches": [
                    {
                        "x": loc[0], "y": loc[1],
                        "width": loc[2], "height": loc[3],
                        "center_x": loc[0] + loc[2] // 2,
                        "center_y": loc[1] + loc[3] // 2,
                    }
                    for loc in locations[:5]
                ],
            }
        except Exception as e:
            return {"error": f"Text search failed: {e}"}

    # ─── Computer Use: Mouse Tools ────────────────────────────

    def _tool_mouse_click(self, args: Dict) -> Dict:
        """Click at screen coordinates."""
        auto = self._get_automation()
        x, y = args["x"], args["y"]
        button = args.get("button", "left")

        if button == "double":
            auto.double_click(x, y)
        elif button == "right":
            auto.right_click(x, y)
        else:
            auto.click(x, y)

        return {"clicked": True, "x": x, "y": y, "button": button}

    def _tool_mouse_move(self, args: Dict) -> Dict:
        """Move mouse to coordinates."""
        auto = self._get_automation()
        auto.move_mouse(args["x"], args["y"])
        return {"moved": True, "x": args["x"], "y": args["y"]}

    def _tool_mouse_scroll(self, args: Dict) -> Dict:
        """Scroll the mouse wheel."""
        auto = self._get_automation()
        direction = args["direction"]
        clicks = args.get("clicks", 3)
        auto.scroll(clicks, direction=direction)
        return {"scrolled": True, "direction": direction, "clicks": clicks}

    # ─── Recipe Primitives: OCR-driven GUI Automation ──────────
    # These are the building blocks playbooks use to drive real apps
    # without hand-coding coordinates. They wrap the same ScreenCapture +
    # InputController stack used by _tool_find_text_on_screen, but add
    # fuzzy matching and higher-level actions (click label, fill labeled field).

    def _ocr_labels(self, region=None) -> List[Dict[str, Any]]:
        """Return OCR word list with bounding boxes for the current screen."""
        auto = self._get_automation()
        return auto.screen.read_text_detailed(region=region)

    def _best_label_match(self, labels: List[Dict[str, Any]], target: str,
                          threshold: int = 75) -> Optional[Dict[str, Any]]:
        """Find the best OCR match for ``target`` using fuzzy matching.

        Tries RapidFuzz first, then falls back to case-insensitive substring.
        Returns the matching label dict (with x/y/width/height) or None.
        """
        target_lc = (target or "").strip().lower()
        if not target_lc:
            return None

        # Prefer RapidFuzz (fast, tolerant of OCR noise) when available.
        try:
            from rapidfuzz import fuzz
            best = None
            best_score = 0.0
            for item in labels:
                text = (item.get("text") or "").strip()
                if not text:
                    continue
                if int(item.get("confidence", 0)) < 40:
                    continue
                score = fuzz.partial_ratio(target_lc, text.lower())
                if score > best_score:
                    best_score = score
                    best = item
            if best and best_score >= threshold:
                return best
        except ImportError:
            pass

        # Substring fallback — good enough for exact labels like "Install".
        for item in labels:
            text = (item.get("text") or "").strip().lower()
            if target_lc in text and int(item.get("confidence", 0)) > 30:
                return item
        return None

    def _tool_gui_read_labels(self, args: Dict) -> Dict:
        """Return all OCR hits on screen with bounding boxes and confidences.

        Optional ``region`` (x, y, w, h) narrows the search. Useful as a
        diagnostic step before gui_click_label when a click misses.
        """
        region = args.get("region")
        if region and isinstance(region, (list, tuple)) and len(region) == 4:
            region = tuple(int(v) for v in region)
        else:
            region = None
        try:
            details = self._ocr_labels(region=region)
        except Exception as e:
            return {"error": f"OCR failed: {e}",
                    "hint": "Is Tesseract installed and on PATH?"}
        # Keep payload small for the UI — drop empties and cap at 80 entries.
        cleaned = [
            {
                "text": item["text"],
                "confidence": int(item.get("confidence", 0)),
                "x": int(item["x"]),
                "y": int(item["y"]),
                "width": int(item["width"]),
                "height": int(item["height"]),
            }
            for item in details
            if (item.get("text") or "").strip() and int(item.get("confidence", 0)) > 30
        ]
        return {"labels": cleaned[:80], "total": len(cleaned)}

    def _tool_gui_click_label(self, args: Dict) -> Dict:
        """Find a label on screen via OCR and click its center.

        Args:
            label: text to search for (fuzzy matched).
            threshold: optional minimum fuzzy score (default 75).
            timeout_s: seconds to keep retrying OCR (default 3).
            offset: {"dx": int, "dy": int} applied to the click point.
            double_click: if true, double-click instead.
        """
        label = args.get("label", "")
        if not label:
            return {"error": "gui_click_label requires 'label'."}
        threshold = int(args.get("threshold", 75))
        timeout_s = float(args.get("timeout_s", 3.0))
        offset = args.get("offset") or {}
        dx = int(offset.get("dx", 0))
        dy = int(offset.get("dy", 0))
        double = bool(args.get("double_click", False))

        auto = self._get_automation()
        deadline = time.time() + max(0.0, timeout_s)
        match = None
        last_error = None
        while True:
            try:
                labels = self._ocr_labels()
                match = self._best_label_match(labels, label, threshold=threshold)
            except Exception as e:
                last_error = str(e)
                match = None
            if match or time.time() >= deadline:
                break
            time.sleep(0.5)

        if not match:
            return {
                "clicked": False,
                "label": label,
                "error": last_error or f"Label '{label}' not found on screen.",
            }
        cx = int(match["x"] + match["width"] / 2) + dx
        cy = int(match["y"] + match["height"] / 2) + dy
        try:
            if double:
                auto.double_click(cx, cy)
            else:
                auto.click(cx, cy)
        except Exception as e:
            return {"clicked": False, "error": str(e), "label": label}
        return {
            "clicked": True,
            "label": label,
            "matched_text": match.get("text"),
            "x": cx,
            "y": cy,
            "double_click": double,
        }

    def _tool_gui_fill_labeled_field(self, args: Dict) -> Dict:
        """Find a form label, click the adjacent input field, and type a value.

        Args:
            label: the field's label text (fuzzy matched).
            value: the string to type.
            direction: 'right' (default) or 'below' — where the input lives
                       relative to the label.
            clear_first: if true, select-all + delete before typing.
        """
        label = args.get("label", "")
        value = args.get("value")
        if not label or value is None:
            return {"error": "gui_fill_labeled_field requires 'label' and 'value'."}
        direction = args.get("direction", "right").lower()
        clear_first = bool(args.get("clear_first", False))

        auto = self._get_automation()
        try:
            labels = self._ocr_labels()
        except Exception as e:
            return {"error": f"OCR failed: {e}"}
        match = self._best_label_match(labels, label)
        if not match:
            return {"filled": False, "label": label,
                    "error": f"Label '{label}' not found on screen."}

        # Compute the probable click point on the adjacent input.
        if direction == "below":
            # Click roughly one row below the label, aligned horizontally.
            target_x = int(match["x"] + match["width"] / 2)
            target_y = int(match["y"] + match["height"] + max(match["height"], 18))
        else:
            # Default: click to the right of the label, vertically centered.
            target_x = int(match["x"] + match["width"] + max(match["width"] // 2, 40))
            target_y = int(match["y"] + match["height"] / 2)

        try:
            auto.click(target_x, target_y)
            if clear_first:
                auto.hotkey("ctrl", "a")
                time.sleep(0.05)
                auto.press_key("delete")
            auto.type_text(str(value))
        except Exception as e:
            # Fall back: Tab from the label and try typing anyway.
            try:
                auto.press_key("tab")
                auto.type_text(str(value))
            except Exception as inner:
                return {"filled": False, "error": f"{e}; fallback: {inner}"}
        return {
            "filled": True,
            "label": label,
            "matched_text": match.get("text"),
            "click_x": target_x,
            "click_y": target_y,
            "direction": direction,
            "length": len(str(value)),
        }

    def _tool_gui_wizard_next(self, args: Dict) -> Dict:
        """Walk a typical installer / setup wizard by clicking the next
        button until it runs out of screens.

        On each iteration:
          1. OCR the current screen.
          2. Look for the first button in ``buttons_in_order`` that matches.
          3. Click it, wait ``step_delay_s`` for the next screen to render,
             and repeat.

        Stops when no matching button is found (meaning the wizard is done
        or stuck on an unknown screen) or after ``max_steps`` iterations.
        Never clicks UAC prompts — those require explicit manual gating
        because Windows strips the ability to auto-confirm them.
        """
        default_buttons = [
            "Next", "I Agree", "Agree", "Accept", "I Accept",
            "Install", "Continue", "Finish", "Done", "Close", "OK",
        ]
        buttons = args.get("buttons_in_order") or default_buttons
        if isinstance(buttons, str):
            buttons = [b.strip() for b in buttons.split(",") if b.strip()]
        max_steps = int(args.get("max_steps", 15))
        step_delay = float(args.get("step_delay_s", 1.2))
        threshold = int(args.get("threshold", 80))

        clicks: List[Dict[str, Any]] = []
        last_missing: List[str] = []
        for iteration in range(max_steps):
            # Grab one OCR snapshot per iteration, then try each button
            # against the same snapshot. This keeps the screen-read cost
            # down on slow machines.
            try:
                labels = self._ocr_labels()
            except Exception as e:
                return {
                    "ok": False,
                    "iterations": iteration,
                    "clicks": clicks,
                    "error": f"OCR failed mid-wizard: {e}",
                }

            clicked_this_round = None
            for btn in buttons:
                match = self._best_label_match(labels, btn, threshold=threshold)
                if not match:
                    continue
                cx = int(match["x"] + match["width"] / 2)
                cy = int(match["y"] + match["height"] / 2)
                try:
                    self._get_automation().click(cx, cy)
                except Exception as e:
                    return {
                        "ok": False,
                        "iterations": iteration,
                        "clicks": clicks,
                        "error": f"Click failed on '{btn}': {e}",
                    }
                clicks.append({
                    "iteration": iteration,
                    "button": btn,
                    "matched_text": match.get("text"),
                    "x": cx,
                    "y": cy,
                })
                clicked_this_round = btn
                break

            if not clicked_this_round:
                last_missing = [b for b in buttons]
                break

            # If we just hit a terminal button, the wizard is done.
            if clicked_this_round.lower() in {"finish", "done", "close"}:
                time.sleep(step_delay)
                break
            time.sleep(step_delay)

        return {
            "ok": True,
            "iterations": len(clicks),
            "clicks": clicks,
            "stopped_reason": "terminal_button" if clicks and clicks[-1]["button"].lower() in {"finish", "done", "close"}
                              else ("no_button_visible" if not clicks or iteration < max_steps - 1 else "max_steps"),
            "buttons_searched": buttons,
        }

    # ─── Recipe Primitives: User Input & Profile ──────────────
    # ``ask_user`` is handled specially by the orchestrator: executing it
    # returns a sentinel that pauses the plan and emits a user_input_request
    # event. ``user_profile_get/set`` read/write a local JSON store so later
    # steps can consume whatever the user typed.

    def _user_profile_path(self) -> str:
        base = os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
            "Zora",
        )
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, "user_profile.json")

    def _load_user_profile(self) -> Dict[str, Any]:
        path = self._user_profile_path()
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}

    def _save_user_profile(self, profile: Dict[str, Any]) -> None:
        with open(self._user_profile_path(), "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, default=str)

    def _tool_user_profile_get(self, args: Dict) -> Dict:
        """Read one or more fields from the persistent user profile."""
        profile = self._load_user_profile()
        field = args.get("field")
        if field:
            return {"field": field, "value": profile.get(field, "")}
        # No specific field → return redacted snapshot (never echo secrets).
        redacted = {k: ("***" if _looks_secret(k) else v) for k, v in profile.items()}
        return {"profile": redacted}

    def _tool_user_profile_set(self, args: Dict) -> Dict:
        """Write a single field to the persistent user profile."""
        field = args.get("field")
        value = args.get("value")
        if not field:
            return {"error": "user_profile_set requires 'field'."}
        profile = self._load_user_profile()
        profile[field] = value
        self._save_user_profile(profile)
        echo = "***" if _looks_secret(field) else value
        return {"saved": True, "field": field, "value": echo}

    def _tool_ask_user(self, args: Dict) -> Dict:
        """Pause the plan and ask the user for one piece of information.

        The orchestrator treats ``status: 'awaiting_user_input'`` as a signal
        to emit a user_input_request event and stop until the user answers.
        When they answer, the value is stored via user_profile_set under
        ``field_name`` so later steps can reference it with
        ``{user.<field_name>}``.
        """
        prompt = args.get("prompt") or "I need one quick detail to continue."
        field_name = args.get("field_name") or args.get("field") or "answer"
        return {
            "status": "awaiting_user_input",
            "prompt": prompt,
            "field_name": field_name,
        }

    def _tool_select_from_list(self, args: Dict) -> Dict:
        """Ask the user to pick one option from a list.

        Reuses the ``awaiting_user_input`` pause/resume machinery so the
        orchestrator treats this exactly like ``ask_user`` — the only
        difference is that the UI surfaces a radio-button list instead of
        a text field. If the list has zero items we short-circuit with an
        error so the recipe can fall through to a manual path.
        """
        prompt = args.get("prompt") or "Which one do you want to use?"
        field_name = args.get("field_name") or "selection"
        choices = args.get("choices") or args.get("items") or []
        if isinstance(choices, str):
            choices = [c.strip() for c in choices.split(",") if c.strip()]
        if not choices:
            return {"error": "select_from_list needs a non-empty 'choices' list."}
        # Normalize every entry into {label, value} so the UI card can render
        # without guessing shape.
        normalized: List[Dict[str, Any]] = []
        for item in choices:
            if isinstance(item, dict):
                label = item.get("label") or item.get("name") or str(item.get("value", ""))
                value = item.get("value", label)
                normalized.append({"label": label, "value": value})
            else:
                normalized.append({"label": str(item), "value": item})
        return {
            "status": "awaiting_user_input",
            "prompt": prompt,
            "field_name": field_name,
            "choices": normalized,
            "kind": "select_from_list",
        }

    # ─── Phase 7: Smart-home tools ────────────────────────────
    # Every handler is resilient to "no backend configured" — smart-home
    # is optional and the first-time user should get a helpful hint, not
    # a traceback.

    def _smart_home_store(self):
        from .smart_home import SmartHomeConfigStore
        if not hasattr(self, "_sh_store"):
            self._sh_store = SmartHomeConfigStore()
        return self._sh_store

    def _smart_home_config(self):
        return self._smart_home_store().load()

    def _pick_smart_home_backend(self, backend: Optional[str], config) -> str:
        """Resolve which backend to talk to.

        Preference order when the user doesn't name one:
            home_assistant → hue → mqtt
        HA is tried first because it typically exposes the largest
        inventory; Hue second because it has direct LAN access with no
        additional hub; MQTT last because it needs user-authored topics.
        """
        configured = config.backends_configured()
        if backend:
            return backend if configured.get(backend) else ""
        for candidate in ("home_assistant", "hue", "mqtt"):
            if configured.get(candidate):
                return candidate
        return ""

    def _resolve_smart_home_entity(self, entity_id: str, config) -> str:
        """Look up a friendly alias (e.g. 'living room lights') if the user
        didn't pass a canonical entity ID."""
        if not entity_id:
            return ""
        # Exact match against aliases first (case-insensitive).
        lowered = entity_id.lower()
        for alias, canonical in (config.aliases or {}).items():
            if alias.lower() == lowered:
                return canonical
        return entity_id

    async def _tool_smart_home_list_entities(self, args: Dict) -> Dict:
        """Enumerate devices visible through the configured smart-home backend(s).

        Args:
            backend: optional — 'home_assistant', 'hue', 'mqtt'. Defaults to
                first configured.
            domain: optional — e.g. 'light', 'switch', 'climate', 'lock'.
                Only applied to Home Assistant.
        """
        config = self._smart_home_config()
        if not config.any_configured():
            return {
                "error": "No smart-home backend configured.",
                "hint": "Run 'connect my home assistant' or 'connect my hue bridge' to get started.",
            }
        backend = self._pick_smart_home_backend(args.get("backend"), config)
        if not backend:
            return {"error": f"Backend '{args.get('backend')}' is not configured."}

        try:
            if backend == "home_assistant":
                from .smart_home import HomeAssistantClient
                client = HomeAssistantClient(config.home_assistant.url, config.home_assistant.token)
                entities = await client.list_states(domain=args.get("domain"))
                return {"backend": backend, "entities": entities, "count": len(entities)}
            if backend == "hue":
                from .smart_home import HueClient
                client = HueClient(config.hue.bridge_ip, config.hue.username)
                lights = await client.list_lights()
                groups = await client.list_groups()
                entities = lights + groups
                return {"backend": backend, "entities": entities, "count": len(entities)}
            if backend == "mqtt":
                return {
                    "backend": backend,
                    "entities": [],
                    "hint": "MQTT is topic-based — use mqtt_subscribe(topic) to read state.",
                }
        except Exception as e:
            return {"error": f"{backend} list failed: {e}"}
        return {"error": f"Unknown backend: {backend}"}

    async def _tool_smart_home_call(self, args: Dict) -> Dict:
        """Invoke an action on a smart-home entity.

        Canonical actions (mapped per-backend below):
            on, off, toggle, set_brightness, set_temperature, set_color,
            activate_scene, lock, unlock, arm_home, arm_away, arm_night, disarm
        """
        config = self._smart_home_config()
        if not config.any_configured():
            return {
                "error": "No smart-home backend configured.",
                "hint": "Run 'connect my home assistant' or 'connect my hue bridge' first.",
            }
        backend = self._pick_smart_home_backend(args.get("backend"), config)
        if not backend:
            return {"error": f"Backend '{args.get('backend')}' is not configured."}

        entity_id = self._resolve_smart_home_entity(str(args.get("entity_id") or ""), config)
        action = str(args.get("action") or "").strip().lower()
        if not entity_id:
            return {"error": "entity_id is required."}
        if not action:
            return {"error": "action is required."}
        extra = args.get("args") or {}

        try:
            if backend == "home_assistant":
                return await self._smart_home_call_ha(config, entity_id, action, extra)
            if backend == "hue":
                return await self._smart_home_call_hue(config, entity_id, action, extra)
            if backend == "mqtt":
                return {
                    "error": "MQTT does not support canonical actions — use mqtt_publish directly.",
                }
        except Exception as e:
            return {"error": f"{backend} call failed: {e}"}
        return {"error": f"Unknown backend: {backend}"}

    async def _smart_home_call_ha(
        self, config, entity_id: str, action: str, extra: Dict[str, Any]
    ) -> Dict[str, Any]:
        from .smart_home import HomeAssistantClient
        client = HomeAssistantClient(config.home_assistant.url, config.home_assistant.token)
        domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
        if not domain:
            return {"error": f"entity_id '{entity_id}' is missing a domain prefix."}

        action_map = {
            "on": ("turn_on", {}),
            "off": ("turn_off", {}),
            "toggle": ("toggle", {}),
            "set_brightness": ("turn_on", {"brightness": int(extra.get("brightness", extra.get("value", 128)))}),
            "set_temperature": (
                "set_temperature",
                {"temperature": float(extra.get("temperature", extra.get("value", 68)))},
            ),
            "set_color": ("turn_on", {"rgb_color": extra.get("rgb") or extra.get("color")}),
            "activate_scene": ("turn_on", {}),
            "lock": ("lock", {}),
            "unlock": ("unlock", {}),
            "arm_home": ("alarm_arm_home", {}),
            "arm_away": ("alarm_arm_away", {}),
            "arm_night": ("alarm_arm_night", {}),
            "disarm": ("alarm_disarm", {}),
        }
        if action not in action_map:
            return {"error": f"Unsupported action '{action}' for Home Assistant."}

        service, payload = action_map[action]
        body = {"entity_id": entity_id}
        body.update({k: v for k, v in payload.items() if v is not None})
        result = await client.call_service(domain, service, body)
        return {
            "backend": "home_assistant",
            "entity_id": entity_id,
            "action": action,
            "service": f"{domain}.{service}",
            "result": result,
        }

    async def _smart_home_call_hue(
        self, config, entity_id: str, action: str, extra: Dict[str, Any]
    ) -> Dict[str, Any]:
        from .smart_home import HueClient
        client = HueClient(config.hue.bridge_ip, config.hue.username)
        # Hue entity_ids look like "hue.light.5" or "hue.group.2".
        parts = entity_id.split(".")
        if len(parts) != 3 or parts[0] != "hue":
            return {"error": f"Hue entity_id must look like 'hue.light.<id>' or 'hue.group.<id>', got '{entity_id}'."}
        kind, hue_id = parts[1], parts[2]

        body: Dict[str, Any] = {}
        if action == "on":
            body = {"on": True}
        elif action == "off":
            body = {"on": False}
        elif action == "toggle":
            # Hue has no native toggle — read state first.
            if kind == "light":
                lights = await client.list_lights()
                current = next((l for l in lights if l["hue_id"] == hue_id), None)
            else:
                lights = await client.list_groups()
                current = next((g for g in lights if g["hue_id"] == hue_id), None)
            body = {"on": not (current and current.get("state") == "on")}
        elif action == "set_brightness":
            raw = int(extra.get("brightness", extra.get("value", 50)))
            # Accept 0-100 as a percentage, scale to Hue's 0-254.
            scaled = max(0, min(254, int(round(raw * 254 / 100)))) if raw <= 100 else max(0, min(254, raw))
            body = {"on": scaled > 0, "bri": scaled}
        elif action == "set_color":
            body = {"on": True}
            if extra.get("xy"):
                body["xy"] = extra["xy"]
            if extra.get("hue"):
                body["hue"] = int(extra["hue"])
            if extra.get("sat"):
                body["sat"] = int(extra["sat"])
        elif action == "activate_scene":
            body = {"scene": extra.get("scene") or extra.get("value")}
        else:
            return {"error": f"Hue does not support action '{action}' directly."}

        if kind == "light":
            result = await client.set_light_state(hue_id, body)
        else:
            result = await client.set_group_action(hue_id, body)
        return {
            "backend": "hue",
            "entity_id": entity_id,
            "action": action,
            "result": result,
        }

    async def _tool_smart_home_query(self, args: Dict) -> Dict:
        """Read the current state of one entity across any backend."""
        config = self._smart_home_config()
        if not config.any_configured():
            return {"error": "No smart-home backend configured."}
        backend = self._pick_smart_home_backend(args.get("backend"), config)
        if not backend:
            return {"error": f"Backend '{args.get('backend')}' is not configured."}
        entity_id = self._resolve_smart_home_entity(str(args.get("entity_id") or ""), config)
        if not entity_id:
            return {"error": "entity_id is required."}

        try:
            if backend == "home_assistant":
                from .smart_home import HomeAssistantClient
                client = HomeAssistantClient(config.home_assistant.url, config.home_assistant.token)
                return {"backend": backend, **(await client.get_state(entity_id))}
            if backend == "hue":
                from .smart_home import HueClient
                client = HueClient(config.hue.bridge_ip, config.hue.username)
                parts = entity_id.split(".")
                if len(parts) != 3:
                    return {"error": f"bad Hue entity_id: {entity_id}"}
                lights = await client.list_lights() if parts[1] == "light" else await client.list_groups()
                match = next((x for x in lights if x["hue_id"] == parts[2]), None)
                if not match:
                    return {"error": f"Hue entity {entity_id} not found"}
                return {"backend": backend, **match}
        except Exception as e:
            return {"error": f"{backend} query failed: {e}"}
        return {"error": f"Unknown backend: {backend}"}

    async def _tool_smart_home_setup(self, args: Dict) -> Dict:
        """Write a backend credential to ``storage/smart_home.json``.

        Callers pass the backend + a flat dict of fields. Secrets are
        obfuscated at rest via SmartHomeConfigStore. After saving we
        validate by calling ``ping`` so the user gets immediate feedback
        if their token / IP is wrong.
        """
        backend = str(args.get("backend") or "").strip().lower()
        if backend not in {"home_assistant", "mqtt", "hue"}:
            return {"error": "backend must be one of: home_assistant, mqtt, hue"}

        store = self._smart_home_store()
        config = store.load()

        if backend == "home_assistant":
            url = str(args.get("url") or "").strip()
            token = str(args.get("token") or "").strip()
            if not url or not token:
                return {"error": "home_assistant setup needs url and token"}
            config.home_assistant.url = url
            config.home_assistant.token = token
            store.save(config)
            from .smart_home import HomeAssistantClient
            ping = await HomeAssistantClient(url, token).ping()
            return {"saved": True, "backend": backend, "validation": ping}

        if backend == "mqtt":
            host = str(args.get("host") or "").strip()
            if not host:
                return {"error": "mqtt setup needs host"}
            config.mqtt.host = host
            config.mqtt.port = int(args.get("port") or 1883)
            config.mqtt.username = str(args.get("username") or "")
            config.mqtt.password = str(args.get("password") or "")
            store.save(config)
            from .smart_home import MqttClient
            ping = await MqttClient(
                config.mqtt.host,
                config.mqtt.port,
                config.mqtt.username,
                config.mqtt.password,
            ).ping()
            return {"saved": True, "backend": backend, "validation": ping}

        if backend == "hue":
            bridge_ip = str(args.get("bridge_ip") or "").strip()
            username = str(args.get("username") or "").strip()
            if not bridge_ip:
                return {"error": "hue setup needs bridge_ip"}
            # If the user hasn't paired yet, call create_username — requires
            # they press the physical link button first.
            if not username:
                from .smart_home import HueClient
                pairing = await HueClient.create_username(bridge_ip)
                if not pairing.get("ok"):
                    return {"error": "Hue pairing failed", "detail": pairing}
                username = pairing["username"]
            config.hue.bridge_ip = bridge_ip
            config.hue.username = username
            store.save(config)
            from .smart_home import HueClient
            ping = await HueClient(bridge_ip, username).ping()
            return {"saved": True, "backend": backend, "validation": ping}

        return {"error": f"unsupported backend {backend}"}

    async def _tool_smart_home_discover_hue(self, args: Dict) -> Dict:
        """Find Hue bridges on the LAN via discovery.meethue.com / mDNS."""
        from .smart_home import HueClient
        bridges = await HueClient.discover(timeout_s=float(args.get("timeout_s") or 3.0))
        return {"bridges": bridges, "count": len(bridges)}

    def _tool_smart_home_set_alias(self, args: Dict) -> Dict:
        """Remember that 'living room lights' maps to e.g. 'light.living_room'."""
        alias = str(args.get("alias") or "").strip()
        entity_id = str(args.get("entity_id") or "").strip()
        if not alias or not entity_id:
            return {"error": "alias and entity_id are required"}
        store = self._smart_home_store()
        config = store.load()
        config.aliases[alias] = entity_id
        store.save(config)
        return {"saved": True, "alias": alias, "entity_id": entity_id}

    async def _tool_mqtt_publish(self, args: Dict) -> Dict:
        """Publish a raw MQTT message. First-use of any topic is policy-gated."""
        config = self._smart_home_config()
        if not config.backends_configured().get("mqtt"):
            return {"error": "MQTT is not configured."}
        topic = str(args.get("topic") or "").strip()
        if not topic:
            return {"error": "topic is required"}
        from .smart_home import MqttClient
        client = MqttClient(
            config.mqtt.host,
            config.mqtt.port,
            config.mqtt.username,
            config.mqtt.password,
        )
        result = await client.publish(
            topic,
            args.get("payload"),
            qos=int(args.get("qos") or 0),
            retain=bool(args.get("retain")),
        )
        # Remember this topic so the policy engine doesn't gate it next time.
        if result.get("published") and topic not in config.mqtt.known_topics:
            config.mqtt.known_topics.append(topic)
            self._smart_home_store().save(config)
        return result

    async def _tool_mqtt_subscribe(self, args: Dict) -> Dict:
        """Subscribe to one topic and wait for a single message (or retained)."""
        config = self._smart_home_config()
        if not config.backends_configured().get("mqtt"):
            return {"error": "MQTT is not configured."}
        from .smart_home import MqttClient
        client = MqttClient(
            config.mqtt.host,
            config.mqtt.port,
            config.mqtt.username,
            config.mqtt.password,
        )
        return await client.subscribe_once(
            str(args.get("topic") or ""),
            timeout_s=float(args.get("timeout_s") or 5.0),
        )

    # ─── Computer Use: Screen Highlight ───────────────────────

    def _tool_highlight_screen_area(self, args: Dict) -> Dict:
        """Draw a temporary rectangle on screen to show user what we're looking at."""
        x, y = args["x"], args["y"]
        w, h = args["width"], args["height"]
        color = args.get("color", "red")

        color_map = {
            "red": (255, 0, 0),
            "green": (0, 255, 0),
            "blue": (0, 120, 255),
            "yellow": (255, 255, 0),
        }
        rgb = color_map.get(color, (255, 0, 0))

        def _draw_highlight():
            try:
                import ctypes
                from ctypes import wintypes

                user32 = ctypes.windll.user32
                gdi32 = ctypes.windll.gdi32

                hdc = user32.GetDC(0)
                pen = gdi32.CreatePen(0, 3, rgb[0] | (rgb[1] << 8) | (rgb[2] << 16))
                old_pen = gdi32.SelectObject(hdc, pen)
                old_brush = gdi32.SelectObject(hdc, gdi32.GetStockObject(5))  # NULL_BRUSH

                gdi32.Rectangle(hdc, x, y, x + w, y + h)

                gdi32.SelectObject(hdc, old_pen)
                gdi32.SelectObject(hdc, old_brush)
                gdi32.DeleteObject(pen)
                user32.ReleaseDC(0, hdc)

                # Clear after 2 seconds by invalidating the region
                time.sleep(2)
                user32.InvalidateRect(0, None, True)
            except Exception:
                pass

        thread = threading.Thread(target=_draw_highlight, daemon=True)
        thread.start()

        return {"highlighted": True, "x": x, "y": y, "width": w, "height": h, "color": color}

    # ─── Windows Settings Tool ────────────────────────────────

    def _tool_change_windows_setting(self, args: Dict) -> Dict:
        """Change Windows settings via safe PowerShell commands."""
        setting = args["setting"]
        value = args.get("value", "")

        # Map setting names to safe PowerShell commands. Phase 3a adds a batch
        # of ms-settings: deep-link presets so recipes can land on the right
        # page without memorizing the exact URI scheme.
        setting_commands = {
            "check_updates": 'Start-Process "ms-settings:windowsupdate"',
            "wifi_connect": f'netsh wlan connect name="{value}"' if value else 'Start-Process "ms-settings:network-wifi"',
            "wifi_disconnect": "netsh wlan disconnect",
            "set_power_plan": {
                "balanced": 'powercfg /setactive 381b4222-f694-41f0-9685-ff5bb260df2e',
                "high_performance": 'powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c',
                "power_saver": 'powercfg /setactive a1841308-3541-4fab-bc81-f71556f20b4a',
            }.get(value, 'powercfg /list'),
            "toggle_bluetooth": 'Start-Process "ms-settings:bluetooth"',
            "open_device_manager": "devmgmt.msc",
            "open_settings_page": f'Start-Process "ms-settings:{value}"' if value else 'Start-Process "ms-settings:"',
            "enable_dark_mode": 'Set-ItemProperty -Path "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize" -Name "AppsUseLightTheme" -Value 0 -Type DWord',
            "disable_dark_mode": 'Set-ItemProperty -Path "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize" -Name "AppsUseLightTheme" -Value 1 -Type DWord',
            "set_volume": f'(New-Object -ComObject WScript.Shell).SendKeys([char]173)' if not value else f'Set-AudioDevice -PlaybackVolume {value}',
            "toggle_firewall": 'Start-Process "ms-settings:windowsdefender"',
            # --- Phase 3a: ms-settings deep-link presets ---
            # Each of these just opens the relevant Settings page so a
            # follow-up gui_click_label step can drive the UI.
            "open_bluetooth_devices": 'Start-Process "ms-settings:bluetooth"',
            "open_connected_devices": 'Start-Process "ms-settings:connecteddevices"',
            "open_phone_link": 'Start-Process "ms-settings:mobile-devices"',
            "open_printers": 'Start-Process "ms-settings:printers"',
            "open_default_apps": 'Start-Process "ms-settings:defaultapps"',
            "open_installed_apps": 'Start-Process "ms-settings:appsfeatures"',
            "open_startup_apps": 'Start-Process "ms-settings:startupapps"',
            "open_optional_features": 'Start-Process "ms-settings:optionalfeatures"',
            "open_network_status": 'Start-Process "ms-settings:network-status"',
            "open_display": 'Start-Process "ms-settings:display"',
            "open_sound": 'Start-Process "ms-settings:sound"',
            "open_storage": 'Start-Process "ms-settings:storagesense"',
            "open_privacy_camera": 'Start-Process "ms-settings:privacy-webcam"',
            "open_privacy_microphone": 'Start-Process "ms-settings:privacy-microphone"',
            "open_privacy_location": 'Start-Process "ms-settings:privacy-location"',
            "open_accounts": 'Start-Process "ms-settings:yourinfo"',
            "open_windows_security": 'Start-Process "windowsdefender:"',
            "open_recovery": 'Start-Process "ms-settings:recovery"',
            "open_about": 'Start-Process "ms-settings:about"',
        }

        if setting not in setting_commands:
            return {
                "error": f"Unknown setting: {setting}",
                "available": list(setting_commands.keys()),
            }

        cmd = setting_commands[setting]

        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True, text=True, timeout=15,
            )
            return {
                "setting": setting,
                "value": value,
                "success": result.returncode == 0,
                "output": result.stdout[:500] if result.stdout else "",
                "error": result.stderr[:200] if result.stderr else "",
            }
        except subprocess.TimeoutExpired:
            return {"error": f"Setting change timed out: {setting}"}

    # ─── Support Ticket Tool ──────────────────────────────────

    def _tool_create_support_ticket(self, args: Dict) -> Dict:
        """Create a support ticket with diagnostics and system info."""
        summary = args["issue_summary"]
        steps_tried = args.get("steps_tried", "None")

        # Gather system info
        sys_info = self._tool_get_system_info({})

        # Create ticket content
        ticket_id = f"ZORA-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        ticket_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "tickets",
        )
        os.makedirs(ticket_dir, exist_ok=True)

        ticket = {
            "ticket_id": ticket_id,
            "created": datetime.datetime.now().isoformat(),
            "issue_summary": summary,
            "steps_tried": steps_tried,
            "system_info": sys_info,
            "status": "open",
        }

        # Try to capture screenshot for ticket
        try:
            auto = self._get_automation()
            img = auto.capture_screen()
            screenshot_path = os.path.join(ticket_dir, f"{ticket_id}.png")
            img.save(screenshot_path)
            ticket["screenshot"] = screenshot_path
        except Exception:
            ticket["screenshot"] = None

        # Save ticket
        ticket_path = os.path.join(ticket_dir, f"{ticket_id}.json")
        with open(ticket_path, "w", encoding="utf-8") as f:
            json.dump(ticket, f, indent=2, default=str)

        # Open Microsoft support page
        try:
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command",
                 'Start-Process "https://support.microsoft.com/contactus"'],
            )
        except Exception:
            pass

        return {
            "ticket_id": ticket_id,
            "ticket_path": ticket_path,
            "message": f"Ticket {ticket_id} created. Opening Microsoft Support page.",
        }

    # ─── PowerShell Tool ─────────────────────────────────────

    def _tool_run_powershell(self, args: Dict) -> Dict:
        """Execute a PowerShell command with safety checks."""
        command = args["command"].strip()
        if not command:
            return {"error": "Blocked: empty command"}

        # Safety: allowlist top-level command only
        first_token = command.split()[0]
        normalized = first_token.lstrip("./").split("\\")[-1]
        if normalized not in self._powershell_allowlist:
            return {
                "error": "Blocked: command is not in allowlist",
                "allowed_commands": sorted(self._powershell_allowlist),
            }

        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return {
                "stdout": result.stdout[:3000],
                "stderr": result.stderr[:500] if result.stderr else "",
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out after 30 seconds"}

    # ─── Web Search Tool ─────────────────────────────────────

    def _tool_web_search(self, args: Dict) -> Dict:
        """Search the web using DuckDuckGo (free, no API key)."""
        query = args["query"]

        # Try duckduckgo_search package first
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            if results:
                return {
                    "query": query,
                    "results": [
                        {
                            "title": r.get("title", ""),
                            "url": r.get("href", r.get("link", "")),
                            "snippet": r.get("body", r.get("snippet", "")),
                        }
                        for r in results
                    ],
                    "total": len(results),
                }
        except ImportError:
            pass  # Package not installed, try fallback
        except Exception:
            pass  # DuckDuckGo search failed, try fallback

        # Fallback: DuckDuckGo Instant Answer API (no package needed)
        try:
            import urllib.request
            import urllib.parse
            encoded = urllib.parse.quote_plus(query)
            url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
            req = urllib.request.Request(url, headers={"User-Agent": "Zora/2.0"})
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))

            results = []
            if data.get("Abstract"):
                results.append({
                    "title": data.get("Heading", "Answer"),
                    "url": data.get("AbstractURL", ""),
                    "snippet": data["Abstract"][:500],
                })
            for topic in (data.get("RelatedTopics", []) or [])[:4]:
                if isinstance(topic, dict) and "Text" in topic:
                    results.append({
                        "title": topic.get("Text", "")[:100],
                        "url": topic.get("FirstURL", ""),
                        "snippet": topic.get("Text", "")[:300],
                    })
            if results:
                return {"query": query, "results": results, "total": len(results)}
        except Exception:
            pass

        return {
            "query": query,
            "results": [],
            "note": f"Couldn't search right now. Try in your browser.",
            "suggestion": f"https://duckduckgo.com/?q={query.replace(' ', '+')}",
        }

    # ─── Flow-Based Diagnostics ─────────────────────────────

    def _tool_run_flow_diagnostic(self, args: Dict) -> Dict:
        """Run a flow-based diagnostic decision tree."""
        flow_id = args["flow_id"]

        try:
            from diagnostics.flow_engine import FlowEngine
            from diagnostics.flow_actions import FLOW_ACTIONS
            from diagnostics.base import TechSupportNarrator

            engine = FlowEngine()
            narrator = TechSupportNarrator(verbose=False)
            results = engine.run_flow(flow_id, FLOW_ACTIONS, narrator)

            return {
                "flow_id": flow_id,
                "steps_executed": len(results),
                "results": [
                    {
                        "name": r.name,
                        "status": r.status,
                        "details": r.details,
                        "fix_available": r.fix_available,
                    }
                    for r in results
                ],
                "issues_found": sum(1 for r in results if r.status != "ok"),
                "narrator_log": narrator.log,
            }
        except ImportError as e:
            return {"error": f"Flow engine not available: {e}. Install pyyaml: pip install pyyaml"}
        except Exception as e:
            return {"error": f"Flow diagnostic failed: {e}", "flow_id": flow_id}

    # ─── Remediation Library ────────────────────────────────

    def _tool_apply_remediation(self, args: Dict) -> Dict:
        """Apply a fix from the remediation library."""
        fix_id = args["fix_id"]

        try:
            from remediation.library import get_fix

            fix = get_fix(fix_id)
            if not fix:
                from remediation.library import REMEDIATION_LIBRARY
                available = list(REMEDIATION_LIBRARY.keys())[:20]
                return {
                    "error": f"Fix '{fix_id}' not found",
                    "available_fixes": available,
                }

            # Execute each command
            outputs = []
            all_success = True
            for cmd in fix["commands"]:
                try:
                    result = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", cmd],
                        capture_output=True, text=True, timeout=60,
                    )
                    outputs.append({
                        "command": cmd[:100],
                        "success": result.returncode == 0,
                        "output": result.stdout[:300] if result.stdout else "",
                        "error": result.stderr[:200] if result.stderr else "",
                    })
                    if result.returncode != 0:
                        all_success = False
                except subprocess.TimeoutExpired:
                    outputs.append({"command": cmd[:100], "success": False, "error": "Timed out"})
                    all_success = False

            # Verify if verification command exists
            verify_result = None
            if fix.get("verify"):
                try:
                    vr = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", fix["verify"]],
                        capture_output=True, text=True, timeout=15,
                    )
                    verify_result = vr.stdout[:300]
                except Exception:
                    verify_result = "Could not verify"

            return {
                "fix_id": fix_id,
                "name": fix["name"],
                "risk": fix["risk"],
                "success": all_success,
                "requires_reboot": fix.get("requires_reboot", False),
                "outputs": outputs,
                "verification": verify_result,
            }
        except ImportError:
            return {"error": "Remediation library not available"}
        except Exception as e:
            return {"error": f"Remediation failed: {e}", "fix_id": fix_id}

    # ─── Tool Auto-Download from GitHub ───────────────────────

    # Trusted repos that Zora is allowed to download from
    TRUSTED_REPOS = {
        "BleachBit/bleachbit",        # Disk cleanup
        "henrypp/memreduct",          # Memory optimizer
        "aria2/aria2",                # Download manager
        "NirSoft",                    # Windows utilities (prefix match)
        "microsoft/winget-cli",       # Windows package manager
        "PowerShell/PowerShell",      # PowerShell updates
        "Git-for-Windows/git",        # Git for Windows
        "AveYo/MediaCreationTool.bat", # Windows Media Creation
    }

    def _tool_download_tool(self, args: Dict) -> Dict:
        """Download and stage an open-source tool from GitHub releases."""
        import urllib.request
        import zipfile
        import tempfile
        import fnmatch

        repo = args.get("repo", "")
        reason = args.get("reason", "")
        pattern = args.get("asset_pattern", "*.exe")

        if not repo or "/" not in repo:
            return {"error": f"Invalid repo format: '{repo}'. Use 'owner/repo' format."}

        # Security: check trusted repos
        is_trusted = any(
            repo.startswith(tr) or repo == tr
            for tr in self.TRUSTED_REPOS
        )
        if not is_trusted:
            return {
                "status": "blocked",
                "reason": f"Repo '{repo}' is not in the trusted list. "
                          f"For safety, Zora only downloads from verified repos. "
                          f"Trusted: {', '.join(sorted(self.TRUSTED_REPOS))}",
                "suggestion": "Use run_powershell with 'winget install' instead, "
                              "or ask the user to manually download from GitHub.",
            }

        tool_dir = os.path.join(
            os.environ.get("LOCALAPPDATA", tempfile.gettempdir()),
            "Zora", "tools", repo.replace("/", "_"),
        )
        os.makedirs(tool_dir, exist_ok=True)

        try:
            # Get latest release info
            api_url = f"https://api.github.com/repos/{repo}/releases/latest"
            req = urllib.request.Request(api_url, headers={"User-Agent": "Zora/2.0"})
            data = urllib.request.urlopen(req, timeout=15).read()
            release = json.loads(data)

            tag = release.get("tag_name", "unknown")
            assets = release.get("assets", [])

            if not assets:
                return {
                    "status": "no_assets",
                    "repo": repo,
                    "tag": tag,
                    "message": f"Release {tag} has no downloadable assets.",
                }

            # Find matching asset
            matched = None
            for asset in assets:
                name = asset["name"]
                if fnmatch.fnmatch(name.lower(), pattern.lower()):
                    # Prefer Windows assets
                    if "win" in name.lower() or "x64" in name.lower() or name.endswith(".exe"):
                        matched = asset
                        break
            if not matched:
                # Fall back to first match
                for asset in assets:
                    if fnmatch.fnmatch(asset["name"].lower(), pattern.lower()):
                        matched = asset
                        break
            if not matched:
                matched = assets[0]  # Just take first asset

            download_url = matched["browser_download_url"]
            filename = matched["name"]
            filepath = os.path.join(tool_dir, filename)

            # Skip if already downloaded
            if os.path.exists(filepath):
                return {
                    "status": "already_downloaded",
                    "repo": repo,
                    "tag": tag,
                    "path": filepath,
                    "filename": filename,
                    "reason": reason,
                }

            # Download
            urllib.request.urlretrieve(download_url, filepath)

            # Auto-extract ZIP if needed
            extracted_dir = None
            if filename.endswith(".zip"):
                extracted_dir = os.path.join(tool_dir, "extracted")
                with zipfile.ZipFile(filepath, "r") as zf:
                    zf.extractall(extracted_dir)

            return {
                "status": "downloaded",
                "repo": repo,
                "tag": tag,
                "path": filepath,
                "extracted": extracted_dir,
                "filename": filename,
                "size_mb": round(matched["size"] / (1024 * 1024), 1),
                "reason": reason,
                "message": f"Downloaded {filename} ({tag}) to {tool_dir}. "
                           f"Use run_powershell to execute it if needed.",
            }

        except Exception as e:
            return {
                "status": "error",
                "repo": repo,
                "error": str(e),
                "suggestion": "Try 'winget install' via run_powershell instead.",
            }

    # ─── Desktop Assistant: Email ──────────────────────────────

    def _tool_send_email(self, args: Dict) -> Dict:
        """Send an email via Outlook COM or mailto: fallback."""
        to = args["to"]
        subject = args["subject"]
        body = args["body"]
        cc = args.get("cc", "")

        # Try Outlook COM first (most common on Windows)
        try:
            import win32com.client
            outlook = win32com.client.Dispatch("Outlook.Application")
            mail = outlook.CreateItem(0)
            mail.To = to
            mail.Subject = subject
            mail.Body = body
            if cc:
                mail.CC = cc
            # Display for user review instead of auto-send
            mail.Display(True)
            return {
                "status": "draft_opened",
                "method": "outlook",
                "to": to,
                "subject": subject,
                "message": "Email draft opened in Outlook. Please review and click Send.",
            }
        except Exception:
            pass

        # Fallback: open default mail client via mailto: link
        try:
            import urllib.parse
            params = {"subject": subject, "body": body}
            if cc:
                params["cc"] = cc
            mailto_url = f"mailto:{to}?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"
            os.startfile(mailto_url)
            return {
                "status": "mailto_opened",
                "method": "default_mail_client",
                "to": to,
                "subject": subject,
                "message": "Email draft opened in your default mail app. Review and send.",
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"Could not open email: {e}",
                "suggestion": "Copy the text and paste it into your email app manually.",
                "email_content": {"to": to, "subject": subject, "body": body},
            }

    # ─── Desktop Assistant: File Management ────────────────────

    def _tool_manage_files(self, args: Dict) -> Dict:
        """Organize, move, copy, rename, find files."""
        import glob as glob_mod
        import shutil

        action = args["action"]
        path = args["path"]

        # Expand ~ to user home
        if path.startswith("~"):
            path = os.path.expanduser(path)
        path = os.path.abspath(path)

        try:
            if action == "list":
                pattern = args.get("pattern", "*")
                entries = []
                search_path = os.path.join(path, pattern)
                for item in glob_mod.glob(search_path):
                    stat = os.stat(item)
                    entries.append({
                        "name": os.path.basename(item),
                        "path": item,
                        "is_dir": os.path.isdir(item),
                        "size_mb": round(stat.st_size / (1024 * 1024), 2) if not os.path.isdir(item) else None,
                        "modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    })
                entries.sort(key=lambda x: x["name"].lower())
                return {"action": "list", "path": path, "count": len(entries), "entries": entries[:50]}

            elif action == "find":
                pattern = args.get("pattern", "*")
                found = []
                for root, dirs, files in os.walk(path):
                    import fnmatch as fnm
                    for f in files:
                        if fnm.fnmatch(f.lower(), pattern.lower()):
                            fp = os.path.join(root, f)
                            found.append({
                                "name": f, "path": fp,
                                "size_mb": round(os.path.getsize(fp) / (1024 * 1024), 2),
                            })
                    if len(found) >= 50:
                        break
                return {"action": "find", "pattern": pattern, "path": path,
                        "count": len(found), "results": found}

            elif action == "move":
                dest = args.get("destination", "")
                if not dest:
                    return {"error": "Destination required for move"}
                dest = os.path.expanduser(dest) if dest.startswith("~") else dest
                dest = os.path.abspath(dest)
                shutil.move(path, dest)
                return {"action": "move", "from": path, "to": dest, "status": "done"}

            elif action == "copy":
                dest = args.get("destination", "")
                if not dest:
                    return {"error": "Destination required for copy"}
                dest = os.path.expanduser(dest) if dest.startswith("~") else dest
                dest = os.path.abspath(dest)
                if os.path.isdir(path):
                    shutil.copytree(path, dest)
                else:
                    shutil.copy2(path, dest)
                return {"action": "copy", "from": path, "to": dest, "status": "done"}

            elif action == "rename":
                new_name = args.get("new_name", "")
                if not new_name:
                    return {"error": "new_name required for rename"}
                new_path = os.path.join(os.path.dirname(path), new_name)
                os.rename(path, new_path)
                return {"action": "rename", "from": path, "to": new_path, "status": "done"}

            elif action == "create_folder":
                os.makedirs(path, exist_ok=True)
                return {"action": "create_folder", "path": path, "status": "done"}

            elif action == "delete":
                dangerous = ["windows", "system32", "program files", "programdata"]
                if any(d in path.lower() for d in dangerous):
                    return {"error": f"Blocked: refusing to delete system path '{path}'"}
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                return {"action": "delete", "path": path, "status": "done"}

            elif action == "get_size":
                if os.path.isfile(path):
                    size = os.path.getsize(path)
                else:
                    size = sum(
                        os.path.getsize(os.path.join(r, f))
                        for r, _, files in os.walk(path) for f in files
                    )
                return {"action": "get_size", "path": path,
                        "size_mb": round(size / (1024 * 1024), 2)}

            elif action == "organize_by_type":
                if not os.path.isdir(path):
                    return {"error": f"'{path}' is not a folder"}
                type_map = {
                    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico"},
                    "Documents": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                                  ".txt", ".csv", ".rtf"},
                    "Videos": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv"},
                    "Music": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma"},
                    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz"},
                    "Programs": {".exe", ".msi", ".bat", ".cmd", ".ps1"},
                }
                moved = {}
                for f in os.listdir(path):
                    fp = os.path.join(path, f)
                    if os.path.isdir(fp):
                        continue
                    ext = os.path.splitext(f)[1].lower()
                    folder = "Other"
                    for cat, exts in type_map.items():
                        if ext in exts:
                            folder = cat
                            break
                    dest_dir = os.path.join(path, folder)
                    os.makedirs(dest_dir, exist_ok=True)
                    shutil.move(fp, os.path.join(dest_dir, f))
                    moved[folder] = moved.get(folder, 0) + 1
                return {"action": "organize_by_type", "path": path, "moved": moved,
                        "status": "done"}

            else:
                return {"error": f"Unknown action: {action}"}

        except Exception as e:
            return {"error": str(e), "action": action, "path": path}

    # ─── Desktop Assistant: Open URL ───────────────────────────

    def _tool_open_url(self, args: Dict) -> Dict:
        """Open a URL in the user's default browser."""
        import webbrowser
        url = args["url"]
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        webbrowser.open(url)
        return {"status": "opened", "url": url}

    # ─── Desktop Assistant: Clipboard ──────────────────────────

    def _tool_clipboard(self, args: Dict) -> Dict:
        """Read or write to the system clipboard."""
        action = args["action"]
        try:
            if action == "read":
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                    capture_output=True, text=True, timeout=5,
                )
                return {"action": "read", "content": result.stdout.strip()}
            elif action == "write":
                text = args.get("text", "")
                escaped = text.replace("'", "''")
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     f"Set-Clipboard -Value '{escaped}'"],
                    capture_output=True, text=True, timeout=5,
                )
                return {"action": "write", "status": "done", "length": len(text)}
            else:
                return {"error": f"Unknown clipboard action: {action}"}
        except Exception as e:
            return {"error": str(e)}

    # ─── Desktop Assistant: Remember / Notes / Follow-ups ──────

    def _tool_remember(self, args: Dict) -> Dict:
        """Save, list, search, or delete persistent notes and reminders."""
        action = args["action"]
        memory_dir = os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
            "Zora", "memory",
        )
        os.makedirs(memory_dir, exist_ok=True)
        memory_file = os.path.join(memory_dir, "notes.json")

        # Load existing notes
        notes = []
        if os.path.exists(memory_file):
            try:
                with open(memory_file, "r", encoding="utf-8") as f:
                    notes = json.load(f)
            except Exception:
                notes = []

        def _save():
            with open(memory_file, "w", encoding="utf-8") as f:
                json.dump(notes, f, indent=2, default=str)

        if action == "save":
            content = args.get("content", "")
            if not content:
                return {"error": "Nothing to save — 'content' is required."}
            entry = {
                "id": len(notes) + 1,
                "content": content,
                "category": args.get("category", "note"),
                "due": args.get("due"),
                "created": datetime.datetime.now().isoformat(),
                "done": False,
            }
            notes.append(entry)
            _save()
            return {"action": "save", "entry": entry, "total_notes": len(notes)}

        elif action == "list":
            category = args.get("category")
            filtered = notes
            if category:
                filtered = [n for n in notes if n.get("category") == category]
            due_now = []
            others = []
            now = datetime.datetime.now().isoformat()
            for n in filtered:
                if n.get("due") and n["due"] <= now and not n.get("done"):
                    due_now.append(n)
                else:
                    others.append(n)
            return {"action": "list", "due_now": due_now, "notes": others[-20:],
                    "total": len(filtered)}

        elif action == "search":
            query = args.get("content", "").lower()
            matches = [n for n in notes if query in n.get("content", "").lower()]
            return {"action": "search", "query": query, "results": matches,
                    "count": len(matches)}

        elif action == "delete":
            content = args.get("content", "")
            if content.isdigit():
                note_id = int(content)
                notes = [n for n in notes if n.get("id") != note_id]
            else:
                notes = [n for n in notes
                         if content.lower() not in n.get("content", "").lower()]
            _save()
            return {"action": "delete", "remaining": len(notes)}

        else:
            return {"error": f"Unknown memory action: {action}"}

    # ─── Desktop Assistant: Notification Toast ─────────────────

    def _tool_notify(self, args: Dict) -> Dict:
        """Show a Windows notification toast."""
        title = args["title"]
        message = args["message"]

        try:
            # Try win10toast first
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(title, message, duration=5, threaded=True)
            return {"status": "shown", "method": "win10toast", "title": title}
        except ImportError:
            pass

        # Fallback: PowerShell balloon notification
        try:
            ps_script = (
                'Add-Type -AssemblyName System.Windows.Forms; '
                '$n = New-Object System.Windows.Forms.NotifyIcon; '
                '$n.Icon = [System.Drawing.SystemIcons]::Information; '
                '$n.Visible = $true; '
                f'$n.ShowBalloonTip(5000, "{title}", "{message}", '
                '"Info"); Start-Sleep -Seconds 6; $n.Dispose()'
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", ps_script],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return {"status": "shown", "method": "balloon", "title": title}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ─── Browser: Playwright DOM-first automation ────────────
    # A single persistent context is started on the first browser_* call and
    # reused across steps so the user's session (logins, cookies) is preserved.
    # Runs headed so the user can see what's happening. Non-allowlisted hosts
    # should be consent-gated at the policy layer, not here.

    def _browser_user_data_dir(self) -> str:
        base = os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
            "Zora", "browser_profile",
        )
        os.makedirs(base, exist_ok=True)
        return base

    async def _ensure_browser(self):
        """Start Playwright + persistent context lazily. Returns the active page."""
        if self._pw_page is not None:
            return self._pw_page
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise RuntimeError(
                "Playwright is not installed. Run: pip install playwright "
                "&& python -m playwright install chromium"
            ) from e
        self._pw = await async_playwright().start()
        # Persistent context keeps cookies, localStorage, passwords across runs.
        self._pw_context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=self._browser_user_data_dir(),
            headless=False,
            viewport={"width": 1280, "height": 800},
        )
        if self._pw_context.pages:
            self._pw_page = self._pw_context.pages[0]
        else:
            self._pw_page = await self._pw_context.new_page()
        return self._pw_page

    async def _tool_browser_open(self, args: Dict) -> Dict:
        """Open a URL in the persistent Zora browser context.

        Args:
            url: the URL to load (http/https).
            wait_until: Playwright load state — 'domcontentloaded' (default),
                        'load', or 'networkidle'.
        """
        url = args.get("url")
        if not url:
            return {"error": "browser_open requires 'url'."}
        wait_until = args.get("wait_until", "domcontentloaded")
        try:
            page = await self._ensure_browser()
            await page.goto(url, wait_until=wait_until, timeout=30000)
            title = await page.title()
            return {"opened": True, "url": page.url, "title": title}
        except Exception as e:
            return {"error": f"browser_open failed: {e}", "url": url}

    async def _tool_browser_click(self, args: Dict) -> Dict:
        """Click an element by CSS selector or visible text.

        Args:
            selector: CSS selector (preferred when the page is stable).
            text: visible text to click (uses Playwright get_by_text).
            timeout_s: how long to wait for the element (default 10).
        """
        selector = args.get("selector")
        text = args.get("text")
        timeout_ms = int(float(args.get("timeout_s", 10)) * 1000)
        if not selector and not text:
            return {"error": "browser_click requires 'selector' or 'text'."}
        try:
            page = await self._ensure_browser()
            if selector:
                await page.locator(selector).first.click(timeout=timeout_ms)
                target = f"selector:{selector}"
            else:
                await page.get_by_text(text, exact=False).first.click(timeout=timeout_ms)
                target = f"text:{text}"
            return {"clicked": True, "target": target, "url": page.url}
        except Exception as e:
            return {"error": f"browser_click failed: {e}"}

    async def _tool_browser_fill(self, args: Dict) -> Dict:
        """Fill a form field by CSS selector or label.

        Args:
            selector: CSS selector for an <input>/<textarea>.
            label: visible label text; uses Playwright get_by_label as fallback.
            value: the string to type.
        """
        value = args.get("value")
        if value is None:
            return {"error": "browser_fill requires 'value'."}
        selector = args.get("selector")
        label = args.get("label")
        if not selector and not label:
            return {"error": "browser_fill requires 'selector' or 'label'."}
        try:
            page = await self._ensure_browser()
            if selector:
                await page.locator(selector).first.fill(str(value))
                target = f"selector:{selector}"
            else:
                await page.get_by_label(label).first.fill(str(value))
                target = f"label:{label}"
            return {"filled": True, "target": target, "length": len(str(value))}
        except Exception as e:
            return {"error": f"browser_fill failed: {e}"}

    async def _tool_browser_read_text(self, args: Dict) -> Dict:
        """Return visible text from the page or a specific selector.

        Args:
            selector: optional CSS selector — returns that element's innerText.
                      If omitted, returns the whole page body text (trimmed).
            max_chars: cap the returned string (default 4000).
        """
        selector = args.get("selector")
        max_chars = int(args.get("max_chars", 4000))
        try:
            page = await self._ensure_browser()
            if selector:
                text = await page.locator(selector).first.inner_text()
            else:
                text = await page.locator("body").first.inner_text()
            text = (text or "").strip()
            if len(text) > max_chars:
                text = text[:max_chars] + "\n\n[…truncated…]"
            return {"text": text, "url": page.url, "length": len(text)}
        except Exception as e:
            return {"error": f"browser_read_text failed: {e}"}

    async def _tool_browser_close(self, args: Dict) -> Dict:
        """Tear down the Playwright session. Safe to call when nothing is open."""
        try:
            if self._pw_context is not None:
                await self._pw_context.close()
            if self._pw is not None:
                await self._pw.stop()
        except Exception as e:
            return {"closed": False, "error": str(e)}
        finally:
            self._pw_page = None
            self._pw_context = None
            self._pw = None
        return {"closed": True}

    # ─── Community Q&A: search + page summarization ──────────
    # Thin wrappers over the existing web_search tool plus Playwright.
    # community_search restricts to tech forums where answers are
    # typically higher-quality than generic search.

    async def _tool_community_search(self, args: Dict) -> Dict:
        """Search tech support communities (Stack Overflow, Super User,
        r/techsupport, answers.microsoft.com) for a question.

        Args:
            query: the user's question or error message.
            sites: optional list of domains to restrict to. Defaults to the
                   curated community list.
            max_results: cap on the number of hits (default 5).
        """
        query = args.get("query")
        if not query:
            return {"error": "community_search requires 'query'."}
        default_sites = [
            "stackoverflow.com",
            "superuser.com",
            "answers.microsoft.com",
            "reddit.com/r/techsupport",
            "learn.microsoft.com",
        ]
        sites = args.get("sites") or default_sites
        site_filter = " OR ".join(f"site:{s}" for s in sites)
        scoped_query = f"{query} ({site_filter})"
        max_results = int(args.get("max_results", 5))
        # Delegate to the existing web_search tool so ranking/retry logic is shared.
        web = await self.execute("web_search", {"query": scoped_query})
        results = web.get("results", []) if isinstance(web, dict) else []
        # Light ranking: prefer Microsoft-official > Stack Overflow > everything else.
        def _rank(r):
            url = (r.get("url") or "").lower()
            if "learn.microsoft.com" in url or "answers.microsoft.com" in url:
                return 0
            if "stackoverflow.com" in url or "superuser.com" in url:
                return 1
            return 2
        results.sort(key=_rank)
        return {
            "query": query,
            "scoped_query": scoped_query,
            "results": results[:max_results],
            "sites": sites,
        }

    async def _tool_summarize_page(self, args: Dict) -> Dict:
        """Fetch a page via the browser context and return a short excerpt.

        This is intentionally *not* an LLM summarizer — it just pulls the
        ``<main>``/``<article>`` text so the calling model can read it as
        context. Always returns the source URL for citation.
        """
        url = args.get("url")
        if not url:
            return {"error": "summarize_page requires 'url'."}
        max_chars = int(args.get("max_chars", 3000))
        try:
            page = await self._ensure_browser()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Try common content containers in order of specificity.
            for selector in ("article", "main", '[role="main"]', "body"):
                try:
                    locator = page.locator(selector).first
                    if await locator.count() > 0:
                        text = (await locator.inner_text()).strip()
                        if text:
                            break
                except Exception:
                    text = ""
            else:
                text = ""
            if len(text) > max_chars:
                text = text[:max_chars] + "\n\n[…truncated…]"
            title = await page.title()
            return {
                "url": url,
                "title": title,
                "excerpt": text,
                "length": len(text),
                "citation": url,
            }
        except Exception as e:
            return {"error": f"summarize_page failed: {e}", "url": url}
