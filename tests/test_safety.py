#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Safety System."""

import os
import sys
import json
import time
import tempfile
import unittest

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.safety import (
    RateLimiter, Blacklist, ActionLogger, SafetyController,
    EmergencyStop, SafetyCheckResult, RiskLevel,
)


class TestRateLimiter(unittest.TestCase):

    def test_allows_within_limit(self):
        rl = RateLimiter(max_actions_per_minute=10)
        for _ in range(10):
            self.assertTrue(rl.allow())

    def test_blocks_over_limit(self):
        rl = RateLimiter(max_actions_per_minute=3)
        self.assertTrue(rl.allow())
        self.assertTrue(rl.allow())
        self.assertTrue(rl.allow())
        self.assertFalse(rl.allow())

    def test_current_count(self):
        rl = RateLimiter(max_actions_per_minute=100)
        rl.allow()
        rl.allow()
        self.assertEqual(rl.current_count, 2)


class TestBlacklist(unittest.TestCase):

    def test_system_path_restricted(self):
        bl = Blacklist(system_protected=True)
        self.assertTrue(bl.is_path_restricted(r"C:\Windows\System32\config"))

    def test_custom_path_restricted(self):
        bl = Blacklist(custom_paths=[r"C:\SensitiveData"])
        self.assertTrue(bl.is_path_restricted(r"C:\SensitiveData\secrets.txt"))

    def test_normal_path_allowed(self):
        bl = Blacklist()
        self.assertFalse(bl.is_path_restricted(r"C:\Users\me\Documents\file.txt"))

    def test_custom_process_restricted(self):
        bl = Blacklist(custom_processes=["antivirus.exe"])
        self.assertTrue(bl.is_process_restricted("antivirus.exe"))
        self.assertTrue(bl.is_process_restricted("ANTIVIRUS.EXE"))

    def test_normal_process_allowed(self):
        bl = Blacklist()
        self.assertFalse(bl.is_process_restricted("notepad.exe"))


class TestActionLogger(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.tmpdir, "test_log.jsonl")
        self.logger = ActionLogger(self.log_file)

    def test_log_creates_file(self):
        self.logger.log("test_action", {"param": "value"}, True)
        self.assertTrue(os.path.exists(self.log_file))

    def test_log_writes_json(self):
        self.logger.log("click", {"x": 100, "y": 200}, True)
        with open(self.log_file, "r") as f:
            entry = json.loads(f.readline())
        self.assertEqual(entry["action_type"], "click")
        self.assertTrue(entry["success"])

    def test_get_recent(self):
        for i in range(5):
            self.logger.log(f"action_{i}", {}, True)
        recent = self.logger.get_recent(3)
        self.assertEqual(len(recent), 3)

    def tearDown(self):
        try:
            os.remove(self.log_file)
            os.rmdir(self.tmpdir)
        except Exception:
            pass


class TestEmergencyStop(unittest.TestCase):

    def test_not_triggered_initially(self):
        es = EmergencyStop.__new__(EmergencyStop)
        es._triggered = False
        es._lock = __import__("threading").Lock()
        self.assertFalse(es.is_triggered())

    def test_trigger(self):
        es = EmergencyStop.__new__(EmergencyStop)
        es._triggered = False
        es._lock = __import__("threading").Lock()
        es.trigger()
        self.assertTrue(es.is_triggered())

    def test_reset(self):
        es = EmergencyStop.__new__(EmergencyStop)
        es._triggered = True
        es._lock = __import__("threading").Lock()
        es.reset()
        self.assertFalse(es.is_triggered())


class TestSafetyController(unittest.TestCase):

    def setUp(self):
        self.controller = SafetyController({
            "safety": {
                "max_actions_per_minute": 50,
                "require_confirmation_for_high_risk": True,
                "log_file": os.path.join(tempfile.mkdtemp(), "test.jsonl"),
            }
        })

    def test_allows_normal_action(self):
        result = self.controller.check_action("click")
        self.assertTrue(result.allowed)

    def test_blocks_after_emergency_stop(self):
        self.controller.emergency_stop.trigger()
        result = self.controller.check_action("click")
        self.assertFalse(result.allowed)
        self.controller.emergency_stop.reset()

    def test_requires_confirmation_for_high_risk(self):
        result = self.controller.check_action("kill_process")
        self.assertTrue(result.allowed)
        self.assertTrue(result.confirm_required)

    def test_blocks_restricted_path(self):
        result = self.controller.check_action("delete_file", r"C:\Windows\System32\cmd.exe")
        self.assertFalse(result.allowed)

    def test_risk_assessment(self):
        self.assertEqual(self.controller.assess_risk("kill_process"), RiskLevel.HIGH)
        self.assertEqual(self.controller.assess_risk("launch_process"), RiskLevel.MEDIUM)
        self.assertEqual(self.controller.assess_risk("click"), RiskLevel.LOW)


if __name__ == "__main__":
    unittest.main()
