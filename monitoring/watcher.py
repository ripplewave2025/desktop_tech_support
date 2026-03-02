"""
System Watcher — background thread that monitors system health.

Polls system metrics every 30 seconds (2 minutes on battery) and
fires alerts when thresholds are exceeded. Uses the existing
ProcessManager for all system queries.
"""

import time
import logging
import threading
from collections import deque
from typing import List, Dict, Optional

import psutil

from .alerts import Alert

logger = logging.getLogger("zora.watcher")


class SystemWatcher:
    """Background monitor that checks system health and queues alerts."""

    # ─── Thresholds ─────────────────────────────────────
    THRESHOLDS = {
        "cpu_percent": 90,          # CPU > 90% sustained
        "cpu_sustained_seconds": 120,  # Must stay high for 2 minutes
        "memory_percent": 90,       # RAM > 90%
        "disk_free_gb": 5,          # Disk < 5GB free
        "uptime_hours": 168,        # Uptime > 7 days (suggest reboot)
        "temperature_celsius": 85,  # CPU temp > 85C (if available)
    }

    POLL_INTERVAL_AC = 30       # Seconds between checks (on AC power)
    POLL_INTERVAL_BATTERY = 120  # Seconds between checks (on battery)
    MAX_ALERTS = 50             # Keep last 50 alerts in memory

    def __init__(self):
        self._alerts: deque = deque(maxlen=self.MAX_ALERTS)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._cpu_high_since: Optional[float] = None  # Timestamp when CPU first went high
        self._crash_tracker: Dict[str, List[float]] = {}  # process_name -> [crash timestamps]
        self._lock = threading.Lock()

    def start(self):
        """Start the background watcher thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="ZoraWatcher")
        self._thread.start()
        logger.info("System watcher started")

    def stop(self):
        """Stop the background watcher."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("System watcher stopped")

    def _run(self):
        """Main polling loop."""
        while self._running:
            try:
                self._check_all()
            except Exception as e:
                logger.error(f"Watcher check failed: {e}")

            # Sleep based on power source
            interval = self._get_poll_interval()
            # Sleep in small increments so we can stop quickly
            for _ in range(int(interval)):
                if not self._running:
                    return
                time.sleep(1)

    def _get_poll_interval(self) -> int:
        """Return poll interval based on whether we're on battery."""
        try:
            battery = psutil.sensors_battery()
            if battery and not battery.power_plugged:
                return self.POLL_INTERVAL_BATTERY
        except Exception:
            pass
        return self.POLL_INTERVAL_AC

    # ─── Health Checks ─────────────────────────────────
    def _check_all(self):
        """Run all health checks."""
        self._check_cpu()
        self._check_memory()
        self._check_disk()
        self._check_uptime()
        self._check_temperature()

    def _check_cpu(self):
        """Check if CPU usage is sustained above threshold."""
        cpu = psutil.cpu_percent(interval=1)

        if cpu >= self.THRESHOLDS["cpu_percent"]:
            now = time.time()
            if self._cpu_high_since is None:
                self._cpu_high_since = now
            elif (now - self._cpu_high_since) >= self.THRESHOLDS["cpu_sustained_seconds"]:
                # Get top CPU consumers
                top_procs = []
                for proc in psutil.process_iter(["pid", "name", "cpu_percent"]):
                    try:
                        if proc.info["cpu_percent"] and proc.info["cpu_percent"] > 5:
                            top_procs.append(f"{proc.info['name']} ({proc.info['cpu_percent']:.0f}%)")
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                top_procs = top_procs[:3]
                top_str = ", ".join(top_procs) if top_procs else "unknown processes"

                self._add_alert(Alert(
                    severity="warning",
                    category="cpu",
                    title="CPU Running Hot",
                    message=f"CPU has been above {self.THRESHOLDS['cpu_percent']}% for over 2 minutes. Top consumers: {top_str}. Want me to investigate?",
                ))
                self._cpu_high_since = None  # Reset after alerting
        else:
            self._cpu_high_since = None

    def _check_memory(self):
        """Check RAM usage."""
        mem = psutil.virtual_memory()
        if mem.percent >= self.THRESHOLDS["memory_percent"]:
            used_gb = round(mem.used / (1024 ** 3), 1)
            total_gb = round(mem.total / (1024 ** 3), 1)

            self._add_alert(Alert(
                severity="warning",
                category="memory",
                title="Memory Running Low",
                message=f"RAM usage is at {mem.percent}% ({used_gb}/{total_gb} GB). Your PC might slow down. Want me to find what's using the most memory?",
            ))

    def _check_disk(self):
        """Check disk free space."""
        try:
            disk = psutil.disk_usage("C:\\")
            free_gb = round(disk.free / (1024 ** 3), 1)

            if free_gb < self.THRESHOLDS["disk_free_gb"]:
                severity = "critical" if free_gb < 1 else "warning"
                self._add_alert(Alert(
                    severity=severity,
                    category="disk",
                    title="Disk Space Low",
                    message=f"Only {free_gb} GB free on C: drive. {'This is critical!' if free_gb < 1 else 'Time for some cleanup.'} Want me to run a disk cleanup?",
                ))
        except Exception:
            pass

    def _check_uptime(self):
        """Check if system hasn't been rebooted in a while."""
        boot_time = psutil.boot_time()
        uptime_hours = (time.time() - boot_time) / 3600

        if uptime_hours >= self.THRESHOLDS["uptime_hours"]:
            days = int(uptime_hours / 24)
            self._add_alert(Alert(
                severity="info",
                category="uptime",
                title="Reboot Recommended",
                message=f"Your PC has been running for {days} days without a restart. A reboot can help with performance and pending updates.",
            ))

    def _check_temperature(self):
        """Check CPU temperature (if available via psutil)."""
        try:
            temps = psutil.sensors_temperatures()
            if not temps:
                return
            for name, entries in temps.items():
                for entry in entries:
                    if entry.current and entry.current >= self.THRESHOLDS["temperature_celsius"]:
                        self._add_alert(Alert(
                            severity="critical" if entry.current >= 95 else "warning",
                            category="temperature",
                            title="CPU Temperature High",
                            message=f"CPU temperature is {entry.current:.0f}C. This could cause throttling or damage. Check your cooling.",
                        ))
                        return  # One temp alert is enough
        except (AttributeError, Exception):
            # sensors_temperatures() not available on all platforms
            pass

    # ─── Crash Loop Detection ──────────────────────────
    def report_crash(self, process_name: str):
        """Call this when a process crashes. Detects crash loops."""
        now = time.time()
        if process_name not in self._crash_tracker:
            self._crash_tracker[process_name] = []

        # Keep only crashes from last 5 minutes
        window = 5 * 60
        self._crash_tracker[process_name] = [
            t for t in self._crash_tracker[process_name]
            if (now - t) < window
        ]
        self._crash_tracker[process_name].append(now)

        if len(self._crash_tracker[process_name]) >= 3:
            self._add_alert(Alert(
                severity="warning",
                category="crash_loop",
                title=f"{process_name} Keeps Crashing",
                message=f"{process_name} has crashed {len(self._crash_tracker[process_name])} times in the last 5 minutes. Want me to investigate?",
            ))
            self._crash_tracker[process_name] = []  # Reset after alerting

    # ─── Alert Management ──────────────────────────────
    def _add_alert(self, alert: Alert):
        """Add alert with de-duplication."""
        with self._lock:
            # Check for duplicates in recent alerts
            for existing in self._alerts:
                if not existing.dismissed and alert.is_duplicate_of(existing):
                    return  # Duplicate, skip

            self._alerts.append(alert)
            logger.info(f"Alert: [{alert.severity}] {alert.title} — {alert.message}")

    def get_alerts(self, include_dismissed: bool = False) -> List[dict]:
        """Get all active alerts as dicts."""
        with self._lock:
            alerts = []
            for a in self._alerts:
                if include_dismissed or not a.dismissed:
                    alerts.append(a.to_dict())
            return list(reversed(alerts))  # Newest first

    def dismiss_alert(self, alert_id: str) -> bool:
        """Mark an alert as dismissed."""
        with self._lock:
            for a in self._alerts:
                if a.id == alert_id:
                    a.dismissed = True
                    return True
            return False

    def dismiss_all(self):
        """Dismiss all alerts."""
        with self._lock:
            for a in self._alerts:
                a.dismissed = True

    @property
    def active_count(self) -> int:
        """Number of undismissed alerts."""
        with self._lock:
            return sum(1 for a in self._alerts if not a.dismissed)
