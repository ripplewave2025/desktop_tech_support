"""
Flow Engine — execute YAML decision trees with branching logic.

Walks through diagnostic flows step-by-step, branching based on
results. Unlike flat diagnostics, flows follow the same logic a
real tech support person would: check A -> if fail, try B -> if
B works, verify -> done.
"""

import os
import logging
from typing import Dict, List, Any, Optional

from diagnostics.base import DiagnosticResult, TechSupportNarrator

logger = logging.getLogger("zora.flow_engine")


class FlowEngine:
    """Execute YAML decision trees with branching logic."""

    def __init__(self, flows_dir: Optional[str] = None):
        if flows_dir is None:
            flows_dir = os.path.join(os.path.dirname(__file__), "flows")
        self._flows_dir = flows_dir
        self._flows: Dict[str, dict] = {}
        self._load_flows()

    def _load_flows(self):
        """Load all YAML flow definitions from the flows directory."""
        try:
            import yaml
        except ImportError:
            logger.warning("PyYAML not installed — flow-based diagnostics disabled")
            return

        if not os.path.isdir(self._flows_dir):
            logger.warning(f"Flows directory not found: {self._flows_dir}")
            return

        for filename in os.listdir(self._flows_dir):
            if not filename.endswith((".yaml", ".yml")):
                continue
            filepath = os.path.join(self._flows_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    flow = yaml.safe_load(f)
                if flow and "id" in flow and "steps" in flow:
                    self._flows[flow["id"]] = flow
                    logger.debug(f"Loaded flow: {flow['id']} ({len(flow['steps'])} steps)")
            except Exception as e:
                logger.error(f"Failed to load flow {filename}: {e}")

        logger.info(f"Loaded {len(self._flows)} diagnostic flows")

    @property
    def available_flows(self) -> List[Dict[str, str]]:
        """List available flow IDs and names."""
        return [
            {
                "id": f["id"],
                "name": f.get("name", f["id"]),
                "trigger_keywords": f.get("trigger_keywords", []),
            }
            for f in self._flows.values()
        ]

    def find_flow_for_query(self, query: str) -> Optional[str]:
        """Find the best matching flow for a user query."""
        query_lower = query.lower()
        for flow in self._flows.values():
            for keyword in flow.get("trigger_keywords", []):
                if keyword.lower() in query_lower:
                    return flow["id"]
        return None

    def run_flow(
        self,
        flow_id: str,
        actions: Dict[str, Any],
        narrator: Optional[TechSupportNarrator] = None,
    ) -> List[DiagnosticResult]:
        """Execute a flow decision tree.

        Args:
            flow_id: The flow identifier (e.g., "internet_slow")
            actions: Dict mapping action names to callable functions.
                     Each function takes no args and returns a dict with results.
            narrator: Optional narrator for logging progress.

        Returns:
            List of DiagnosticResult for each step executed.
        """
        if flow_id not in self._flows:
            return [DiagnosticResult(
                name=f"Flow '{flow_id}' not found",
                status="error",
                details=f"Available flows: {', '.join(self._flows.keys())}",
            )]

        flow = self._flows[flow_id]
        steps = {s["id"]: s for s in flow["steps"]}
        results = []
        visited = set()

        # Start from first step
        current_id = flow["steps"][0]["id"]

        while current_id and current_id not in visited:
            visited.add(current_id)
            step = steps.get(current_id)
            if not step:
                break

            if narrator:
                narrator.log.append(f"[Flow] Running step: {step.get('name', step['id'])}")

            # Execute the action
            action_name = step.get("action", "")
            action_fn = actions.get(action_name)

            if action_fn is None:
                result = DiagnosticResult(
                    name=step.get("name", step["id"]),
                    status="error",
                    details=f"Action '{action_name}' not implemented",
                )
                results.append(result)
                break

            try:
                action_result = action_fn()
                success = action_result.get("success", True)
                status = "ok" if success else action_result.get("status", "warning")

                result = DiagnosticResult(
                    name=step.get("name", step["id"]),
                    status=status,
                    details=action_result.get("details", ""),
                    fix_available=action_result.get("fix_available", False),
                )
                results.append(result)

                # Determine next step based on branching
                current_id = self._get_next_step(step, action_result, success)

            except Exception as e:
                result = DiagnosticResult(
                    name=step.get("name", step["id"]),
                    status="error",
                    details=f"Action failed: {e}",
                )
                results.append(result)
                # Try failure branch
                current_id = step.get("failure")

        return results

    def _get_next_step(self, step: dict, result: dict, success: bool) -> Optional[str]:
        """Determine next step based on result and branch conditions."""
        # Check conditions first (most specific)
        conditions = step.get("condition", [])
        for cond in conditions:
            if_expr = cond.get("if", "")
            if self._evaluate_condition(if_expr, result):
                return cond.get("goto")

        # Check else condition
        for cond in conditions:
            if "else" in cond:
                return cond.get("goto", cond.get("else"))

        # Simple success/failure branching
        if success:
            return step.get("success")
        else:
            return step.get("failure")

    def _evaluate_condition(self, expr: str, result: dict) -> bool:
        """Safely evaluate a simple condition expression.

        Supports: "result.field < value", "result.field > value",
                  "result.field == value", "result.field != value"
        """
        if not expr:
            return False

        try:
            # Parse simple expressions like "result.download_mbps < 1"
            expr = expr.strip()
            if expr.startswith("result."):
                expr = expr[7:]  # Remove "result."

            for op in ["<=", ">=", "!=", "==", "<", ">"]:
                if op in expr:
                    parts = expr.split(op, 1)
                    field = parts[0].strip()
                    value_str = parts[1].strip()

                    actual = result.get(field)
                    if actual is None:
                        return False

                    # Try numeric comparison
                    try:
                        actual_num = float(actual)
                        expected_num = float(value_str)
                        if op == "<":
                            return actual_num < expected_num
                        elif op == ">":
                            return actual_num > expected_num
                        elif op == "<=":
                            return actual_num <= expected_num
                        elif op == ">=":
                            return actual_num >= expected_num
                        elif op == "==":
                            return actual_num == expected_num
                        elif op == "!=":
                            return actual_num != expected_num
                    except (ValueError, TypeError):
                        # String comparison
                        if op == "==":
                            return str(actual) == value_str.strip("'\"")
                        elif op == "!=":
                            return str(actual) != value_str.strip("'\"")

        except Exception as e:
            logger.debug(f"Condition eval failed: {expr} — {e}")

        return False
