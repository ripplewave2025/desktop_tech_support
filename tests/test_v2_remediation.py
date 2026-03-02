"""
Tests for v2.0 Remediation Library — 52 structured Windows fixes.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from remediation.library import (
    REMEDIATION_LIBRARY,
    get_fix,
    get_fixes_by_category,
    get_all_categories,
    get_library_stats,
)


class TestRemediationLibrary(unittest.TestCase):
    """Test the REMEDIATION_LIBRARY structure."""

    def test_library_not_empty(self):
        self.assertGreater(len(REMEDIATION_LIBRARY), 0)

    def test_at_least_50_fixes(self):
        self.assertGreaterEqual(len(REMEDIATION_LIBRARY), 50)

    def test_all_fixes_have_required_fields(self):
        required = ["name", "category", "risk", "commands", "requires_reboot"]
        for fix_id, fix in REMEDIATION_LIBRARY.items():
            for field in required:
                self.assertIn(field, fix, f"Fix '{fix_id}' missing field '{field}'")

    def test_all_fixes_have_valid_risk(self):
        valid_risks = {"low", "medium", "high"}
        for fix_id, fix in REMEDIATION_LIBRARY.items():
            self.assertIn(fix["risk"], valid_risks,
                         f"Fix '{fix_id}' has invalid risk: {fix['risk']}")

    def test_all_fixes_have_commands(self):
        for fix_id, fix in REMEDIATION_LIBRARY.items():
            self.assertIsInstance(fix["commands"], list)
            self.assertGreater(len(fix["commands"]), 0,
                              f"Fix '{fix_id}' has no commands")

    def test_requires_reboot_is_bool(self):
        for fix_id, fix in REMEDIATION_LIBRARY.items():
            self.assertIsInstance(fix["requires_reboot"], bool,
                                f"Fix '{fix_id}' requires_reboot is not bool")

    def test_all_fixes_have_valid_category(self):
        valid_categories = {"network", "audio", "display", "software",
                           "hardware", "security", "printer"}
        for fix_id, fix in REMEDIATION_LIBRARY.items():
            self.assertIn(fix["category"], valid_categories,
                         f"Fix '{fix_id}' has invalid category: {fix['category']}")


class TestRemediationCategories(unittest.TestCase):
    """Test category distribution."""

    def test_expected_categories_exist(self):
        categories = get_all_categories()
        expected = {"network", "audio", "display", "software",
                    "hardware", "security", "printer"}
        for cat in expected:
            self.assertIn(cat, categories)

    def test_network_has_15_fixes(self):
        fixes = get_fixes_by_category("network")
        self.assertEqual(len(fixes), 15,
                        f"Network has {len(fixes)} fixes, expected 15")

    def test_audio_has_8_fixes(self):
        fixes = get_fixes_by_category("audio")
        self.assertEqual(len(fixes), 8)

    def test_display_has_6_fixes(self):
        fixes = get_fixes_by_category("display")
        self.assertEqual(len(fixes), 6)

    def test_software_has_8_fixes(self):
        fixes = get_fixes_by_category("software")
        self.assertEqual(len(fixes), 8)

    def test_hardware_has_5_fixes(self):
        fixes = get_fixes_by_category("hardware")
        self.assertEqual(len(fixes), 5)

    def test_security_has_5_fixes(self):
        fixes = get_fixes_by_category("security")
        self.assertEqual(len(fixes), 5)

    def test_printer_has_5_fixes(self):
        fixes = get_fixes_by_category("printer")
        self.assertEqual(len(fixes), 5)


class TestRemediationHelpers(unittest.TestCase):
    """Test helper functions."""

    def test_get_fix_exists(self):
        fix = get_fix("dns_flush")
        self.assertIsNotNone(fix)
        self.assertEqual(fix["name"], "Flush DNS Cache")

    def test_get_fix_nonexistent(self):
        fix = get_fix("nonexistent_fix")
        self.assertIsNone(fix)

    def test_get_fixes_by_category_returns_list(self):
        fixes = get_fixes_by_category("network")
        self.assertIsInstance(fixes, list)
        for fix in fixes:
            self.assertEqual(fix["category"], "network")

    def test_get_fixes_empty_category(self):
        fixes = get_fixes_by_category("nonexistent")
        self.assertEqual(len(fixes), 0)

    def test_get_library_stats(self):
        stats = get_library_stats()
        self.assertIn("total_fixes", stats)
        self.assertIn("categories", stats)
        self.assertIn("low_risk", stats)
        self.assertIn("medium_risk", stats)
        self.assertIn("high_risk", stats)
        self.assertEqual(stats["total_fixes"], len(REMEDIATION_LIBRARY))

    def test_risk_counts_add_up(self):
        stats = get_library_stats()
        total = stats["low_risk"] + stats["medium_risk"] + stats["high_risk"]
        self.assertEqual(total, stats["total_fixes"])


class TestSpecificFixes(unittest.TestCase):
    """Test a few specific well-known fixes."""

    def test_dns_flush(self):
        fix = get_fix("dns_flush")
        self.assertEqual(fix["risk"], "low")
        self.assertIn("ipconfig /flushdns", fix["commands"])
        self.assertFalse(fix["requires_reboot"])

    def test_winsock_reset(self):
        fix = get_fix("winsock_reset")
        self.assertEqual(fix["risk"], "medium")
        self.assertTrue(fix["requires_reboot"])

    def test_sfc_scan(self):
        fix = get_fix("sfc_scan")
        self.assertIsNotNone(fix)
        self.assertEqual(fix["category"], "software")

    def test_defender_scan(self):
        fix = get_fix("defender_quick_scan")
        self.assertIsNotNone(fix)
        self.assertEqual(fix["category"], "security")

    def test_spooler_restart(self):
        fix = get_fix("spooler_restart")
        self.assertIsNotNone(fix)
        self.assertEqual(fix["category"], "printer")


if __name__ == "__main__":
    unittest.main()
