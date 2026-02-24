#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Software Troubleshooting Diagnostic — App crashes, updates, startup issues."""

import subprocess
import os
from typing import List

import psutil

from .base import BaseDiagnostic, DiagnosticResult, ask_permission


class SoftwareDiagnostic(BaseDiagnostic):
    CATEGORY = "software"
    DESCRIPTION = "Software & Application Troubleshooting"

    def diagnose(self) -> List[DiagnosticResult]:
        results = []
        total_steps = 5

        # Step 1: Check for hung/not-responding processes
        self.narrator.step(1, total_steps, "Checking for frozen applications")
        hung = []
        for proc in psutil.process_iter(["pid", "name", "status"]):
            try:
                if proc.info["status"] == psutil.STATUS_STOPPED:
                    hung.append(proc.info["name"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if hung:
            self.narrator.problem(f"Found {len(hung)} frozen application(s): {', '.join(hung[:5])}")
            results.append(DiagnosticResult(
                "Frozen Apps", "warning",
                f"{len(hung)} frozen: {', '.join(hung[:5])}", fix_available=True
            ))
        else:
            self.narrator.success("No frozen applications detected.")
            results.append(DiagnosticResult("Frozen Apps", "ok", "None"))

        # Step 2: Check Windows Update status
        self.narrator.step(2, total_steps, "Checking Windows Update status")
        try:
            r = subprocess.run(
                ["powershell", "-Command",
                 "Get-Service wuauserv | Select-Object -ExpandProperty Status"],
                capture_output=True, text=True, timeout=15
            )
            status = r.stdout.strip()
            if "Running" in status:
                self.narrator.success("Windows Update service is running.")
                results.append(DiagnosticResult("Windows Update Service", "ok", "Running"))
            else:
                self.narrator.problem(f"Windows Update service status: {status}")
                results.append(DiagnosticResult(
                    "Windows Update Service", "warning",
                    f"Status: {status}", fix_available=True
                ))
        except Exception as e:
            self.narrator.think(f"Could not check Windows Update: {e}")
            results.append(DiagnosticResult("Windows Update Service", "warning", str(e)))

        # Step 3: Check startup programs
        self.narrator.step(3, total_steps, "Checking startup programs")
        try:
            r = subprocess.run(
                ["powershell", "-Command",
                 "Get-CimInstance Win32_StartupCommand | Select-Object Name, Command | ConvertTo-Json"],
                capture_output=True, text=True, timeout=15
            )
            import json
            try:
                startups = json.loads(r.stdout)
                if isinstance(startups, dict):
                    startups = [startups]
                count = len(startups) if startups else 0
                if count > 10:
                    self.narrator.problem(f"You have {count} startup programs. This can slow down boot time.")
                    for s in startups[:5]:
                        self.narrator.think(f"  - {s.get('Name', 'Unknown')}")
                    results.append(DiagnosticResult(
                        "Startup Programs", "warning",
                        f"{count} startup programs (high)", fix_available=False
                    ))
                    self.narrator.tip("Consider disabling unnecessary startup programs in Task Manager.")
                else:
                    self.narrator.success(f"{count} startup program(s) — reasonable.")
                    results.append(DiagnosticResult("Startup Programs", "ok", f"{count} programs"))
            except (json.JSONDecodeError, TypeError):
                results.append(DiagnosticResult("Startup Programs", "ok", "Could not parse"))
        except Exception as e:
            self.narrator.think(f"Could not check startups: {e}")
            results.append(DiagnosticResult("Startup Programs", "warning", str(e)))

        # Step 4: Check for pending reboots
        self.narrator.step(4, total_steps, "Checking if a reboot is needed")
        try:
            r = subprocess.run(
                ["powershell", "-Command",
                 "Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired'"],
                capture_output=True, text=True, timeout=10
            )
            if "True" in r.stdout:
                self.narrator.problem("Your computer needs a restart to finish installing updates.")
                results.append(DiagnosticResult(
                    "Pending Reboot", "warning",
                    "Reboot required for updates", fix_available=False
                ))
                self.narrator.tip("Save your work and restart when you have a chance.")
            else:
                self.narrator.success("No pending reboot required.")
                results.append(DiagnosticResult("Pending Reboot", "ok", "Not required"))
        except Exception as e:
            self.narrator.think(f"Could not check reboot status: {e}")
            results.append(DiagnosticResult("Pending Reboot", "warning", str(e)))

        # Step 5: Check temp files size
        self.narrator.step(5, total_steps, "Checking temporary files")
        try:
            temp_dir = os.environ.get("TEMP", os.path.join(os.environ["USERPROFILE"], "AppData", "Local", "Temp"))
            total_size = 0
            file_count = 0
            for dirpath, dirnames, filenames in os.walk(temp_dir):
                for f in filenames:
                    try:
                        fp = os.path.join(dirpath, f)
                        total_size += os.path.getsize(fp)
                        file_count += 1
                    except (OSError, PermissionError):
                        continue

            size_mb = round(total_size / (1024 * 1024), 1)
            if size_mb > 500:
                self.narrator.problem(f"Temporary files are using {size_mb} MB ({file_count} files).")
                self.narrator.say("Cleaning these up can free space and improve performance.")
                results.append(DiagnosticResult(
                    "Temp Files", "warning",
                    f"{size_mb} MB in temp files", fix_available=True
                ))
            else:
                self.narrator.success(f"Temp files: {size_mb} MB ({file_count} files) — reasonable.")
                results.append(DiagnosticResult("Temp Files", "ok", f"{size_mb} MB"))
        except Exception as e:
            self.narrator.think(f"Could not check temp files: {e}")
            results.append(DiagnosticResult("Temp Files", "warning", str(e)))

        return results

    def apply_fix(self, result: DiagnosticResult) -> bool:
        if result.name == "Frozen Apps":
            if ask_permission("close the frozen applications"):
                for proc in psutil.process_iter(["pid", "name", "status"]):
                    try:
                        if proc.info["status"] == psutil.STATUS_STOPPED:
                            proc.terminate()
                            self.narrator.say(f"Closed: {proc.info['name']}")
                    except Exception:
                        continue
                return True
        elif result.name == "Windows Update Service":
            if ask_permission("restart the Windows Update service"):
                try:
                    subprocess.run(["net", "stop", "wuauserv"], capture_output=True, timeout=15)
                    subprocess.run(["net", "start", "wuauserv"], capture_output=True, timeout=15)
                    return True
                except Exception:
                    pass
        elif result.name == "Temp Files":
            if ask_permission("clean up temporary files"):
                try:
                    subprocess.run(
                        ["powershell", "-Command", "Remove-Item $env:TEMP\\* -Recurse -Force -ErrorAction SilentlyContinue"],
                        capture_output=True, timeout=30
                    )
                    return True
                except Exception:
                    pass
        return False
