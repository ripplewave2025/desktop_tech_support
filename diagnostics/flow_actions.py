"""
Flow Actions — reusable diagnostic action functions for the flow engine.

Each function performs a single check and returns a dict with:
- success: bool
- status: str ("ok", "warning", "error")
- details: str (human-readable result)
- fix_available: bool
- Any additional fields used by flow conditions (e.g., download_mbps)
"""

import subprocess
import time
import logging
from typing import Dict, Any

import psutil

logger = logging.getLogger("zora.flow_actions")


def _ps(cmd: str, timeout: int = 15) -> str:
    """Run a PowerShell command and return stdout."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.stdout.strip()
    except Exception:
        return ""


# ─── Network Actions ───────────────────────────────────

def check_network_adapter() -> Dict[str, Any]:
    """Check if any network adapter is connected."""
    adapters = psutil.net_if_stats()
    active = [name for name, stats in adapters.items() if stats.isup]
    if active:
        return {
            "success": True,
            "status": "ok",
            "details": f"Active adapters: {', '.join(active[:3])}",
            "adapter_count": len(active),
        }
    return {
        "success": False,
        "status": "error",
        "details": "No active network adapters found",
        "fix_available": True,
        "adapter_count": 0,
    }


def check_dns_resolution() -> Dict[str, Any]:
    """Test DNS resolution by resolving google.com."""
    try:
        import socket
        ip = socket.gethostbyname("google.com")
        return {
            "success": True,
            "status": "ok",
            "details": f"DNS working — google.com resolved to {ip}",
        }
    except Exception as e:
        return {
            "success": False,
            "status": "error",
            "details": f"DNS resolution failed: {e}",
            "fix_available": True,
        }


def fix_dns() -> Dict[str, Any]:
    """Flush DNS cache."""
    output = _ps("ipconfig /flushdns")
    return {
        "success": "Successfully" in output,
        "status": "ok" if "Successfully" in output else "warning",
        "details": output or "DNS cache flushed",
        "fix_available": False,
    }


def measure_bandwidth() -> Dict[str, Any]:
    """Measure download/upload speed over 3 seconds."""
    before = psutil.net_io_counters()
    time.sleep(3)
    after = psutil.net_io_counters()

    download_mbps = round((after.bytes_recv - before.bytes_recv) * 8 / (3 * 1_000_000), 2)
    upload_mbps = round((after.bytes_sent - before.bytes_sent) * 8 / (3 * 1_000_000), 2)

    status = "ok" if download_mbps > 10 else ("warning" if download_mbps > 1 else "error")
    return {
        "success": download_mbps > 1,
        "status": status,
        "details": f"Download: {download_mbps} Mbps, Upload: {upload_mbps} Mbps",
        "download_mbps": download_mbps,
        "upload_mbps": upload_mbps,
    }


def check_wifi_signal() -> Dict[str, Any]:
    """Check WiFi signal strength."""
    output = _ps('(netsh wlan show interfaces) -Match "Signal"')
    if output:
        try:
            pct = int("".join(c for c in output if c.isdigit()))
            status = "ok" if pct > 60 else ("warning" if pct > 30 else "error")
            return {
                "success": pct > 30,
                "status": status,
                "details": f"WiFi signal strength: {pct}%",
                "signal_pct": pct,
                "fix_available": pct < 30,
            }
        except ValueError:
            pass
    return {
        "success": True,
        "status": "info",
        "details": "Could not determine WiFi signal (may be wired connection)",
        "signal_pct": 100,
    }


def check_background_usage() -> Dict[str, Any]:
    """Check for bandwidth-heavy background processes."""
    heavy_procs = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            conns = proc.net_connections()
            if len(conns) > 5:
                heavy_procs.append(proc.info["name"])
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue

    if heavy_procs:
        return {
            "success": False,
            "status": "warning",
            "details": f"High network usage: {', '.join(heavy_procs[:5])}",
            "fix_available": False,
        }
    return {
        "success": True,
        "status": "ok",
        "details": "No bandwidth-heavy background processes detected",
    }


def fix_adapter() -> Dict[str, Any]:
    """Reset network adapter."""
    _ps("ipconfig /release")
    time.sleep(2)
    output = _ps("ipconfig /renew")
    return {
        "success": "renewed" in output.lower() if output else False,
        "status": "ok",
        "details": "Network adapter reset (IP released and renewed)",
    }


def check_ping() -> Dict[str, Any]:
    """Ping 8.8.8.8 to test raw connectivity."""
    try:
        r = subprocess.run(
            ["ping", "-n", "3", "8.8.8.8"],
            capture_output=True, text=True, timeout=15,
        )
        lost = "0% loss" in r.stdout or "(0% loss)" in r.stdout
        if lost:
            # Extract average time
            return {
                "success": True,
                "status": "ok",
                "details": "Ping to 8.8.8.8: 0% loss",
            }
        return {
            "success": False,
            "status": "warning",
            "details": "Some packets lost pinging 8.8.8.8",
            "fix_available": True,
        }
    except Exception as e:
        return {
            "success": False,
            "status": "error",
            "details": f"Ping failed: {e}",
            "fix_available": True,
        }


# ─── Audio Actions ─────────────────────────────────────

def check_audio_service() -> Dict[str, Any]:
    """Check if Windows Audio service is running."""
    output = _ps('(Get-Service -Name "Audiosrv").Status')
    running = "running" in output.lower() if output else False
    return {
        "success": running,
        "status": "ok" if running else "error",
        "details": f"Windows Audio service: {'Running' if running else 'Stopped'}",
        "fix_available": not running,
    }


def fix_audio_service() -> Dict[str, Any]:
    """Restart Windows Audio service."""
    _ps("Restart-Service -Name Audiosrv -Force")
    _ps("Restart-Service -Name AudioEndpointBuilder -Force")
    time.sleep(2)
    return check_audio_service()


def check_audio_devices() -> Dict[str, Any]:
    """Check for audio output devices."""
    output = _ps('Get-CimInstance -ClassName Win32_SoundDevice | Select-Object -ExpandProperty Status')
    if output and "ok" in output.lower():
        return {
            "success": True,
            "status": "ok",
            "details": "Audio devices detected and working",
        }
    return {
        "success": False,
        "status": "error",
        "details": "No working audio devices found",
        "fix_available": True,
    }


def check_volume() -> Dict[str, Any]:
    """Check if system volume is muted or very low."""
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = interface.QueryInterface(IAudioEndpointVolume)
        muted = volume.GetMute()
        level = round(volume.GetMasterVolumeLevelScalar() * 100)

        if muted:
            return {"success": False, "status": "warning", "details": "System volume is MUTED", "fix_available": True}
        if level < 10:
            return {"success": False, "status": "warning", "details": f"Volume very low: {level}%", "fix_available": True}
        return {"success": True, "status": "ok", "details": f"Volume: {level}%"}
    except Exception:
        return {"success": True, "status": "info", "details": "Could not check volume (pycaw not available)"}


def fix_volume() -> Dict[str, Any]:
    """Unmute and set volume to 50%."""
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = interface.QueryInterface(IAudioEndpointVolume)
        volume.SetMute(0, None)
        volume.SetMasterVolumeLevelScalar(0.5, None)
        return {"success": True, "status": "ok", "details": "Volume set to 50% and unmuted"}
    except Exception as e:
        return {"success": False, "status": "error", "details": f"Could not adjust volume: {e}"}


# ─── Printer Actions ───────────────────────────────────

def check_spooler_service() -> Dict[str, Any]:
    """Check Print Spooler service."""
    output = _ps('(Get-Service -Name "Spooler").Status')
    running = "running" in output.lower() if output else False
    return {
        "success": running,
        "status": "ok" if running else "error",
        "details": f"Print Spooler: {'Running' if running else 'Stopped'}",
        "fix_available": not running,
    }


def fix_spooler() -> Dict[str, Any]:
    """Restart Print Spooler and clear queue."""
    _ps("Stop-Service -Name Spooler -Force")
    time.sleep(1)
    _ps('Remove-Item -Path "$env:SystemRoot\\System32\\spool\\PRINTERS\\*" -Force -ErrorAction SilentlyContinue')
    _ps("Start-Service -Name Spooler")
    time.sleep(2)
    return check_spooler_service()


def check_printers_installed() -> Dict[str, Any]:
    """Check installed printers."""
    output = _ps('Get-Printer | Select-Object -ExpandProperty Name')
    if output:
        printers = [p.strip() for p in output.split("\n") if p.strip()]
        return {
            "success": True,
            "status": "ok",
            "details": f"Printers found: {', '.join(printers[:5])}",
            "printer_count": len(printers),
        }
    return {
        "success": False,
        "status": "error",
        "details": "No printers installed",
        "fix_available": False,
    }


def check_print_queue() -> Dict[str, Any]:
    """Check for stuck print jobs."""
    output = _ps('Get-PrintJob -PrinterName * -ErrorAction SilentlyContinue | Measure-Object | Select-Object -ExpandProperty Count')
    try:
        count = int(output.strip()) if output.strip() else 0
    except ValueError:
        count = 0

    if count > 0:
        return {
            "success": False,
            "status": "warning",
            "details": f"{count} print job(s) in queue — may be stuck",
            "fix_available": True,
            "job_count": count,
        }
    return {"success": True, "status": "ok", "details": "Print queue is clear", "job_count": 0}


# ─── Performance Actions ───────────────────────────────

def check_cpu_usage() -> Dict[str, Any]:
    """Check current CPU usage."""
    cpu = psutil.cpu_percent(interval=1)
    status = "ok" if cpu < 80 else ("warning" if cpu < 95 else "error")
    return {
        "success": cpu < 90,
        "status": status,
        "details": f"CPU usage: {cpu}%",
        "cpu_percent": cpu,
    }


def check_memory_usage() -> Dict[str, Any]:
    """Check RAM usage."""
    mem = psutil.virtual_memory()
    free_gb = round((mem.total - mem.used) / (1024 ** 3), 1)
    status = "ok" if mem.percent < 85 else ("warning" if mem.percent < 95 else "error")
    return {
        "success": mem.percent < 90,
        "status": status,
        "details": f"RAM: {mem.percent}% used ({free_gb} GB free)",
        "memory_percent": mem.percent,
        "free_gb": free_gb,
    }


def check_disk_space() -> Dict[str, Any]:
    """Check C: drive free space."""
    disk = psutil.disk_usage("C:\\")
    free_gb = round(disk.free / (1024 ** 3), 1)
    status = "ok" if free_gb > 10 else ("warning" if free_gb > 2 else "error")
    return {
        "success": free_gb > 5,
        "status": status,
        "details": f"C: drive has {free_gb} GB free",
        "free_gb": free_gb,
        "fix_available": free_gb < 10,
    }


def check_startup_programs() -> Dict[str, Any]:
    """Check startup program count."""
    output = _ps('Get-CimInstance Win32_StartupCommand | Measure-Object | Select-Object -ExpandProperty Count')
    try:
        count = int(output.strip()) if output.strip() else 0
    except ValueError:
        count = 0

    status = "ok" if count < 10 else ("warning" if count < 20 else "error")
    return {
        "success": count < 15,
        "status": status,
        "details": f"{count} startup programs",
        "startup_count": count,
        "fix_available": count > 10,
    }


def check_temp_files() -> Dict[str, Any]:
    """Check temp folder size."""
    import os
    temp_dir = os.environ.get("TEMP", "")
    total_mb = 0
    try:
        for root, dirs, files in os.walk(temp_dir):
            for f in files:
                try:
                    total_mb += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        total_mb = round(total_mb / (1024 * 1024))
    except Exception:
        total_mb = 0

    status = "ok" if total_mb < 500 else ("warning" if total_mb < 2000 else "error")
    return {
        "success": total_mb < 1000,
        "status": status,
        "details": f"Temp files: {total_mb} MB",
        "temp_mb": total_mb,
        "fix_available": total_mb > 200,
    }


def fix_temp_files() -> Dict[str, Any]:
    """Clean temp files."""
    output = _ps('Remove-Item -Path "$env:TEMP\\*" -Recurse -Force -ErrorAction SilentlyContinue; "Cleaned"')
    return {
        "success": True,
        "status": "ok",
        "details": "Temp files cleaned",
    }


# ─── Action Registry ──────────────────────────────────

FLOW_ACTIONS = {
    # Network
    "check_network_adapter": check_network_adapter,
    "check_dns_resolution": check_dns_resolution,
    "fix_dns": fix_dns,
    "measure_bandwidth": measure_bandwidth,
    "check_wifi_signal": check_wifi_signal,
    "check_background_usage": check_background_usage,
    "fix_adapter": fix_adapter,
    "check_ping": check_ping,
    # Audio
    "check_audio_service": check_audio_service,
    "fix_audio_service": fix_audio_service,
    "check_audio_devices": check_audio_devices,
    "check_volume": check_volume,
    "fix_volume": fix_volume,
    # Printer
    "check_spooler_service": check_spooler_service,
    "fix_spooler": fix_spooler,
    "check_printers_installed": check_printers_installed,
    "check_print_queue": check_print_queue,
    # Performance
    "check_cpu_usage": check_cpu_usage,
    "check_memory_usage": check_memory_usage,
    "check_disk_space": check_disk_space,
    "check_startup_programs": check_startup_programs,
    "check_temp_files": check_temp_files,
    "fix_temp_files": fix_temp_files,
}
