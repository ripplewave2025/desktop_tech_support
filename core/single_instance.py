"""
Single-instance enforcement and port discovery for the Zora launcher.

Why this module exists
----------------------
Two failure modes the launcher used to have:

1. **Double launch.** A user double-clicks the Zora desktop shortcut twice.
   The second process tries to bind uvicorn to port 8000, collides with the
   first, and either crashes silently (windowed mode) or shows a stack trace.
   Either way, the user has no working Zora and no idea why.

2. **Port 8000 already taken.** Some other tool on the box (a dev server, a
   second copy of Zora that didn't clean up, a corporate proxy) is already
   on 8000. Same outcome: silent crash.

This module solves both:

  * ``acquire_lock(name)``  → returns a lock or None if another instance owns it.
    On Windows uses ``win32event.CreateMutex`` (Kernel32 Named Mutex). Falls
    back to an O_EXCL file lock for non-Windows test environments.
  * ``find_free_port(...)`` → returns the preferred port if free, else walks up.
  * ``read_running_instance(...)`` → returns the URL of the existing Zora so
    the duplicate-launch case can pop open the live UI instead of dying.
  * ``write_instance_metadata(...)`` / cleanup is idempotent + atexit-registered.

Lock file lives at ``%LOCALAPPDATA%\\Zora\\.instance.json``. It records PID,
port, URL, and launch time. "Stale" means the PID isn't running OR the port
doesn't answer — in that case we treat it as no instance and take over.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import socket
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("zora.single_instance")


_DEFAULT_LOCK_NAME = "Zora-DesktopAssistant-SingleInstance"
_DEFAULT_LOCK_FILE = (
    Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")))
    / "Zora"
    / ".instance.json"
)


class SingleInstanceLock:
    """A held lock. Released on ``release()`` or at process exit."""

    def __init__(self, handle: Any, name: str, kind: str):
        # kind is "mutex" (Windows) or "file" (cross-platform fallback).
        self._handle = handle
        self._name = name
        self._kind = kind
        self._released = False
        self._cleanup_paths: list = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def kind(self) -> str:
        return self._kind

    def release(self) -> None:
        if self._released:
            return
        try:
            if self._kind == "mutex":
                import win32api  # type: ignore
                win32api.CloseHandle(self._handle)
            elif self._kind == "file":
                try:
                    os.close(self._handle)
                except OSError:
                    pass
                for path in self._cleanup_paths:
                    try:
                        Path(path).unlink(missing_ok=True)
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Lock release failed: {e}")
        self._released = True

    def __enter__(self) -> "SingleInstanceLock":
        return self

    def __exit__(self, *exc) -> None:
        self.release()


def acquire_lock(name: str = _DEFAULT_LOCK_NAME) -> Optional[SingleInstanceLock]:
    """Acquire a system-wide named lock.

    Returns the lock object if we're the first instance; returns None if
    another process already holds it.

    On Windows this is a named kernel mutex — robust across user sessions
    on the same desktop and survives the launcher's working dir changing.
    Off Windows we use an O_EXCL file lock with PID-aliveness fallback so
    a crashed previous run doesn't permanently brick subsequent launches.
    """
    if os.name == "nt":
        result = _acquire_windows_mutex(name)
        if result is not None:
            return result
        # If the mutex path was unusable (pywin32 import failed in some
        # weird PyInstaller setups), fall through to the file lock so the
        # app still runs.
        logger.warning("Windows mutex unavailable; falling back to file lock.")
    return _acquire_file_lock(name)


def _acquire_windows_mutex(name: str) -> Optional[SingleInstanceLock]:
    try:
        import win32event  # type: ignore
        import win32api  # type: ignore
        import winerror  # type: ignore
    except ImportError:
        return None
    handle = win32event.CreateMutex(None, False, name)
    last_error = win32api.GetLastError()
    if last_error == winerror.ERROR_ALREADY_EXISTS:
        win32api.CloseHandle(handle)
        return None
    lock = SingleInstanceLock(handle, name, "mutex")
    atexit.register(lock.release)
    return lock


def _acquire_file_lock(name: str) -> Optional[SingleInstanceLock]:
    base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("TMPDIR") or "/tmp")
    lock_path = base / "Zora" / f".{name}.pid"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
    except FileExistsError:
        # Existing lock — check if the previous owner is still alive.
        try:
            previous_pid = int(lock_path.read_text().strip() or "0")
        except Exception:
            previous_pid = 0
        if previous_pid and not _pid_alive(previous_pid):
            # Stale lock from a crashed run. Reclaim.
            try:
                lock_path.unlink()
            except Exception:
                pass
            return _acquire_file_lock(name)
        return None
    try:
        os.write(fd, str(os.getpid()).encode())
    except OSError:
        pass
    lock = SingleInstanceLock(fd, name, "file")
    lock._cleanup_paths.append(lock_path)
    atexit.register(lock.release)
    return lock


# ──────────────────────────────────────────────────────────────────────
# Port discovery
# ──────────────────────────────────────────────────────────────────────

def find_free_port(preferred: int = 8000, max_tries: int = 20) -> int:
    """Return ``preferred`` if it's free, else the next free port up.

    "Free" means ``bind(127.0.0.1, port)`` succeeds. We don't accept-listen,
    we just probe by binding then closing — fast and accurate. Walks up to
    ``preferred + max_tries - 1`` before giving up.
    """
    for offset in range(max_tries):
        port = preferred + offset
        if _port_is_bindable(port):
            return port
    raise RuntimeError(
        f"No free port found in range {preferred}..{preferred + max_tries - 1}"
    )


def _port_is_bindable(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        try:
            s.close()
        except OSError:
            pass


def _port_responds(port: int, timeout: float = 1.0) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        try:
            s.close()
        except OSError:
            pass


# ──────────────────────────────────────────────────────────────────────
# Instance metadata (lock file)
# ──────────────────────────────────────────────────────────────────────

def write_instance_metadata(port: int,
                            lock_file: Path = _DEFAULT_LOCK_FILE) -> Dict[str, Any]:
    """Atomically write PID + port to the lock file. Returns the payload."""
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": os.getpid(),
        "port": int(port),
        "url": f"http://127.0.0.1:{int(port)}",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "version": 1,
    }
    tmp = lock_file.with_suffix(lock_file.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(lock_file))
    atexit.register(_safe_unlink, lock_file)
    return payload


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def read_running_instance(lock_file: Path = _DEFAULT_LOCK_FILE) -> Optional[Dict[str, Any]]:
    """Return metadata for the currently-running Zora, or None if stale.

    A lock file is "stale" if any of these is true:
      * the file is missing or unreadable
      * the PID it points to isn't a live process
      * the recorded port doesn't accept TCP connections

    The third check matters because a process might still exist but have
    its uvicorn dead, in which case the new launch should take over.
    """
    if not lock_file.exists():
        return None
    try:
        data = json.loads(lock_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    pid = int(data.get("pid") or 0)
    port = int(data.get("port") or 0)
    if not pid or not port:
        return None
    if not _pid_alive(pid):
        return None
    if not _port_responds(port):
        return None
    return data


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil  # type: ignore
        return psutil.pid_exists(pid)
    except ImportError:
        # Fallback to os.kill(pid, 0) — works on POSIX, raises on Windows
        # without permissions; in that case we conservatively say "alive".
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False
        except OSError:
            return True
