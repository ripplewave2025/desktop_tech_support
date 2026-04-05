"""
Desktop navigation specialist for generic on-screen tasks.
"""

from __future__ import annotations

from typing import List

from .base import SpecialistAgent
from ..task_types import AgentRoute, ExecutionStep, OEMProfile, ResearchPacket, TaskIntent


class DesktopNavigationAgent(SpecialistAgent):
    name = "DesktopNavigationAgent"
    allowed_tools = ["screenshot_and_analyze", "list_windows", "focus_window"]

    async def build_steps(
        self,
        intent: TaskIntent,
        route: AgentRoute,
        research: ResearchPacket,
        profile: OEMProfile,
    ) -> List[ExecutionStep]:
        return [
            ExecutionStep(
                step_id="desktop-analyze-screen",
                title="Analyze the current screen",
                description="Inspect the current screen before acting.",
                kind="tool",
                agent_name=self.name,
                tool_name="screenshot_and_analyze",
                tool_args={"prompt": f"Describe the controls relevant to: {intent.normalized_goal}"},
            ),
            ExecutionStep(
                step_id="desktop-list-windows",
                title="List open windows",
                description="Identify the app window that matches the request.",
                kind="tool",
                agent_name=self.name,
                tool_name="list_windows",
                tool_args={},
            ),
        ]
