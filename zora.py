#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zora - Desktop Tech Support
Entry point for PyInstaller build.
"""
import sys
import os

# Ensure the bundled app's root is on the path
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from cli.main import main

if __name__ == "__main__":
    sys.exit(main())
