#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Internet / Network Troubleshooting Diagnostic."""

import subprocess
import time
from typing import List

import psutil

from .base import BaseDiagnostic, DiagnosticResult, ask_permission


class InternetDiagnostic(BaseDiagnostic):
    CATEGORY = "internet"
    DESCRIPTION = "Internet & Network Troubleshooting"

    def diagnose(self) -> List[DiagnosticResult]:
        results = []
        total_steps = 6

        # Step 1: Check network interfaces
        self.narrator.step(1, total_steps, "Checking network adapters")
        adapters = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        active = []
        for name, addresses in adapters.items():
            is_up = stats.get(name, None)
            if is_up and is_up.isup:
                active.append(name)
                for addr in addresses:
                    if addr.family.name == "AF_INET" and not addr.address.startswith("127."):
                        self.narrator.think(f"  {name}: {addr.address}")

        if active:
            self.narrator.say(f"Found {len(active)} active network adapter(s).")
            results.append(DiagnosticResult("Network Adapters", "ok", f"{len(active)} active"))
        else:
            self.narrator.problem("No active network adapters found!")
            results.append(DiagnosticResult(
                "Network Adapters", "error",
                "No active adapters", fix_available=True
            ))
            self.narrator.tip("Check if WiFi is enabled or Ethernet cable is connected.")

        # Step 2: DNS resolution
        self.narrator.step(2, total_steps, "Testing DNS resolution")
        try:
            import socket
            socket.setdefaulttimeout(5)
            ip = socket.gethostbyname("www.google.com")
            self.narrator.success(f"DNS working (google.com -> {ip})")
            results.append(DiagnosticResult("DNS Resolution", "ok", f"Resolved to {ip}"))
        except Exception:
            self.narrator.problem("Cannot resolve domain names. DNS might be broken.")
            results.append(DiagnosticResult(
                "DNS Resolution", "error",
                "DNS resolution failed", fix_available=True
            ))

        # Step 3: Ping test
        self.narrator.step(3, total_steps, "Testing connection to the internet")
        try:
            ping = subprocess.run(
                ["ping", "-n", "3", "-w", "2000", "8.8.8.8"],
                capture_output=True, text=True, timeout=15
            )
            if "Reply from" in ping.stdout:
                # Extract average time
                lines = ping.stdout.strip().split("\n")
                for line in lines:
                    if "Average" in line or "average" in line.lower():
                        self.narrator.say(f"Internet connection working. {line.strip()}")
                        break
                else:
                    self.narrator.success("Internet connection is working.")
                results.append(DiagnosticResult("Ping Test", "ok", "Connected"))
            else:
                self.narrator.problem("Cannot reach the internet.")
                results.append(DiagnosticResult(
                    "Ping Test", "error",
                    "No internet connectivity", fix_available=True
                ))
        except Exception as e:
            self.narrator.problem(f"Ping test failed: {e}")
            results.append(DiagnosticResult("Ping Test", "error", str(e), fix_available=True))

        # Step 4: Bandwidth measurement
        self.narrator.step(4, total_steps, "Measuring bandwidth usage")
        try:
            before = psutil.net_io_counters()
            time.sleep(2)
            after = psutil.net_io_counters()

            download_mbps = round((after.bytes_recv - before.bytes_recv) * 8 / (2 * 1_000_000), 2)
            upload_mbps = round((after.bytes_sent - before.bytes_sent) * 8 / (2 * 1_000_000), 2)

            self.narrator.say(f"Current bandwidth: {download_mbps} Mbps down, {upload_mbps} Mbps up")
            results.append(DiagnosticResult(
                "Bandwidth", "ok",
                f"Down: {download_mbps} Mbps, Up: {upload_mbps} Mbps"
            ))
        except Exception as e:
            self.narrator.think(f"Could not measure bandwidth: {e}")
            results.append(DiagnosticResult("Bandwidth", "warning", str(e)))

        # Step 5: Top bandwidth consumers
        self.narrator.step(5, total_steps, "Finding programs using the most internet")
        try:
            connections = psutil.net_connections(kind="inet")
            conn_by_proc = {}
            for conn in connections:
                if conn.pid and conn.status == "ESTABLISHED":
                    try:
                        name = psutil.Process(conn.pid).name()
                        conn_by_proc[name] = conn_by_proc.get(name, 0) + 1
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

            if conn_by_proc:
                sorted_procs = sorted(conn_by_proc.items(), key=lambda x: x[1], reverse=True)
                self.narrator.say("Programs with active internet connections:")
                for name, count in sorted_procs[:5]:
                    self.narrator.think(f"  {name}: {count} connection(s)")
                results.append(DiagnosticResult(
                    "Network Processes", "ok",
                    f"{len(conn_by_proc)} programs using network"
                ))
            else:
                self.narrator.say("No programs are actively using the internet right now.")
                results.append(DiagnosticResult("Network Processes", "ok", "No active connections"))
        except Exception as e:
            self.narrator.think(f"Could not check network processes: {e}")
            results.append(DiagnosticResult("Network Processes", "warning", str(e)))

        # Step 6: WiFi signal (Windows)
        self.narrator.step(6, total_steps, "Checking WiFi signal strength")
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, timeout=10
            )
            if "Signal" in result.stdout:
                for line in result.stdout.split("\n"):
                    if "Signal" in line:
                        signal = line.split(":")[1].strip()
                        self.narrator.say(f"WiFi signal strength: {signal}")
                        pct = int(signal.replace("%", ""))
                        if pct < 40:
                            self.narrator.problem("WiFi signal is weak!")
                            self.narrator.tip("Try moving closer to your WiFi router.")
                            results.append(DiagnosticResult(
                                "WiFi Signal", "warning",
                                f"Signal: {signal} (weak)", fix_available=False
                            ))
                        else:
                            results.append(DiagnosticResult("WiFi Signal", "ok", f"Signal: {signal}"))
                        break
            elif "not running" in result.stdout.lower() or not result.stdout.strip():
                self.narrator.say("No WiFi adapter detected. You might be using Ethernet.")
                results.append(DiagnosticResult("WiFi Signal", "ok", "WiFi not in use (Ethernet?)"))
            else:
                results.append(DiagnosticResult("WiFi Signal", "ok", "Could not determine"))
        except Exception as e:
            self.narrator.think(f"Could not check WiFi: {e}")
            results.append(DiagnosticResult("WiFi Signal", "warning", str(e)))

        return results

    def apply_fix(self, result: DiagnosticResult) -> bool:
        if result.name == "DNS Resolution" and "failed" in result.details:
            if ask_permission("flush the DNS cache to fix name resolution"):
                try:
                    subprocess.run(
                        ["ipconfig", "/flushdns"],
                        capture_output=True, timeout=10
                    )
                    self.narrator.success("DNS cache flushed.")
                    return True
                except Exception as e:
                    self.narrator.problem(f"Could not flush DNS: {e}")
        elif result.name == "Ping Test" and "No internet" in result.details:
            if ask_permission("reset the network adapter to restore connectivity"):
                try:
                    subprocess.run(
                        ["netsh", "winsock", "reset"],
                        capture_output=True, timeout=10
                    )
                    subprocess.run(
                        ["ipconfig", "/release"],
                        capture_output=True, timeout=10
                    )
                    subprocess.run(
                        ["ipconfig", "/renew"],
                        capture_output=True, timeout=15
                    )
                    self.narrator.success("Network adapter reset. Try connecting again.")
                    return True
                except Exception as e:
                    self.narrator.problem(f"Could not reset network: {e}")
        return False
