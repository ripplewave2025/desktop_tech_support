"""
Smart-home credential store.

Persists Home Assistant, MQTT, and Hue configuration in
``storage/smart_home.json``. Non-secret fields (URL, host, port, bridge IP,
known topics, aliases) live in the JSON file. **Secrets — tokens,
passwords, usernames — live in the Windows Credential Manager via DPAPI**,
accessed through ``ai.secret_store``.

Legacy data
-----------
Earlier builds obfuscated secrets in the JSON with an XOR+base64 scheme
prefixed by ``zxor$``. That was acknowledged in the file header as not
real encryption. On load, we detect any ``zxor$`` values, deobfuscate
them, migrate to the secret store, and overwrite the JSON so the
plaintext-equivalent values never get re-saved.

Mirrors the "redact on read for tool results, persist via OS keystore on
disk" pattern used in v2.x+.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from .. import secret_store

logger = logging.getLogger("zora.smart_home.config")


# Fields that must never live in the JSON file on disk.
_SECRET_KEYS = {"token", "password", "username", "api_key", "apikey", "client_secret"}

# Legacy XOR marker — present only so we can recognize and migrate old data.
_OBFUSCATION_MARKER = "zxor$"
_LEGACY_LOCAL_KEY = b"zora-smart-home-local-v1"


def _xor(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _deobfuscate_legacy(value: str) -> str:
    """Decode a legacy ``zxor$``-prefixed value. Used only during migration."""
    if not isinstance(value, str) or not value.startswith(_OBFUSCATION_MARKER):
        return value
    try:
        encoded = value[len(_OBFUSCATION_MARKER):]
        return _xor(base64.b64decode(encoded), _LEGACY_LOCAL_KEY).decode("utf-8")
    except Exception:
        return ""


@dataclass
class HomeAssistantConfig:
    url: str = ""
    token: str = ""


@dataclass
class MqttConfig:
    host: str = ""
    port: int = 1883
    username: str = ""
    password: str = ""
    known_topics: list[str] = field(default_factory=list)


@dataclass
class HueConfig:
    bridge_ip: str = ""
    username: str = ""  # Hue calls this a "username" but it's really a bridge auth token.


@dataclass
class SmartHomeConfig:
    home_assistant: HomeAssistantConfig = field(default_factory=HomeAssistantConfig)
    mqtt: MqttConfig = field(default_factory=MqttConfig)
    hue: HueConfig = field(default_factory=HueConfig)
    aliases: Dict[str, str] = field(default_factory=dict)  # friendly name → entity_id

    def backends_configured(self) -> Dict[str, bool]:
        return {
            "home_assistant": bool(self.home_assistant.url and self.home_assistant.token),
            "mqtt": bool(self.mqtt.host),
            "hue": bool(self.hue.bridge_ip and self.hue.username),
        }

    def any_configured(self) -> bool:
        return any(self.backends_configured().values())


class SmartHomeConfigStore:
    """Load/save ``storage/smart_home.json`` with secret obfuscation.

    The file lives next to ``storage/db.py`` so it's inside the project
    tree (where the rest of the runtime state lives) rather than in
    %LOCALAPPDATA% — keeping smart-home setup backup-able with the
    project if the user wants.
    """

    def __init__(self, path: Optional[str] = None):
        if path is None:
            here = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.abspath(os.path.join(here, "..", ".."))
            path = os.path.join(project_root, "storage", "smart_home.json")
        self._path = path
        # Set to True by _from_dict when it migrates legacy zxor$ data so
        # load() knows to rewrite the file without the plaintext-equivalent
        # values present.
        self._needs_rewrite = False

    @property
    def path(self) -> str:
        return self._path

    def load(self) -> SmartHomeConfig:
        if not os.path.exists(self._path):
            return SmartHomeConfig()
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                raw = json.load(f) or {}
        except Exception:
            return SmartHomeConfig()
        config = self._from_dict(raw)
        # If we just migrated any legacy zxor$ values out of the JSON,
        # rewrite the file so the plaintext-equivalent string isn't there
        # anymore. _from_dict sets this flag when it migrates anything.
        if self._needs_rewrite:
            try:
                self.save(config)
                logger.info("Migrated legacy smart-home secrets to OS keystore.")
            except Exception as e:
                logger.warning(f"Post-migration save failed: {e}")
            self._needs_rewrite = False
        return config

    def save(self, config: SmartHomeConfig) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._to_dict(config), f, indent=2, default=str)

    def redacted_snapshot(self) -> Dict[str, Any]:
        """Return a serializable view safe for API responses / UI."""
        config = self.load()
        return {
            "home_assistant": {
                "url": config.home_assistant.url,
                "token": "***" if config.home_assistant.token else "",
                "configured": bool(config.home_assistant.url and config.home_assistant.token),
            },
            "mqtt": {
                "host": config.mqtt.host,
                "port": config.mqtt.port,
                "username": "***" if config.mqtt.username else "",
                "password": "***" if config.mqtt.password else "",
                "known_topics": list(config.mqtt.known_topics),
                "configured": bool(config.mqtt.host),
            },
            "hue": {
                "bridge_ip": config.hue.bridge_ip,
                "username": "***" if config.hue.username else "",
                "configured": bool(config.hue.bridge_ip and config.hue.username),
            },
            "aliases": dict(config.aliases),
            "backends_configured": config.backends_configured(),
            "any_configured": config.any_configured(),
        }

    # --- helpers ---------------------------------------------------------

    def _to_dict(self, config: SmartHomeConfig) -> Dict[str, Any]:
        """Serialize for disk. Secrets are pushed to the keystore, not the file."""
        payload = {
            "home_assistant": asdict(config.home_assistant),
            "mqtt": asdict(config.mqtt),
            "hue": asdict(config.hue),
            "aliases": dict(config.aliases),
        }
        self._persist_secrets(payload)
        return payload

    def _from_dict(self, raw: Dict[str, Any]) -> SmartHomeConfig:
        """Hydrate from disk. Secrets are pulled from the keystore. Legacy
        ``zxor$`` values are migrated transparently on first read.
        """
        data = {
            "home_assistant": dict(raw.get("home_assistant") or {}),
            "mqtt": dict(raw.get("mqtt") or {}),
            "hue": dict(raw.get("hue") or {}),
            "aliases": dict(raw.get("aliases") or {}),
        }
        self._hydrate_secrets(data)
        ha = HomeAssistantConfig(
            url=data["home_assistant"].get("url", "") or "",
            token=data["home_assistant"].get("token", "") or "",
        )
        mqtt = MqttConfig(
            host=data["mqtt"].get("host", "") or "",
            port=int(data["mqtt"].get("port") or 1883),
            username=data["mqtt"].get("username", "") or "",
            password=data["mqtt"].get("password", "") or "",
            known_topics=list(data["mqtt"].get("known_topics") or []),
        )
        hue = HueConfig(
            bridge_ip=data["hue"].get("bridge_ip", "") or "",
            username=data["hue"].get("username", "") or "",
        )
        return SmartHomeConfig(
            home_assistant=ha,
            mqtt=mqtt,
            hue=hue,
            aliases=data["aliases"],
        )

    # ------------------------------------------------------------------
    # Secret routing — every secret field in every section goes through
    # the OS keystore. The JSON on disk only ever contains non-secret
    # config and empty strings for secret fields.
    # ------------------------------------------------------------------

    def _persist_secrets(self, payload: Dict[str, Any]) -> None:
        """For each secret field: write to the keystore, then blank it in the dict."""
        for section_key in ("home_assistant", "mqtt", "hue"):
            section = payload.get(section_key) or {}
            for field_name, value in list(section.items()):
                if field_name in _SECRET_KEYS and isinstance(value, str):
                    if value:
                        secret_store.set_secret(
                            secret_store.smart_home_secret_name(section_key, field_name),
                            value,
                        )
                    else:
                        secret_store.delete_secret(
                            secret_store.smart_home_secret_name(section_key, field_name)
                        )
                    # The file on disk must never carry the live value.
                    section[field_name] = ""

    def _hydrate_secrets(self, data: Dict[str, Any]) -> None:
        """For every secret field, route the live value through the keystore.

        Migration rules:
          1. If the JSON holds a ``zxor$``-prefixed legacy value: deobfuscate
             it and push the cleartext to the keystore.
          2. If the JSON holds a plain string (e.g., someone hand-edited the
             file): treat it as a migration candidate and push to keystore.
          3. Always blank the secret in the in-memory dict view that lives on
             disk; the file shouldn't carry the live value once we've left.
          4. If anything was migrated, set _needs_rewrite so load() will save
             the file again after this call.

        Whatever the keystore returns becomes the live value supplied to the
        config dataclass.
        """
        for section_key in ("home_assistant", "mqtt", "hue"):
            section = data.get(section_key) or {}
            for field_name in list(section.keys()):
                if field_name not in _SECRET_KEYS:
                    continue
                raw_value = section.get(field_name)
                if not isinstance(raw_value, str):
                    continue
                key_name = secret_store.smart_home_secret_name(section_key, field_name)

                # Recover whatever the disk wants to contribute, then pick the
                # authoritative copy: prefer keystore, then disk.
                disk_cleartext: Optional[str] = None
                if raw_value.startswith(_OBFUSCATION_MARKER):
                    disk_cleartext = _deobfuscate_legacy(raw_value) or None
                elif raw_value:
                    disk_cleartext = raw_value

                stored = secret_store.get_secret(key_name)

                # Migration: disk has data, keystore doesn't.
                if disk_cleartext and not stored:
                    secret_store.set_secret(key_name, disk_cleartext)
                    stored = disk_cleartext

                # If the file had any non-empty representation, we'll rewrite
                # the JSON to clear it.
                if raw_value:
                    self._needs_rewrite = True

                section[field_name] = stored or ""
