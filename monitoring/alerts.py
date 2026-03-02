"""
Alert data model for proactive monitoring.

Alerts represent system health issues detected by the background watcher.
They are stored in-memory and exposed via the API for the UI to display.
"""

import uuid
import datetime
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Alert:
    """A system health alert."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    severity: str = "warning"  # "info", "warning", "critical"
    category: str = ""  # "cpu", "memory", "disk", "uptime", "crash_loop", "temperature"
    title: str = ""
    message: str = ""
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)
    dismissed: bool = False
    auto_dismiss_minutes: int = 10  # De-duplicate window

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "severity": self.severity,
            "category": self.category,
            "title": self.title,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "dismissed": self.dismissed,
        }

    def is_duplicate_of(self, other: "Alert") -> bool:
        """Check if this alert is a duplicate (same category within time window)."""
        if self.category != other.category:
            return False
        time_diff = abs((self.timestamp - other.timestamp).total_seconds())
        return time_diff < (self.auto_dismiss_minutes * 60)
