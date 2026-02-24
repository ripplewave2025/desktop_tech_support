#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for Process Manager."""

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.process_manager import ProcessManager, SystemInfo


class TestProcessManager(unittest.TestCase):

    def setUp(self):
        self.pm = ProcessManager()

    def test_list_processes(self):
        procs = self.pm.list_processes()
        self.assertGreater(len(procs), 0, "Should find at least one process")

    def test_find_python(self):
        proc = self.pm.find_process(name="python.exe")
        # python.exe or pythonw.exe should be running
        self.assertIsNotNone(proc, "Should find running Python process")

    def test_is_running(self):
        # Current process should be running
        import os
        self.assertTrue(self.pm.is_running(os.getpid()))

    def test_system_info(self):
        info = self.pm.get_system_info()
        self.assertIsInstance(info, SystemInfo)
        self.assertGreater(info.cpu_count, 0)
        self.assertGreater(info.memory_total_gb, 0)
        self.assertGreater(info.disk_total_gb, 0)

    def test_list_processes_with_filter(self):
        procs = self.pm.list_processes(name_filter="python")
        self.assertGreater(len(procs), 0, "Filter should find Python")

    def test_network_io(self):
        io = self.pm.get_network_io()
        self.assertIn("bytes_sent", io)
        self.assertIn("bytes_recv", io)


class TestSystemInfo(unittest.TestCase):

    def test_repr(self):
        info = SystemInfo()
        s = repr(info)
        self.assertIn("CPU:", s)
        self.assertIn("RAM:", s)


if __name__ == "__main__":
    unittest.main()
