"""
Remediation Library — structured collection of Windows fixes.

Each fix has:
- name: Human-readable description
- category: Grouping (network, audio, display, software, hardware, security, printer)
- risk: "low" (safe), "medium" (may disrupt), "high" (requires care)
- commands: List of PowerShell commands to execute
- verify: Command to verify the fix worked (optional)
- rollback: Command to undo (optional)
- requires_reboot: Whether a reboot is needed after
"""

REMEDIATION_LIBRARY = {
    # ─── Network (15 fixes) ─────────────────────────────
    "dns_flush": {
        "name": "Flush DNS Cache",
        "category": "network",
        "risk": "low",
        "commands": ["ipconfig /flushdns"],
        "verify": "nslookup google.com",
        "rollback": None,
        "requires_reboot": False,
    },
    "winsock_reset": {
        "name": "Reset Winsock Catalog",
        "category": "network",
        "risk": "medium",
        "commands": ["netsh winsock reset"],
        "verify": "ping 8.8.8.8 -n 1",
        "rollback": None,
        "requires_reboot": True,
    },
    "ip_renew": {
        "name": "Release and Renew IP Address",
        "category": "network",
        "risk": "low",
        "commands": ["ipconfig /release", "ipconfig /renew"],
        "verify": "ipconfig | findstr IPv4",
        "rollback": None,
        "requires_reboot": False,
    },
    "adapter_reset": {
        "name": "Disable and Re-enable Network Adapter",
        "category": "network",
        "risk": "medium",
        "commands": [
            'Get-NetAdapter | Where-Object {$_.Status -eq "Up"} | Disable-NetAdapter -Confirm:$false',
            "Start-Sleep 3",
            'Get-NetAdapter | Enable-NetAdapter -Confirm:$false',
        ],
        "verify": "Test-NetConnection -ComputerName google.com -Port 80",
        "rollback": "Get-NetAdapter | Enable-NetAdapter -Confirm:$false",
        "requires_reboot": False,
    },
    "proxy_clear": {
        "name": "Clear Proxy Settings",
        "category": "network",
        "risk": "low",
        "commands": [
            'Set-ItemProperty -Path "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings" -Name ProxyEnable -Value 0',
        ],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "hosts_file_check": {
        "name": "Check Hosts File for Suspicious Entries",
        "category": "network",
        "risk": "low",
        "commands": ["Get-Content $env:SystemRoot\\System32\\drivers\\etc\\hosts | Where-Object {$_ -notmatch '^#' -and $_ -ne ''}"],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "route_reset": {
        "name": "Reset TCP/IP Stack and Routes",
        "category": "network",
        "risk": "medium",
        "commands": ["netsh int ip reset"],
        "verify": "ping 8.8.8.8 -n 1",
        "rollback": None,
        "requires_reboot": True,
    },
    "arp_cache_clear": {
        "name": "Clear ARP Cache",
        "category": "network",
        "risk": "low",
        "commands": ["netsh interface ip delete arpcache"],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "bits_restart": {
        "name": "Restart BITS Service",
        "category": "network",
        "risk": "low",
        "commands": ["Restart-Service BITS -Force"],
        "verify": "(Get-Service BITS).Status",
        "rollback": None,
        "requires_reboot": False,
    },
    "network_discovery_toggle": {
        "name": "Enable Network Discovery",
        "category": "network",
        "risk": "low",
        "commands": ["netsh advfirewall firewall set rule group=\"Network Discovery\" new enable=Yes"],
        "verify": None,
        "rollback": "netsh advfirewall firewall set rule group=\"Network Discovery\" new enable=No",
        "requires_reboot": False,
    },
    "wifi_reconnect": {
        "name": "Disconnect and Reconnect WiFi",
        "category": "network",
        "risk": "low",
        "commands": ["netsh wlan disconnect", "Start-Sleep 3", "netsh wlan connect"],
        "verify": "netsh wlan show interfaces | findstr Signal",
        "rollback": None,
        "requires_reboot": False,
    },
    "firewall_rule_reset": {
        "name": "Reset Firewall Rules to Default",
        "category": "network",
        "risk": "high",
        "commands": ["netsh advfirewall reset"],
        "verify": "netsh advfirewall show allprofiles",
        "rollback": None,
        "requires_reboot": False,
    },
    "netsh_diag": {
        "name": "Run Network Diagnostics",
        "category": "network",
        "risk": "low",
        "commands": ["msdt.exe /id NetworkDiagnosticsWeb"],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "vpn_disconnect": {
        "name": "Disconnect VPN Connections",
        "category": "network",
        "risk": "low",
        "commands": ["rasdial /disconnect"],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "dns_set_google": {
        "name": "Set DNS to Google (8.8.8.8)",
        "category": "network",
        "risk": "medium",
        "commands": [
            'Get-NetAdapter | Where-Object {$_.Status -eq "Up"} | Set-DnsClientServerAddress -ServerAddresses ("8.8.8.8","8.8.4.4")',
        ],
        "verify": "nslookup google.com 8.8.8.8",
        "rollback": 'Get-NetAdapter | Set-DnsClientServerAddress -ResetServerAddresses',
        "requires_reboot": False,
    },

    # ─── Audio (8 fixes) ────────────────────────────────
    "audio_service_restart": {
        "name": "Restart Windows Audio Service",
        "category": "audio",
        "risk": "low",
        "commands": ["Restart-Service Audiosrv -Force"],
        "verify": "(Get-Service Audiosrv).Status",
        "rollback": None,
        "requires_reboot": False,
    },
    "audio_endpoint_restart": {
        "name": "Restart Audio Endpoint Builder",
        "category": "audio",
        "risk": "low",
        "commands": ["Restart-Service AudioEndpointBuilder -Force"],
        "verify": "(Get-Service AudioEndpointBuilder).Status",
        "rollback": None,
        "requires_reboot": False,
    },
    "audio_enhancement_disable": {
        "name": "Disable Audio Enhancements",
        "category": "audio",
        "risk": "low",
        "commands": ['Start-Process "ms-settings:sound"'],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "audio_sample_rate_reset": {
        "name": "Open Audio Properties (Reset Sample Rate)",
        "category": "audio",
        "risk": "low",
        "commands": ["mmsys.cpl"],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "audio_driver_rollback": {
        "name": "Open Device Manager for Audio Driver",
        "category": "audio",
        "risk": "medium",
        "commands": ["devmgmt.msc"],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "audio_spatial_toggle": {
        "name": "Open Spatial Sound Settings",
        "category": "audio",
        "risk": "low",
        "commands": ['Start-Process "ms-settings:sound"'],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "audio_default_device": {
        "name": "Open Sound Settings (Set Default Device)",
        "category": "audio",
        "risk": "low",
        "commands": ['Start-Process "ms-settings:sound"'],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "audio_unmute_all": {
        "name": "Unmute All Audio Sessions",
        "category": "audio",
        "risk": "low",
        "commands": ["sndvol.exe"],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },

    # ─── Display (6 fixes) ──────────────────────────────
    "display_resolution_reset": {
        "name": "Open Display Settings (Reset Resolution)",
        "category": "display",
        "risk": "low",
        "commands": ['Start-Process "ms-settings:display"'],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "display_dpi_reset": {
        "name": "Open Display Settings (Reset DPI/Scaling)",
        "category": "display",
        "risk": "low",
        "commands": ['Start-Process "ms-settings:display"'],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "display_driver_rollback": {
        "name": "Open Device Manager (Display Driver)",
        "category": "display",
        "risk": "medium",
        "commands": ["devmgmt.msc"],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "display_night_light": {
        "name": "Toggle Night Light",
        "category": "display",
        "risk": "low",
        "commands": ['Start-Process "ms-settings:nightlight"'],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "display_refresh_rate": {
        "name": "Open Advanced Display Settings",
        "category": "display",
        "risk": "low",
        "commands": ['Start-Process "ms-settings:display-advancedgraphics"'],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "display_detect_monitors": {
        "name": "Detect Connected Monitors",
        "category": "display",
        "risk": "low",
        "commands": ["Get-CimInstance -ClassName Win32_DesktopMonitor | Select-Object Name, ScreenWidth, ScreenHeight"],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },

    # ─── Software (8 fixes) ─────────────────────────────
    "wu_restart": {
        "name": "Restart Windows Update Service",
        "category": "software",
        "risk": "low",
        "commands": ["Restart-Service wuauserv -Force"],
        "verify": "(Get-Service wuauserv).Status",
        "rollback": None,
        "requires_reboot": False,
    },
    "sfc_scan": {
        "name": "System File Checker (SFC Scan)",
        "category": "software",
        "risk": "low",
        "commands": ["sfc /scannow"],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "dism_repair": {
        "name": "DISM Component Repair",
        "category": "software",
        "risk": "low",
        "commands": ["DISM /Online /Cleanup-Image /RestoreHealth"],
        "verify": None,
        "rollback": None,
        "requires_reboot": True,
    },
    "temp_cleanup": {
        "name": "Clean Temp Files",
        "category": "software",
        "risk": "low",
        "commands": ['Remove-Item -Path "$env:TEMP\\*" -Recurse -Force -ErrorAction SilentlyContinue'],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "prefetch_clear": {
        "name": "Clear Prefetch Cache",
        "category": "software",
        "risk": "low",
        "commands": ['Remove-Item -Path "$env:SystemRoot\\Prefetch\\*" -Force -ErrorAction SilentlyContinue'],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "store_cache_clear": {
        "name": "Clear Microsoft Store Cache",
        "category": "software",
        "risk": "low",
        "commands": ["wsreset.exe"],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "app_reset": {
        "name": "Open Apps & Features (Reset App)",
        "category": "software",
        "risk": "low",
        "commands": ['Start-Process "ms-settings:appsfeatures"'],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "startup_disable": {
        "name": "Open Task Manager (Disable Startup Apps)",
        "category": "software",
        "risk": "low",
        "commands": ["taskmgr /7"],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },

    # ─── Hardware (5 fixes) ─────────────────────────────
    "disk_cleanup": {
        "name": "Run Disk Cleanup",
        "category": "hardware",
        "risk": "low",
        "commands": ["cleanmgr /d C"],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "power_plan_balanced": {
        "name": "Set Power Plan to Balanced",
        "category": "hardware",
        "risk": "low",
        "commands": ["powercfg /setactive 381b4222-f694-41f0-9685-ff5bb260df2e"],
        "verify": "powercfg /getactivescheme",
        "rollback": None,
        "requires_reboot": False,
    },
    "power_plan_performance": {
        "name": "Set Power Plan to High Performance",
        "category": "hardware",
        "risk": "low",
        "commands": ["powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"],
        "verify": "powercfg /getactivescheme",
        "rollback": "powercfg /setactive 381b4222-f694-41f0-9685-ff5bb260df2e",
        "requires_reboot": False,
    },
    "battery_report": {
        "name": "Generate Battery Report",
        "category": "hardware",
        "risk": "low",
        "commands": ["powercfg /batteryreport /output $env:TEMP\\battery-report.html", "Start-Process $env:TEMP\\battery-report.html"],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "chkdsk_schedule": {
        "name": "Schedule Disk Check",
        "category": "hardware",
        "risk": "medium",
        "commands": ["chkdsk C: /f /r /x"],
        "verify": None,
        "rollback": None,
        "requires_reboot": True,
    },

    # ─── Security (5 fixes) ─────────────────────────────
    "defender_quick_scan": {
        "name": "Run Windows Defender Quick Scan",
        "category": "security",
        "risk": "low",
        "commands": ["Start-MpScan -ScanType QuickScan"],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "firewall_enable_all": {
        "name": "Enable Firewall on All Profiles",
        "category": "security",
        "risk": "low",
        "commands": ["Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled True"],
        "verify": "Get-NetFirewallProfile | Select-Object Name, Enabled",
        "rollback": None,
        "requires_reboot": False,
    },
    "uac_check": {
        "name": "Check UAC Status",
        "category": "security",
        "risk": "low",
        "commands": ['(Get-ItemProperty "HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System").EnableLUA'],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "hosts_audit": {
        "name": "Audit Hosts File",
        "category": "security",
        "risk": "low",
        "commands": ["Get-Content $env:SystemRoot\\System32\\drivers\\etc\\hosts"],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "credential_flush": {
        "name": "Clear Cached Credentials",
        "category": "security",
        "risk": "medium",
        "commands": ["cmdkey /list", "klist purge"],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },

    # ─── Printer (5 fixes) ──────────────────────────────
    "spooler_restart": {
        "name": "Restart Print Spooler",
        "category": "printer",
        "risk": "low",
        "commands": [
            "Stop-Service Spooler -Force",
            'Remove-Item "$env:SystemRoot\\System32\\spool\\PRINTERS\\*" -Force -ErrorAction SilentlyContinue',
            "Start-Service Spooler",
        ],
        "verify": "(Get-Service Spooler).Status",
        "rollback": None,
        "requires_reboot": False,
    },
    "printer_driver_clear": {
        "name": "Open Print Management",
        "category": "printer",
        "risk": "medium",
        "commands": ["printmanagement.msc"],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "printer_port_check": {
        "name": "List Printer Ports",
        "category": "printer",
        "risk": "low",
        "commands": ["Get-PrinterPort | Select-Object Name, PrinterHostAddress"],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "printer_test_page": {
        "name": "Print Test Page",
        "category": "printer",
        "risk": "low",
        "commands": ["rundll32 printui.dll,PrintUIEntry /k /n $env:PRINTER"],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
    "printer_set_default": {
        "name": "Open Printers Settings",
        "category": "printer",
        "risk": "low",
        "commands": ['Start-Process "ms-settings:printers"'],
        "verify": None,
        "rollback": None,
        "requires_reboot": False,
    },
}


def get_fixes_by_category(category: str) -> list:
    """Get all fixes for a specific category."""
    return [
        {"id": k, **v}
        for k, v in REMEDIATION_LIBRARY.items()
        if v["category"] == category
    ]


def get_fix(fix_id: str) -> dict:
    """Get a specific fix by ID."""
    fix = REMEDIATION_LIBRARY.get(fix_id)
    if fix:
        return {"id": fix_id, **fix}
    return None


def get_all_categories() -> list:
    """Get all unique categories."""
    return sorted(set(v["category"] for v in REMEDIATION_LIBRARY.values()))


def get_library_stats() -> dict:
    """Get statistics about the library."""
    cats = {}
    for v in REMEDIATION_LIBRARY.values():
        cats[v["category"]] = cats.get(v["category"], 0) + 1
    return {
        "total_fixes": len(REMEDIATION_LIBRARY),
        "categories": cats,
        "low_risk": sum(1 for v in REMEDIATION_LIBRARY.values() if v["risk"] == "low"),
        "medium_risk": sum(1 for v in REMEDIATION_LIBRARY.values() if v["risk"] == "medium"),
        "high_risk": sum(1 for v in REMEDIATION_LIBRARY.values() if v["risk"] == "high"),
    }
