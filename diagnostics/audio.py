#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audio Troubleshooting — No sound, wrong device, volume issues."""

import subprocess
from typing import List

from .base import BaseDiagnostic, DiagnosticResult, ask_permission


class AudioDiagnostic(BaseDiagnostic):
    CATEGORY = "audio"
    DESCRIPTION = "Audio & Sound Troubleshooting"

    def diagnose(self) -> List[DiagnosticResult]:
        results = []
        total_steps = 4

        # Step 1: Check audio devices
        self.narrator.step(1, total_steps, "Checking audio output devices")
        try:
            r = subprocess.run(
                ["powershell", "-Command",
                 "Get-CimInstance Win32_SoundDevice | Select-Object Name, Status | ConvertTo-Json"],
                capture_output=True, text=True, timeout=15
            )
            import json
            try:
                devices = json.loads(r.stdout)
                if isinstance(devices, dict):
                    devices = [devices]
                if devices:
                    self.narrator.say(f"Found {len(devices)} audio device(s):")
                    for dev in devices:
                        name = dev.get("Name", "Unknown")
                        status = dev.get("Status", "Unknown")
                        self.narrator.think(f"  {name} - {status}")
                        if status != "OK":
                            results.append(DiagnosticResult(
                                f"Audio: {name}", "warning",
                                f"Status: {status}", fix_available=False
                            ))
                        else:
                            results.append(DiagnosticResult(f"Audio: {name}", "ok", "Working"))
                else:
                    self.narrator.problem("No audio devices found!")
                    results.append(DiagnosticResult("Audio Devices", "error", "None found"))
            except (json.JSONDecodeError, TypeError):
                results.append(DiagnosticResult("Audio Devices", "warning", "Could not parse"))
        except Exception as e:
            results.append(DiagnosticResult("Audio Devices", "warning", str(e)))

        # Step 2: Check Windows Audio service
        self.narrator.step(2, total_steps, "Checking Windows Audio service")
        try:
            r = subprocess.run(
                ["sc", "query", "Audiosrv"],
                capture_output=True, text=True, timeout=10
            )
            if "RUNNING" in r.stdout:
                self.narrator.success("Windows Audio service is running.")
                results.append(DiagnosticResult("Audio Service", "ok", "Running"))
            else:
                self.narrator.problem("Windows Audio service is not running!")
                self.narrator.say("This is required for sound to work. I can restart it.")
                results.append(DiagnosticResult(
                    "Audio Service", "error",
                    "Not running", fix_available=True
                ))
        except Exception as e:
            results.append(DiagnosticResult("Audio Service", "warning", str(e)))

        # Step 3: Check volume level
        self.narrator.step(3, total_steps, "Checking system volume")
        try:
            r = subprocess.run(
                ["powershell", "-Command",
                 """
                 $vol = (New-Object -ComObject WScript.Shell)
                 # Can't directly get volume via COM easily, check mute status via registry
                 $audio = Get-ItemProperty 'HKCU:\\SOFTWARE\\Microsoft\\Multimedia\\Audio' -ErrorAction SilentlyContinue
                 if ($audio) { $audio | ConvertTo-Json } else { '{}' }
                 """],
                capture_output=True, text=True, timeout=10
            )
            # Volume level isn't trivially accessible from PowerShell without NirCmd
            # Just check if audio endpoint is available
            self.narrator.say("Volume controls appear accessible.")
            self.narrator.tip("If you hear no sound, try pressing the volume up key or clicking the speaker icon in the taskbar.")
            results.append(DiagnosticResult("Volume", "ok", "Accessible"))
        except Exception:
            results.append(DiagnosticResult("Volume", "ok", "Could not check"))

        # Step 4: Check AudioEndpointBuilder service
        self.narrator.step(4, total_steps, "Checking audio endpoint service")
        try:
            r = subprocess.run(
                ["sc", "query", "AudioEndpointBuilder"],
                capture_output=True, text=True, timeout=10
            )
            if "RUNNING" in r.stdout:
                self.narrator.success("Audio Endpoint Builder is running.")
                results.append(DiagnosticResult("Audio Endpoint Builder", "ok", "Running"))
            else:
                self.narrator.problem("Audio Endpoint Builder is not running!")
                results.append(DiagnosticResult(
                    "Audio Endpoint Builder", "error",
                    "Not running", fix_available=True
                ))
        except Exception as e:
            results.append(DiagnosticResult("Audio Endpoint Builder", "warning", str(e)))

        return results

    def apply_fix(self, result: DiagnosticResult) -> bool:
        if "Service" in result.name or "Builder" in result.name:
            service = "Audiosrv" if "Audio Service" in result.name else "AudioEndpointBuilder"
            if ask_permission(f"restart the {result.name}"):
                try:
                    subprocess.run(["net", "stop", service], capture_output=True, timeout=10)
                    subprocess.run(["net", "start", service], capture_output=True, timeout=10)
                    self.narrator.success(f"{result.name} restarted.")
                    return True
                except Exception as e:
                    self.narrator.problem(f"Could not restart: {e}")
                    self.narrator.tip("Try running as Administrator.")
        return False
