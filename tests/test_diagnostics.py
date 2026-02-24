#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for diagnostic modules — validates loading and structure."""

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from diagnostics.base import BaseDiagnostic, TechSupportNarrator, DiagnosticResult


DIAGNOSTIC_MODULES = {
    "printer": ("diagnostics.printer", "PrinterDiagnostic"),
    "internet": ("diagnostics.internet", "InternetDiagnostic"),
    "software": ("diagnostics.software", "SoftwareDiagnostic"),
    "hardware": ("diagnostics.hardware", "HardwareDiagnostic"),
    "files": ("diagnostics.files", "FilesDiagnostic"),
    "display": ("diagnostics.display", "DisplayDiagnostic"),
    "audio": ("diagnostics.audio", "AudioDiagnostic"),
    "security": ("diagnostics.security", "SecurityDiagnostic"),
}


class TestNarrator(unittest.TestCase):

    def test_say(self):
        n = TechSupportNarrator(verbose=False)
        n.say("Hello")
        self.assertEqual(len(n.log), 1)
        self.assertEqual(n.log[0]["type"], "say")

    def test_all_methods(self):
        n = TechSupportNarrator(verbose=False)
        n.say("test")
        n.think("detail")
        n.success("done")
        n.problem("issue")
        n.tip("hint")
        n.step(1, 3, "first")
        self.assertEqual(len(n.log), 6)

    def test_session_summary(self):
        n = TechSupportNarrator(verbose=False)
        n.problem("issue1")
        n.success("fix1")
        summary = n.get_session_summary()
        self.assertEqual(summary["problems_found"], 1)
        self.assertEqual(summary["fixes_applied"], 1)


class TestDiagnosticResult(unittest.TestCase):

    def test_creation(self):
        r = DiagnosticResult("Test", "ok", "All good")
        self.assertEqual(r.name, "Test")
        self.assertEqual(r.status, "ok")

    def test_fix_available(self):
        r = DiagnosticResult("Test", "error", "bad", fix_available=True)
        self.assertTrue(r.fix_available)
        self.assertFalse(r.fix_applied)


class TestDiagnosticModulesLoad(unittest.TestCase):
    """Verify all 8 diagnostic modules can be imported and instantiated."""

    def test_all_modules_importable(self):
        import importlib
        for name, (module_path, class_name) in DIAGNOSTIC_MODULES.items():
            with self.subTest(module=name):
                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name)
                self.assertTrue(issubclass(cls, BaseDiagnostic))

    def test_all_modules_instantiable(self):
        import importlib
        for name, (module_path, class_name) in DIAGNOSTIC_MODULES.items():
            with self.subTest(module=name):
                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name)
                instance = cls(narrator=TechSupportNarrator(verbose=False))
                self.assertIsNotNone(instance)

    def test_all_have_diagnose(self):
        import importlib
        for name, (module_path, class_name) in DIAGNOSTIC_MODULES.items():
            with self.subTest(module=name):
                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name)
                self.assertTrue(hasattr(cls, "diagnose"))
                self.assertTrue(callable(getattr(cls, "diagnose")))

    def test_all_have_category(self):
        import importlib
        for name, (module_path, class_name) in DIAGNOSTIC_MODULES.items():
            with self.subTest(module=name):
                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name)
                self.assertEqual(cls.CATEGORY, name)


if __name__ == "__main__":
    unittest.main()
