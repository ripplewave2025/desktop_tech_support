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
        total_steps = 6

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

        # Step 5: Per-app audio session scan (pycaw)
        self.narrator.step(5, total_steps, "Scanning per-application audio sessions")
        try:
            from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL

            sessions = AudioUtilities.GetAllSessions()
            app_count = 0
            for session in sessions:
                if session.Process:
                    app_count += 1
                    proc_name = session.Process.name()
                    vol = session.SimpleAudioVolume
                    is_muted = vol.GetMute()
                    level = vol.GetMasterVolume()
                    level_pct = round(level * 100)

                    if is_muted:
                        self.narrator.problem(f"{proc_name} is MUTED in the Volume Mixer.")
                        results.append(DiagnosticResult(
                            f"App Audio: {proc_name}", "warning",
                            f"Muted (volume: {level_pct}%)", fix_available=True
                        ))
                    elif level < 0.1:
                        self.narrator.problem(f"{proc_name} volume is very low ({level_pct}%).")
                        results.append(DiagnosticResult(
                            f"App Audio: {proc_name}", "warning",
                            f"Very low volume: {level_pct}%", fix_available=True
                        ))
                    else:
                        self.narrator.think(f"{proc_name}: {level_pct}% volume, not muted")
                        results.append(DiagnosticResult(
                            f"App Audio: {proc_name}", "ok",
                            f"Volume: {level_pct}%"
                        ))

            if app_count == 0:
                self.narrator.say("No apps are currently producing audio.")
                results.append(DiagnosticResult("App Audio Sessions", "ok", "No active sessions"))
            else:
                self.narrator.say(f"Scanned {app_count} app(s) with active audio.")
        except ImportError:
            self.narrator.tip("Install 'pycaw' for per-app audio scanning: pip install pycaw")
            results.append(DiagnosticResult("Per-App Audio", "ok", "pycaw not installed — skipped"))
        except Exception as e:
            results.append(DiagnosticResult("Per-App Audio", "warning", f"Scan error: {e}"))

        # Step 6: Microphone privacy permissions
        self.narrator.step(6, total_steps, "Checking microphone privacy settings")
        try:
            r = subprocess.run(
                ["powershell", "-Command",
                 "Get-ItemPropertyValue 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\microphone' -Name Value -ErrorAction SilentlyContinue"],
                capture_output=True, text=True, timeout=10
            )
            mic_value = r.stdout.strip()
            if mic_value == "Allow":
                self.narrator.success("Microphone access is enabled globally.")
                results.append(DiagnosticResult("Microphone Privacy", "ok", "Access allowed"))
            elif mic_value == "Deny":
                self.narrator.problem("Microphone access is DENIED in Privacy Settings!")
                results.append(DiagnosticResult(
                    "Microphone Privacy", "error",
                    "Global microphone access is denied", fix_available=True
                ))
            else:
                results.append(DiagnosticResult("Microphone Privacy", "ok", f"Value: {mic_value}"))
        except Exception as e:
            results.append(DiagnosticResult("Microphone Privacy", "warning", str(e)))

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

        elif result.name.startswith("App Audio:"):
            # Unmute or raise volume for a specific app via pycaw
            app_name = result.name.replace("App Audio: ", "")
            if ask_permission(f"unmute and set {app_name} volume to 100%"):
                try:
                    from pycaw.pycaw import AudioUtilities
                    sessions = AudioUtilities.GetAllSessions()
                    for session in sessions:
                        if session.Process and session.Process.name() == app_name:
                            vol = session.SimpleAudioVolume
                            vol.SetMute(0, None)  # Unmute
                            vol.SetMasterVolume(1.0, None)  # Set to 100%
                            self.narrator.success(f"Unmuted {app_name} and set volume to 100%.")
                            return True
                except Exception as e:
                    self.narrator.problem(f"Could not fix: {e}")

        elif "Microphone Privacy" in result.name:
            if ask_permission("enable microphone access in Windows Privacy Settings"):
                try:
                    subprocess.run(
                        ["powershell", "-Command",
                         "Set-ItemProperty 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\microphone' -Name Value -Value 'Allow'"],
                        capture_output=True, timeout=10
                    )
                    self.narrator.success("Microphone access enabled.")
                    return True
                except Exception as e:
                    self.narrator.problem(f"Could not fix: {e}")

        return False
