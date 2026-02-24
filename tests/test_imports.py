#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test that all required packages can be imported."""

import unittest


class TestImports(unittest.TestCase):
    """Verify all required packages are available."""

    PACKAGES = {
        "pywinauto": "pywinauto",
        "pynput": "pynput",
        "mss": "mss",
        "pytesseract": "pytesseract",
        "cv2": "opencv-python",
        "psutil": "psutil",
        "win32gui": "pywin32",
        "PIL": "Pillow",
    }

    def test_all_imports(self):
        """All required packages should import without errors."""
        failed = []
        for module, package in self.PACKAGES.items():
            try:
                __import__(module)
            except ImportError:
                failed.append(package)
        self.assertEqual(failed, [], f"Failed imports: {', '.join(failed)}")

    def test_psutil(self):
        import psutil
        self.assertTrue(psutil.cpu_count() > 0)

    def test_mss(self):
        import mss
        sct = mss.mss()
        self.assertTrue(len(sct.monitors) > 0)

    def test_pynput(self):
        from pynput.mouse import Controller
        mouse = Controller()
        pos = mouse.position
        self.assertIsInstance(pos, tuple)

    def test_pillow(self):
        from PIL import Image
        img = Image.new("RGB", (10, 10))
        self.assertEqual(img.size, (10, 10))


if __name__ == "__main__":
    unittest.main()
