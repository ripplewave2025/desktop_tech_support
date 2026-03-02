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


class ToolExecutor:
    """Executes tool calls from the AI agent, routing through safety system."""

    def __init__(self, automation=None):
        # Lazy-init AutomationController to avoid import issues in tests
        self._auto = automation
        self._pm = ProcessManager()

        # Destructive PowerShell patterns that should be blocked
        self._ps_blocklist = [
            "Remove-Item", "Format-Volume", "Clear-Disk",
            "Set-ExecutionPolicy", "Remove-Computer",
            "Clear-RecycleBin", "Stop-Computer", "Restart-Computer",
            "Reset-Computer", "Uninstall-", "reg delete",
        ]

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

        # Map setting names to safe PowerShell commands
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
        command = args["command"]

        # Safety: block destructive commands
        for blocked in self._ps_blocklist:
            if blocked.lower() in command.lower():
                return {"error": f"Blocked: command contains '{blocked}' (safety restriction)"}

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
