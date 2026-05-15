"""
Tests for ai.secret_store and the migration of smart-home + API-key secrets.

The tests use a stub keyring backend so they don't touch the real OS
keystore. On Windows in production, the real backend is
``Windows.WinVaultKeyring`` (Credential Manager / DPAPI).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from typing import Dict
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai import secret_store
from ai.smart_home.config import (
    SmartHomeConfig,
    SmartHomeConfigStore,
    HomeAssistantConfig,
    MqttConfig,
    HueConfig,
)


class StubKeyring:
    """In-process stand-in for the real keyring module."""

    def __init__(self):
        self.vault: Dict[tuple, str] = {}

    def get_keyring(self):
        return self  # any non-None value satisfies the backend check

    def set_password(self, service: str, name: str, value: str) -> None:
        self.vault[(service, name)] = value

    def get_password(self, service: str, name: str):
        return self.vault.get((service, name))

    def delete_password(self, service: str, name: str) -> None:
        self.vault.pop((service, name), None)


def _install_stub() -> StubKeyring:
    """Wire a fresh StubKeyring into secret_store's lazy backend lookup."""
    stub = StubKeyring()
    # Reset module state so the next call to _get_backend picks up our stub.
    secret_store._reset_for_tests()
    # Pre-cache the backend to skip the import path entirely.
    secret_store._backend_checked = True
    secret_store._backend_available = True
    secret_store._kr_module = stub  # type: ignore[attr-defined]
    return stub


class TestSecretStoreBasics(unittest.TestCase):
    def setUp(self):
        self.stub = _install_stub()

    def tearDown(self):
        secret_store._reset_for_tests()

    def test_set_and_get(self):
        self.assertTrue(secret_store.set_secret("foo", "bar"))
        self.assertEqual(secret_store.get_secret("foo"), "bar")

    def test_empty_value_deletes(self):
        secret_store.set_secret("foo", "bar")
        secret_store.set_secret("foo", "")
        self.assertIsNone(secret_store.get_secret("foo"))

    def test_delete_unknown_is_noop(self):
        # Should not raise.
        secret_store.delete_secret("does-not-exist")

    def test_get_missing_returns_none(self):
        self.assertIsNone(secret_store.get_secret("never-stored"))

    def test_is_secure_when_backend_present(self):
        self.assertTrue(secret_store.is_secure())

    def test_canonical_names(self):
        self.assertEqual(secret_store.api_key_name("Claude"), "api_key:claude")
        self.assertEqual(
            secret_store.smart_home_secret_name("home_assistant", "token"),
            "smart_home:home_assistant:token",
        )

    def test_empty_name_rejected_on_set(self):
        with self.assertRaises(ValueError):
            secret_store.set_secret("", "value")


class TestFallbackWhenBackendUnavailable(unittest.TestCase):
    def setUp(self):
        secret_store._reset_for_tests()
        secret_store._backend_checked = True
        secret_store._backend_available = False  # force fallback path

    def tearDown(self):
        secret_store._reset_for_tests()

    def test_fallback_still_round_trips(self):
        # Setting returns False because it's NOT secure, but the value
        # still round-trips so the app stays functional.
        secured = secret_store.set_secret("api_key:test", "abc")
        self.assertFalse(secured)
        self.assertEqual(secret_store.get_secret("api_key:test"), "abc")
        self.assertFalse(secret_store.is_secure())


class TestSmartHomeMigration(unittest.TestCase):
    """The legacy zxor$ values must be migrated transparently on first load."""

    def setUp(self):
        self.stub = _install_stub()
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        self.tmp.close()
        self.path = self.tmp.name

    def tearDown(self):
        secret_store._reset_for_tests()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def _write(self, payload: dict) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def _read(self) -> dict:
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_save_writes_secrets_to_keystore_not_file(self):
        store = SmartHomeConfigStore(self.path)
        cfg = SmartHomeConfig(
            home_assistant=HomeAssistantConfig(
                url="http://ha.local:8123",
                token="my-long-lived-token-1234567890",
            ),
        )
        store.save(cfg)
        on_disk = self._read()
        # URL is fine to persist; token must not be.
        self.assertEqual(on_disk["home_assistant"]["url"], "http://ha.local:8123")
        self.assertEqual(on_disk["home_assistant"]["token"], "")
        # And the actual secret lives in the keystore.
        self.assertEqual(
            secret_store.get_secret("smart_home:home_assistant:token"),
            "my-long-lived-token-1234567890",
        )

    def test_load_round_trips_via_keystore(self):
        store = SmartHomeConfigStore(self.path)
        cfg = SmartHomeConfig(
            mqtt=MqttConfig(
                host="broker.lan", port=1883,
                username="iot", password="hunter2-password",
            ),
        )
        store.save(cfg)
        loaded = store.load()
        self.assertEqual(loaded.mqtt.host, "broker.lan")
        self.assertEqual(loaded.mqtt.username, "iot")
        self.assertEqual(loaded.mqtt.password, "hunter2-password")

    def test_legacy_zxor_value_is_migrated_then_wiped(self):
        # Manually build a legacy-style JSON: pre-existing zxor$ token.
        from ai.smart_home.config import _xor, _OBFUSCATION_MARKER, _LEGACY_LOCAL_KEY
        import base64

        cleartext = "legacy-hue-username-zXyzZ"
        encoded = _OBFUSCATION_MARKER + base64.b64encode(
            _xor(cleartext.encode("utf-8"), _LEGACY_LOCAL_KEY)
        ).decode("ascii")
        self._write({
            "home_assistant": {"url": "", "token": ""},
            "mqtt": {"host": "", "port": 1883, "username": "", "password": "",
                     "known_topics": []},
            "hue": {"bridge_ip": "192.168.1.50", "username": encoded},
            "aliases": {},
        })

        store = SmartHomeConfigStore(self.path)
        loaded = store.load()
        # Migration recovered the cleartext.
        self.assertEqual(loaded.hue.username, cleartext)
        # Keystore now holds the value.
        self.assertEqual(
            secret_store.get_secret("smart_home:hue:username"), cleartext
        )
        # The JSON file was rewritten without the zxor$ prefix.
        on_disk = self._read()
        self.assertEqual(on_disk["hue"]["username"], "")
        self.assertNotIn("zxor$", json.dumps(on_disk))

    def test_handedited_plaintext_is_migrated(self):
        # Someone pasted a token directly into the JSON. We should pick it up,
        # move it to the keystore, and rewrite the file without it.
        self._write({
            "home_assistant": {
                "url": "http://ha.local:8123",
                "token": "abc.def.ghi-plaintext",
            },
            "mqtt": {"host": "", "port": 1883, "username": "", "password": "",
                     "known_topics": []},
            "hue": {"bridge_ip": "", "username": ""},
            "aliases": {},
        })
        store = SmartHomeConfigStore(self.path)
        loaded = store.load()
        self.assertEqual(loaded.home_assistant.token, "abc.def.ghi-plaintext")
        self.assertEqual(
            secret_store.get_secret("smart_home:home_assistant:token"),
            "abc.def.ghi-plaintext",
        )
        on_disk = self._read()
        self.assertEqual(on_disk["home_assistant"]["token"], "")

    def test_redacted_snapshot_never_returns_token(self):
        store = SmartHomeConfigStore(self.path)
        store.save(SmartHomeConfig(
            home_assistant=HomeAssistantConfig(
                url="http://ha", token="real-token-here"),
        ))
        snap = store.redacted_snapshot()
        self.assertEqual(snap["home_assistant"]["token"], "***")
        self.assertNotIn("real-token-here", json.dumps(snap))


class TestApiKeyHelpers(unittest.TestCase):
    """Exercise the api/server.py helpers that route through the secret store."""

    _ENV_VARS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY", "GROQ_API_KEY")

    def setUp(self):
        self.stub = _install_stub()
        self._saved_env = {k: os.environ.get(k) for k in self._ENV_VARS}
        for k in self._ENV_VARS:
            os.environ.pop(k, None)

    def tearDown(self):
        secret_store._reset_for_tests()
        # Restore the env exactly as we found it.
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_save_and_load_api_key_round_trip(self):
        from api import server as srv
        srv._runtime_api_keys.clear()
        srv._save_api_key("claude", "sk-ant-test-abc")
        # In memory and in the keystore.
        self.assertEqual(srv._runtime_api_keys.get("claude"), "sk-ant-test-abc")
        self.assertEqual(
            secret_store.get_secret("api_key:claude"), "sk-ant-test-abc"
        )
        # And mirrored into the env var the Anthropic SDK reads.
        self.assertEqual(os.environ.get("ANTHROPIC_API_KEY"), "sk-ant-test-abc")

        # Clearing removes everywhere.
        srv._save_api_key("claude", "")
        self.assertNotIn("claude", srv._runtime_api_keys)
        self.assertIsNone(secret_store.get_secret("api_key:claude"))
        self.assertNotIn("ANTHROPIC_API_KEY", os.environ)

    def test_api_key_for_pulls_from_keystore_on_cold_cache(self):
        from api import server as srv
        srv._runtime_api_keys.clear()
        # Bypass _save_api_key so we only touch the keystore, not the cache.
        secret_store.set_secret("api_key:openai", "sk-openai-cached")
        # First call hydrates from keystore.
        self.assertEqual(srv._api_key_for("openai"), "sk-openai-cached")
        # And populates the cache.
        self.assertEqual(srv._runtime_api_keys.get("openai"), "sk-openai-cached")

    def test_legacy_api_key_migration_moves_from_config_to_keystore(self):
        from api import server as srv
        srv._runtime_api_keys.clear()
        # Build a config.json that has the legacy api_key field.
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(
            {"ai": {"provider": "claude", "model": "x", "api_key": "legacy-sk-key"}},
            tmp,
        )
        tmp.close()
        try:
            with open(tmp.name, "r", encoding="utf-8") as f:
                config = json.load(f)
            cleaned = srv._migrate_legacy_api_keys(config, tmp.name)
            self.assertNotIn("api_key", cleaned["ai"])
            self.assertEqual(
                secret_store.get_secret("api_key:claude"), "legacy-sk-key"
            )
            with open(tmp.name, "r", encoding="utf-8") as f:
                on_disk = json.load(f)
            self.assertNotIn("api_key", on_disk["ai"])
        finally:
            os.unlink(tmp.name)


if __name__ == "__main__":
    unittest.main()
