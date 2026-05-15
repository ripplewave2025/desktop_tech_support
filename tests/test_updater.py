"""
Tests for core.updater.

Coverage:
  * Version parsing / comparison
  * GitHub API call shape (HTTP stubbed)
  * Download streams + computes SHA-256
  * SHA mismatch → file deleted, "ok" False
  * launch_installer rejects missing path / non-Windows
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import updater


class TestVersionParsing(unittest.TestCase):
    def test_parses_v_prefix(self):
        self.assertEqual(updater.parse_version("v2.4.1"), (2, 4, 1))

    def test_parses_no_prefix(self):
        self.assertEqual(updater.parse_version("2.4"), (2, 4, 0))

    def test_parses_with_suffix(self):
        self.assertEqual(updater.parse_version("v2.4.1-beta"), (2, 4, 1))

    def test_garbage_returns_none(self):
        self.assertIsNone(updater.parse_version("not a version"))
        self.assertIsNone(updater.parse_version(""))
        self.assertIsNone(updater.parse_version(None))  # type: ignore[arg-type]

    def test_is_newer_strict(self):
        self.assertTrue(updater.is_newer("v2.4", "2.3.0"))
        self.assertTrue(updater.is_newer("v2.3.1", "v2.3.0"))
        self.assertFalse(updater.is_newer("v2.3.0", "v2.3.0"))
        self.assertFalse(updater.is_newer("v2.2", "v2.3"))

    def test_is_newer_handles_unparseable(self):
        self.assertFalse(updater.is_newer("garbage", "2.3.0"))
        self.assertFalse(updater.is_newer("2.4", "garbage"))


class TestCheckForUpdate(unittest.TestCase):
    """Mock the HTTP layer so we never actually hit GitHub from tests."""

    def _make_release(self, tag="v2.4.0", asset_name="ZoraSetup.exe",
                      include_sha=False):
        assets = [{
            "name": asset_name,
            "browser_download_url": f"https://github.com/x/y/releases/download/{tag}/{asset_name}",
            "size": 1234567,
        }]
        if include_sha:
            assets.append({
                "name": asset_name + ".sha256",
                "browser_download_url": f"https://github.com/x/y/releases/download/{tag}/{asset_name}.sha256",
                "size": 64,
            })
        return {
            "tag_name": tag,
            "published_at": "2026-05-10T12:00:00Z",
            "body": "Bug fixes and new BSOD parser.",
            "assets": assets,
        }

    def test_detects_newer_release(self):
        payload = json.dumps(self._make_release(tag="v2.4.0")).encode("utf-8")
        with patch("core.updater._http_get", return_value=payload):
            info = updater.check_for_update(current_version="2.3.0")
        self.assertTrue(info["available"])
        self.assertEqual(info["latest_version"], "2.4.0")
        self.assertEqual(info["tag_name"], "v2.4.0")
        self.assertTrue(info["asset_url"].endswith("ZoraSetup.exe"))

    def test_says_not_available_when_same(self):
        payload = json.dumps(self._make_release(tag="v2.3.0")).encode("utf-8")
        with patch("core.updater._http_get", return_value=payload):
            info = updater.check_for_update(current_version="2.3.0")
        self.assertFalse(info["available"])

    def test_says_not_available_when_older(self):
        payload = json.dumps(self._make_release(tag="v2.2.0")).encode("utf-8")
        with patch("core.updater._http_get", return_value=payload):
            info = updater.check_for_update(current_version="2.3.0")
        self.assertFalse(info["available"])

    def test_missing_asset_name_yields_error(self):
        payload = json.dumps(self._make_release(asset_name="Other.exe")).encode("utf-8")
        with patch("core.updater._http_get", return_value=payload):
            info = updater.check_for_update(current_version="2.3.0",
                                            asset_name="ZoraSetup.exe")
        self.assertIn("error", info)
        self.assertIn("no asset", info["error"])

    def test_http_error_returns_friendly_message(self):
        def boom(*args, **kwargs):
            raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)  # type: ignore[arg-type]
        with patch("core.updater._http_get", boom):
            info = updater.check_for_update(current_version="2.3.0")
        self.assertIn("error", info)
        self.assertIn("404", info["error"])

    def test_picks_up_sha256_companion(self):
        payload = json.dumps(self._make_release(include_sha=True)).encode("utf-8")
        with patch("core.updater._http_get", return_value=payload):
            info = updater.check_for_update(current_version="2.3.0")
        self.assertTrue(info["sha256_url"].endswith(".sha256"))


class TestDownloadUpdate(unittest.TestCase):
    """Stub urllib.request.urlopen with a BytesIO so we don't touch the network."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="zora-update-"))

    def tearDown(self):
        for f in self.tmpdir.glob("*"):
            try:
                f.unlink()
            except OSError:
                pass
        try:
            self.tmpdir.rmdir()
        except OSError:
            pass

    def _stub_urlopen(self, body: bytes):
        """Return a context-manager-compatible stub for urlopen."""
        class _Resp:
            def __init__(self, data):
                self._stream = io.BytesIO(data)
            def read(self, n=-1):
                return self._stream.read(n)
            def __enter__(self):
                return self
            def __exit__(self, *exc):
                return False
        return lambda *a, **kw: _Resp(body)

    def test_download_streams_and_hashes(self):
        payload = b"installer-bytes-" * 1024  # ~16 KB
        expected = hashlib.sha256(payload).hexdigest()
        url = "https://github.com/x/y/releases/download/v2.4/ZoraSetup.exe"
        with patch("core.updater.urllib.request.urlopen",
                   self._stub_urlopen(payload)):
            result = updater.download_update(url, dest_dir=self.tmpdir)
        self.assertTrue(result["ok"])
        self.assertEqual(result["sha256"], expected)
        self.assertEqual(result["size_bytes"], len(payload))
        self.assertTrue(Path(result["path"]).exists())

    def test_sha_mismatch_deletes_file_and_fails(self):
        payload = b"x" * 1000
        bad_hash = "0" * 64
        url = "https://github.com/x/y/releases/download/v2.4/ZoraSetup.exe"
        sha_url = url + ".sha256"

        def fake_http_get(u, timeout=15):
            # Companion .sha256 lookup must hit the get path, not urlopen.
            return f"{bad_hash}  ZoraSetup.exe".encode("utf-8")

        with patch("core.updater.urllib.request.urlopen",
                   self._stub_urlopen(payload)), \
             patch("core.updater._http_get", fake_http_get):
            result = updater.download_update(url, sha256_url=sha_url,
                                              dest_dir=self.tmpdir)
        self.assertFalse(result["ok"])
        self.assertFalse(result["sha256_match"])
        self.assertIn("SHA-256 mismatch", result["error"])
        # File must NOT remain on disk.
        self.assertFalse(Path(result["path"]).exists())

    def test_sha_match_keeps_file(self):
        payload = b"some installer bytes here"
        good_hash = hashlib.sha256(payload).hexdigest()
        url = "https://github.com/x/y/releases/download/v2.4/ZoraSetup.exe"
        sha_url = url + ".sha256"

        def fake_http_get(u, timeout=15):
            return f"{good_hash}  ZoraSetup.exe".encode("utf-8")

        with patch("core.updater.urllib.request.urlopen",
                   self._stub_urlopen(payload)), \
             patch("core.updater._http_get", fake_http_get):
            result = updater.download_update(url, sha256_url=sha_url,
                                              dest_dir=self.tmpdir)
        self.assertTrue(result["ok"])
        self.assertTrue(result["sha256_match"])
        self.assertEqual(result["sha256"], good_hash)
        self.assertTrue(Path(result["path"]).exists())

    def test_empty_url_returns_error(self):
        result = updater.download_update("", dest_dir=self.tmpdir)
        self.assertFalse(result["ok"])
        self.assertIn("No asset URL", result["error"])

    def test_network_error_surfaces(self):
        def boom(*args, **kwargs):
            raise urllib.error.URLError("connection refused")
        with patch("core.updater.urllib.request.urlopen", boom):
            result = updater.download_update(
                "https://x.example/installer.exe",
                dest_dir=self.tmpdir,
            )
        self.assertFalse(result["ok"])
        self.assertIn("Download failed", result["error"])


class TestLaunchInstaller(unittest.TestCase):
    def test_missing_file_rejected(self):
        result = updater.launch_installer("/does/not/exist.exe")
        self.assertFalse(result["started"])
        self.assertIn("not found", result["error"].lower())

    @patch("core.updater.os.name", "posix")
    def test_non_windows_rejected(self):
        # Create a real file so the path-exists check passes — we want
        # the OS check to be the failure reason.
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            f.write(b"stub")
            path = f.name
        try:
            result = updater.launch_installer(path)
            self.assertFalse(result["started"])
            self.assertIn("Windows", result["error"])
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
