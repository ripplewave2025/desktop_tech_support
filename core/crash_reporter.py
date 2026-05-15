"""
Crash reporting + log rotation for Zora.

What this gives you
-------------------
1. Every uncaught exception (sync or async) writes a structured JSON crash
   dump to ``%LOCALAPPDATA%\\Zora\\crashes\\`` so you find out when Zora
   dies on a user's machine.
2. The dump includes: timestamp, Zora version, Python version, platform,
   the full traceback, and a snapshot of CPU / memory / disk.
3. A bounded retention policy (default 20 most recent) so a crash loop
   doesn't fill the user's disk.
4. ``attach_rotating_log()`` swaps the unbounded ``zora.log`` for a
   ``RotatingFileHandler`` (default 10 MB × 5 files).
5. ``build_support_bundle()`` zips a crash dump + the last N log lines
   for the user to email you. Path-traversal guarded.

Why file-based, not Sentry
--------------------------
Sentry requires an account, an API token, and the user agreeing that their
crash data can leave the machine. File-based works offline, requires no
signup, and the user can review what they're sending before they send it.
A future opt-in Sentry hook can layer on top of this — write_crash() is
still the single funnel.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import socket
import sys
import time
import traceback
import zipfile
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("zora.crash")


_DEFAULT_BASE_DIR = Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / "Zora"
_DEFAULT_CRASH_DIR = _DEFAULT_BASE_DIR / "crashes"
_DEFAULT_LOG_PATH = _DEFAULT_BASE_DIR / "zora.log"
_DEFAULT_RETAIN = 20
_DEFAULT_LOG_BYTES = 10 * 1024 * 1024
_DEFAULT_LOG_BACKUPS = 5

# Idempotency guard so install_crash_handlers can be called from multiple
# entry points without stacking excepthooks.
_installed = False


# ──────────────────────────────────────────────────────────────────────
# Installer
# ──────────────────────────────────────────────────────────────────────

def install_crash_handlers(version: str = "unknown",
                           crash_dir: Path = _DEFAULT_CRASH_DIR,
                           retain: int = _DEFAULT_RETAIN) -> None:
    """Install ``sys.excepthook`` (+ asyncio handler if a loop is reachable).

    Safe to call multiple times. Should be invoked very early in launcher.py,
    before imports that might raise — the earlier this lands, the more
    failure modes get captured.
    """
    global _installed
    if _installed:
        return
    _installed = True
    try:
        crash_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"Crash dir setup failed: {e}")

    previous_excepthook = sys.excepthook

    def _excepthook(exc_type, exc_value, tb):
        try:
            write_crash(exc_type, exc_value, tb,
                        version=version, crash_dir=crash_dir)
            _prune(crash_dir, retain)
        except Exception:
            # Never let the crash handler itself crash — silence is better
            # than a recursive failure that masks the original exception.
            pass
        previous_excepthook(exc_type, exc_value, tb)

    sys.excepthook = _excepthook

    # Try to install an asyncio loop handler too. If no loop exists yet
    # (typical during launcher startup), this just no-ops; the FastAPI
    # startup hook can call install_async_handler() once a loop is alive.
    try:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None
        if loop is not None and not loop.is_closed():
            install_async_handler(version=version, crash_dir=crash_dir, retain=retain)
    except Exception:
        pass


def install_async_handler(version: str = "unknown",
                          crash_dir: Path = _DEFAULT_CRASH_DIR,
                          retain: int = _DEFAULT_RETAIN) -> None:
    """Attach an exception handler to the *currently running* asyncio loop.

    Call this from FastAPI's startup hook to pick up the loop uvicorn creates.
    """
    try:
        import asyncio
        loop = asyncio.get_event_loop()
    except Exception:
        return
    previous = loop.get_exception_handler()

    def _handler(loop_, context):
        exc = context.get("exception")
        if exc is not None:
            try:
                write_crash(type(exc), exc, exc.__traceback__,
                            version=version, crash_dir=crash_dir, kind="asyncio")
                _prune(crash_dir, retain)
            except Exception:
                pass
        if previous:
            previous(loop_, context)
        else:
            loop_.default_exception_handler(context)

    loop.set_exception_handler(_handler)


# ──────────────────────────────────────────────────────────────────────
# Writing crashes
# ──────────────────────────────────────────────────────────────────────

def write_crash(exc_type, exc_value, tb,
                version: str = "unknown",
                crash_dir: Path = _DEFAULT_CRASH_DIR,
                kind: str = "exception") -> Path:
    """Write a single crash dump JSON. Returns the file path."""
    crash_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kind": kind,
        "version": version,
        "platform": platform.platform(),
        "python_version": sys.version,
        "host": socket.gethostname(),
        "exception_type": exc_type.__name__ if exc_type else "Unknown",
        "exception_message": str(exc_value) if exc_value is not None else "",
        "traceback": "".join(
            traceback.format_exception(exc_type, exc_value, tb)
        ) if exc_type else "",
        "system": _system_snapshot(),
    }
    # Filename includes a millisecond suffix so two crashes in the same
    # second don't collide.
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    suffix = f"{int(time.time() * 1000) % 1000:03d}"
    name = f"{stamp}-{suffix}-{kind}.json"
    path = crash_dir / name
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def _system_snapshot() -> Dict[str, Any]:
    snap: Dict[str, Any] = {}
    try:
        import psutil  # type: ignore
        snap["cpu_percent"] = psutil.cpu_percent(interval=None)
        snap["memory_percent"] = psutil.virtual_memory().percent
        try:
            target = "C:\\" if os.name == "nt" else "/"
            snap["disk_free_gb"] = round(
                psutil.disk_usage(target).free / (1024 ** 3), 1
            )
        except Exception:
            pass
    except ImportError:
        pass
    return snap


def _prune(crash_dir: Path, retain: int) -> None:
    """Delete oldest crash files in excess of ``retain``."""
    if retain <= 0:
        return
    try:
        files = sorted(
            (p for p in crash_dir.glob("*.json") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        return
    for old in files[retain:]:
        try:
            old.unlink()
        except OSError:
            pass


# ──────────────────────────────────────────────────────────────────────
# Reading / managing
# ──────────────────────────────────────────────────────────────────────

def _safe_filename(name: str) -> bool:
    """Reject anything that could path-traverse out of the crash dir."""
    if not name or "/" in name or "\\" in name or ".." in name:
        return False
    return name.endswith(".json")


def list_crashes(crash_dir: Path = _DEFAULT_CRASH_DIR) -> List[Dict[str, Any]]:
    """Return summaries of stored crash dumps, newest first."""
    if not crash_dir.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        files = sorted(crash_dir.glob("*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            out.append({
                "filename": path.name,
                "timestamp": data.get("timestamp"),
                "exception_type": data.get("exception_type"),
                "exception_message": (data.get("exception_message") or "")[:200],
                "kind": data.get("kind"),
                "size_bytes": path.stat().st_size,
            })
        except Exception:
            continue
    return out


def read_crash(filename: str,
               crash_dir: Path = _DEFAULT_CRASH_DIR) -> Optional[Dict[str, Any]]:
    """Read a single crash dump. Returns None on any unsafe input or read error."""
    if not _safe_filename(filename):
        return None
    path = crash_dir / filename
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def delete_crash(filename: str,
                 crash_dir: Path = _DEFAULT_CRASH_DIR) -> bool:
    if not _safe_filename(filename):
        return False
    path = crash_dir / filename
    try:
        path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def build_support_bundle(filename: str,
                         crash_dir: Path = _DEFAULT_CRASH_DIR,
                         log_path: Path = _DEFAULT_LOG_PATH,
                         output_dir: Optional[Path] = None,
                         log_tail_lines: int = 500) -> Optional[Path]:
    """Zip a crash dump + the last N log lines so the user can email it.

    Secrets live in the OS keystore (see ai/secret_store.py), not in the log
    file or in the crash dump, so this is safe to send to support without
    further redaction.
    """
    if not _safe_filename(filename):
        return None
    crash_path = crash_dir / filename
    if not crash_path.exists():
        return None
    output_dir = output_dir or crash_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = output_dir / f"zora-support-bundle-{crash_path.stem}.zip"
    log_text = _tail_log(log_path, log_tail_lines)
    try:
        with zipfile.ZipFile(str(bundle_path), "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(str(crash_path), arcname=crash_path.name)
            zf.writestr("zora.log.tail.txt", log_text)
    except Exception as e:
        logger.warning(f"Bundle write failed: {e}")
        return None
    return bundle_path


def _tail_log(log_path: Path, n: int) -> str:
    """Return the last `n` lines of a file efficiently. Empty string if missing."""
    if not log_path.exists():
        return "(no log file present)"
    try:
        with open(log_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 64 * 1024
            data = b""
            pos = size
            # Read backwards until we have at least n+1 newlines or hit BOF.
            while pos > 0 and data.count(b"\n") <= n:
                read = min(block, pos)
                pos -= read
                f.seek(pos)
                data = f.read(read) + data
            text = data.decode("utf-8", errors="replace")
            lines = text.splitlines()
            return "\n".join(lines[-n:])
    except Exception as e:
        return f"(failed to read log: {e})"


# ──────────────────────────────────────────────────────────────────────
# Log rotation
# ──────────────────────────────────────────────────────────────────────

def attach_rotating_log(log_path: Path = _DEFAULT_LOG_PATH,
                        max_bytes: int = _DEFAULT_LOG_BYTES,
                        backups: int = _DEFAULT_LOG_BACKUPS) -> RotatingFileHandler:
    """Add a ``RotatingFileHandler`` to the root logger.

    Returns the handler so callers can also pipe ``stdout``/``stderr`` through
    its underlying stream if they want ``print()`` output captured too.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        str(log_path), maxBytes=max_bytes, backupCount=backups,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    ))
    root = logging.getLogger()
    # Avoid duplicate handlers on repeated calls (idempotency).
    for existing in root.handlers:
        if (isinstance(existing, RotatingFileHandler)
                and getattr(existing, "baseFilename", None) == handler.baseFilename):
            return existing
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > logging.INFO:
        root.setLevel(logging.INFO)
    return handler


def _reset_for_tests() -> None:
    """Reset the install guard. Tests only."""
    global _installed
    _installed = False
