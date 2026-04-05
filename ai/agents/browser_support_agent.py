"""
Browser and vendor-portal specialist.
"""

from __future__ import annotations

from typing import List

from .base import SpecialistAgent
from ..task_types import AgentRoute, ExecutionStep, OEMProfile, ResearchPacket, TaskIntent


class BrowserSupportAgent(SpecialistAgent):
    name = "BrowserSupportAgent"
    allowed_tools = [
        "open_url",
        "notify",
        # Playwright DOM-first primitives (Phase 2).
        "browser_open",
        "browser_click",
        "browser_fill",
        "browser_read_text",
        "browser_close",
        # Community knowledge tools.
        "community_search",
        "summarize_page",
        # OCR-driven GUI clicks are allowed inside browser recipes
        # for cases where the page renders inside a native app shell
        # (e.g. the Zoom desktop client launched from a join link).
        "gui_click_label",
        "gui_read_labels",
        "gui_fill_labeled_field",
        "gui_wizard_next",
        # Lets the recipe pause to collect missing values (e.g. meeting ID).
        "ask_user",
        "select_from_list",
        "user_profile_get",
        "user_profile_set",
    ]

    async def build_steps(
        self,
        intent: TaskIntent,
        route: AgentRoute,
        research: ResearchPacket,
        profile: OEMProfile,
    ) -> List[ExecutionStep]:
        selected = research.selected
        url = selected.url if selected else "https://support.microsoft.com/"
        steps = [
            ExecutionStep(
                step_id="browser-open-source",
                title="Open the selected support page",
                description="Open the most trusted support or product page in the browser.",
                kind="tool",
                agent_name=self.name,
                tool_name="open_url",
                tool_args={"url": url},
            )
        ]
        if intent.needs_manual_login:
            steps.append(
                ExecutionStep(
                    step_id="browser-manual-login",
                    title="Pause for manual sign-in",
                    description="User must complete login and 2FA manually before automation continues.",
                    kind="manual",
                    agent_name=self.name,
                    manual_gate=True,
                    requires_confirmation=True,
                )
            )
        return steps
