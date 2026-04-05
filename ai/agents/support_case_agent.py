"""
Support case drafting and tracking specialist.
"""

from __future__ import annotations

from typing import List

from .base import SpecialistAgent
from ..task_types import AgentRoute, ExecutionStep, OEMProfile, ResearchPacket, TaskIntent


class SupportCaseAgent(SpecialistAgent):
    name = "SupportCaseAgent"
    allowed_tools = ["create_support_ticket", "open_url", "notify"]

    async def build_steps(
        self,
        intent: TaskIntent,
        route: AgentRoute,
        research: ResearchPacket,
        profile: OEMProfile,
    ) -> List[ExecutionStep]:
        selected = research.selected
        steps = [
            ExecutionStep(
                step_id="support-ticket-draft",
                title="Create a local support draft",
                description="Create a local ticket bundle with system info and screenshots.",
                kind="tool",
                agent_name=self.name,
                tool_name="create_support_ticket",
                tool_args={"issue_summary": intent.normalized_goal, "steps_tried": "; ".join(research.notes[:3])},
            )
        ]
        if selected and selected.url:
            steps.append(
                ExecutionStep(
                    step_id="support-open-portal",
                    title="Open the support portal",
                    description="Open the selected vendor or Microsoft support page.",
                    kind="tool",
                    agent_name=self.name,
                    tool_name="open_url",
                    tool_args={"url": selected.url},
                )
            )
        steps.append(
            ExecutionStep(
                step_id="support-final-submit",
                title="Pause before final submit",
                description="Do not submit the support request without explicit confirmation.",
                kind="manual",
                agent_name=self.name,
                manual_gate=True,
                requires_confirmation=True,
                irreversible=True,
            )
        )
        return steps
