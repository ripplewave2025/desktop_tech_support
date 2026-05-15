"""
BSOD / bugcheck triage.

When Windows blue-screens, two things land on the system:
  1. A minidump file at ``C:\\Windows\\Minidump\\*.dmp`` (small kernel dump).
  2. An Event Log entry with source ``BugCheck`` (event ID 1001) carrying
     the bugcheck code and the names of any drivers blamed.

Reading the .dmp file requires WinDbg or ``dbghelp.dll`` — neither is
appropriate to redistribute. The Event Log entry covers ~80% of the value
for a tech-support workflow: bugcheck code, parameters, faulting driver
guess, and timestamp.

This module exposes:
  * ``recent_bsods(limit)`` — last N BSODs from the System log
  * ``minidump_files()`` — list raw .dmp files (for offline analysis)
  * ``explain(code)`` — human-readable name + common causes for a bugcheck
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


# A curated map of the 30-ish bugcheck codes that account for the vast
# majority of consumer-PC blue screens. The "common_causes" list is what a
# tier-1 tech would say when the user reads the code over the phone.
_BUGCHECKS: Dict[int, Dict[str, Any]] = {
    0x0A: {
        "name": "IRQL_NOT_LESS_OR_EQUAL",
        "common_causes": [
            "Faulty or incompatible driver (often graphics or networking)",
            "Bad RAM",
            "A recent driver update — try rolling back",
        ],
    },
    0x1E: {
        "name": "KMODE_EXCEPTION_NOT_HANDLED",
        "common_causes": [
            "Driver bug",
            "Failing hardware (test RAM with mdsched)",
        ],
    },
    0x3B: {
        "name": "SYSTEM_SERVICE_EXCEPTION",
        "common_causes": [
            "Driver bug — first parameter is the exception code",
            "Recently installed antivirus or VPN driver",
        ],
    },
    0x50: {
        "name": "PAGE_FAULT_IN_NONPAGED_AREA",
        "common_causes": [
            "Failing RAM (very common — run mdsched.exe)",
            "Bad sector on the system drive (chkdsk /f /r)",
            "Driver writing to freed memory",
        ],
    },
    0x7A: {
        "name": "KERNEL_DATA_INPAGE_ERROR",
        "common_causes": [
            "Disk error reading paged-out memory back from the page file",
            "Failing drive (check SMART)",
            "Loose SATA / NVMe connection",
        ],
    },
    0x7B: {
        "name": "INACCESSIBLE_BOOT_DEVICE",
        "common_causes": [
            "Storage controller driver mismatch (often after a chipset update)",
            "BIOS storage mode changed (RAID/AHCI)",
            "Failed boot drive",
        ],
    },
    0x7E: {
        "name": "SYSTEM_THREAD_EXCEPTION_NOT_HANDLED",
        "common_causes": [
            "Driver crash — the faulting driver name is in the dump",
            "Common after Windows Update if a driver wasn't refreshed",
        ],
    },
    0x9F: {
        "name": "DRIVER_POWER_STATE_FAILURE",
        "common_causes": [
            "Driver didn't respond during sleep/wake",
            "Often graphics, USB, or networking driver",
        ],
    },
    0xA0: {
        "name": "INTERNAL_POWER_ERROR",
        "common_causes": [
            "Power management issue, often after sleep",
            "Try updating the chipset and graphics drivers via the OEM tool",
        ],
    },
    0xC2: {
        "name": "BAD_POOL_CALLER",
        "common_causes": [
            "Driver freeing memory it doesn't own",
            "Update or remove the driver named in the dump",
        ],
    },
    0xC4: {
        "name": "DRIVER_VERIFIER_DETECTED_VIOLATION",
        "common_causes": [
            "Driver Verifier is on and caught a buggy driver",
            "Disable Verifier (verifier /reset) once you've identified the driver",
        ],
    },
    0xC5: {
        "name": "DRIVER_CORRUPTED_EXPOOL",
        "common_causes": [
            "Driver wrote past a buffer",
            "Bad RAM is also a possibility",
        ],
    },
    0xD1: {
        "name": "DRIVER_IRQL_NOT_LESS_OR_EQUAL",
        "common_causes": [
            "Driver bug accessing memory at high IRQL",
            "Update the driver named in the dump",
        ],
    },
    0xEF: {
        "name": "CRITICAL_PROCESS_DIED",
        "common_causes": [
            "A critical Windows process (csrss, smss, wininit, etc.) terminated",
            "Run sfc /scannow + DISM /Online /Cleanup-Image /RestoreHealth",
            "Could be malware or a corrupt system file",
        ],
    },
    0xF4: {
        "name": "CRITICAL_OBJECT_TERMINATION",
        "common_causes": [
            "Like 0xEF — a kernel-critical process died",
            "Failing storage is a common root cause",
        ],
    },
    0x109: {
        "name": "CRITICAL_STRUCTURE_CORRUPTION",
        "common_causes": [
            "Kernel detected its own structures were modified — usually bad RAM",
            "Sometimes overclocking or buggy anti-cheat / security driver",
        ],
    },
    0x124: {
        "name": "WHEA_UNCORRECTABLE_ERROR",
        "common_causes": [
            "Hardware reported an unrecoverable error (CPU, RAM, motherboard)",
            "Check temperatures, then test RAM, then suspect the CPU",
        ],
    },
    0x133: {
        "name": "DPC_WATCHDOG_VIOLATION",
        "common_causes": [
            "A driver took too long in a DPC — usually storage (NVMe firmware) or networking",
            "Update SSD firmware via the OEM tool",
        ],
    },
    0x139: {
        "name": "KERNEL_SECURITY_CHECK_FAILURE",
        "common_causes": [
            "Kernel detected a memory corruption — driver bug or bad RAM",
            "Run sfc /scannow + Driver Verifier",
        ],
    },
    0x18B: {
        "name": "SECURE_KERNEL_ERROR",
        "common_causes": [
            "Issue with virtualization-based security (VBS) or HVCI",
            "Try toggling Memory Integrity in Windows Security",
        ],
    },
    0x1A: {
        "name": "MEMORY_MANAGEMENT",
        "common_causes": [
            "Almost always bad RAM — run mdsched.exe overnight",
            "Sometimes a driver writing past its buffer",
        ],
    },
    0x1C: {
        "name": "PFN_LIST_CORRUPT",
        "common_causes": [
            "Memory page management got corrupted — usually bad RAM",
        ],
    },
}


@dataclass
class BSODEvent:
    timestamp: str           # ISO from Event Log
    bugcheck_code: int       # e.g., 0x7E
    parameters: List[str]    # 4 hex strings if available
    raw_message: str         # the original event text (truncated)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["bugcheck_code_hex"] = f"0x{self.bugcheck_code:X}"
        info = explain(self.bugcheck_code)
        d.update({
            "name": info.get("name"),
            "common_causes": info.get("common_causes", []),
        })
        return d


def explain(bugcheck_code: int) -> Dict[str, Any]:
    """Return name + common causes for a bugcheck code, or a generic note."""
    info = _BUGCHECKS.get(bugcheck_code)
    if info:
        return {
            "code": bugcheck_code,
            "code_hex": f"0x{bugcheck_code:X}",
            "name": info["name"],
            "common_causes": list(info["common_causes"]),
            "known": True,
        }
    return {
        "code": bugcheck_code,
        "code_hex": f"0x{bugcheck_code:X}" if bugcheck_code else "0x0",
        "name": "Unknown bugcheck",
        "common_causes": [
            "Look up the code at https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/bug-check-code-reference",
            "Generic next steps: run sfc /scannow, test RAM, update OEM drivers",
        ],
        "known": False,
    }


# Regex pulled from the canonical Event ID 1001 (BugCheck source) message.
# The message format is documented and stable across Windows 10/11.
_BUGCHECK_RE = re.compile(
    r"bugcheck was:?\s*0x([0-9A-Fa-f]+)\s*"
    r"\(0x([0-9A-Fa-f]+)?,?\s*0x([0-9A-Fa-f]+)?,?\s*0x([0-9A-Fa-f]+)?,?\s*0x([0-9A-Fa-f]+)?\)?",
    re.IGNORECASE,
)


def _parse_message(message: str) -> Optional[Dict[str, Any]]:
    if not message:
        return None
    m = _BUGCHECK_RE.search(message)
    if not m:
        return None
    code = int(m.group(1), 16)
    params = [m.group(i) for i in (2, 3, 4, 5) if m.group(i)]
    return {"bugcheck_code": code, "parameters": params}


def recent_bsods(limit: int = 10) -> Dict[str, Any]:
    """Read the last `limit` BugCheck events from the System log.

    Returns ``{"events": [BSODEvent...], "supported": bool, "error": str?}``.
    On non-Windows or when ``Get-WinEvent`` isn't available, returns a stub
    with ``supported=False`` so callers can decline gracefully.
    """
    if os.name != "nt":
        return {"events": [], "supported": False,
                "error": "BSOD analyzer only works on Windows."}
    cmd = (
        f"Get-WinEvent -MaxEvents {int(limit)} "
        "-FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-WER-SystemErrorReporting','BugCheck'} "
        "-ErrorAction SilentlyContinue | "
        "Select-Object TimeCreated,Id,ProviderName,Message | "
        "ConvertTo-Json -Depth 3 -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=30, shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return {"events": [], "supported": False, "error": str(e)}

    if result.returncode != 0 and not result.stdout.strip():
        return {
            "events": [], "supported": True,
            "error": (result.stderr or "Get-WinEvent returned no data").strip()[:500],
        }
    return {"events": _parse_event_json(result.stdout), "supported": True}


def _parse_event_json(stdout: str) -> List[Dict[str, Any]]:
    import json as _json
    try:
        data = _json.loads(stdout) if stdout.strip() else []
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    out = []
    for entry in data:
        msg = entry.get("Message") or ""
        parsed = _parse_message(msg) or {}
        ev = BSODEvent(
            timestamp=str(entry.get("TimeCreated") or ""),
            bugcheck_code=int(parsed.get("bugcheck_code") or 0),
            parameters=parsed.get("parameters", []),
            raw_message=msg[:1000],
        )
        out.append(ev.to_dict())
    return out


def minidump_files() -> Dict[str, Any]:
    """List raw minidump files. Useful for handing off to a deeper tool."""
    if os.name != "nt":
        return {"files": [], "supported": False}
    folder = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Minidump"
    if not folder.exists():
        return {"files": [], "supported": True, "folder": str(folder)}
    files = []
    for p in sorted(folder.glob("*.dmp"),
                    key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            files.append({
                "path": str(p),
                "size_bytes": p.stat().st_size,
                "modified": int(p.stat().st_mtime),
            })
        except OSError:
            continue
    return {"files": files, "supported": True, "folder": str(folder)}
