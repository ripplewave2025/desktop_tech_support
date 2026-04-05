"""
Smart-home specialist agent.

Covers lights, switches, thermostats, locks, scenes, and vacuum / blinds
through whatever backend the user has connected:
  • Home Assistant (REST)
  • Philips Hue (direct LAN)
  • MQTT (raw pub/sub for advanced users)

All actual device calls go through the tool layer — this agent's job is
to pick the right playbook (handled at hydration time) and to produce a
friendly "what backend is connected?" fallback when none is configured.

Destructive actions (unlock, disarm, open door) are marked
``requires_confirmation=true`` + ``manual_gate=true`` by PolicyEngine's
runtime rules so the user has to explicitly confirm each invocation.
"""

from __future__ import annotations

from typing import List

from .base import SpecialistAgent
from ..smart_home import SmartHomeConfigStore
from ..task_types import AgentRoute, ExecutionStep, OEMProfile, ResearchPacket, TaskIntent


class SmartHomeAgent(SpecialistAgent):
    name = "SmartHomeAgent"
    allowed_tools = [
        "smart_home_list_entities",
        "smart_home_call",
        "smart_home_query",
        "smart_home_setup",
        "smart_home_discover_hue",
        "smart_home_set_alias",
        "mqtt_publish",
        "mqtt_subscribe",
        # Reuses from earlier phases: onboarding / disambiguation / feedback.
        "ask_user",
        "select_from_list",
        "user_profile_get",
        "user_profile_set",
        "notify",
    ]

    def __init__(self, config_store: SmartHomeConfigStore | None = None):
        self._config_store = config_store or SmartHomeConfigStore()

    async def build_steps(
        self,
        intent: TaskIntent,
        route: AgentRoute,
        research: ResearchPacket,
        profile: OEMProfile,
    ) -> List[ExecutionStep]:
        """Fallback path used when no smart-home playbook matches.

        If no backend is configured, guide the user to connect one.
        Otherwise, list entities so the user can see what's available.
        """
        config = self._config_store.load()
        if not config.any_configured():
            return [
                ExecutionStep(
                    step_id="smart-home-not-configured",
                    title="No smart-home hub connected yet",
                    description=(
                        "I don't see a Home Assistant, Hue bridge, or MQTT "
                        "broker configured. Want to connect one? Just ask "
                        "'connect my Home Assistant' or 'connect my Hue "
                        "bridge' and I'll walk you through it."
                    ),
                    kind="tool",
                    agent_name=self.name,
                    tool_name="notify",
                    tool_args={
                        "title": "Smart home not configured",
                        "message": "Ask me to 'connect my Home Assistant' or 'connect my Hue bridge' to get started.",
                    },
                )
            ]
        return [
            ExecutionStep(
                step_id="smart-home-list",
                title="List connected smart-home devices",
                description="Show everything Zora can currently control on the LAN.",
                kind="tool",
                agent_name=self.name,
                tool_name="smart_home_list_entities",
                tool_args={},
            )
        ]
