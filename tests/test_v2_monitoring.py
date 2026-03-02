"""
Tests for v2.0 Proactive Monitoring — Alert model + SystemWatcher.
"""

import os
import sys
import time
import unittest
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitoring.alerts import Alert
from monitoring.watcher import SystemWatcher


class TestAlertModel(unittest.TestCase):
    """Test the Alert dataclass."""

    def test_default_fields(self):
        alert = Alert(category="cpu", title="CPU Hot", message="CPU is hot")
        self.assertEqual(alert.severity, "warning")
        self.assertFalse(alert.dismissed)
        self.assertEqual(alert.auto_dismiss_minutes, 10)
        self.assertIsInstance(alert.id, str)
        self.assertGreater(len(alert.id), 0)

    def test_to_dict(self):
        alert = Alert(
            severity="critical",
            category="disk",
            title="Low Disk",
            message="Only 1GB free",
        )
        d = alert.to_dict()
        self.assertEqual(d["severity"], "critical")
        self.assertEqual(d["category"], "disk")
        self.assertEqual(d["title"], "Low Disk")
        self.assertEqual(d["message"], "Only 1GB free")
        self.assertFalse(d["dismissed"])
        self.assertIn("timestamp", d)
        self.assertIn("id", d)

    def test_duplicate_detection_same_category(self):
        a1 = Alert(category="cpu", title="CPU 1", message="1")
        a2 = Alert(category="cpu", title="CPU 2", message="2")
        self.assertTrue(a1.is_duplicate_of(a2))

    def test_duplicate_detection_different_category(self):
        a1 = Alert(category="cpu", title="CPU", message="1")
        a2 = Alert(category="disk", title="Disk", message="2")
        self.assertFalse(a1.is_duplicate_of(a2))

    def test_duplicate_detection_outside_window(self):
        a1 = Alert(category="cpu", title="CPU 1", message="1")
        a2 = Alert(category="cpu", title="CPU 2", message="2")
        # Move a1 timestamp 15 minutes back
        a1.timestamp = a2.timestamp - datetime.timedelta(minutes=15)
        self.assertFalse(a1.is_duplicate_of(a2))

    def test_severity_values(self):
        for sev in ("info", "warning", "critical"):
            alert = Alert(severity=sev, category="test", title="T", message="M")
            self.assertEqual(alert.severity, sev)


class TestSystemWatcher(unittest.TestCase):
    """Test the SystemWatcher (without starting the background thread)."""

    def setUp(self):
        self.watcher = SystemWatcher()

    def test_initial_state(self):
        self.assertEqual(self.watcher.active_count, 0)
        self.assertEqual(len(self.watcher.get_alerts()), 0)
        self.assertFalse(self.watcher._running)

    def test_add_and_get_alerts(self):
        self.watcher._add_alert(Alert(
            category="cpu", title="CPU Hot", message="CPU > 90%"
        ))
        alerts = self.watcher.get_alerts()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["category"], "cpu")
        self.assertEqual(self.watcher.active_count, 1)

    def test_dismiss_alert(self):
        self.watcher._add_alert(Alert(
            category="disk", title="Disk Low", message="1GB free"
        ))
        alerts = self.watcher.get_alerts()
        alert_id = alerts[0]["id"]

        self.assertTrue(self.watcher.dismiss_alert(alert_id))
        self.assertEqual(self.watcher.active_count, 0)
        # Dismissed alerts are hidden by default
        self.assertEqual(len(self.watcher.get_alerts()), 0)
        # But available with include_dismissed
        self.assertEqual(len(self.watcher.get_alerts(include_dismissed=True)), 1)

    def test_dismiss_nonexistent(self):
        self.assertFalse(self.watcher.dismiss_alert("nonexistent"))

    def test_dismiss_all(self):
        self.watcher._add_alert(Alert(category="cpu", title="1", message="1"))
        self.watcher._add_alert(Alert(category="disk", title="2", message="2"))
        self.assertEqual(self.watcher.active_count, 2)

        self.watcher.dismiss_all()
        self.assertEqual(self.watcher.active_count, 0)

    def test_dedup_within_window(self):
        self.watcher._add_alert(Alert(category="cpu", title="CPU 1", message="1"))
        self.watcher._add_alert(Alert(category="cpu", title="CPU 2", message="2"))
        # Second should be deduped
        self.assertEqual(self.watcher.active_count, 1)

    def test_different_categories_not_deduped(self):
        self.watcher._add_alert(Alert(category="cpu", title="CPU", message="1"))
        self.watcher._add_alert(Alert(category="disk", title="Disk", message="2"))
        self.assertEqual(self.watcher.active_count, 2)

    def test_crash_loop_detection(self):
        # 2 crashes shouldn't trigger alert
        self.watcher.report_crash("notepad.exe")
        self.watcher.report_crash("notepad.exe")
        self.assertEqual(self.watcher.active_count, 0)

        # 3rd crash should trigger
        self.watcher.report_crash("notepad.exe")
        self.assertEqual(self.watcher.active_count, 1)
        alerts = self.watcher.get_alerts()
        self.assertIn("notepad.exe", alerts[0]["title"])

    def test_max_alerts_limit(self):
        for i in range(60):
            # Use different categories so dedup doesn't kick in
            self.watcher._add_alert(Alert(
                category=f"test_{i}",
                title=f"Alert {i}",
                message=f"Message {i}",
            ))
        # Should be capped at MAX_ALERTS
        all_alerts = self.watcher.get_alerts(include_dismissed=True)
        self.assertLessEqual(len(all_alerts), self.watcher.MAX_ALERTS)

    def test_alerts_newest_first(self):
        self.watcher._add_alert(Alert(category="first", title="First", message="1"))
        time.sleep(0.01)
        self.watcher._add_alert(Alert(category="second", title="Second", message="2"))
        alerts = self.watcher.get_alerts()
        self.assertEqual(alerts[0]["category"], "second")
        self.assertEqual(alerts[1]["category"], "first")

    def test_start_and_stop(self):
        """Verify watcher thread starts and stops cleanly."""
        self.watcher.start()
        self.assertTrue(self.watcher._running)
        self.assertIsNotNone(self.watcher._thread)

        self.watcher.stop()
        self.assertFalse(self.watcher._running)

    def test_thresholds_exist(self):
        """Verify all expected thresholds are defined."""
        expected = ["cpu_percent", "cpu_sustained_seconds", "memory_percent",
                    "disk_free_gb", "uptime_hours", "temperature_celsius"]
        for key in expected:
            self.assertIn(key, self.watcher.THRESHOLDS)


if __name__ == "__main__":
    unittest.main()
