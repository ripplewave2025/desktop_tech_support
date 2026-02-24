#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Safety System — Multi-layered protection for automation actions.

Provides: SafetyController, EmergencyStop, RateLimiter, Blacklist, ActionLogger
"""

import os
import json
import time
import threading
from collections import deque
from datetime import datetime
from enum import Enum, auto
from typing import Optional, Dict, Any, List


class RiskLevel(Enum):
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()


class SafetyCheckResult:
    """Result of a safety check on an action."""

    def __init__(self, allowed: bool, reason: str = "", confirm_required: bool = False):
        self.allowed = allowed
        self.reason = reason
        self.confirm_required = confirm_required

    @classmethod
    def ALLOW(cls):
        return cls(allowed=True)

    @classmethod
    def DENY(cls, reason: str):
        return cls(allowed=False, reason=reason)

    @classmethod
    def CONFIRM_REQUIRED(cls, reason: str):
        return cls(allowed=True, reason=reason, confirm_required=True)


class EmergencyStop:
    """Global hotkey to abort all automation (Ctrl+Alt+Esc)."""

    def __init__(self, hotkey: str = "ctrl+alt+esc"):
        self._triggered = False
        self._lock = threading.Lock()
        self.hotkey = hotkey
        self._listener_thread = None
        self._setup_listener()

    def _setup_listener(self):
        """Register global hotkey listener in background thread."""
        try:
            from pynput import keyboard

            combo = {keyboard.Key.ctrl_l, keyboard.Key.alt_l, keyboard.Key.esc}
            current_keys = set()

            def on_press(key):
                current_keys.add(key)
                if combo.issubset(current_keys):
                    self.trigger()

            def on_release(key):
                current_keys.discard(key)

            self._listener_thread = keyboard.Listener(
                on_press=on_press, on_release=on_release
            )
            self._listener_thread.daemon = True
            self._listener_thread.start()
        except ImportError:
            pass  # pynput not available, emergency stop via hotkey disabled

    def trigger(self):
        with self._lock:
            self._triggered = True
            print("\n[EMERGENCY STOP] Automation halted! Press Ctrl+C or restart to continue.")

    def is_triggered(self) -> bool:
        with self._lock:
            return self._triggered

    def reset(self):
        with self._lock:
            self._triggered = False


class RateLimiter:
    """Prevent runaway automation loops."""

    def __init__(self, max_actions_per_minute: int = 100):
        self.max_actions = max_actions_per_minute
        self._timestamps: deque = deque()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        now = time.time()
        with self._lock:
            # Remove timestamps older than 60 seconds
            while self._timestamps and now - self._timestamps[0] > 60:
                self._timestamps.popleft()
            if len(self._timestamps) >= self.max_actions:
                return False
            self._timestamps.append(now)
            return True

    @property
    def current_count(self) -> int:
        now = time.time()
        with self._lock:
            while self._timestamps and now - self._timestamps[0] > 60:
                self._timestamps.popleft()
            return len(self._timestamps)


class Blacklist:
    """Defines restricted zones for automation actions."""

    SYSTEM_PROTECTED = [
        r"C:\Windows\System32",
        r"C:\Windows\SysWOW64",
        r"C:\Windows\boot",
        r"C:\$Recycle.Bin",
        r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
    ]

    def __init__(self, custom_paths: Optional[List[str]] = None,
                 custom_processes: Optional[List[str]] = None,
                 system_protected: bool = True):
        self.protected_paths = list(self.SYSTEM_PROTECTED) if system_protected else []
        self.protected_paths.extend(custom_paths or [])
        self.protected_processes = [p.lower() for p in (custom_processes or [])]

    def is_path_restricted(self, path: str) -> bool:
        norm = os.path.normpath(path).lower()
        for protected in self.protected_paths:
            if norm.startswith(os.path.normpath(protected).lower()):
                return True
        return False

    def is_process_restricted(self, name: str) -> bool:
        return name.lower() in self.protected_processes


class ActionLogger:
    """Audit trail for all automation actions — writes JSON lines."""

    def __init__(self, log_file: str = "logs/automation_log.jsonl"):
        self.log_file = log_file
        os.makedirs(os.path.dirname(log_file) if os.path.dirname(log_file) else ".", exist_ok=True)

    def log(self, action_type: str, params: Dict[str, Any],
            success: bool, error: Optional[str] = None,
            duration_ms: float = 0):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action_type": action_type,
            "parameters": params,
            "success": success,
            "error": error,
            "duration_ms": round(duration_ms, 2),
        }
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except OSError:
            pass  # Don't crash on logging failure

    def get_recent(self, limit: int = 20) -> List[Dict]:
        if not os.path.exists(self.log_file):
            return []
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            entries = []
            for line in lines[-limit:]:
                try:
                    entries.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
            return entries
        except OSError:
            return []


class SafetyController:
    """Central safety coordinator — validates all actions before execution."""

    # Actions considered high-risk
    HIGH_RISK_ACTIONS = frozenset([
        "kill_process", "delete_file", "registry_edit",
        "uninstall_program", "modify_settings", "clear_data",
    ])

    MEDIUM_RISK_ACTIONS = frozenset([
        "launch_process", "move_window", "install_software",
        "restart_service", "close_window",
    ])

    def __init__(self, config: Optional[Dict] = None):
        config = config or {}
        safety_cfg = config.get("safety", {})
        blacklist_cfg = config.get("blacklist", {})

        self.emergency_stop = EmergencyStop(
            safety_cfg.get("emergency_stop_hotkey", "ctrl+alt+esc")
        )
        self.rate_limiter = RateLimiter(
            safety_cfg.get("max_actions_per_minute", 100)
        )
        self.blacklist = Blacklist(
            custom_paths=blacklist_cfg.get("custom_paths", []),
            custom_processes=blacklist_cfg.get("custom_processes", []),
            system_protected=blacklist_cfg.get("system_protected", True),
        )
        self.logger = ActionLogger(
            safety_cfg.get("log_file", "logs/automation_log.jsonl")
        )
        self.require_confirmation = safety_cfg.get("require_confirmation_for_high_risk", True)

    def check_action(self, action_type: str, target: Optional[str] = None) -> SafetyCheckResult:
        """Validate whether an action is safe to execute."""

        # 1. Emergency stop
        if self.emergency_stop.is_triggered():
            return SafetyCheckResult.DENY("Emergency stop is active")

        # 2. Rate limiting
        if not self.rate_limiter.allow():
            return SafetyCheckResult.DENY(
                f"Rate limit exceeded ({self.rate_limiter.max_actions}/min)"
            )

        # 3. Blacklist check
        if target:
            if self.blacklist.is_path_restricted(target):
                return SafetyCheckResult.DENY(f"Target path is protected: {target}")
            if self.blacklist.is_process_restricted(target):
                return SafetyCheckResult.DENY(f"Target process is protected: {target}")

        # 4. Risk assessment
        if action_type in self.HIGH_RISK_ACTIONS and self.require_confirmation:
            return SafetyCheckResult.CONFIRM_REQUIRED(
                f"High-risk action: {action_type}"
            )

        return SafetyCheckResult.ALLOW()

    def assess_risk(self, action_type: str) -> RiskLevel:
        if action_type in self.HIGH_RISK_ACTIONS:
            return RiskLevel.HIGH
        elif action_type in self.MEDIUM_RISK_ACTIONS:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
