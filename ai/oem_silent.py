"""
OEM silent-mode CLI wrappers.

The point of this module: when a non-technical user says
"update my computer" or "fix my drivers", we should not pretend to be a
driver installer. The OEM already ships one — Dell Command Update, HP Image
Assistant, Lenovo Thin Installer — and IT departments use them in silent /
unattended mode every day. We just call them with the right flags.

Routing
-------
  detect()                       → vendor + tool path + model info
  scan_drivers(...)              → list available driver/BIOS updates
  apply_drivers(reboot=False)    → install pending updates (consent-gated)
  open_official_support()        → URL of vendor's support portal

For each vendor we use the documented silent-mode invocation:

  Dell    : dcu-cli.exe /scan -outputLog=...
            dcu-cli.exe /applyUpdates -reboot=disable -outputLog=...
  HP      : HPImageAssistant.exe /Operation:Analyze /Action:List   /Silent
            HPImageAssistant.exe /Operation:Analyze /Action:Install /Silent
  Lenovo  : ThinInstaller.exe /CM -search A -action LIST    -noicon ...
            ThinInstaller.exe /CM -search A -action INSTALL -noicon -noreboot ...

None of these install Bloatware on top — they only fetch drivers/firmware
from the vendor's catalog. That's the right primitive for a tech-support app.

The functions never autodetect-and-run; the orchestrator decides whether to
gate behind a consent prompt. `apply_drivers` is always considered a write.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .oem import OEMService


SUPPORT_URLS = {
    "dell": "https://www.dell.com/support/home/",
    "hp": "https://support.hp.com/",
    "lenovo": "https://support.lenovo.com/",
}


@dataclass
class OEMInvocation:
    """Description of a silent OEM invocation, suitable for previewing."""
    vendor: str
    tool: str               # human-readable, e.g. "Dell Command | Update"
    executable: str         # absolute path
    argv: List[str]         # arguments (does not include the executable)
    description: str        # plain-English line for the consent preview
    risk: str               # "read" | "write" | "dangerous"
    timeout: int = 1800
    log_path: Optional[str] = None  # populated when the invocation writes a log


def _log_path(tag: str) -> str:
    """Return a per-invocation log path under %LOCALAPPDATA%\\Zora\\oem-logs."""
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    folder = os.path.join(base, "Zora", "oem-logs")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{tag}.log")


@dataclass
class VendorContext:
    vendor: str             # "dell" | "hp" | "lenovo" | "generic"
    manufacturer: str
    model: str
    serial: str
    bios_version: str
    cli_tool_name: str = ""
    cli_tool_path: str = ""
    gui_tool_name: str = ""
    gui_tool_path: str = ""
    has_cli: bool = False
    has_gui: bool = False

    def to_dict(self) -> Dict[str, object]:
        return {
            "vendor": self.vendor, "manufacturer": self.manufacturer,
            "model": self.model, "serial": self.serial,
            "bios_version": self.bios_version,
            "cli_tool": self.cli_tool_name if self.has_cli else None,
            "gui_tool": self.gui_tool_name if self.has_gui else None,
            "support_url": SUPPORT_URLS.get(self.vendor, ""),
        }


def detect(svc: Optional[OEMService] = None) -> VendorContext:
    """Detect vendor + installed tooling. This is cheap to call repeatedly."""
    service = svc or OEMService()
    profile = service.detect_profile()
    ctx = VendorContext(
        vendor=profile.vendor_slug if hasattr(profile, "vendor_slug") else "generic",
        manufacturer=profile.manufacturer,
        model=profile.model,
        serial=getattr(profile, "serial_number", ""),
        bios_version=getattr(profile, "bios_version", ""),
    )
    for tool in profile.tools:
        if tool.status != "installed":
            continue
        if tool.automation_mode == "cli" and not ctx.has_cli:
            ctx.cli_tool_name = tool.name
            ctx.cli_tool_path = tool.path
            ctx.has_cli = True
        elif tool.automation_mode == "gui" and not ctx.has_gui:
            ctx.gui_tool_name = tool.name
            ctx.gui_tool_path = tool.path
            ctx.has_gui = True
    return ctx


# ──────────────────────────────────────────────────────────────────────
# Per-vendor invocation builders
# ──────────────────────────────────────────────────────────────────────

def _dell_scan(path: str) -> OEMInvocation:
    log = _log_path("dcu-scan")
    return OEMInvocation(
        vendor="dell", tool="Dell Command | Update", executable=path,
        argv=["/scan", f"-outputLog={log}"],
        description="Scan Dell catalog for pending driver, BIOS, and firmware updates.",
        risk="read", timeout=600, log_path=log,
    )


def _dell_apply(path: str, allow_reboot: bool) -> OEMInvocation:
    log = _log_path("dcu-apply")
    reboot_flag = "enable" if allow_reboot else "disable"
    return OEMInvocation(
        vendor="dell", tool="Dell Command | Update", executable=path,
        argv=["/applyUpdates", f"-reboot={reboot_flag}", f"-outputLog={log}"],
        description=(
            "Install all pending Dell-signed driver/BIOS/firmware updates "
            f"({'reboot allowed' if allow_reboot else 'no reboot'})."
        ),
        risk="write", timeout=3600, log_path=log,
    )


def _hp_scan(path: str) -> OEMInvocation:
    folder = os.path.dirname(_log_path("hpia-scan"))
    return OEMInvocation(
        vendor="hp", tool="HP Image Assistant", executable=path,
        argv=[
            "/Operation:Analyze", "/Action:List", "/Silent",
            "/Category:Drivers,BIOS,Firmware",
            f"/ReportFolder:{folder}",
            f"/SoftpaqDownloadFolder:{folder}",
        ],
        description="Scan HP catalog for pending driver, BIOS, and firmware updates.",
        risk="read", timeout=900, log_path=folder,
    )


def _hp_apply(path: str) -> OEMInvocation:
    folder = os.path.dirname(_log_path("hpia-apply"))
    return OEMInvocation(
        vendor="hp", tool="HP Image Assistant", executable=path,
        argv=[
            "/Operation:Analyze", "/Action:Install", "/Silent",
            "/Category:Drivers,BIOS,Firmware",
            f"/ReportFolder:{folder}",
            f"/SoftpaqDownloadFolder:{folder}",
        ],
        description="Download and install pending HP driver/BIOS/firmware updates.",
        risk="write", timeout=3600, log_path=folder,
    )


def _lenovo_scan(path: str) -> OEMInvocation:
    log = _log_path("thininstaller-scan")
    return OEMInvocation(
        vendor="lenovo", tool="Lenovo Thin Installer", executable=path,
        argv=["/CM", "-search", "A", "-action", "LIST",
              "-noicon", "-nolicense", "-log", log],
        description="Scan Lenovo catalog for pending driver, BIOS, and firmware updates.",
        risk="read", timeout=900, log_path=log,
    )


def _lenovo_apply(path: str, allow_reboot: bool) -> OEMInvocation:
    log = _log_path("thininstaller-apply")
    argv = ["/CM", "-search", "A", "-action", "INSTALL",
            "-includerebootpackages", "1,3", "-noicon", "-nolicense",
            "-log", log]
    if not allow_reboot:
        argv.append("-noreboot")
    return OEMInvocation(
        vendor="lenovo", tool="Lenovo Thin Installer", executable=path,
        argv=argv,
        description=(
            "Install all pending Lenovo-signed driver/BIOS/firmware updates "
            f"({'reboot allowed' if allow_reboot else 'no reboot'})."
        ),
        risk="write", timeout=3600, log_path=log,
    )


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def plan_scan(ctx: Optional[VendorContext] = None) -> Optional[OEMInvocation]:
    """Build (but do not run) the scan invocation for the current machine."""
    ctx = ctx or detect()
    if not ctx.has_cli:
        return None
    if ctx.vendor == "dell":
        return _dell_scan(ctx.cli_tool_path)
    if ctx.vendor == "hp":
        return _hp_scan(ctx.cli_tool_path)
    if ctx.vendor == "lenovo":
        return _lenovo_scan(ctx.cli_tool_path)
    return None


def plan_apply(ctx: Optional[VendorContext] = None,
               allow_reboot: bool = False) -> Optional[OEMInvocation]:
    """Build (but do not run) the apply invocation for the current machine."""
    ctx = ctx or detect()
    if not ctx.has_cli:
        return None
    if ctx.vendor == "dell":
        return _dell_apply(ctx.cli_tool_path, allow_reboot)
    if ctx.vendor == "hp":
        return _hp_apply(ctx.cli_tool_path)   # HPIA reboot policy via flags omitted for safety
    if ctx.vendor == "lenovo":
        return _lenovo_apply(ctx.cli_tool_path, allow_reboot)
    return None


def execute(inv: OEMInvocation) -> Dict[str, object]:
    """Run a planned OEM invocation. Returns a uniform result dict.

    Always uses shell=False with a fixed argv list — there's no way for the
    LLM-supplied parameters (vendor, allow_reboot) to inject shell metachars.
    """
    try:
        result = subprocess.run(
            [inv.executable, *inv.argv],
            capture_output=True, text=True,
            timeout=inv.timeout, shell=False,
        )
        return {
            "vendor": inv.vendor, "tool": inv.tool,
            "description": inv.description, "risk": inv.risk,
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": (result.stdout or "")[:8000],
            "stderr": (result.stderr or "")[:2000],
            "log_path": inv.log_path,
        }
    except subprocess.TimeoutExpired:
        return {
            "vendor": inv.vendor, "tool": inv.tool,
            "description": inv.description, "risk": inv.risk,
            "ok": False, "returncode": -1,
            "stdout": "", "stderr": f"OEM tool timed out after {inv.timeout}s",
            "log_path": inv.log_path,
        }
    except FileNotFoundError:
        return {
            "vendor": inv.vendor, "tool": inv.tool,
            "description": inv.description, "risk": inv.risk,
            "ok": False, "returncode": -2,
            "stdout": "",
            "stderr": (f"{inv.tool} is not installed at {inv.executable}. "
                       f"Install from {SUPPORT_URLS.get(inv.vendor, '')}"),
            "log_path": inv.log_path,
        }


def fallback_support_url(ctx: Optional[VendorContext] = None) -> str:
    """When no OEM tool is installed, return the right support portal URL."""
    ctx = ctx or detect()
    return SUPPORT_URLS.get(ctx.vendor, "https://support.microsoft.com/")


# ──────────────────────────────────────────────────────────────────────
# Warranty lookup
# ──────────────────────────────────────────────────────────────────────
#
# A real warranty API needs vendor credentials we don't ship. The
# pragmatic alternative is to build the *exact* support URL the vendor's
# own warranty page expects, with the user's service tag / serial number
# pre-filled. Clicking it lands them on the official "your warranty
# expires on …" page — same outcome, no scraping.

_WARRANTY_URL_TEMPLATES = {
    # Dell support page accepts the service tag in the URL path.
    "dell": "https://www.dell.com/support/home/en-us/product-support/servicetag/{serial}/overview",
    # HP support landing page; they auto-detect the serial from the URL.
    "hp": "https://support.hp.com/us-en/checkwarranty?seriallookup={serial}",
    # Lenovo's product-support deep link.
    "lenovo": "https://pcsupport.lenovo.com/products/{serial}",
}


def warranty_lookup_url(ctx: Optional[VendorContext] = None) -> Dict[str, Any]:
    """Return a vendor-specific warranty page URL with the serial pre-filled.

    Returns one of:
      * ``{"supported": True, "url": "...", "vendor": "dell", ...}``
      * ``{"supported": False, "reason": "...", "vendor": "..."}``

    The reason gives the AI something to tell the user — usually "I don't
    recognize this as a Dell/HP/Lenovo" or "I couldn't read your serial
    number from the BIOS."
    """
    ctx = ctx or detect()
    template = _WARRANTY_URL_TEMPLATES.get(ctx.vendor)
    if not template:
        return {
            "supported": False,
            "vendor": ctx.vendor,
            "reason": f"Warranty lookup not wired for vendor '{ctx.vendor}'.",
            "manufacturer": ctx.manufacturer,
        }
    if not ctx.serial:
        return {
            "supported": False,
            "vendor": ctx.vendor,
            "reason": "Could not read the service tag / serial number from BIOS.",
            "manufacturer": ctx.manufacturer,
            "fallback_url": SUPPORT_URLS.get(ctx.vendor, ""),
        }
    return {
        "supported": True,
        "vendor": ctx.vendor,
        "manufacturer": ctx.manufacturer,
        "model": ctx.model,
        "serial": ctx.serial,
        "url": template.format(serial=ctx.serial),
    }
