"""
Secret store — Windows Credential Manager (DPAPI) wrapper.

Why this module exists
----------------------
Zora keeps two kinds of secrets:
  * Cloud API keys (Anthropic / OpenAI / Grok / Groq / Custom)
  * Smart-home credentials (Home Assistant token, MQTT password, Hue token)

Both used to live in plaintext or near-plaintext on disk:
  - API keys: kept only in memory (good) but lost on every restart (bad UX,
    so users were tempted to paste them back into config.json (bad)).
  - Smart-home creds: XOR + base64 in storage/smart_home.json. The module
    that wrote them said "this is NOT cryptographic defence" — true. Local
    admin or file backup = plaintext recovery.

This module routes both flows through the `keyring` library, which on
Windows uses `Windows.WinVaultKeyring` → Credential Manager → DPAPI. That
ties the secret to the current user on the current machine: a different
user can't decrypt it, a OneDrive sync of the project folder doesn't carry
it, a screenshot of the JSON doesn't leak it.

Threat model
------------
Protects against:
  * Another local user reading the project folder
  * Plaintext spillage in backups, cloud syncs, screenshots, error reports
  * "I grepped my Documents for `sk-`" attacks

Does NOT protect against:
  * Malware running AS the user (DPAPI can't help here — anything the user
    can decrypt, malware running as them can too)
  * Physical access with a logged-in session

That's the correct trade-off for a desktop tech-support app. The user IS
the trust boundary; we're hardening against accidental leaks, not nation-
state attackers.

Fallback
--------
If `keyring` isn't installed (CI, headless tests, non-Windows dev), we
fall back to an in-process dict. `is_secure()` reports which backend is
active so the UI can show a warning if running in fallback mode.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

logger = logging.getLogger("zora.secrets")

# Service name shown in Windows Credential Manager. Keep this stable —
# changing it would orphan every existing user's saved secrets.
SERVICE_NAME = "Zora-DesktopAssistant"

# In-process fallback when keyring is unavailable. NOT secure — it just
# keeps the codepath functional for tests and CI.
_fallback: Dict[str, str] = {}
_backend_checked = False
_backend_available = False
_kr_module = None  # populated lazily by _get_backend, or by tests directly


def _get_backend():
    """Lazy-load keyring. Cache the result so we don't pay the import every call."""
    global _backend_checked, _backend_available, _kr_module
    if _backend_checked:
        return _kr_module if _backend_available else None
    _backend_checked = True
    try:
        import keyring  # type: ignore
        # Verify the backend can actually be reached. On some headless
        # environments the import succeeds but there's no keyring daemon.
        try:
            keyring.get_keyring()
            _kr_module = keyring
            _backend_available = True
            return keyring
        except Exception as e:
            logger.warning(f"keyring imported but no backend usable: {e}")
            return None
    except ImportError:
        logger.warning(
            "keyring package not installed; secrets will use in-process fallback "
            "(this is NOT secure — install `keyring` for DPAPI-backed storage)"
        )
        return None


def is_secure() -> bool:
    """Return True if secrets are backed by the OS keystore (not the fallback)."""
    return _get_backend() is not None


def set_secret(name: str, value: str) -> bool:
    """Store a secret. Returns True if it was stored securely.

    Empty value deletes the entry.
    """
    if not isinstance(name, str) or not name:
        raise ValueError("Secret name must be a non-empty string.")
    if value is None or value == "":
        delete_secret(name)
        return is_secure()
    kr = _get_backend()
    if kr is None:
        _fallback[name] = value
        return False
    try:
        kr.set_password(SERVICE_NAME, name, value)
        return True
    except Exception as e:
        logger.warning(f"keyring.set_password failed for {name!r}: {e}; using fallback")
        _fallback[name] = value
        return False


def get_secret(name: str) -> Optional[str]:
    """Retrieve a stored secret. Returns None when nothing is stored under that name."""
    if not isinstance(name, str) or not name:
        return None
    kr = _get_backend()
    if kr is None:
        return _fallback.get(name)
    try:
        value = kr.get_password(SERVICE_NAME, name)
        # Edge case: some keyring implementations return "" for "not present".
        return value or None
    except Exception as e:
        logger.warning(f"keyring.get_password failed for {name!r}: {e}")
        return _fallback.get(name)


def delete_secret(name: str) -> None:
    """Remove a stored secret. No-op if it doesn't exist."""
    if not isinstance(name, str) or not name:
        return
    kr = _get_backend()
    if kr is None:
        _fallback.pop(name, None)
        return
    try:
        kr.delete_password(SERVICE_NAME, name)
    except Exception:
        # PasswordDeleteError is raised when the entry doesn't exist — safe to ignore.
        pass
    # Always clean the fallback too, in case keyring became unavailable mid-session.
    _fallback.pop(name, None)


def list_known_names() -> list:
    """Return the names currently held in the in-memory fallback only.

    keyring's standard API doesn't expose enumeration on Windows (Credential
    Manager doesn't support enumerate by service prefix safely), so this is
    primarily for the test suite. Production code should track its own
    namespace.
    """
    return sorted(_fallback.keys())


# ──────────────────────────────────────────────────────────────────────
# Convenience namespaces — keep names stable and centralized.
# Anything that needs a secret should import the helper, never spell the
# raw key by hand.
# ──────────────────────────────────────────────────────────────────────

def api_key_name(provider: str) -> str:
    """Canonical secret name for a cloud-AI provider API key."""
    return f"api_key:{provider.lower()}"


def smart_home_secret_name(section: str, field: str) -> str:
    """Canonical secret name for a smart-home credential field.

    e.g. ("home_assistant", "token") → "smart_home:home_assistant:token"
    """
    return f"smart_home:{section}:{field}"


# ──────────────────────────────────────────────────────────────────────
# Test helpers
# ──────────────────────────────────────────────────────────────────────

def _reset_for_tests() -> None:
    """Clear the in-process fallback. NOT to be called in production code."""
    global _backend_checked, _backend_available
    _fallback.clear()
    _backend_checked = False
    _backend_available = False
