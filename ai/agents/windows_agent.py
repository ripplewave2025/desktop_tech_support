"""
Windows settings and native troubleshooting specialist.
"""

from __future__ import annotations

from typing import List

from .base import SpecialistAgent
from ..task_types import AgentRoute, ExecutionStep, OEMProfile, ResearchPacket, TaskIntent


class WindowsAgent(SpecialistAgent):
    name = "WindowsAgent"
    allowed_tools = [
        "change_windows_setting",
        "run_powershell",
        "open_url",
        # Phase 3: Windows recipes drive native Settings UI through OCR clicks
        # and can pause for a user name / device name before continuing.
        "gui_click_label",
        "gui_read_labels",
        "gui_fill_labeled_field",
        "gui_wizard_next",
        "ask_user",
        "select_from_list",
        "user_profile_get",
        "user_profile_set",
        "notify",
        "launch_app",
        "manage_files",
    ]

    async def build_steps(
        self,
        intent: TaskIntent,
        route: AgentRoute,
        research: ResearchPacket,
        profile: OEMProfile,
    ) -> List[ExecutionStep]:
        lowered = intent.raw_message.lower()
        if "dark mode" in lowered:
            return [
                ExecutionStep(
                    step_id="windows-dark-mode",
                    title="Enable dark mode",
                    description="Switch Windows apps to dark mode.",
                    kind="tool",
                    agent_name=self.name,
                    tool_name="change_windows_setting",
                    tool_args={"setting": "enable_dark_mode"},
                )
            ]
        if "default browser" in lowered:
            return [
                ExecutionStep(
                    step_id="windows-default-browser",
                    title="Open Default Apps settings",
                    description="Launch the Default Apps page so the browser can be changed safely.",
                    kind="tool",
                    agent_name=self.name,
                    tool_name="change_windows_setting",
                    tool_args={"setting": "open_settings_page", "value": "defaultapps"},
                )
            ]
        if "update" in lowered:
            return [
                ExecutionStep(
                    step_id="windows-update",
                    title="Open Windows Update",
                    description="Open the Windows Update page.",
                    kind="tool",
                    agent_name=self.name,
                    tool_name="change_windows_setting",
                    tool_args={"setting": "check_updates"},
                )
            ]
        return [
            ExecutionStep(
                step_id="windows-settings-generic",
                title="Open the right Windows settings page",
                description="Use the Windows settings deep link for the requested task.",
                kind="tool",
                agent_name=self.name,
                tool_name="change_windows_setting",
                tool_args={"setting": "open_settings_page", "value": ""},
            )
        ]
