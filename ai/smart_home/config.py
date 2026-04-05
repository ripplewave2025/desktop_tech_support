"""
Smart-home credential store.

Persists Home Assistant, MQTT, and Hue configuration in
``storage/smart_home.json``. Secrets (``token``, ``password``, ``username``)
are obfuscated at rest via a local-only XOR + base64 scheme so they don't
sit in the JSON as plaintext.

This is NOT cryptographic defence — the key lives next to the data on the
same machine. It exists so a screenshot, a backup, or a stray grep doesn't
spill the token. Anyone with local admin on this box can read these
values the same as they could read the raw file.

Mirrors the "redact on read for tool results, persist obfuscated on disk"
pattern already used for user_profile.json and config.json.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


_SECRET_KEYS = {"token", "password", "username", "api_key", "apikey", "client_secret"}
_OBFUSCATION_MARKER = "zxor$"
# Module-level constant key: deliberately not from config because if the
# user restores from backup on a new machine the token was never portable
# anyway (HA tokens, Hue usernames, and MQTT creds are all bridge-specific).
_LOCAL_KEY = b"zora-smart-home-local-v1"


def _xor(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _obfuscate(value: str) -> str:
    raw = value.encode("utf-8")
    return _OBFUSCATION_MARKER + base64.b64encode(_xor(raw, _LOCAL_KEY)).decode("ascii")


def _deobfuscate(value: str) -> str:
    if not isinstance(value, str) or not value.startswith(_OBFUSCATION_MARKER):
        return value
    try:
        encoded = value[len(_OBFUSCATION_MARKER):]
        return _xor(base64.b64decode(encoded), _LOCAL_KEY).decode("utf-8")
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
        return self._from_dict(raw)

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
        payload = {
            "home_assistant": asdict(config.home_assistant),
            "mqtt": asdict(config.mqtt),
            "hue": asdict(config.hue),
            "aliases": dict(config.aliases),
        }
        self._apply_obfuscation(payload, encode=True)
        return payload

    def _from_dict(self, raw: Dict[str, Any]) -> SmartHomeConfig:
        data = {
            "home_assistant": dict(raw.get("home_assistant") or {}),
            "mqtt": dict(raw.get("mqtt") or {}),
            "hue": dict(raw.get("hue") or {}),
            "aliases": dict(raw.get("aliases") or {}),
        }
        self._apply_obfuscation(data, encode=False)
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

    def _apply_obfuscation(self, payload: Dict[str, Any], encode: bool) -> None:
        """Walk every secret field and encode/decode in place."""
        fn = _obfuscate if encode else _deobfuscate
        for section_key in ("home_assistant", "mqtt", "hue"):
            section = payload.get(section_key) or {}
            for field_name, value in list(section.items()):
                if field_name in _SECRET_KEYS and isinstance(value, str) and value:
                    section[field_name] = fn(value)
