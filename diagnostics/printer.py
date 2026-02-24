#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Printer Troubleshooting Diagnostic."""

import subprocess
from typing import List

from .base import BaseDiagnostic, DiagnosticResult, ask_permission


class PrinterDiagnostic(BaseDiagnostic):
    CATEGORY = "printer"
    DESCRIPTION = "Printer Troubleshooting"

    def diagnose(self) -> List[DiagnosticResult]:
        results = []
        total_steps = 5

        # Step 1: Check for installed printers
        self.narrator.step(1, total_steps, "Checking installed printers")
        try:
            import win32print
            printers = win32print.EnumPrinters(
                win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            )
            if printers:
                self.narrator.say(f"Found {len(printers)} printer(s):")
                for _, _, name, _ in printers:
                    self.narrator.think(f"  - {name}")
                results.append(DiagnosticResult(
                    "Installed Printers", "ok",
                    f"{len(printers)} printer(s) found"
                ))
            else:
                self.narrator.problem("No printers found on this computer.")
                results.append(DiagnosticResult(
                    "Installed Printers", "error",
                    "No printers detected", fix_available=False
                ))
                self.narrator.tip("Connect your printer via USB or add it through Settings > Devices > Printers.")
                return results
        except ImportError:
            self.narrator.problem("Cannot check printers (win32print not available).")
            results.append(DiagnosticResult("Installed Printers", "error", "win32print not available"))
            return results

        # Step 2: Check default printer
        self.narrator.step(2, total_steps, "Checking default printer")
        try:
            default = win32print.GetDefaultPrinter()
            self.narrator.say(f"Your default printer is: {default}")
            results.append(DiagnosticResult("Default Printer", "ok", default))
        except Exception:
            self.narrator.problem("No default printer is set.")
            results.append(DiagnosticResult(
                "Default Printer", "warning",
                "No default printer set", fix_available=True
            ))

        # Step 3: Check printer status
        self.narrator.step(3, total_steps, "Checking printer status")
        try:
            default = win32print.GetDefaultPrinter()
            handle = win32print.OpenPrinter(default)
            info = win32print.GetPrinter(handle, 2)
            status = info.get("Status", 0)
            win32print.ClosePrinter(handle)

            status_messages = {
                0: "Ready",
                1: "Paused",
                2: "Error",
                3: "Pending Deletion",
                4: "Paper Jam",
                5: "Paper Out",
                6: "Manual Feed",
                7: "Paper Problem",
                8: "Offline",
            }
            status_text = status_messages.get(status, f"Unknown ({status})")

            if status == 0:
                self.narrator.success(f"Printer status: {status_text}")
                results.append(DiagnosticResult("Printer Status", "ok", status_text))
            elif status == 8:
                self.narrator.problem("Your printer is offline.")
                self.narrator.say("This usually means Windows lost connection to the printer.")
                results.append(DiagnosticResult(
                    "Printer Status", "error",
                    "Printer is offline", fix_available=True
                ))
            else:
                self.narrator.problem(f"Printer issue: {status_text}")
                results.append(DiagnosticResult(
                    "Printer Status", "warning", status_text, fix_available=True
                ))
        except Exception as e:
            self.narrator.think(f"Could not check printer status: {e}")
            results.append(DiagnosticResult("Printer Status", "warning", str(e)))

        # Step 4: Check print queue
        self.narrator.step(4, total_steps, "Checking print queue")
        try:
            default = win32print.GetDefaultPrinter()
            handle = win32print.OpenPrinter(default)
            jobs = win32print.EnumJobs(handle, 0, 100, 1)
            win32print.ClosePrinter(handle)

            if jobs:
                self.narrator.problem(f"Found {len(jobs)} job(s) in the print queue.")
                if len(jobs) > 3:
                    self.narrator.say("The print queue might be clogged. I can clear it for you.")
                    results.append(DiagnosticResult(
                        "Print Queue", "warning",
                        f"{len(jobs)} jobs queued", fix_available=True
                    ))
                else:
                    results.append(DiagnosticResult("Print Queue", "ok", f"{len(jobs)} jobs"))
            else:
                self.narrator.success("Print queue is empty (no stuck jobs).")
                results.append(DiagnosticResult("Print Queue", "ok", "Queue clear"))
        except Exception as e:
            self.narrator.think(f"Could not check print queue: {e}")
            results.append(DiagnosticResult("Print Queue", "warning", str(e)))

        # Step 5: Check Print Spooler service
        self.narrator.step(5, total_steps, "Checking Print Spooler service")
        try:
            result = subprocess.run(
                ["sc", "query", "Spooler"],
                capture_output=True, text=True, timeout=10
            )
            if "RUNNING" in result.stdout:
                self.narrator.success("Print Spooler service is running.")
                results.append(DiagnosticResult("Print Spooler", "ok", "Running"))
            else:
                self.narrator.problem("Print Spooler service is not running.")
                self.narrator.say("This service is needed for printing. I can restart it.")
                results.append(DiagnosticResult(
                    "Print Spooler", "error",
                    "Service not running", fix_available=True
                ))
        except Exception as e:
            self.narrator.think(f"Could not check Print Spooler: {e}")
            results.append(DiagnosticResult("Print Spooler", "warning", str(e)))

        return results

    def apply_fix(self, result: DiagnosticResult) -> bool:
        if result.name == "Print Spooler" and "not running" in result.details:
            if ask_permission("restart the Print Spooler service"):
                try:
                    subprocess.run(["net", "stop", "spooler"], capture_output=True, timeout=10)
                    subprocess.run(["net", "start", "spooler"], capture_output=True, timeout=10)
                    self.narrator.success("Print Spooler restarted.")
                    return True
                except Exception as e:
                    self.narrator.problem(f"Could not restart spooler: {e}")
                    self.narrator.tip("Try running this program as Administrator.")
        elif result.name == "Print Queue" and "jobs" in result.details:
            if ask_permission("clear the print queue"):
                try:
                    subprocess.run(["net", "stop", "spooler"], capture_output=True, timeout=10)
                    import glob, os
                    spool_dir = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                                             "System32", "spool", "PRINTERS")
                    for f in glob.glob(os.path.join(spool_dir, "*")):
                        try:
                            os.remove(f)
                        except Exception:
                            pass
                    subprocess.run(["net", "start", "spooler"], capture_output=True, timeout=10)
                    self.narrator.success("Print queue cleared.")
                    return True
                except Exception as e:
                    self.narrator.problem(f"Could not clear queue: {e}")
        return False
