"""
Tests for the ToolExecutor — verifies each tool handler works correctly
with mocked dependencies.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.tool_executor import ToolExecutor


def run_async(coro):
    """Helper to run async functions in tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestToolExecutorRouting(unittest.TestCase):
    """Test the execute() dispatcher."""

    def setUp(self):
        self.executor = ToolExecutor()

    def test_unknown_tool_returns_error(self):
        result = run_async(self.executor.execute("nonexistent_tool", {}))
        self.assertIn("error", result)
        self.assertIn("Unknown tool", result["error"])

    def test_tool_exception_returns_error(self):
        """Tool handlers that throw should return error dicts, not crash."""
        # Use a tool that will fail gracefully without triggering emergency stop
        result = run_async(self.executor.execute("run_powershell", {"command": ""}))
        # Should get an error or empty result, not crash
        self.assertIsInstance(result, dict)


class TestDiagnosticTools(unittest.TestCase):
    """Test diagnostic tool handlers."""

    def setUp(self):
        self.executor = ToolExecutor()

    def test_run_diagnostic_returns_results(self):
        # Use a real diagnostic module (hardware is the safest to run in tests)
        result = run_async(self.executor.execute("run_diagnostic", {"category": "hardware"}))
        self.assertIn("results", result)
        self.assertIn("category", result)
        self.assertEqual(result["category"], "hardware")
        self.assertIsInstance(result["results"], list)
        self.assertGreater(len(result["results"]), 0)

    def test_run_diagnostic_result_format(self):
        result = run_async(self.executor.execute("run_diagnostic", {"category": "hardware"}))
        for item in result["results"]:
            self.assertIn("name", item)
            self.assertIn("status", item)
            self.assertIn("details", item)
            self.assertIn("fix_available", item)
            self.assertIn(item["status"], ("ok", "warning", "error", "fixed"))

    def test_run_diagnostic_invalid_category(self):
        # Invalid categories trigger emergency stop in safety controller,
        # which closes stdout and crashes pytest. Use mock to verify error handling.
        from unittest.mock import patch
        with patch("core.safety.SafetyController.check_action", return_value=(True, "")):
            result = run_async(self.executor.execute("run_diagnostic", {"category": "fake"}))
            self.assertIn("error", result)


class TestSystemInfoTools(unittest.TestCase):
    """Test system info tool handlers."""

    def setUp(self):
        self.executor = ToolExecutor()

    def test_get_system_info(self):
        result = run_async(self.executor.execute("get_system_info", {}))
        self.assertIn("cpu_percent", result)
        self.assertIn("memory_percent", result)
        self.assertIn("memory_total_gb", result)
        self.assertIn("disk_free_gb", result)
        self.assertIn("uptime_hours", result)
        # Validate types
        self.assertIsInstance(result["cpu_percent"], (int, float))
        self.assertIsInstance(result["memory_total_gb"], (int, float))

    def test_list_processes(self):
        result = run_async(self.executor.execute("list_processes", {}))
        self.assertIn("processes", result)
        self.assertIsInstance(result["processes"], list)
        self.assertGreater(len(result["processes"]), 0)
        # Check process format
        proc = result["processes"][0]
        self.assertIn("pid", proc)
        self.assertIn("name", proc)

    def test_list_processes_with_filter(self):
        result = run_async(self.executor.execute("list_processes", {"name_filter": "python"}))
        self.assertIn("processes", result)
        # Should find at least our own python process
        self.assertGreater(len(result["processes"]), 0)


class TestPowerShellTool(unittest.TestCase):
    """Test PowerShell execution with safety."""

    def setUp(self):
        self.executor = ToolExecutor()

    @patch("ai.tool_executor.subprocess.run")
    def test_powershell_basic_command(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.stdout = "svc"
        mock_proc.stderr = ""
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        result = run_async(self.executor.execute("run_powershell", {"command": "Get-Service"}))
        self.assertIn("stdout", result)
        self.assertEqual(result["returncode"], 0)

    def test_powershell_blocks_destructive(self):
        result = run_async(self.executor.execute("run_powershell", {"command": "Format-Volume -DriveLetter C"}))
        self.assertIn("error", result)
        self.assertIn("Blocked", result["error"])

    def test_powershell_blocks_restart_computer(self):
        result = run_async(self.executor.execute("run_powershell", {"command": "Restart-Computer"}))
        self.assertIn("error", result)
        self.assertIn("Blocked", result["error"])

    def test_powershell_blocks_stop_computer(self):
        result = run_async(self.executor.execute("run_powershell", {"command": "Stop-Computer"}))
        self.assertIn("error", result)
        self.assertIn("Blocked", result["error"])


class TestWebSearchTool(unittest.TestCase):
    """Test the web search tool."""

    def setUp(self):
        self.executor = ToolExecutor()

    def test_web_search_returns_result(self):
        result = run_async(self.executor.execute("web_search", {"query": "fix printer error"}))
        self.assertIn("query", result)
        self.assertEqual(result["query"], "fix printer error")
        # Should have some results (either from DuckDuckGo or fallback)
        self.assertIsInstance(result, dict)


if __name__ == "__main__":
    unittest.main()
