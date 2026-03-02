"""
Tests for v2.0 Flow Engine — YAML-based decision trees.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from diagnostics.flow_engine import FlowEngine
from diagnostics.flow_actions import FLOW_ACTIONS


class TestFlowEngineLoading(unittest.TestCase):
    """Test flow loading from YAML files."""

    def setUp(self):
        self.engine = FlowEngine()

    def test_flows_loaded(self):
        flows = self.engine.available_flows
        self.assertGreater(len(flows), 0)

    def test_expected_flows_present(self):
        flow_ids = [f["id"] for f in self.engine.available_flows]
        expected = ["internet_slow", "no_sound", "printer_not_working", "slow_pc", "wifi_disconnects"]
        for fid in expected:
            self.assertIn(fid, flow_ids, f"Flow '{fid}' not loaded")

    def test_each_flow_has_fields(self):
        for flow in self.engine.available_flows:
            self.assertIn("id", flow)
            self.assertIn("name", flow)
            self.assertIn("trigger_keywords", flow)
            self.assertIsInstance(flow["trigger_keywords"], list)

    def test_empty_dir_loads_no_flows(self):
        engine = FlowEngine(flows_dir="/nonexistent/path")
        self.assertEqual(len(engine.available_flows), 0)


class TestFlowEngineKeywordMatching(unittest.TestCase):
    """Test user query -> flow matching."""

    def setUp(self):
        self.engine = FlowEngine()

    def test_match_internet_slow(self):
        # Keywords use substring matching, so query must contain exact keyword
        for query in ["slow internet connection", "buffering video", "lag in games", "internet slow today"]:
            result = self.engine.find_flow_for_query(query)
            self.assertEqual(result, "internet_slow", f"Failed for query: {query}")

    def test_match_no_sound(self):
        for query in ["no sound", "no audio", "speakers not working"]:
            result = self.engine.find_flow_for_query(query)
            self.assertEqual(result, "no_sound", f"Failed for query: {query}")

    def test_match_printer(self):
        for query in ["printer not working", "can't print", "printer offline"]:
            result = self.engine.find_flow_for_query(query)
            self.assertEqual(result, "printer_not_working", f"Failed for query: {query}")

    def test_match_slow_pc(self):
        for query in ["slow computer lately", "pc slow today", "laptop freezing up"]:
            result = self.engine.find_flow_for_query(query)
            self.assertEqual(result, "slow_pc", f"Failed for query: {query}")

    def test_match_wifi(self):
        for query in ["wifi keeps disconnecting", "wifi drops"]:
            result = self.engine.find_flow_for_query(query)
            self.assertEqual(result, "wifi_disconnects", f"Failed for query: {query}")

    def test_no_match(self):
        result = self.engine.find_flow_for_query("how to bake a cake")
        self.assertIsNone(result)


class TestFlowEngineExecution(unittest.TestCase):
    """Test flow execution with mock actions."""

    def setUp(self):
        self.engine = FlowEngine()

    def test_nonexistent_flow_returns_error(self):
        results = self.engine.run_flow("nonexistent_flow", {})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "error")
        self.assertIn("not found", results[0].name.lower())

    def test_missing_action_returns_error(self):
        results = self.engine.run_flow("internet_slow", {})  # No actions provided
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].status, "error")
        self.assertIn("not implemented", results[0].details.lower())

    def test_successful_flow_execution(self):
        """Mock a simple flow where all checks pass."""
        mock_actions = {}
        for action_name in FLOW_ACTIONS:
            mock_actions[action_name] = lambda: {"success": True, "details": "All good"}

        results = self.engine.run_flow("internet_slow", mock_actions)
        self.assertGreater(len(results), 0)
        # At least some steps should have run
        statuses = [r.status for r in results]
        self.assertTrue(any(s == "ok" for s in statuses))

    def test_flow_branches_on_failure(self):
        """Mock a flow where the first check fails."""
        call_log = []

        def fail_action():
            call_log.append("fail")
            return {"success": False, "details": "Failed"}

        def fix_action():
            call_log.append("fix")
            return {"success": True, "details": "Fixed"}

        def pass_action():
            call_log.append("pass")
            return {"success": True, "details": "OK"}

        # For internet_slow: first step is check_network_adapter
        # On failure, it should go to fix_adapter
        actions = {
            "check_network_adapter": fail_action,
            "fix_adapter": fix_action,
            "check_dns_resolution": pass_action,
            "fix_dns": pass_action,
            "check_ping": pass_action,
            "measure_bandwidth": lambda: {"success": True, "details": "OK", "download_mbps": 50},
            "check_wifi_signal": pass_action,
            "check_background_usage": pass_action,
        }

        results = self.engine.run_flow("internet_slow", actions)
        self.assertGreater(len(results), 1)
        # First step should show failure
        self.assertNotEqual(results[0].status, "ok")
        # Should have branched to fix
        self.assertIn("fix", call_log)

    def test_loop_prevention(self):
        """Verify that visited-set prevents infinite loops."""
        actions = {}
        for name in FLOW_ACTIONS:
            actions[name] = lambda: {"success": True, "details": "OK"}

        results = self.engine.run_flow("internet_slow", actions)
        # Should terminate (not infinite loop)
        self.assertLessEqual(len(results), 20)


class TestConditionEvaluation(unittest.TestCase):
    """Test the condition evaluator."""

    def setUp(self):
        self.engine = FlowEngine()

    def test_less_than(self):
        self.assertTrue(self.engine._evaluate_condition(
            "result.download_mbps < 1", {"download_mbps": 0.5}
        ))
        self.assertFalse(self.engine._evaluate_condition(
            "result.download_mbps < 1", {"download_mbps": 5}
        ))

    def test_greater_than(self):
        self.assertTrue(self.engine._evaluate_condition(
            "result.job_count > 0", {"job_count": 3}
        ))
        self.assertFalse(self.engine._evaluate_condition(
            "result.job_count > 0", {"job_count": 0}
        ))

    def test_missing_field(self):
        self.assertFalse(self.engine._evaluate_condition(
            "result.nonexistent < 5", {}
        ))

    def test_empty_expression(self):
        self.assertFalse(self.engine._evaluate_condition("", {}))

    def test_equal(self):
        self.assertTrue(self.engine._evaluate_condition(
            "result.status == 'ok'", {"status": "ok"}
        ))

    def test_not_equal(self):
        self.assertTrue(self.engine._evaluate_condition(
            "result.status != 'ok'", {"status": "error"}
        ))


class TestFlowActions(unittest.TestCase):
    """Test the FLOW_ACTIONS registry."""

    def test_actions_not_empty(self):
        self.assertGreater(len(FLOW_ACTIONS), 0)

    def test_all_actions_callable(self):
        for name, fn in FLOW_ACTIONS.items():
            self.assertTrue(callable(fn), f"Action '{name}' is not callable")

    def test_expected_actions_exist(self):
        expected = [
            "check_network_adapter", "check_dns_resolution", "measure_bandwidth",
            "check_audio_service", "check_audio_devices", "check_volume",
            "check_spooler_service", "check_printers_installed",
            "check_cpu_usage", "check_memory_usage", "check_disk_space",
        ]
        for action in expected:
            self.assertIn(action, FLOW_ACTIONS, f"Action '{action}' not found")


if __name__ == "__main__":
    unittest.main()
