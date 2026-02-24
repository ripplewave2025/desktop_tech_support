#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automation Controller — Unified API for all Windows automation capabilities.

This is the main entry point. All actions go through safety checks, logging,
and error handling before being dispatched to the appropriate component.
"""

import json
import os
import time
from typing import Optional, List, Tuple, Dict, Any

from .safety import SafetyController, SafetyCheckResult
from .window_manager import WindowManager, Window, WindowInfo
from .input_controller import InputController
from .screen_capture import ScreenCapture
from .process_manager import ProcessManager, ProcessInfo, SystemInfo


class AutomationError(Exception):
    """Base exception for automation errors."""

    def __init__(self, message: str, recoverable: bool = False,
                 suggestions: Optional[List[str]] = None):
        self.message = message
        self.recoverable = recoverable
        self.suggestions = suggestions or []
        super().__init__(message)


class SafetyError(AutomationError):
    """Action blocked by safety system."""

    def __init__(self, message: str):
        super().__init__(message, recoverable=False,
                         suggestions=["Reset emergency stop", "Adjust rate limits in config"])


class WindowNotFoundError(AutomationError):
    def __init__(self, query: str):
        super().__init__(
            f"Window not found: {query}",
            recoverable=True,
            suggestions=[
                "Check if the application is running",
                "Verify window title spelling",
                "Use list_windows() to see available windows",
            ],
        )


class ElementNotFoundError(AutomationError):
    def __init__(self, element: str, window: str = ""):
        ctx = f" in '{window}'" if window else ""
        super().__init__(
            f"UI element not found: '{element}'{ctx}",
            recoverable=True,
            suggestions=[
                "Use window.print_control_identifiers() to inspect elements",
                "Try a different element name or control_type",
            ],
        )


class AutomationController:
    """
    Main controller for all automation operations.
    
    All public methods go through safety checks before execution.
    Results are logged automatically.
    """

    def __init__(self, config_path: Optional[str] = None):
        # Load config
        self._config = self._load_config(config_path)

        # Initialize components
        self.safety = SafetyController(self._config)

        win_cfg = self._config.get("windows", {})
        self.windows = WindowManager(
            backend=win_cfg.get("backend", "uia"),
            search_timeout=win_cfg.get("search_timeout", 5.0),
        )

        input_cfg = self._config.get("input", {})
        self.input = InputController(
            mouse_move_duration=input_cfg.get("mouse_move_duration", 0.2),
            typing_interval=input_cfg.get("typing_interval", 0.01),
            click_delay=input_cfg.get("click_delay", 0.1),
        )

        screen_cfg = self._config.get("screen", {})
        self.screen = ScreenCapture(
            ocr_language=screen_cfg.get("ocr_language", "eng"),
            screenshot_format=screen_cfg.get("screenshot_format", "png"),
        )

        self.processes = ProcessManager()

    def _load_config(self, path: Optional[str] = None) -> Dict:
        """Load configuration from JSON file."""
        if path is None:
            # Look in common locations
            candidates = [
                os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json"),
                "config.json",
                os.path.join(os.path.expanduser("~"), ".techsupport", "config.json"),
            ]
            for candidate in candidates:
                if os.path.exists(candidate):
                    path = candidate
                    break

        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _check_safety(self, action_type: str, target: Optional[str] = None) -> SafetyCheckResult:
        """Run safety checks and raise on denial."""
        result = self.safety.check_action(action_type, target)
        if not result.allowed:
            raise SafetyError(f"Action blocked: {result.reason}")
        return result

    def _log(self, action: str, params: Dict, success: bool,
             error: Optional[str] = None, start_time: float = 0):
        duration = (time.time() - start_time) * 1000 if start_time else 0
        self.safety.logger.log(action, params, success, error, duration)

    # ─── Window Operations ───────────────────────────────────

    def find_window(self, title: Optional[str] = None,
                    title_re: Optional[str] = None,
                    process: Optional[str] = None) -> Window:
        """Find a window by title, regex, or process name."""
        self._check_safety("find_window")
        t0 = time.time()
        win = self.windows.find_window(title=title, title_re=title_re, process=process)
        if not win:
            query = title or title_re or process or "unknown"
            self._log("find_window", {"query": query}, False, "Not found", t0)
            raise WindowNotFoundError(query)
        self._log("find_window", {"title": win.title}, True, start_time=t0)
        return win

    def get_active_window(self) -> Optional[Window]:
        return self.windows.get_active_window()

    def list_windows(self) -> List[WindowInfo]:
        return self.windows.list_windows()

    # ─── Input Operations ────────────────────────────────────

    def click(self, x: Optional[int] = None, y: Optional[int] = None,
              button: str = "left", count: int = 1):
        self._check_safety("click")
        t0 = time.time()
        self.input.click(x, y, button, count)
        self._log("click", {"x": x, "y": y, "button": button}, True, start_time=t0)

    def double_click(self, x: Optional[int] = None, y: Optional[int] = None):
        self.click(x, y, count=2)

    def right_click(self, x: Optional[int] = None, y: Optional[int] = None):
        self.click(x, y, button="right")

    def move_mouse(self, x: int, y: int):
        self.input.move_mouse(x, y)

    def get_mouse_position(self) -> Tuple[int, int]:
        return self.input.get_mouse_position()

    def scroll(self, clicks: int, direction: str = "down"):
        self.input.scroll(clicks, direction)

    def drag(self, start_x: int, start_y: int, end_x: int, end_y: int):
        self.input.drag(start_x, start_y, end_x, end_y)

    def type_text(self, text: str, interval: Optional[float] = None):
        self._check_safety("type_text")
        t0 = time.time()
        self.input.type_text(text, interval)
        self._log("type_text", {"length": len(text)}, True, start_time=t0)

    def press_key(self, key: str):
        self.input.press_key(key)

    def hotkey(self, *keys: str):
        self.input.hotkey(*keys)

    # ─── Screen Operations ───────────────────────────────────

    def capture_screen(self, region: Optional[Tuple] = None,
                       output_file: Optional[str] = None,
                       monitor: int = 0):
        """Capture a screenshot, optionally saving to file."""
        if output_file:
            return self.screen.capture_to_file(output_file, region=region, monitor=monitor)
        return self.screen.capture(region=region, monitor=monitor)

    def read_text(self, region: Optional[Tuple] = None) -> str:
        return self.screen.read_text(region=region)

    def find_text(self, needle: str, region: Optional[Tuple] = None):
        return self.screen.find_text(needle, region=region)

    def find_image(self, template_path: str, confidence: float = 0.8):
        return self.screen.find_image(template_path, confidence=confidence)

    def get_pixel_color(self, x: int, y: int) -> Tuple[int, int, int]:
        return self.screen.get_pixel_color(x, y)

    # ─── Process Operations ──────────────────────────────────

    def launch_process(self, path: str, args: Optional[List[str]] = None) -> Optional[ProcessInfo]:
        self._check_safety("launch_process", path)
        t0 = time.time()
        try:
            result = self.processes.launch(path, args)
            self._log("launch_process", {"path": path}, True, start_time=t0)
            return result
        except Exception as e:
            self._log("launch_process", {"path": path}, False, str(e), t0)
            raise

    def kill_process(self, name_or_pid, force: bool = False) -> bool:
        target = str(name_or_pid)
        self._check_safety("kill_process", target)
        t0 = time.time()
        result = self.processes.kill(name_or_pid, force=force)
        self._log("kill_process", {"target": target, "force": force}, result, start_time=t0)
        return result

    def is_process_running(self, name_or_pid) -> bool:
        return self.processes.is_running(name_or_pid)

    def list_processes(self, name_filter: Optional[str] = None) -> List[ProcessInfo]:
        return self.processes.list_processes(name_filter)

    def get_system_info(self) -> SystemInfo:
        return self.processes.get_system_info()

    # ─── Compound Operations ─────────────────────────────────

    def click_element(self, window_title: str, element_name: str,
                      control_type: Optional[str] = None) -> bool:
        """Find a window and click a UI element within it."""
        win = self.find_window(title=window_title)
        win.focus()
        time.sleep(0.3)
        result = win.click_element(element_name, control_type)
        if not result:
            raise ElementNotFoundError(element_name, window_title)
        return True

    def fill_field(self, window_title: str, field_name: str, text: str) -> bool:
        """Find a window, locate a text field, and type into it."""
        win = self.find_window(title=window_title)
        win.focus()
        time.sleep(0.3)
        result = win.type_into_element(field_name, text)
        if not result:
            raise ElementNotFoundError(field_name, window_title)
        return True

    def click_text(self, text: str, region: Optional[Tuple] = None) -> bool:
        """Find text on screen via OCR and click its center."""
        locations = self.find_text(text, region=region)
        if locations:
            x, y, w, h = locations[0]
            self.click(x + w // 2, y + h // 2)
            return True
        return False

    def open_and_type(self, app: str, text: str, wait_seconds: float = 2.0):
        """Launch app, wait, and type text."""
        self.launch_process(app)
        time.sleep(wait_seconds)
        self.type_text(text)

    # ─── Emergency Stop ──────────────────────────────────────

    def is_emergency_stop_triggered(self) -> bool:
        return self.safety.emergency_stop.is_triggered()

    def reset_emergency_stop(self):
        self.safety.emergency_stop.reset()

    def get_recent_actions(self, limit: int = 20):
        return self.safety.logger.get_recent(limit)
