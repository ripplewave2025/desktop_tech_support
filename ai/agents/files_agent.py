"""
File search and organization specialist.
"""

from __future__ import annotations

from typing import List

from .base import SpecialistAgent
from ..task_types import AgentRoute, ExecutionStep, OEMProfile, ResearchPacket, TaskIntent


class FilesAgent(SpecialistAgent):
    name = "FilesAgent"
    allowed_tools = ["manage_files"]

    async def build_steps(
        self,
        intent: TaskIntent,
        route: AgentRoute,
        research: ResearchPacket,
        profile: OEMProfile,
    ) -> List[ExecutionStep]:
        lowered = intent.raw_message.lower()
        if any(term in lowered for term in ("organize", "clean up", "cleanup")):
            return [
                ExecutionStep(
                    step_id="files-organize-downloads",
                    title="Organize files by type",
                    description="Sort files into folders by file type.",
                    kind="tool",
                    agent_name=self.name,
                    tool_name="manage_files",
                    tool_args={"action": "organize_by_type", "path": "~/Downloads"},
                    requires_confirmation=True,
                )
            ]

        pattern = "*"
        if intent.target_file:
            pattern = f"*{intent.target_file}*"
        elif "pdf" in lowered:
            pattern = "*.pdf"

        return [
            ExecutionStep(
                step_id="files-find",
                title="Search common user folders",
                description="Search the user profile for matching files.",
                kind="tool",
                agent_name=self.name,
                tool_name="manage_files",
                tool_args={"action": "find", "path": "~", "pattern": pattern},
            )
        ]
