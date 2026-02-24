#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hardware Troubleshooting Diagnostic — Slow PC, overheating, disk space."""

import time
from typing import List

import psutil

from .base import BaseDiagnostic, DiagnosticResult, ask_permission


class HardwareDiagnostic(BaseDiagnostic):
    CATEGORY = "hardware"
    DESCRIPTION = "Hardware & Performance Troubleshooting"

    def diagnose(self) -> List[DiagnosticResult]:
        results = []
        total_steps = 6

        # Step 1: CPU usage
        self.narrator.step(1, total_steps, "Checking CPU usage")
        cpu = psutil.cpu_percent(interval=1.5)
        cpu_count = psutil.cpu_count()
        self.narrator.say(f"CPU usage: {cpu}% ({cpu_count} cores)")

        if cpu > 90:
            self.narrator.problem("CPU is very busy! This will make everything slow.")
            # Find top consumers
            top = []
            for proc in psutil.process_iter(["pid", "name", "cpu_percent"]):
                try:
                    top.append((proc.info["name"], proc.cpu_percent(interval=0)))
                except Exception:
                    continue
            time.sleep(0.5)
            top_final = []
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    top_final.append((proc.name(), proc.cpu_percent(interval=0)))
                except Exception:
                    continue
            top_final.sort(key=lambda x: x[1], reverse=True)
            for name, c in top_final[:3]:
                self.narrator.think(f"  {name}: {c:.0f}%")
            results.append(DiagnosticResult(
                "CPU Usage", "warning",
                f"{cpu}% (high)", fix_available=True
            ))
        elif cpu > 70:
            self.narrator.say("CPU is moderately busy. Should be fine for most tasks.")
            results.append(DiagnosticResult("CPU Usage", "ok", f"{cpu}%"))
        else:
            self.narrator.success(f"CPU usage is normal ({cpu}%).")
            results.append(DiagnosticResult("CPU Usage", "ok", f"{cpu}%"))

        # Step 2: Memory usage
        self.narrator.step(2, total_steps, "Checking memory (RAM)")
        mem = psutil.virtual_memory()
        mem_pct = mem.percent
        mem_used_gb = round(mem.used / (1024 ** 3), 1)
        mem_total_gb = round(mem.total / (1024 ** 3), 1)

        self.narrator.say(f"Memory: {mem_used_gb} GB used out of {mem_total_gb} GB ({mem_pct}%)")

        if mem_pct > 90:
            self.narrator.problem("Memory is almost full! This makes your computer very slow.")
            # Top memory users
            procs = []
            for proc in psutil.process_iter(["pid", "name", "memory_info"]):
                try:
                    m = proc.info["memory_info"]
                    procs.append((proc.info["name"], m.rss / (1024 ** 2)))
                except Exception:
                    continue
            procs.sort(key=lambda x: x[1], reverse=True)
            self.narrator.say("Programs using the most memory:")
            for name, mb in procs[:5]:
                self.narrator.think(f"  {name}: {mb:.0f} MB")
            results.append(DiagnosticResult(
                "Memory", "warning",
                f"{mem_pct}% used ({mem_used_gb}/{mem_total_gb} GB)", fix_available=True
            ))
        elif mem_pct > 75:
            self.narrator.say("Memory usage is moderate. Close some programs if things feel slow.")
            results.append(DiagnosticResult("Memory", "ok", f"{mem_pct}%"))
        else:
            self.narrator.success(f"Memory usage is healthy ({mem_pct}%).")
            results.append(DiagnosticResult("Memory", "ok", f"{mem_pct}%"))

        # Step 3: Disk space
        self.narrator.step(3, total_steps, "Checking disk space")
        try:
            partitions = psutil.disk_partitions()
            for part in partitions:
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    free_gb = round(usage.free / (1024 ** 3), 1)
                    total_gb = round(usage.total / (1024 ** 3), 1)
                    pct = usage.percent

                    self.narrator.say(f"Drive {part.device}: {free_gb} GB free of {total_gb} GB ({pct}% used)")

                    if free_gb < 5:
                        self.narrator.problem(f"Drive {part.device} is almost full!")
                        results.append(DiagnosticResult(
                            f"Disk {part.device}", "error",
                            f"Only {free_gb} GB free", fix_available=True
                        ))
                    elif free_gb < 20:
                        self.narrator.say(f"Drive {part.device} is getting full.")
                        results.append(DiagnosticResult(
                            f"Disk {part.device}", "warning",
                            f"{free_gb} GB free", fix_available=True
                        ))
                    else:
                        results.append(DiagnosticResult(f"Disk {part.device}", "ok", f"{free_gb} GB free"))
                except Exception:
                    continue
        except Exception as e:
            self.narrator.think(f"Could not check disk: {e}")
            results.append(DiagnosticResult("Disk Space", "warning", str(e)))

        # Step 4: Temperature (if available)
        self.narrator.step(4, total_steps, "Checking temperatures")
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    for entry in entries:
                        if entry.current > 80:
                            self.narrator.problem(f"{name}: {entry.current}C - Running hot!")
                            results.append(DiagnosticResult(
                                "Temperature", "warning",
                                f"{entry.current}C", fix_available=False
                            ))
                        else:
                            self.narrator.say(f"{name}: {entry.current}C")
                            results.append(DiagnosticResult(
                                "Temperature", "ok", f"{entry.current}C"
                            ))
            else:
                self.narrator.say("Temperature sensors not available on this system.")
                results.append(DiagnosticResult("Temperature", "ok", "Sensors not available"))
        except Exception:
            self.narrator.say("Temperature monitoring not supported.")
            results.append(DiagnosticResult("Temperature", "ok", "Not supported"))

        # Step 5: Battery (if laptop)
        self.narrator.step(5, total_steps, "Checking battery status")
        try:
            battery = psutil.sensors_battery()
            if battery:
                self.narrator.say(
                    f"Battery: {battery.percent}% "
                    f"({'Charging' if battery.power_plugged else 'On battery'})"
                )
                if battery.percent < 15 and not battery.power_plugged:
                    self.narrator.problem("Battery is very low! Plug in your charger.")
                    results.append(DiagnosticResult(
                        "Battery", "warning",
                        f"{battery.percent}% (low)", fix_available=False
                    ))
                else:
                    results.append(DiagnosticResult("Battery", "ok", f"{battery.percent}%"))
            else:
                self.narrator.say("No battery detected (desktop computer).")
                results.append(DiagnosticResult("Battery", "ok", "Desktop"))
        except Exception:
            results.append(DiagnosticResult("Battery", "ok", "Not available"))

        # Step 6: System uptime
        self.narrator.step(6, total_steps, "Checking system uptime")
        boot = psutil.boot_time()
        uptime_hours = round((time.time() - boot) / 3600, 1)

        if uptime_hours > 168:  # 7 days
            self.narrator.problem(f"Your computer has been running for {uptime_hours} hours ({uptime_hours/24:.0f} days).")
            self.narrator.tip("Restarting your computer can help with performance.")
            results.append(DiagnosticResult(
                "Uptime", "warning",
                f"{uptime_hours}h ({uptime_hours/24:.0f} days)", fix_available=False
            ))
        else:
            self.narrator.success(f"System uptime: {uptime_hours} hours.")
            results.append(DiagnosticResult("Uptime", "ok", f"{uptime_hours}h"))

        return results

    def apply_fix(self, result: DiagnosticResult) -> bool:
        if "CPU" in result.name and "high" in result.details:
            self.narrator.say("I can show you the top CPU-consuming programs, but for safety I won't force-close them.")
            self.narrator.tip("Open Task Manager (Ctrl+Shift+Esc) to end heavy processes.")
            return False
        if "Disk" in result.name:
            if ask_permission("run Windows Disk Cleanup to free space"):
                import subprocess
                try:
                    subprocess.Popen(["cleanmgr.exe"])
                    self.narrator.success("Disk Cleanup opened. Follow the prompts to free space.")
                    return True
                except Exception:
                    pass
        if "Memory" in result.name and "high" in result.details.lower():
            self.narrator.say("Here's a tip: close programs you're not using to free up memory.")
            self.narrator.tip("Right-click the taskbar and open Task Manager to see what's using memory.")
            return False
        return False
