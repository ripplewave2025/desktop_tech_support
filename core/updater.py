"""
Auto-update via GitHub Releases.

Why this module exists
----------------------
Without an auto-updater, every patch requires the user to find the
GitHub Releases page, download the installer, close Zora, re-run setup.
A non-technical user won't do any of that. They'll keep running a broken
v2.3 forever.

How the flow works
------------------
1. **check_for_update()** hits the GitHub Releases API once. Compares the
   running version to the latest tag. Returns a structured result the UI
   can render: "Update available: v2.4 — 12.3 MB — released Mar 5."
2. **download_update()** streams the installer .exe from the release's
   assets into a temp dir. Returns the path + the SHA-256 it computed
   over the bytes it received (so the UI can show a fingerprint).
3. **launch_installer()** runs the Inno Setup installer in silent mode
   (``/SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS``), then asks the
   backend to exit so Inno can replace files. The installer relaunches
   Zora when it's done.

Why use Inno Setup instead of in-place file replacement
-------------------------------------------------------
On Windows you can't overwrite a running ``.exe`` (file locked by the
loader). Inno can — it queues the replacement after Zora exits and runs
it during its own privileged session. The user already has an Inno
installer (``installer/zora_setup.iss``), so we leverage that rather
than building a second update binary.

Security caveats
----------------
* Transport: HTTPS to ``api.github.com`` / ``github.com``. Python's stdlib
  verifies the certificate chain by default — that protects against a
  network-level MITM.
* Authenticity: we compute SHA-256 over the downloaded file and surface
  it in the UI. If you publish a ``ZoraSetup.exe.sha256`` companion file
  in the release, we'll fetch and compare it. WITHOUT code signing this
  is informational only — a compromised GitHub account could push a bad
  installer and a matching hash. Code signing (a separate roadmap item)
  is what makes this airtight.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("zora.updater")


# Configurable via env so we don't hard-code the user's repo here.
DEFAULT_REPO = os.environ.get("ZORA_UPDATE_REPO", "ripplewave2025/desktop_tech_support")
DEFAULT_ASSET_NAME = os.environ.get("ZORA_UPDATE_ASSET", "ZoraSetup.exe")
DEFAULT_TIMEOUT = 15
USER_AGENT = "Zora-Updater/1.0 (+github.com/ripplewave2025/desktop_tech_support)"


# ──────────────────────────────────────────────────────────────────────
# Version handling
# ──────────────────────────────────────────────────────────────────────

# Matches "v2.4", "2.4", "v2.4.1", "v2.4-beta" — keeps it permissive so
# tag conventions can drift without breaking the comparison.
_VERSION_RE = re.compile(r"v?(\d+)\.(\d+)(?:\.(\d+))?(?:[-+].*)?")


def parse_version(s: str) -> Optional[Tuple[int, int, int]]:
    """Parse a version-ish string to a sortable 3-tuple. None if unparseable."""
    if not s:
        return None
    m = _VERSION_RE.match(s.strip())
    if not m:
        return None
    major = int(m.group(1))
    minor = int(m.group(2))
    patch = int(m.group(3) or 0)
    return (major, minor, patch)


def is_newer(candidate: str, current: str) -> bool:
    """True iff `candidate` is a strictly newer version than `current`."""
    c = parse_version(candidate)
    cur = parse_version(current)
    if c is None or cur is None:
        return False
    return c > cur


# ──────────────────────────────────────────────────────────────────────
# GitHub API
# ──────────────────────────────────────────────────────────────────────

@dataclass
class UpdateInfo:
    available: bool
    current_version: str
    latest_version: str
    tag_name: str
    asset_name: str
    asset_url: str        # browser_download_url
    asset_size_bytes: int
    published_at: str
    release_notes: str    # markdown body, truncated for display
    sha256_url: str = ""  # optional companion file URL

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _http_get(url: str, timeout: int = DEFAULT_TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def check_for_update(current_version: str,
                     repo: str = DEFAULT_REPO,
                     asset_name: str = DEFAULT_ASSET_NAME,
                     timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Query GitHub for the latest release and report whether it's newer.

    Returns the dict form of UpdateInfo, plus an ``error`` field on failure.
    Never raises — the UI calls this on every settings open, so a flaky
    network shouldn't crash anything.
    """
    api = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        body = _http_get(api, timeout=timeout)
        data = json.loads(body)
    except urllib.error.HTTPError as e:
        return _err(current_version, f"GitHub API returned {e.code}")
    except urllib.error.URLError as e:
        return _err(current_version, f"Network error: {e.reason}")
    except (ValueError, TimeoutError) as e:
        return _err(current_version, f"Bad response: {e}")

    tag_name = str(data.get("tag_name") or "")
    latest = (parse_version(tag_name) or (0, 0, 0))
    latest_str = f"{latest[0]}.{latest[1]}.{latest[2]}"
    assets = data.get("assets") or []
    target = next((a for a in assets if a.get("name") == asset_name), None)
    if target is None:
        return _err(current_version,
                    f"Release '{tag_name}' has no asset named '{asset_name}'.")
    sha256_asset = next(
        (a for a in assets if a.get("name") == asset_name + ".sha256"),
        None,
    )

    info = UpdateInfo(
        available=is_newer(tag_name, current_version),
        current_version=current_version,
        latest_version=latest_str,
        tag_name=tag_name,
        asset_name=asset_name,
        asset_url=str(target.get("browser_download_url") or ""),
        asset_size_bytes=int(target.get("size") or 0),
        published_at=str(data.get("published_at") or ""),
        release_notes=(data.get("body") or "")[:4000],
        sha256_url=str(sha256_asset.get("browser_download_url") or "") if sha256_asset else "",
    )
    return info.to_dict()


def _err(current_version: str, message: str) -> Dict[str, Any]:
    return UpdateInfo(
        available=False, current_version=current_version,
        latest_version="", tag_name="", asset_name="",
        asset_url="", asset_size_bytes=0, published_at="",
        release_notes="",
    ).to_dict() | {"error": message}


# ──────────────────────────────────────────────────────────────────────
# Download + verify
# ──────────────────────────────────────────────────────────────────────

@dataclass
class DownloadResult:
    ok: bool
    path: str
    size_bytes: int
    sha256: str
    expected_sha256: str = ""    # populated if a .sha256 companion was fetched
    sha256_match: Optional[bool] = None
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def download_update(asset_url: str,
                    *,
                    sha256_url: str = "",
                    dest_dir: Optional[Path] = None,
                    timeout: int = 300,
                    chunk_size: int = 256 * 1024) -> Dict[str, Any]:
    """Stream the installer asset to disk. Computes SHA-256 as we go.

    If `sha256_url` is provided, fetches the expected hash and compares.
    Returns the dict form of DownloadResult. Never raises.
    """
    if not asset_url:
        return DownloadResult(False, "", 0, "", error="No asset URL provided.").to_dict()
    dest_dir = dest_dir or (
        Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Zora" / "updates"
    )
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = asset_url.rsplit("/", 1)[-1] or "ZoraSetup.exe"
    dest_path = dest_dir / filename

    expected_sha = ""
    if sha256_url:
        try:
            sha_body = _http_get(sha256_url, timeout=DEFAULT_TIMEOUT).decode("utf-8", "replace")
            # Standard format: "<hexdigest>  <filename>" — take the first token.
            expected_sha = (sha_body.strip().split() or [""])[0].lower()
        except Exception as e:
            logger.warning(f"Could not fetch SHA-256 companion: {e}")

    hasher = hashlib.sha256()
    bytes_total = 0
    try:
        req = urllib.request.Request(asset_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp, \
             open(dest_path, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                hasher.update(chunk)
                bytes_total += len(chunk)
    except urllib.error.URLError as e:
        return DownloadResult(False, str(dest_path), 0, "",
                              expected_sha256=expected_sha,
                              error=f"Download failed: {e.reason}").to_dict()
    except OSError as e:
        return DownloadResult(False, str(dest_path), 0, "",
                              expected_sha256=expected_sha,
                              error=f"Disk error: {e}").to_dict()

    digest = hasher.hexdigest().lower()
    match: Optional[bool] = None
    if expected_sha:
        match = (digest == expected_sha)
        if not match:
            # Bad hash → delete the file. Don't keep a possibly-tampered
            # binary on disk where the user might accidentally double-click it.
            try:
                dest_path.unlink(missing_ok=True)
            except OSError:
                pass
            return DownloadResult(False, str(dest_path), bytes_total, digest,
                                  expected_sha256=expected_sha,
                                  sha256_match=False,
                                  error="SHA-256 mismatch — installer rejected.").to_dict()
    return DownloadResult(True, str(dest_path), bytes_total, digest,
                          expected_sha256=expected_sha,
                          sha256_match=match).to_dict()


# ──────────────────────────────────────────────────────────────────────
# Install (delegated to Inno Setup)
# ──────────────────────────────────────────────────────────────────────

def launch_installer(installer_path: str,
                     extra_args: Optional[list] = None) -> Dict[str, Any]:
    """Spawn the Inno Setup installer in unattended mode and detach.

    Inno's silent flags:
      /SILENT                — no setup wizard, but show a progress bar
      /SUPPRESSMSGBOXES      — auto-OK any modal dialogs
      /CLOSEAPPLICATIONS     — close Zora (the FastAPI server) before copying
      /RESTARTAPPLICATIONS   — restart Zora after install
      /NORESTART             — don't reboot the machine, just the app

    The caller is expected to ALSO terminate the running Zora shortly after
    this returns so Inno can replace the files. We don't kill ourselves
    here — that's the API layer's job.
    """
    p = Path(installer_path)
    if not p.exists():
        return {"started": False, "error": f"Installer not found: {installer_path}"}
    if os.name != "nt":
        return {"started": False, "error": "Auto-install only supported on Windows."}
    args = [str(p), "/SILENT", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS",
            "/RESTARTAPPLICATIONS", "/NORESTART"]
    if extra_args:
        args.extend(extra_args)
    try:
        # Detached: DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        flags = 0
        try:
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        except AttributeError:
            flags = 0
        subprocess.Popen(args, creationflags=flags, close_fds=True)
    except FileNotFoundError as e:
        return {"started": False, "error": str(e)}
    except OSError as e:
        return {"started": False, "error": f"Could not launch installer: {e}"}
    return {"started": True, "argv": args}
