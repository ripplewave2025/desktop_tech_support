#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Base Diagnostic & Narrator — Shared infrastructure for all diagnostic modules.
"""

import sys
import io
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, List, Dict, Any

# Fix Windows console encoding
# Skip this in frozen (PyInstaller) mode to avoid double-wrapping stdout
try:
    if not getattr(sys, 'frozen', False) and sys.stdout and hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
except Exception:
    pass


class TechSupportNarrator:
    """
    Narration system for explaining actions in simple, friendly language.
    
    Designed for non-technical users — avoids jargon, explains WHY,
    and celebrates successes.
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.log: List[Dict[str, Any]] = []
        self._start_time = time.time()

    def say(self, message: str):
        """Narrate in simple, friendly language."""
        self._record("say", message)
        if self.verbose:
            print(f"\n  [Zora] {message}")

    def think(self, detail: str):
        """Log technical detail (less prominent)."""
        self._record("think", detail)
        if self.verbose:
            print(f"         > {detail}")

    def success(self, message: str):
        """Announce a success."""
        self._record("success", message)
        if self.verbose:
            print(f"\n  [OK] {message}")

    def problem(self, message: str):
        """Announce a problem found."""
        self._record("problem", message)
        if self.verbose:
            print(f"\n  [!!] {message}")

    def tip(self, message: str):
        """Give a helpful tip."""
        self._record("tip", message)
        if self.verbose:
            print(f"\n  [Tip] {message}")

    def step(self, number: int, total: int, description: str):
        """Announce a diagnostic step."""
        self._record("step", f"[{number}/{total}] {description}")
        if self.verbose:
            print(f"\n  --- Step {number}/{total}: {description} ---")

    def separator(self):
        if self.verbose:
            print(f"\n  {'=' * 56}")

    def _record(self, msg_type: str, message: str):
        self.log.append({
            "timestamp": datetime.now().isoformat(),
            "type": msg_type,
            "message": message,
        })

    def get_session_summary(self) -> Dict[str, Any]:
        """Get summary of this narration session."""
        problems = [e for e in self.log if e["type"] == "problem"]
        successes = [e for e in self.log if e["type"] == "success"]
        return {
            "duration_seconds": round(time.time() - self._start_time, 1),
            "total_messages": len(self.log),
            "problems_found": len(problems),
            "fixes_applied": len(successes),
            "log": self.log,
        }


def ask_permission(action: str) -> bool:
    """Ask user for permission in simple language."""
    print(f"\n  [?] May I {action}?")
    try:
        response = input("      Type 'yes' or 'no': ").strip().lower()
        return response in ("yes", "y", "ok", "sure", "go ahead")
    except (EOFError, KeyboardInterrupt):
        return False


class DiagnosticResult:
    """Structured result from a diagnostic check."""

    def __init__(self, name: str, status: str = "unknown",
                 details: str = "", fix_available: bool = False,
                 fix_applied: bool = False):
        self.name = name
        self.status = status  # "ok", "warning", "error", "fixed"
        self.details = details
        self.fix_available = fix_available
        self.fix_applied = fix_applied

    def __repr__(self):
        return f"<DiagResult {self.name}: {self.status}>"


class BaseDiagnostic(ABC):
    """
    Abstract base class for all diagnostic modules.
    
    Subclasses implement: diagnose() and optionally apply_fix().
    """

    CATEGORY = "general"
    DESCRIPTION = "Base diagnostic"

    def __init__(self, narrator: Optional[TechSupportNarrator] = None):
        self.narrator = narrator or TechSupportNarrator()
        self.results: List[DiagnosticResult] = []

    @abstractmethod
    def diagnose(self) -> List[DiagnosticResult]:
        """Run diagnostics and return results."""
        pass

    def apply_fix(self, result: DiagnosticResult) -> bool:
        """Apply a fix for a diagnostic finding. Override in subclass."""
        return False

    def run(self, auto_fix: bool = False) -> List[DiagnosticResult]:
        """Run full diagnostic flow: diagnose, optionally fix."""
        self.narrator.separator()
        self.narrator.say(f"Starting {self.DESCRIPTION}...")
        self.narrator.separator()

        self.results = self.diagnose()

        # Report results
        problems = [r for r in self.results if r.status in ("warning", "error")]
        fixed = [r for r in self.results if r.status == "fixed"]
        ok = [r for r in self.results if r.status == "ok"]

        self.narrator.separator()
        if not problems and not fixed:
            self.narrator.success("Everything looks good! No issues found.")
        else:
            if fixed:
                self.narrator.success(f"Fixed {len(fixed)} issue(s).")
            if problems:
                fixable = [p for p in problems if p.fix_available]
                self.narrator.problem(f"Found {len(problems)} issue(s) ({len(fixable)} fixable).")

                if auto_fix and fixable:
                    for result in fixable:
                        self.narrator.say(f"Attempting to fix: {result.name}")
                        if self.apply_fix(result):
                            result.status = "fixed"
                            result.fix_applied = True
                            self.narrator.success(f"Fixed: {result.name}")
                        else:
                            self.narrator.problem(f"Could not fix: {result.name}")

        self.narrator.separator()
        return self.results

    def get_summary(self) -> Dict[str, Any]:
        """Get structured summary of diagnostic results."""
        return {
            "category": self.CATEGORY,
            "total_checks": len(self.results),
            "ok": len([r for r in self.results if r.status == "ok"]),
            "warnings": len([r for r in self.results if r.status == "warning"]),
            "errors": len([r for r in self.results if r.status == "error"]),
            "fixed": len([r for r in self.results if r.status == "fixed"]),
            "results": [
                {"name": r.name, "status": r.status, "details": r.details}
                for r in self.results
            ],
        }
