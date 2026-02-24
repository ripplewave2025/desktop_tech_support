#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Display Troubleshooting — Resolution, scaling, multi-monitor."""

import subprocess
from typing import List

from .base import BaseDiagnostic, DiagnosticResult, ask_permission


class DisplayDiagnostic(BaseDiagnostic):
    CATEGORY = "display"
    DESCRIPTION = "Display & Monitor Troubleshooting"

    def diagnose(self) -> List[DiagnosticResult]:
        results = []
        total_steps = 4

        # Step 1: Detect monitors
        self.narrator.step(1, total_steps, "Detecting monitors")
        try:
            import mss
            sct = mss.mss()
            monitors = sct.monitors
            # monitors[0] is the virtual screen (all combined)
            real_count = len(monitors) - 1

            self.narrator.say(f"Found {real_count} monitor(s):")
            for i, mon in enumerate(monitors[1:], 1):
                w, h = mon["width"], mon["height"]
                self.narrator.think(f"  Monitor {i}: {w}x{h} at position ({mon['left']}, {mon['top']})")
            results.append(DiagnosticResult("Monitors", "ok", f"{real_count} monitor(s)"))
        except Exception as e:
            self.narrator.problem(f"Could not detect monitors: {e}")
            results.append(DiagnosticResult("Monitors", "error", str(e)))

        # Step 2: Check display resolution
        self.narrator.step(2, total_steps, "Checking display resolution")
        try:
            import ctypes
            user32 = ctypes.windll.user32
            w = user32.GetSystemMetrics(0)
            h = user32.GetSystemMetrics(1)
            self.narrator.say(f"Primary display resolution: {w}x{h}")

            if w < 1920 or h < 1080:
                self.narrator.say("Your resolution is below Full HD. Things might look a bit large.")
                results.append(DiagnosticResult(
                    "Resolution", "warning",
                    f"{w}x{h} (below 1080p)", fix_available=False
                ))
                self.narrator.tip("You can change the resolution in Settings > Display.")
            else:
                self.narrator.success(f"Resolution is good ({w}x{h}).")
                results.append(DiagnosticResult("Resolution", "ok", f"{w}x{h}"))
        except Exception as e:
            results.append(DiagnosticResult("Resolution", "warning", str(e)))

        # Step 3: Check DPI scaling
        self.narrator.step(3, total_steps, "Checking display scaling")
        try:
            r = subprocess.run(
                ["powershell", "-Command",
                 "(Get-ItemProperty 'HKCU:\\Control Panel\\Desktop\\WindowMetrics' -Name AppliedDPI -ErrorAction SilentlyContinue).AppliedDPI"],
                capture_output=True, text=True, timeout=10
            )
            dpi = r.stdout.strip()
            if dpi:
                scale = round(int(dpi) / 96 * 100)
                self.narrator.say(f"Display scaling: {scale}%")
                if scale > 150:
                    self.narrator.say("High scaling might make some apps look blurry.")
                    results.append(DiagnosticResult(
                        "Display Scaling", "warning",
                        f"{scale}% (high)", fix_available=False
                    ))
                else:
                    results.append(DiagnosticResult("Display Scaling", "ok", f"{scale}%"))
            else:
                results.append(DiagnosticResult("Display Scaling", "ok", "Default (100%)"))
        except Exception as e:
            results.append(DiagnosticResult("Display Scaling", "warning", str(e)))

        # Step 4: Check graphics driver
        self.narrator.step(4, total_steps, "Checking graphics adapter")
        try:
            r = subprocess.run(
                ["powershell", "-Command",
                 "Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion, Status | ConvertTo-Json"],
                capture_output=True, text=True, timeout=15
            )
            import json
            try:
                gpus = json.loads(r.stdout)
                if isinstance(gpus, dict):
                    gpus = [gpus]
                for gpu in gpus:
                    name = gpu.get("Name", "Unknown")
                    driver = gpu.get("DriverVersion", "Unknown")
                    status = gpu.get("Status", "Unknown")
                    self.narrator.say(f"Graphics: {name}")
                    self.narrator.think(f"  Driver: {driver}, Status: {status}")

                    if status != "OK":
                        results.append(DiagnosticResult(
                            "Graphics Adapter", "warning",
                            f"{name} - Status: {status}", fix_available=False
                        ))
                    else:
                        results.append(DiagnosticResult("Graphics Adapter", "ok", name))
            except (json.JSONDecodeError, TypeError):
                results.append(DiagnosticResult("Graphics Adapter", "ok", "Could not parse"))
        except Exception as e:
            results.append(DiagnosticResult("Graphics Adapter", "warning", str(e)))

        return results
