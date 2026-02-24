#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke test — Quick end-to-end validation that major systems work."""

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.automation import AutomationController


class TestSmoke(unittest.TestCase):
    """End-to-end smoke tests for the AutomationController."""

    def setUp(self):
        self.ctrl = AutomationController()

    def test_controller_initializes(self):
        self.assertIsNotNone(self.ctrl)
        self.assertIsNotNone(self.ctrl.safety)
        self.assertIsNotNone(self.ctrl.windows)
        self.assertIsNotNone(self.ctrl.input)
        self.assertIsNotNone(self.ctrl.screen)
        self.assertIsNotNone(self.ctrl.processes)

    def test_list_windows(self):
        windows = self.ctrl.list_windows()
        self.assertIsInstance(windows, list)
        # Should find at least some windows
        self.assertGreater(len(windows), 0, "Should find visible windows")

    def test_list_processes(self):
        procs = self.ctrl.list_processes()
        self.assertGreater(len(procs), 0, "Should find running processes")

    def test_system_info(self):
        info = self.ctrl.get_system_info()
        self.assertGreater(info.cpu_count, 0)
        self.assertGreater(info.memory_total_gb, 0)

    def test_get_mouse_position(self):
        pos = self.ctrl.get_mouse_position()
        self.assertIsInstance(pos, tuple)
        self.assertEqual(len(pos), 2)

    def test_capture_screen(self):
        img = self.ctrl.capture_screen()
        self.assertIsNotNone(img)
        self.assertGreater(img.size[0], 0)
        self.assertGreater(img.size[1], 0)

    def test_emergency_stop_not_triggered(self):
        self.assertFalse(self.ctrl.is_emergency_stop_triggered())

    def test_recent_actions(self):
        actions = self.ctrl.get_recent_actions()
        self.assertIsInstance(actions, list)


if __name__ == "__main__":
    unittest.main()
