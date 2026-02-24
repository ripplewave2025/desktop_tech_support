#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Setup Script — One-click dependency installer and validator.

Usage:
  python setup.py          # Install all dependencies + validate
  python setup.py --check  # Validate only, don't install
"""

import subprocess
import sys
import os
import argparse


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


def install_packages():
    """Install all required packages."""
    print("\n  Installing Python packages...")
    req_file = os.path.join(os.path.dirname(__file__), "requirements.txt")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", req_file, "--quiet"],
            stdout=subprocess.DEVNULL if os.name == "nt" else None,
        )
        print("  [OK] All packages installed.")
        return True
    except subprocess.CalledProcessError:
        print("  [!!] Some packages failed to install. Trying individually...")
        failed = []
        for module, package in PACKAGES.items():
            try:
                __import__(module)
            except ImportError:
                try:
                    subprocess.check_call(
                        [sys.executable, "-m", "pip", "install", package, "--quiet"],
                    )
                    print(f"  [OK] Installed {package}")
                except subprocess.CalledProcessError:
                    print(f"  [!!] FAILED: {package}")
                    failed.append(package)
        return len(failed) == 0


def validate_imports():
    """Test that all required packages can be imported."""
    print("\n  Validating package imports...")
    failed = []
    for module, package in PACKAGES.items():
        try:
            __import__(module)
            print(f"  [OK] {package:20s} imported")
        except ImportError as e:
            print(f"  [!!] {package:20s} FAILED: {e}")
            failed.append(package)
    return failed


def check_tesseract():
    """Check if Tesseract OCR is available."""
    print("\n  Checking Tesseract OCR...")
    try:
        result = subprocess.run(
            ["tesseract", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        version = result.stdout.split("\n")[0] if result.stdout else "Unknown"
        print(f"  [OK] Tesseract found: {version}")
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("  [!!] Tesseract OCR not found.")
        print("       OCR features will be limited.")
        print("       Install from: https://github.com/UB-Mannheim/tesseract/wiki")
        return False


def create_directories():
    """Create required directories."""
    dirs = ["logs"]
    for d in dirs:
        os.makedirs(os.path.join(os.path.dirname(__file__), d), exist_ok=True)
    print("  [OK] Directories created.")


def main():
    parser = argparse.ArgumentParser(description="Desktop Tech Support Setup")
    parser.add_argument("--check", action="store_true", help="Validate only")
    args = parser.parse_args()

    print("\n  ============================================")
    print("   Desktop Tech Support - Setup")
    print("  ============================================")

    if not args.check:
        install_packages()

    failed = validate_imports()
    check_tesseract()
    create_directories()

    print("\n  ============================================")
    if not failed:
        print("  [OK] Setup complete! All systems go.")
        print("\n  Run: python -m cli.main")
    else:
        print(f"  [!!] {len(failed)} package(s) failed: {', '.join(failed)}")
        print(f"\n  Try: pip install {' '.join(failed)}")
    print("  ============================================\n")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
