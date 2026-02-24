#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""File & Storage Troubleshooting — Missing files, large files, recycle bin."""

import os
import subprocess
from typing import List

from .base import BaseDiagnostic, DiagnosticResult, ask_permission


class FilesDiagnostic(BaseDiagnostic):
    CATEGORY = "files"
    DESCRIPTION = "File & Storage Troubleshooting"

    def diagnose(self) -> List[DiagnosticResult]:
        results = []
        total_steps = 4

        # Step 1: Check recent downloads folder
        self.narrator.step(1, total_steps, "Checking Downloads folder")
        downloads = os.path.join(os.environ.get("USERPROFILE", ""), "Downloads")
        if os.path.exists(downloads):
            try:
                files = os.listdir(downloads)
                total_size = 0
                for f in files:
                    fp = os.path.join(downloads, f)
                    try:
                        if os.path.isfile(fp):
                            total_size += os.path.getsize(fp)
                    except OSError:
                        continue
                size_mb = round(total_size / (1024 * 1024), 1)
                self.narrator.say(f"Downloads folder: {len(files)} items, {size_mb} MB")
                if size_mb > 2000:
                    self.narrator.problem("Downloads folder is quite large.")
                    self.narrator.tip("Consider moving or deleting old downloads.")
                    results.append(DiagnosticResult(
                        "Downloads Folder", "warning",
                        f"{size_mb} MB ({len(files)} files)", fix_available=False
                    ))
                else:
                    results.append(DiagnosticResult("Downloads Folder", "ok", f"{size_mb} MB"))
            except Exception as e:
                results.append(DiagnosticResult("Downloads Folder", "warning", str(e)))
        else:
            results.append(DiagnosticResult("Downloads Folder", "ok", "Not found"))

        # Step 2: Check Desktop clutter
        self.narrator.step(2, total_steps, "Checking Desktop")
        desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
        if os.path.exists(desktop):
            try:
                items = os.listdir(desktop)
                if len(items) > 50:
                    self.narrator.problem(f"Desktop has {len(items)} items. That's quite cluttered!")
                    self.narrator.tip("A clean desktop can improve performance and make files easier to find.")
                    results.append(DiagnosticResult(
                        "Desktop Clutter", "warning",
                        f"{len(items)} items", fix_available=False
                    ))
                else:
                    self.narrator.say(f"Desktop: {len(items)} items")
                    results.append(DiagnosticResult("Desktop Clutter", "ok", f"{len(items)} items"))
            except Exception:
                results.append(DiagnosticResult("Desktop Clutter", "ok", "Could not check"))

        # Step 3: Check Recycle Bin size
        self.narrator.step(3, total_steps, "Checking Recycle Bin")
        try:
            r = subprocess.run(
                ["powershell", "-Command",
                 "(New-Object -ComObject Shell.Application).Namespace(10).Items().Count"],
                capture_output=True, text=True, timeout=15
            )
            count = r.stdout.strip()
            if count and int(count) > 100:
                self.narrator.problem(f"Recycle Bin has {count} items.")
                self.narrator.say("Emptying it can free up disk space.")
                results.append(DiagnosticResult(
                    "Recycle Bin", "warning",
                    f"{count} items", fix_available=True
                ))
            else:
                self.narrator.say(f"Recycle Bin: {count} items")
                results.append(DiagnosticResult("Recycle Bin", "ok", f"{count} items"))
        except Exception as e:
            self.narrator.think(f"Could not check Recycle Bin: {e}")
            results.append(DiagnosticResult("Recycle Bin", "warning", str(e)))

        # Step 4: Find large files in user profile
        self.narrator.step(4, total_steps, "Looking for large files")
        try:
            user_dir = os.environ.get("USERPROFILE", "")
            large_files = []
            checked = 0
            for dirpath, dirnames, filenames in os.walk(user_dir):
                # Skip hidden / system dirs
                dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in ("AppData",)]
                for f in filenames:
                    checked += 1
                    if checked > 50000:
                        break
                    try:
                        fp = os.path.join(dirpath, f)
                        size = os.path.getsize(fp)
                        if size > 500 * 1024 * 1024:  # > 500 MB
                            large_files.append((fp, size))
                    except (OSError, PermissionError):
                        continue

            if large_files:
                large_files.sort(key=lambda x: x[1], reverse=True)
                self.narrator.say(f"Found {len(large_files)} large file(s) (>500 MB):")
                for path, size in large_files[:5]:
                    gb = round(size / (1024 ** 3), 2)
                    self.narrator.think(f"  {gb} GB - {os.path.basename(path)}")
                results.append(DiagnosticResult(
                    "Large Files", "warning",
                    f"{len(large_files)} files > 500 MB", fix_available=False
                ))
            else:
                self.narrator.success("No unusually large files found.")
                results.append(DiagnosticResult("Large Files", "ok", "None found"))
        except Exception as e:
            self.narrator.think(f"Could not scan for large files: {e}")
            results.append(DiagnosticResult("Large Files", "warning", str(e)))

        return results

    def apply_fix(self, result: DiagnosticResult) -> bool:
        if result.name == "Recycle Bin":
            if ask_permission("empty the Recycle Bin"):
                try:
                    subprocess.run(
                        ["powershell", "-Command",
                         "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
                        capture_output=True, timeout=30
                    )
                    self.narrator.success("Recycle Bin emptied.")
                    return True
                except Exception as e:
                    self.narrator.problem(f"Could not empty Recycle Bin: {e}")
        return False
