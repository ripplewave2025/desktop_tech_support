import json
import os
import unittest
from unittest.mock import patch

import api.server as server


class TestApiSecuritySettings(unittest.TestCase):
    def setUp(self):
        server._runtime_api_keys.clear()

    def test_cors_is_localhost_restricted(self):
        cors = None
        for m in server.app.user_middleware:
            if m.cls.__name__ == "CORSMiddleware":
                cors = m
                break
        self.assertIsNotNone(cors)
        self.assertIn("http://127.0.0.1", cors.kwargs["allow_origins"])
        self.assertFalse(cors.kwargs["allow_credentials"])
        self.assertIn("localhost", cors.kwargs["allow_origin_regex"])

    def test_update_settings_does_not_persist_api_key(self):
        fake_config = {"ai": {"provider": "openai", "model": "gpt-4o", "api_key": "old-secret"}}

        captured = {}

        def fake_dump(data, fp, indent=2):
            captured["data"] = data

        with patch("api.server._load_config", return_value=fake_config), \
             patch("api.server.open", create=True), \
             patch("api.server.json.dump", side_effect=fake_dump), \
             patch("api.server._get_agent", return_value=None):
            settings = server.SettingsUpdate(api_key="new-secret", provider="openai")
            server.update_settings(settings)

        self.assertNotIn("api_key", captured["data"]["ai"])
        self.assertEqual(server._runtime_api_keys.get("openai"), "new-secret")
        self.assertEqual(os.environ.get("OPENAI_API_KEY"), "new-secret")


if __name__ == "__main__":
    unittest.main()
