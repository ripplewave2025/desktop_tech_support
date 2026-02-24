#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Security Troubleshooting — Windows Defender, firewall, suspicious processes."""

import subprocess
from typing import List

import psutil

from .base import BaseDiagnostic, DiagnosticResult, ask_permission


class SecurityDiagnostic(BaseDiagnostic):
    CATEGORY = "security"
    DESCRIPTION = "Security & Protection Troubleshooting"

    # Known suspicious process names (simplified list)
    SUSPICIOUS_NAMES = [
        "cryptominer", "miner.exe", "xmrig", "ccminer",
        "backdoor", "trojan", "keylogger", "ratclient",
    ]

    # Known high-port services that might be suspicious
    SUSPICIOUS_PORTS = [4444, 5555, 31337, 12345, 65535]

    def diagnose(self) -> List[DiagnosticResult]:
        results = []
        total_steps = 5

        # Step 1: Check Windows Defender status
        self.narrator.step(1, total_steps, "Checking antivirus protection")
        try:
            r = subprocess.run(
                ["powershell", "-Command",
                 "Get-MpComputerStatus | Select-Object AntivirusEnabled, RealTimeProtectionEnabled, AntivirusSignatureLastUpdated | ConvertTo-Json"],
                capture_output=True, text=True, timeout=20
            )
            import json
            try:
                status = json.loads(r.stdout)
                av_enabled = status.get("AntivirusEnabled", False)
                rtp = status.get("RealTimeProtectionEnabled", False)
                last_update = status.get("AntivirusSignatureLastUpdated", "Unknown")

                if av_enabled and rtp:
                    self.narrator.success("Windows Defender is active with real-time protection.")
                    self.narrator.think(f"  Last signature update: {last_update}")
                    results.append(DiagnosticResult("Antivirus", "ok", "Defender active"))
                elif av_enabled and not rtp:
                    self.narrator.problem("Windows Defender is installed but real-time protection is OFF.")
                    results.append(DiagnosticResult(
                        "Antivirus", "warning",
                        "Real-time protection disabled", fix_available=True
                    ))
                else:
                    self.narrator.problem("Antivirus does not appear to be active!")
                    results.append(DiagnosticResult(
                        "Antivirus", "error",
                        "Antivirus disabled", fix_available=True
                    ))
            except (json.JSONDecodeError, TypeError):
                self.narrator.say("Could not determine Defender status.")
                results.append(DiagnosticResult("Antivirus", "warning", "Status unknown"))
        except Exception as e:
            results.append(DiagnosticResult("Antivirus", "warning", str(e)))

        # Step 2: Check Windows Firewall
        self.narrator.step(2, total_steps, "Checking firewall protection")
        try:
            r = subprocess.run(
                ["netsh", "advfirewall", "show", "allprofiles", "state"],
                capture_output=True, text=True, timeout=10
            )
            profiles_on = r.stdout.count("ON")
            profiles_off = r.stdout.count("OFF")

            if profiles_off == 0:
                self.narrator.success("Windows Firewall is enabled on all profiles.")
                results.append(DiagnosticResult("Firewall", "ok", "All profiles ON"))
            else:
                self.narrator.problem(f"Firewall is disabled on {profiles_off} profile(s)!")
                results.append(DiagnosticResult(
                    "Firewall", "warning",
                    f"{profiles_off} profile(s) OFF", fix_available=True
                ))
        except Exception as e:
            results.append(DiagnosticResult("Firewall", "warning", str(e)))

        # Step 3: Check for suspicious processes
        self.narrator.step(3, total_steps, "Scanning for suspicious processes")
        suspicious = []
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                name = proc.info["name"].lower()
                if any(s in name for s in self.SUSPICIOUS_NAMES):
                    suspicious.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if suspicious:
            self.narrator.problem(f"Found {len(suspicious)} potentially suspicious process(es)!")
            for s in suspicious:
                self.narrator.think(f"  {s['name']} (PID: {s['pid']})")
            results.append(DiagnosticResult(
                "Suspicious Processes", "error",
                f"{len(suspicious)} suspicious process(es)", fix_available=True
            ))
        else:
            self.narrator.success("No obviously suspicious processes detected.")
            results.append(DiagnosticResult("Suspicious Processes", "ok", "None found"))

        # Step 4: Check for listening ports
        self.narrator.step(4, total_steps, "Checking network ports")
        try:
            suspicious_listeners = []
            for conn in psutil.net_connections(kind="inet"):
                if conn.status == "LISTEN" and conn.laddr:
                    port = conn.laddr.port
                    if port in self.SUSPICIOUS_PORTS:
                        proc_name = ""
                        try:
                            proc_name = psutil.Process(conn.pid).name() if conn.pid else "Unknown"
                        except Exception:
                            proc_name = f"PID:{conn.pid}"
                        suspicious_listeners.append((port, proc_name))

            if suspicious_listeners:
                self.narrator.problem("Found processes listening on suspicious ports:")
                for port, name in suspicious_listeners:
                    self.narrator.think(f"  Port {port}: {name}")
                results.append(DiagnosticResult(
                    "Suspicious Ports", "warning",
                    f"{len(suspicious_listeners)} suspicious listeners", fix_available=False
                ))
            else:
                self.narrator.success("No suspicious listening ports detected.")
                results.append(DiagnosticResult("Suspicious Ports", "ok", "All clear"))
        except Exception as e:
            results.append(DiagnosticResult("Suspicious Ports", "warning", str(e)))

        # Step 5: Check User Account Control (UAC)
        self.narrator.step(5, total_steps, "Checking User Account Control")
        try:
            r = subprocess.run(
                ["powershell", "-Command",
                 "(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System' -Name EnableLUA).EnableLUA"],
                capture_output=True, text=True, timeout=10
            )
            uac = r.stdout.strip()
            if uac == "1":
                self.narrator.success("User Account Control (UAC) is enabled.")
                results.append(DiagnosticResult("UAC", "ok", "Enabled"))
            else:
                self.narrator.problem("User Account Control (UAC) is disabled!")
                self.narrator.say("UAC helps protect your computer from unauthorized changes.")
                results.append(DiagnosticResult(
                    "UAC", "warning",
                    "Disabled", fix_available=False
                ))
        except Exception as e:
            results.append(DiagnosticResult("UAC", "warning", str(e)))

        return results

    def apply_fix(self, result: DiagnosticResult) -> bool:
        if result.name == "Antivirus":
            if ask_permission("open Windows Security settings so you can review your protection"):
                try:
                    subprocess.Popen(["start", "windowsdefender:"], shell=True)
                    self.narrator.success("Windows Security opened.")
                    return True
                except Exception:
                    pass
        elif result.name == "Firewall":
            if ask_permission("enable Windows Firewall on all profiles"):
                try:
                    subprocess.run(
                        ["netsh", "advfirewall", "set", "allprofiles", "state", "on"],
                        capture_output=True, timeout=10
                    )
                    self.narrator.success("Firewall enabled on all profiles.")
                    return True
                except Exception as e:
                    self.narrator.problem(f"Could not enable firewall: {e}")
        elif result.name == "Suspicious Processes":
            self.narrator.say("For safety, I recommend running a full Windows Defender scan.")
            if ask_permission("start a quick Windows Defender scan"):
                try:
                    subprocess.Popen(
                        ["powershell", "-Command", "Start-MpScan -ScanType QuickScan"],
                    )
                    self.narrator.success("Quick scan started. This may take a few minutes.")
                    return True
                except Exception:
                    pass
        return False
