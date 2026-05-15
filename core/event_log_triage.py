"""
Structured Event Log triage.

The Windows Event Log is gold for diagnosing intermittent issues but
useless to a non-technical user as raw output. This module:

  1. Pulls recent error/critical events from a chosen log (System,
     Application, Setup) using ``Get-WinEvent`` filtered by Level.
  2. Normalizes every entry to ``{time, log, source, id, level, message}``.
  3. Groups by (source, id) so the user sees "boot lost power 3 times in
     the last 24h" instead of three identical individual events.
  4. Annotates known IDs with a plain-English explanation so the AI can
     say "Event 41 means an unexpected shutdown — usually a power loss
     or a hard crash" rather than reading the raw XML.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


# Annotations for the most common event IDs a tier-1 tech actually cares
# about. (Provider, ID) -> {summary, hint}. The summary is what the AI
# reads to the user; the hint suggests a next diagnostic step.
_KNOWN_EVENTS: Dict[tuple, Dict[str, str]] = {
    ("Microsoft-Windows-Kernel-Power", 41): {
        "summary": "Unexpected shutdown — the system rebooted without a clean stop.",
        "hint": "Check power supply, then look for a BSOD around the same time.",
    },
    ("Microsoft-Windows-EventLog", 6008): {
        "summary": "Dirty shutdown — the previous session ended unexpectedly.",
        "hint": "Pair with Kernel-Power 41 to confirm cause.",
    },
    ("Microsoft-Windows-WHEA-Logger", 18): {
        "summary": "Hardware error — the platform reported a corrected machine check.",
        "hint": "Repeated occurrences point to failing CPU, RAM, or motherboard.",
    },
    ("Microsoft-Windows-WHEA-Logger", 19): {
        "summary": "Hardware error — corrected error from PCI Express.",
        "hint": "Often a flaky GPU/NVMe slot. Reseat the device or update firmware.",
    },
    ("Microsoft-Windows-DNS-Client", 1014): {
        "summary": "DNS name resolution timed out.",
        "hint": "Try safe_op net.flush_dns; if persistent, set a public resolver.",
    },
    ("disk", 7): {
        "summary": "Bad block — disk reported an I/O error.",
        "hint": "Check SMART (safe_op sys.disk_health) and back up immediately.",
    },
    ("disk", 11): {
        "summary": "Disk controller error.",
        "hint": "Could be a failing drive or a bad cable.",
    },
    ("disk", 51): {
        "summary": "Page-out error — disk couldn't write to the page file.",
        "hint": "Often precedes drive failure. Run chkdsk.",
    },
    ("Service Control Manager", 7000): {
        "summary": "A service failed to start.",
        "hint": "Check the service's specific error in the message.",
    },
    ("Service Control Manager", 7031): {
        "summary": "A service terminated unexpectedly.",
        "hint": "Look at the service name; restart it via safe_op service.start.",
    },
    ("Application Error", 1000): {
        "summary": "An application crashed.",
        "hint": "The faulting module name is in the message.",
    },
    ("Application Hang", 1002): {
        "summary": "An application stopped responding.",
        "hint": "If recurring for the same app, try repair/reinstall.",
    },
    ("Microsoft-Windows-Wininit", 1015): {
        "summary": "Critical system component failed initialization.",
        "hint": "Check for recent updates / drivers; consider sfc /scannow.",
    },
    ("Microsoft-Windows-Eventlog", 1101): {
        "summary": "An event channel failed to open due to a configuration issue.",
        "hint": "Usually benign but worth noting if other Eventlog issues appear.",
    },
}

# Levels that ``Get-WinEvent`` understands: 1=Critical, 2=Error, 3=Warning.
_LEVEL_NAMES = {1: "Critical", 2: "Error", 3: "Warning"}
_VALID_LOGS = {"System", "Application", "Setup"}


@dataclass
class EventEntry:
    timestamp: str
    log: str
    provider: str
    event_id: int
    level_name: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        annotation = _KNOWN_EVENTS.get((self.provider, self.event_id))
        if annotation:
            d["explanation"] = annotation["summary"]
            d["next_step"] = annotation["hint"]
            d["known"] = True
        else:
            d["known"] = False
        return d


def recent_errors(log: str = "System",
                  hours: int = 24,
                  limit: int = 50,
                  include_warnings: bool = False) -> Dict[str, Any]:
    """Return recent error (and optionally warning) events from `log`.

    Validation:
      * `log` must be one of the standard channels — refuses arbitrary names.
      * `hours` clamped to [1, 168] (one week).
      * `limit` clamped to [1, 500].

    Returns ``{events: [...], supported: bool, error: str?}``.
    """
    if os.name != "nt":
        return {"events": [], "supported": False,
                "error": "Event Log triage only works on Windows."}
    if log not in _VALID_LOGS:
        return {"events": [], "supported": True,
                "error": f"log must be one of {sorted(_VALID_LOGS)}"}
    hours = max(1, min(int(hours), 168))
    limit = max(1, min(int(limit), 500))
    levels = "1,2,3" if include_warnings else "1,2"

    cmd = (
        "$start = (Get-Date).AddHours(-" + str(hours) + "); "
        f"Get-WinEvent -MaxEvents {limit} "
        f"-FilterHashtable @{{LogName='{log}';Level=@({levels});StartTime=$start}} "
        "-ErrorAction SilentlyContinue | "
        "Select-Object TimeCreated,LogName,ProviderName,Id,LevelDisplayName,Message | "
        "ConvertTo-Json -Depth 3 -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=60, shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return {"events": [], "supported": False, "error": str(e)}

    if result.returncode != 0 and not result.stdout.strip():
        return {"events": [], "supported": True,
                "error": (result.stderr or "no events").strip()[:500]}
    return {"events": _parse_events(result.stdout), "supported": True}


def _parse_events(stdout: str) -> List[Dict[str, Any]]:
    if not stdout.strip():
        return []
    try:
        data = json.loads(stdout)
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    out = []
    for entry in data:
        ev = EventEntry(
            timestamp=str(entry.get("TimeCreated") or ""),
            log=str(entry.get("LogName") or ""),
            provider=str(entry.get("ProviderName") or ""),
            event_id=int(entry.get("Id") or 0),
            level_name=str(entry.get("LevelDisplayName") or ""),
            message=(entry.get("Message") or "")[:800],
        )
        out.append(ev.to_dict())
    return out


def triage_summary(log: str = "System",
                   hours: int = 24,
                   include_warnings: bool = False) -> Dict[str, Any]:
    """Group recent events by (provider, id) and rank by frequency.

    Output:
      {
        "log": "System",
        "hours": 24,
        "supported": True,
        "groups": [
          { "provider": "...", "event_id": 41, "count": 3, "level": "Critical",
            "explanation": "...", "next_step": "...", "latest_message": "..." },
          ...
        ]
      }

    The ranked list is what an AI presents back to the user: "I see X
    critical events in the last 24 hours, here are the top 3 patterns."
    """
    raw = recent_errors(log=log, hours=hours, limit=500,
                        include_warnings=include_warnings)
    if not raw.get("supported"):
        return {"log": log, "hours": hours, "supported": False,
                "error": raw.get("error", "")}
    groups: Dict[tuple, Dict[str, Any]] = {}
    for ev in raw["events"]:
        key = (ev["provider"], ev["event_id"])
        if key not in groups:
            groups[key] = {
                "provider": ev["provider"],
                "event_id": ev["event_id"],
                "count": 0,
                "level": ev["level_name"],
                "latest_timestamp": ev["timestamp"],
                "latest_message": ev["message"],
                "known": ev.get("known", False),
                "explanation": ev.get("explanation"),
                "next_step": ev.get("next_step"),
            }
        groups[key]["count"] += 1
        # Keep the most recent message as the representative one.
        if ev["timestamp"] > groups[key]["latest_timestamp"]:
            groups[key]["latest_timestamp"] = ev["timestamp"]
            groups[key]["latest_message"] = ev["message"]
    ranked = sorted(groups.values(),
                    key=lambda g: (g["count"], 1 if g["known"] else 0),
                    reverse=True)
    return {"log": log, "hours": hours, "supported": True,
            "total_events": sum(g["count"] for g in ranked),
            "groups": ranked}
