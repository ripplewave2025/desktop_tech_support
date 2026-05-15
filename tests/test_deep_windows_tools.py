"""
Tests for the deeper Windows tools:
  * core.bsod_analyzer
  * core.event_log_triage
  * ai.oem_silent.warranty_lookup_url
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import bsod_analyzer, event_log_triage
from ai import oem_silent


class TestBugcheckExplain(unittest.TestCase):
    def test_known_code_returns_name(self):
        result = bsod_analyzer.explain(0x7E)
        self.assertTrue(result["known"])
        self.assertEqual(result["name"], "SYSTEM_THREAD_EXCEPTION_NOT_HANDLED")
        self.assertEqual(result["code_hex"], "0x7E")
        self.assertGreater(len(result["common_causes"]), 0)

    def test_unknown_code_returns_generic(self):
        result = bsod_analyzer.explain(0xFFFF_FFFF)
        self.assertFalse(result["known"])
        self.assertIn("Unknown", result["name"])
        self.assertEqual(result["code_hex"], "0xFFFFFFFF")
        # Generic causes still steer the user somewhere useful.
        self.assertGreater(len(result["common_causes"]), 0)

    def test_zero_code(self):
        result = bsod_analyzer.explain(0)
        self.assertFalse(result["known"])

    def test_memory_management_is_known(self):
        # Real-world: 0x1A is one of the most common consumer BSODs.
        result = bsod_analyzer.explain(0x1A)
        self.assertTrue(result["known"])
        self.assertEqual(result["name"], "MEMORY_MANAGEMENT")


class TestBugcheckMessageParse(unittest.TestCase):
    def test_parse_canonical_message(self):
        msg = (
            "The computer has rebooted from a bugcheck. "
            "The bugcheck was: 0x0000007E (0xC0000005, 0xFFFFF80018E8E000, "
            "0xFFFFC00DAB1, 0xFFFFC00DAB0)."
        )
        parsed = bsod_analyzer._parse_message(msg)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["bugcheck_code"], 0x7E)
        self.assertEqual(len(parsed["parameters"]), 4)

    def test_parse_message_no_match(self):
        self.assertIsNone(bsod_analyzer._parse_message("System rebooted normally"))


class TestRecentBSODsNonWindows(unittest.TestCase):
    @patch("core.bsod_analyzer.os.name", "posix")
    def test_returns_unsupported_off_windows(self):
        result = bsod_analyzer.recent_bsods(limit=5)
        self.assertFalse(result["supported"])
        self.assertEqual(result["events"], [])
        self.assertIn("Windows", result["error"])

    @patch("core.bsod_analyzer.os.name", "posix")
    def test_minidump_files_unsupported_off_windows(self):
        result = bsod_analyzer.minidump_files()
        self.assertFalse(result["supported"])
        self.assertEqual(result["files"], [])


class TestRecentBSODsWindowsPath(unittest.TestCase):
    """On Windows, exercise the subprocess path with a stubbed run."""

    def _fake_run(self, stdout: str, returncode: int = 0):
        class _R:
            def __init__(self, out, rc):
                self.stdout = out
                self.stderr = ""
                self.returncode = rc
        return lambda *a, **kw: _R(stdout, returncode)

    @patch("core.bsod_analyzer.os.name", "nt")
    def test_parses_single_event_json_object(self):
        # PowerShell ConvertTo-Json returns a single object when there's one
        # result (not an array) — make sure we handle both.
        payload = json.dumps({
            "TimeCreated": "2026-05-15T12:34:56",
            "Id": 1001,
            "ProviderName": "BugCheck",
            "Message": "The bugcheck was: 0x0000007E (0x1, 0x2, 0x3, 0x4).",
        })
        with patch("core.bsod_analyzer.subprocess.run", self._fake_run(payload)):
            result = bsod_analyzer.recent_bsods(limit=5)
        self.assertTrue(result["supported"])
        self.assertEqual(len(result["events"]), 1)
        ev = result["events"][0]
        self.assertEqual(ev["bugcheck_code"], 0x7E)
        self.assertEqual(ev["name"], "SYSTEM_THREAD_EXCEPTION_NOT_HANDLED")

    @patch("core.bsod_analyzer.os.name", "nt")
    def test_parses_event_array(self):
        payload = json.dumps([
            {"TimeCreated": "2026-05-15T12:00:00", "Id": 1001,
             "ProviderName": "BugCheck",
             "Message": "The bugcheck was: 0x0000001A (0x1, 0x2, 0x3, 0x4)."},
            {"TimeCreated": "2026-05-14T12:00:00", "Id": 1001,
             "ProviderName": "BugCheck",
             "Message": "The bugcheck was: 0x00000133 (0x1, 0x2, 0x3, 0x4)."},
        ])
        with patch("core.bsod_analyzer.subprocess.run", self._fake_run(payload)):
            result = bsod_analyzer.recent_bsods(limit=10)
        self.assertEqual(len(result["events"]), 2)
        # Order preserved from the input.
        self.assertEqual(result["events"][0]["bugcheck_code"], 0x1A)
        self.assertEqual(result["events"][1]["bugcheck_code"], 0x133)


class TestEventLogTriage(unittest.TestCase):
    def test_unsupported_off_windows(self):
        with patch("core.event_log_triage.os.name", "posix"):
            result = event_log_triage.recent_errors()
        self.assertFalse(result["supported"])

    def test_rejects_invalid_log_name(self):
        with patch("core.event_log_triage.os.name", "nt"):
            result = event_log_triage.recent_errors(log="../etc/passwd")
        self.assertEqual(result["events"], [])
        self.assertIn("log must be one of", result["error"])

    def test_clamps_hours_and_limit(self):
        # Bypass the subprocess: stub it out to capture the command.
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            class _R:
                stdout = "[]"; stderr = ""; returncode = 0
            return _R()

        with patch("core.event_log_triage.os.name", "nt"), \
             patch("core.event_log_triage.subprocess.run", fake_run):
            event_log_triage.recent_errors(hours=9999, limit=99999)
        # hours clamped to 168, limit to 500.
        joined = " ".join(captured["cmd"])
        self.assertIn("AddHours(-168)", joined)
        self.assertIn("MaxEvents 500", joined)

    def test_annotates_known_kernel_power_41(self):
        payload = json.dumps([{
            "TimeCreated": "2026-05-15T03:14:15",
            "LogName": "System",
            "ProviderName": "Microsoft-Windows-Kernel-Power",
            "Id": 41,
            "LevelDisplayName": "Critical",
            "Message": "The system has rebooted without cleanly shutting down first.",
        }])

        def fake_run(cmd, **kwargs):
            class _R:
                stdout = payload; stderr = ""; returncode = 0
            return _R()

        with patch("core.event_log_triage.os.name", "nt"), \
             patch("core.event_log_triage.subprocess.run", fake_run):
            result = event_log_triage.recent_errors()
        self.assertEqual(len(result["events"]), 1)
        ev = result["events"][0]
        self.assertTrue(ev["known"])
        self.assertIn("Unexpected shutdown", ev["explanation"])

    def test_triage_summary_groups_and_counts(self):
        # Three events: two Kernel-Power 41s and one disk 7. Grouping should
        # produce 2 ranked entries with counts 2 and 1.
        payload = json.dumps([
            {"TimeCreated": "2026-05-15T03:00:00", "LogName": "System",
             "ProviderName": "Microsoft-Windows-Kernel-Power", "Id": 41,
             "LevelDisplayName": "Critical", "Message": "msg1"},
            {"TimeCreated": "2026-05-15T04:00:00", "LogName": "System",
             "ProviderName": "Microsoft-Windows-Kernel-Power", "Id": 41,
             "LevelDisplayName": "Critical", "Message": "msg2"},
            {"TimeCreated": "2026-05-15T05:00:00", "LogName": "System",
             "ProviderName": "disk", "Id": 7,
             "LevelDisplayName": "Error", "Message": "bad block"},
        ])

        def fake_run(cmd, **kwargs):
            class _R:
                stdout = payload; stderr = ""; returncode = 0
            return _R()

        with patch("core.event_log_triage.os.name", "nt"), \
             patch("core.event_log_triage.subprocess.run", fake_run):
            summary = event_log_triage.triage_summary(hours=24)

        self.assertTrue(summary["supported"])
        self.assertEqual(summary["total_events"], 3)
        # Highest count first; Kernel-Power 41 has count=2 vs disk 7 count=1.
        self.assertEqual(summary["groups"][0]["count"], 2)
        self.assertEqual(summary["groups"][0]["event_id"], 41)
        # disk 7 is annotated.
        disk_group = next(g for g in summary["groups"] if g["event_id"] == 7)
        self.assertTrue(disk_group["known"])
        self.assertIn("Bad block", disk_group["explanation"])


class TestWarrantyLookup(unittest.TestCase):
    def test_dell_with_serial_builds_url(self):
        ctx = oem_silent.VendorContext(
            vendor="dell", manufacturer="Dell", model="Inspiron 15",
            serial="ABC1234", bios_version="1.0",
        )
        result = oem_silent.warranty_lookup_url(ctx)
        self.assertTrue(result["supported"])
        self.assertIn("ABC1234", result["url"])
        self.assertIn("dell.com", result["url"])

    def test_hp_with_serial(self):
        ctx = oem_silent.VendorContext(
            vendor="hp", manufacturer="HP", model="EliteBook",
            serial="HP1234567", bios_version="2.0",
        )
        result = oem_silent.warranty_lookup_url(ctx)
        self.assertTrue(result["supported"])
        self.assertIn("HP1234567", result["url"])

    def test_lenovo_with_serial(self):
        ctx = oem_silent.VendorContext(
            vendor="lenovo", manufacturer="LENOVO", model="ThinkPad",
            serial="PF1AB2CD", bios_version="3.0",
        )
        result = oem_silent.warranty_lookup_url(ctx)
        self.assertTrue(result["supported"])
        self.assertIn("PF1AB2CD", result["url"])

    def test_missing_serial_returns_unsupported_with_fallback(self):
        ctx = oem_silent.VendorContext(
            vendor="dell", manufacturer="Dell", model="X",
            serial="", bios_version="",
        )
        result = oem_silent.warranty_lookup_url(ctx)
        self.assertFalse(result["supported"])
        self.assertIn("could not", result["reason"].lower())
        self.assertIn("dell.com", result.get("fallback_url", ""))

    def test_unsupported_vendor(self):
        ctx = oem_silent.VendorContext(
            vendor="generic", manufacturer="Acme", model="X",
            serial="ABC", bios_version="",
        )
        result = oem_silent.warranty_lookup_url(ctx)
        self.assertFalse(result["supported"])
        self.assertIn("not wired", result["reason"].lower())


if __name__ == "__main__":
    unittest.main()
