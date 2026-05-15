"""
Safe Operations Catalog — the replacement for free-form PowerShell execution.

Why this module exists
----------------------
The previous design let the LLM author raw PowerShell strings and validated
them by allowlisting the first token. That's bypassable in at least four ways
(pipes, semicolons, encoded commands, subexpression eval). Bad model output —
or a prompt-injected page summary — could pivot a tech-support session into
arbitrary code execution.

This module fixes that by inverting the trust model:

  * The LLM picks an **operation ID** from a finite catalog ("net.flush_dns",
    "service.restart", "defender.scan_quick", ...).
  * The LLM provides **parameters** as a dict.
  * Server-side code validates the params, then builds the exact `argv` list
    for `subprocess.run(..., shell=False)`. The model never sees a shell.

Even if a parameter contains `; rm -rf /`, it lands as a single quoted argument
to a fixed cmdlet — there is no shell to interpret it.

Three risk tiers
----------------
  read        Observable, no system change. No consent gate.
  write       Reversible state change. Consent gate.
  dangerous   Irreversible / affects security or boot. Hard gate.

Uniform result shape
--------------------
  {
    "op": "net.flush_dns",
    "ok": True/False,
    "summary": "Cleared the DNS resolver cache.",
    "stdout": "...",
    "stderr": "...",
    "returncode": 0,
    "risk": "write",
  }
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

# ──────────────────────────────────────────────────────────────────────
# Parameter validators
# ──────────────────────────────────────────────────────────────────────

# Service names, interface aliases, hostnames — strict character classes,
# never trust the LLM's claim about what's "safe".
_SERVICE_NAME_RE = re.compile(r"^[A-Za-z0-9_\-\.\$ ]{1,64}$")
_INTERFACE_RE = re.compile(r"^[A-Za-z0-9 _\-\(\)\.]{1,64}$")
_HOSTNAME_RE = re.compile(
    # RFC-ish hostnames OR IPv4 OR IPv6 (loose; subprocess won't expand it)
    r"^[A-Za-z0-9][A-Za-z0-9\.\-:]{0,253}$"
)
_IPV4_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")
_PATH_SAFE_RE = re.compile(r"^[A-Za-z]:[\\/][A-Za-z0-9 _\-\\/\.\(\)]{0,255}$")


def _v_service(name: str) -> str:
    if not isinstance(name, str) or not _SERVICE_NAME_RE.match(name):
        raise ValueError(f"Invalid service name: {name!r}")
    return name


def _v_interface(name: str) -> str:
    if not isinstance(name, str) or not _INTERFACE_RE.match(name):
        raise ValueError(f"Invalid interface name: {name!r}")
    return name


def _v_hostname(name: str) -> str:
    if not isinstance(name, str) or not _HOSTNAME_RE.match(name):
        raise ValueError(f"Invalid hostname: {name!r}")
    return name


def _v_ipv4_list(value: Any) -> List[str]:
    if isinstance(value, str):
        value = [s.strip() for s in value.split(",") if s.strip()]
    if not isinstance(value, list) or not 1 <= len(value) <= 4:
        raise ValueError(f"Expected list of 1-4 IPv4 addresses, got {value!r}")
    for ip in value:
        if not _IPV4_RE.match(ip):
            raise ValueError(f"Invalid IPv4 address: {ip!r}")
    return value


def _v_int_range(lo: int, hi: int) -> Callable[[Any], int]:
    def _check(value: Any) -> int:
        try:
            n = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"Expected integer in [{lo}, {hi}], got {value!r}")
        if not lo <= n <= hi:
            raise ValueError(f"Integer {n} out of range [{lo}, {hi}]")
        return n
    return _check


def _v_path_writable(path: str) -> str:
    if not isinstance(path, str) or not _PATH_SAFE_RE.match(path):
        raise ValueError(f"Invalid Windows path: {path!r}")
    return path


# ──────────────────────────────────────────────────────────────────────
# Operation catalog
# ──────────────────────────────────────────────────────────────────────

@dataclass
class Param:
    name: str
    type_: str          # "string" | "int" | "list" | "path"
    description: str
    validator: Optional[Callable[[Any], Any]] = None
    required: bool = True
    default: Any = None


@dataclass
class Operation:
    op_id: str
    summary: str                 # what it does, plain English
    risk: str                    # "read" | "write" | "dangerous"
    params: List[Param] = field(default_factory=list)
    # builder receives validated params dict; returns the argv list to exec
    build: Callable[[Dict[str, Any]], List[str]] = None  # type: ignore
    timeout: int = 30
    needs_admin: bool = False


# Powershell launcher — fixed and never built from user input
_PS = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command"]


def _ps(script: str) -> List[str]:
    """Wrap a PowerShell script literal in the fixed launcher.

    The script is a server-side constant; it MUST NOT contain any LLM-supplied
    text without going through subprocess-level argument substitution.
    """
    return _PS + [script]


# Operations live in a registry keyed by op_id. New ops are easy to add — just
# define the builder and append below.
_OPERATIONS: Dict[str, Operation] = {}


def _register(op: Operation) -> None:
    if op.op_id in _OPERATIONS:
        raise RuntimeError(f"Duplicate operation: {op.op_id}")
    _OPERATIONS[op.op_id] = op


# ── Network ──────────────────────────────────────────────────────────

_register(Operation(
    op_id="net.show_config",
    summary="Show network adapter configuration (ipconfig /all).",
    risk="read",
    build=lambda _: ["ipconfig", "/all"],
))

_register(Operation(
    op_id="net.flush_dns",
    summary="Clear the DNS resolver cache. Often fixes 'site not found' errors.",
    risk="write",
    build=lambda _: ["ipconfig", "/flushdns"],
))

_register(Operation(
    op_id="net.show_dns",
    summary="List the DNS servers configured on each network adapter.",
    risk="read",
    build=lambda _: _ps("Get-DnsClientServerAddress | Format-Table -AutoSize"),
))

_register(Operation(
    op_id="net.set_dns",
    summary="Set DNS servers for a specific network adapter.",
    risk="write",
    params=[
        Param("interface", "string", "Adapter name, e.g., 'Wi-Fi' or 'Ethernet'", _v_interface),
        Param("servers", "list", "1-4 IPv4 addresses", _v_ipv4_list),
    ],
    build=lambda p: _ps(
        # Use the PowerShell parameter binder — argv-level, not string-interpolated.
        # Servers are passed as a positional list, no shell parsing involved.
        "Set-DnsClientServerAddress -InterfaceAlias $args[0] -ServerAddresses $args[1..($args.Length-1)]"
    ) + [p["interface"]] + p["servers"],
))

_register(Operation(
    op_id="net.test_connection",
    summary="Test if a host is reachable and time it.",
    risk="read",
    params=[Param("host", "string", "Hostname or IP", _v_hostname)],
    # Test-NetConnection accepts -ComputerName as a typed arg; pass via $args.
    build=lambda p: _ps(
        "Test-NetConnection -ComputerName $args[0] | Format-List ComputerName,RemoteAddress,PingSucceeded,TcpTestSucceeded"
    ) + [p["host"]],
    timeout=15,
))

_register(Operation(
    op_id="net.ping",
    summary="Send 4 ping packets to a host.",
    risk="read",
    params=[Param("host", "string", "Hostname or IP", _v_hostname)],
    build=lambda p: ["ping", "-n", "4", p["host"]],
    timeout=15,
))

_register(Operation(
    op_id="net.reset_winsock",
    summary="Reset Winsock catalog. Fixes broken socket stack. REQUIRES REBOOT.",
    risk="dangerous",
    build=lambda _: ["netsh", "winsock", "reset"],
    needs_admin=True,
))

_register(Operation(
    op_id="net.reset_tcpip",
    summary="Reset the TCP/IP stack. REQUIRES REBOOT.",
    risk="dangerous",
    build=lambda _: ["netsh", "int", "ip", "reset"],
    needs_admin=True,
))

# ── Services ─────────────────────────────────────────────────────────

_register(Operation(
    op_id="service.status",
    summary="Show the status of a Windows service.",
    risk="read",
    params=[Param("name", "string", "Service name (e.g., 'Spooler')", _v_service)],
    build=lambda p: _ps("Get-Service -Name $args[0] | Format-List Name,Status,StartType")
                    + [p["name"]],
))

_register(Operation(
    op_id="service.restart",
    summary="Restart a Windows service.",
    risk="write",
    params=[Param("name", "string", "Service name", _v_service)],
    build=lambda p: _ps("Restart-Service -Name $args[0] -Force") + [p["name"]],
    needs_admin=True,
))

_register(Operation(
    op_id="service.start",
    summary="Start a Windows service.",
    risk="write",
    params=[Param("name", "string", "Service name", _v_service)],
    build=lambda p: _ps("Start-Service -Name $args[0]") + [p["name"]],
    needs_admin=True,
))

_register(Operation(
    op_id="service.stop",
    summary="Stop a Windows service.",
    risk="write",
    params=[Param("name", "string", "Service name", _v_service)],
    build=lambda p: _ps("Stop-Service -Name $args[0] -Force") + [p["name"]],
    needs_admin=True,
))

# ── System info / health ─────────────────────────────────────────────

_register(Operation(
    op_id="sys.info",
    summary="Print a short system summary (OS, install date, BIOS).",
    risk="read",
    build=lambda _: ["systeminfo"],
    timeout=20,
))

_register(Operation(
    op_id="sys.uptime",
    summary="Show how long the computer has been on since the last boot.",
    risk="read",
    build=lambda _: _ps(
        "$b = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime; "
        "$u = (Get-Date) - $b; "
        "'Last boot: {0:yyyy-MM-dd HH:mm} | Uptime: {1:d}d {2:d}h {3:d}m' -f $b,$u.Days,$u.Hours,$u.Minutes"
    ),
))

_register(Operation(
    op_id="sys.disk_health",
    summary="Show physical disk health (SMART status equivalent).",
    risk="read",
    build=lambda _: _ps(
        "Get-PhysicalDisk | Select-Object FriendlyName,MediaType,HealthStatus,OperationalStatus,Size | Format-Table -AutoSize"
    ),
))

_register(Operation(
    op_id="sys.disk_space",
    summary="Show free space on every volume.",
    risk="read",
    build=lambda _: _ps(
        "Get-Volume | Where-Object DriveLetter | "
        "Select-Object DriveLetter,FileSystemLabel,@{n='SizeGB';e={[math]::Round($_.Size/1GB,1)}},"
        "@{n='FreeGB';e={[math]::Round($_.SizeRemaining/1GB,1)}} | Format-Table -AutoSize"
    ),
))

_register(Operation(
    op_id="sys.battery_report",
    summary="Generate a Windows battery health report (HTML).",
    risk="read",
    params=[Param("output_path", "path",
                  r"Output HTML path, e.g., C:\Users\Public\battery.html",
                  _v_path_writable)],
    build=lambda p: ["powercfg", "/batteryreport", "/output", p["output_path"]],
    timeout=20,
))

_register(Operation(
    op_id="sys.event_errors",
    summary="Show the 50 most recent error-level events from the System log.",
    risk="read",
    build=lambda _: _ps(
        "Get-WinEvent -FilterHashtable @{LogName='System';Level=2} -MaxEvents 50 "
        "-ErrorAction SilentlyContinue | "
        "Select-Object TimeCreated,Id,ProviderName,Message | Format-List"
    ),
    timeout=45,
))

# ── Windows update / hotfixes ────────────────────────────────────────

_register(Operation(
    op_id="update.list_installed",
    summary="List installed Windows updates and hotfixes.",
    risk="read",
    build=lambda _: _ps("Get-HotFix | Sort-Object InstalledOn -Descending | "
                        "Select-Object -First 30 HotFixID,Description,InstalledOn | Format-Table -AutoSize"),
))

# ── Processes ────────────────────────────────────────────────────────

_register(Operation(
    op_id="proc.top",
    summary="Show the top 20 processes by CPU.",
    risk="read",
    build=lambda _: _ps(
        "Get-Process | Sort-Object -Descending CPU | Select-Object -First 20 "
        "Name,Id,@{n='CPU(s)';e={[math]::Round($_.CPU,1)}},"
        "@{n='MemMB';e={[math]::Round($_.WS/1MB,1)}} | Format-Table -AutoSize"
    ),
))

# ── Defender ─────────────────────────────────────────────────────────

_register(Operation(
    op_id="defender.status",
    summary="Show Microsoft Defender protection status and signature versions.",
    risk="read",
    build=lambda _: _ps("Get-MpComputerStatus | Format-List AMRunningMode,AntivirusEnabled,"
                        "RealTimeProtectionEnabled,QuickScanAge,FullScanAge,AntivirusSignatureVersion"),
))

_register(Operation(
    op_id="defender.scan_quick",
    summary="Run a Microsoft Defender quick scan.",
    risk="write",
    build=lambda _: _ps("Start-MpScan -ScanType QuickScan"),
    timeout=1800,   # quick scans can take a while
    needs_admin=True,
))

_register(Operation(
    op_id="defender.scan_full",
    summary="Run a Microsoft Defender full scan. Can take 1-3 hours.",
    risk="dangerous",   # not destructive, but long-running and slows the PC
    build=lambda _: _ps("Start-MpScan -ScanType FullScan"),
    timeout=10800,
    needs_admin=True,
))

# ── System file repair ───────────────────────────────────────────────

_register(Operation(
    op_id="repair.sfc",
    summary="Run System File Checker to verify and repair Windows files.",
    risk="dangerous",
    build=lambda _: ["sfc", "/scannow"],
    timeout=2400,
    needs_admin=True,
))

_register(Operation(
    op_id="repair.dism_check",
    summary="Quick check on the Windows component store (DISM /CheckHealth).",
    risk="read",
    build=lambda _: ["DISM", "/Online", "/Cleanup-Image", "/CheckHealth"],
    timeout=120,
    needs_admin=True,
))

_register(Operation(
    op_id="repair.dism_restore",
    summary="Repair the Windows component store from Windows Update (DISM /RestoreHealth).",
    risk="dangerous",
    build=lambda _: ["DISM", "/Online", "/Cleanup-Image", "/RestoreHealth"],
    timeout=3600,
    needs_admin=True,
))


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def list_operations(risk_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return a manifest of available operations, optionally filtered by risk.

    The agent uses this to discover what it can do without seeing argv builders.
    """
    out = []
    for op in _OPERATIONS.values():
        if risk_filter and op.risk != risk_filter:
            continue
        out.append({
            "op_id": op.op_id,
            "summary": op.summary,
            "risk": op.risk,
            "needs_admin": op.needs_admin,
            "params": [
                {"name": p.name, "type": p.type_, "description": p.description, "required": p.required}
                for p in op.params
            ],
        })
    return out


def get_operation(op_id: str) -> Optional[Operation]:
    return _OPERATIONS.get(op_id)


def _validate(op: Operation, params: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and coerce caller-supplied params against the operation's schema."""
    params = dict(params or {})
    # Reject unknown keys — failing closed prevents future-bug param smuggling.
    declared = {p.name for p in op.params}
    extras = set(params) - declared
    if extras:
        raise ValueError(f"Unknown parameters for {op.op_id}: {sorted(extras)}")
    validated: Dict[str, Any] = {}
    for p in op.params:
        if p.name not in params:
            if p.required:
                raise ValueError(f"Missing required parameter for {op.op_id}: {p.name}")
            validated[p.name] = p.default
            continue
        raw = params[p.name]
        validated[p.name] = p.validator(raw) if p.validator else raw
    return validated


def run(op_id: str, params: Optional[Dict[str, Any]] = None,
        *, dry_run: bool = False) -> Dict[str, Any]:
    """Execute an operation by ID with validated parameters.

    `dry_run=True` returns the resolved argv list without executing — useful
    for the consent-gate UI to preview what's about to run, and for tests.
    """
    op = get_operation(op_id)
    if op is None:
        return {
            "op": op_id, "ok": False, "risk": "unknown",
            "stdout": "", "stderr": f"Unknown operation: {op_id}", "returncode": -1,
            "summary": "",
        }
    try:
        validated = _validate(op, params or {})
    except ValueError as e:
        return {
            "op": op_id, "ok": False, "risk": op.risk,
            "stdout": "", "stderr": str(e), "returncode": -2,
            "summary": op.summary,
        }
    argv = op.build(validated)
    if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
        return {
            "op": op_id, "ok": False, "risk": op.risk,
            "stdout": "", "stderr": "Internal error: builder did not return List[str]",
            "returncode": -3, "summary": op.summary,
        }
    if dry_run:
        return {
            "op": op_id, "ok": True, "risk": op.risk,
            "summary": op.summary, "argv": argv,
            "stdout": "", "stderr": "", "returncode": 0,
            "needs_admin": op.needs_admin,
        }
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True,
            timeout=op.timeout, shell=False,
        )
        return {
            "op": op_id, "ok": result.returncode == 0,
            "risk": op.risk, "summary": op.summary,
            "stdout": (result.stdout or "")[:8000],
            "stderr": (result.stderr or "")[:2000],
            "returncode": result.returncode,
            "needs_admin": op.needs_admin,
        }
    except subprocess.TimeoutExpired:
        return {
            "op": op_id, "ok": False, "risk": op.risk, "summary": op.summary,
            "stdout": "", "stderr": f"Operation timed out after {op.timeout}s",
            "returncode": -4, "needs_admin": op.needs_admin,
        }
    except FileNotFoundError as e:
        return {
            "op": op_id, "ok": False, "risk": op.risk, "summary": op.summary,
            "stdout": "", "stderr": f"Required tool not found: {e}",
            "returncode": -5, "needs_admin": op.needs_admin,
        }
