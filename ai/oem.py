"""
OEM profile and tool discovery helpers.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Dict, List

from .task_types import OEMProfile, OEMTool


class OEMService:
    OFFICIAL_URLS = {
        "dell": "https://www.dell.com/support/home/",
        "hp": "https://support.hp.com/",
        "lenovo": "https://support.lenovo.com/",
    }
    TOOL_CATALOG: Dict[str, List[Dict[str, object]]] = {
        "dell": [
            {
                "name": "SupportAssist",
                "executables": ["SupportAssist.exe"],
                "paths": [
                    r"C:\Program Files\Dell\SupportAssistAgent\bin\SupportAssist.exe",
                    r"C:\Program Files\Dell\SupportAssist\SupportAssist.exe",
                ],
                "automation_mode": "gui",
            },
            {
                "name": "Dell Command | Update",
                "executables": ["dcu-cli.exe", "DellCommandUpdate.exe"],
                "paths": [
                    r"C:\Program Files\Dell\CommandUpdate\dcu-cli.exe",
                    r"C:\Program Files (x86)\Dell\CommandUpdate\dcu-cli.exe",
                ],
                "automation_mode": "cli",
            },
        ],
        "hp": [
            {
                "name": "HP Support Assistant",
                "executables": ["HPSF.exe", "HP Support Assistant.exe"],
                "paths": [
                    r"C:\Program Files (x86)\HP\HP Support Framework\HPSF.exe",
                ],
                "automation_mode": "gui",
            },
            {
                "name": "HP Image Assistant",
                "executables": ["HPImageAssistant.exe"],
                "paths": [
                    r"C:\SWSetup\SP146156\HPImageAssistant.exe",
                    r"C:\Program Files\HP\HP Image Assistant\HPImageAssistant.exe",
                ],
                "automation_mode": "cli",
            },
        ],
        "lenovo": [
            {
                "name": "Lenovo Vantage",
                "executables": ["LenovoVantage.exe"],
                "paths": [
                    r"C:\Program Files\Lenovo\VantageService\LenovoVantage.exe",
                ],
                "automation_mode": "gui",
            },
            {
                "name": "Thin Installer",
                "executables": ["ThinInstaller.exe"],
                "paths": [
                    r"C:\Program Files (x86)\Lenovo\ThinInstaller\ThinInstaller.exe",
                    r"C:\Program Files\Lenovo\ThinInstaller\ThinInstaller.exe",
                ],
                "automation_mode": "cli",
            },
        ],
    }

    def detect_profile(self) -> OEMProfile:
        manufacturer = "Unknown"
        model = "Unknown"
        serial = ""
        bios_version = ""
        try:
            cmd = (
                "$system = Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model; "
                "$bios = Get-CimInstance Win32_BIOS | Select-Object SerialNumber,SMBIOSBIOSVersion; "
                "[pscustomobject]@{System=$system; Bios=$bios} | ConvertTo-Json -Compress"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=6,
            )
            if result.returncode == 0 and result.stdout:
                payload = json.loads(result.stdout.strip())
                system = payload.get("System", {}) or {}
                bios = payload.get("Bios", {}) or {}
                manufacturer = system.get("Manufacturer", manufacturer) or manufacturer
                model = system.get("Model", model) or model
                serial = bios.get("SerialNumber", serial) or serial
                bios_version = bios.get("SMBIOSBIOSVersion", bios_version) or bios_version
        except Exception:
            pass
        profile = OEMProfile(
            manufacturer=manufacturer,
            model=model,
            serial_number=serial,
            bios_version=bios_version,
        )
        profile.tools = self.discover_tools(profile)
        return profile

    def discover_tools(self, profile: OEMProfile) -> List[OEMTool]:
        vendor = profile.vendor_slug
        tools: List[OEMTool] = []
        for entry in self.TOOL_CATALOG.get(vendor, []):
            found_path = ""
            found_exec = ""
            for executable in entry["executables"]:
                resolved = shutil.which(executable)
                if resolved:
                    found_exec = executable
                    found_path = resolved
                    break
            if not found_path:
                for path in entry["paths"]:
                    if os.path.exists(path):
                        found_path = path
                        found_exec = os.path.basename(path)
                        break
            status = "installed" if found_path else "not_installed"
            tools.append(
                OEMTool(
                    vendor=vendor,
                    name=entry["name"],
                    status=status,
                    executable=found_exec,
                    path=found_path,
                    notes="Detected from known install path or PATH lookup" if found_path else "Official tool recommended",
                    official_url=self.OFFICIAL_URLS.get(vendor, ""),
                    automation_mode=str(entry["automation_mode"]),
                )
            )
        return tools
