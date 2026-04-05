"""
OEM tooling specialist.
"""

from __future__ import annotations

from typing import Dict, List

from .base import SpecialistAgent
from ..task_types import AgentRoute, ExecutionStep, OEMProfile, ResearchPacket, TaskIntent


class BaseVendorOEMAgent(SpecialistAgent):
    fallback_url = "https://support.microsoft.com/"
    preferred_tools: List[str] = []

    def _pick_installed_tool(self, profile: OEMProfile):
        installed = {tool.name: tool for tool in profile.tools if tool.status == "installed"}
        for name in self.preferred_tools:
            if name in installed:
                return installed[name]
        return next((tool for tool in profile.tools if tool.status == "installed"), None)

    def _pick_support_url(self, research: ResearchPacket) -> str:
        selected = research.selected
        if selected and selected.url.startswith(("https://", "http://")):
            return selected.url
        return self.fallback_url

    async def build_steps(
        self,
        intent: TaskIntent,
        route: AgentRoute,
        research: ResearchPacket,
        profile: OEMProfile,
    ) -> List[ExecutionStep]:
        preferred = self._pick_installed_tool(profile)
        if preferred:
            args = [*preferred.launch_args] if preferred.launch_args else []
            return [
                ExecutionStep(
                    step_id=f"oem-launch-{preferred.name.lower().replace(' ', '-').replace('|', '').replace('--', '-')}",
                    title=f"Open {preferred.name}",
                    description=f"Launch the official {preferred.vendor.upper()} support tool.",
                    kind="tool",
                    agent_name=self.name,
                    tool_name="launch_app",
                    tool_args={"path": preferred.path or preferred.executable, "args": args},
                )
            ]

        return [
            ExecutionStep(
                step_id=f"oem-open-{profile.vendor_slug}-support",
                title="Open the official OEM support page",
                description="Open the official vendor support page because the preferred support tool is not installed.",
                kind="tool",
                agent_name=self.name,
                tool_name="open_url",
                tool_args={"url": self._pick_support_url(research)},
            )
        ]


class DellAgent(BaseVendorOEMAgent):
    name = "DellAgent"
    allowed_tools = ["launch_app", "open_url"]
    fallback_url = "https://www.dell.com/support/home/"
    preferred_tools = ["SupportAssist", "Dell Command | Update"]


class HPAgent(BaseVendorOEMAgent):
    name = "HPAgent"
    allowed_tools = ["launch_app", "open_url"]
    fallback_url = "https://support.hp.com/"
    preferred_tools = ["HP Support Assistant", "HP Image Assistant"]


class LenovoAgent(BaseVendorOEMAgent):
    name = "LenovoAgent"
    allowed_tools = ["launch_app", "open_url"]
    fallback_url = "https://support.lenovo.com/"
    preferred_tools = ["Lenovo Vantage", "Thin Installer"]


class GenericOEMAgent(BaseVendorOEMAgent):
    name = "GenericOEMAgent"
    allowed_tools = ["open_url"]


class OEMAgent(SpecialistAgent):
    name = "OEMAgent"
    allowed_tools = [
        "launch_app",
        "open_url",
        "run_powershell",
        # Phase 4: OEM deep recipes drive vendor apps (SupportAssist,
        # Dell Command | Update, HP Support Assistant, Lenovo Vantage)
        # via OCR clicks + user-acknowledged manual gates.
        "gui_click_label",
        "gui_read_labels",
        "gui_wizard_next",
        "notify",
        "ask_user",
    ]

    def __init__(self):
        self._delegates: Dict[str, BaseVendorOEMAgent] = {
            "dell": DellAgent(),
            "hp": HPAgent(),
            "lenovo": LenovoAgent(),
            "generic": GenericOEMAgent(),
        }

    def _delegate_for(self, profile: OEMProfile) -> BaseVendorOEMAgent:
        return self._delegates.get(profile.vendor_slug, self._delegates["generic"])

    async def build_steps(
        self,
        intent: TaskIntent,
        route: AgentRoute,
        research: ResearchPacket,
        profile: OEMProfile,
    ) -> List[ExecutionStep]:
        return await self._delegate_for(profile).build_steps(intent, route, research, profile)

    async def hydrate_steps(
        self,
        playbook_steps: List[ExecutionStep],
        intent: TaskIntent,
        route: AgentRoute,
        research: ResearchPacket,
        profile: OEMProfile,
    ) -> List[ExecutionStep]:
        # If the playbook references an OEM preferred tool but none is installed, we
        # can't produce a usable launch_app step — fall back to the vendor delegate,
        # which knows how to pick either a tool path or a vendor support URL.
        references_preferred = any(
            "{oem.preferred_tool_" in str(value)
            for step in playbook_steps
            for value in (step.tool_args or {}).values()
        )
        has_installed_tool = any(tool.status == "installed" for tool in profile.tools)
        if references_preferred and not has_installed_tool:
            return await self._delegate_for(profile).build_steps(intent, route, research, profile)
        return await super().hydrate_steps(playbook_steps, intent, route, research, profile)
