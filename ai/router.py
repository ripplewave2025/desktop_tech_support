"""
Rule-based router for the specialist agent team.
"""

from __future__ import annotations

import re

from .policy import PolicyEngine
from .task_types import AgentRoute, OEMProfile, TaskIntent


class RouterAgent:
    def __init__(self, policy: PolicyEngine | None = None):
        self._policy = policy or PolicyEngine()

    def build_intent(self, message: str, profile: OEMProfile) -> TaskIntent:
        lowered = message.lower()
        target_file = self._extract_target_file(message)
        target_domain = self._extract_domain(lowered)
        target_app = self._extract_app_hint(lowered, profile)
        route = self.route(message, profile)
        return TaskIntent(
            raw_message=message,
            normalized_goal=message.strip(),
            route_hint=route.agent_name,
            risk=self._policy.detect_risk(message),
            target_app=target_app,
            target_domain=target_domain,
            target_file=target_file,
            requires_web=route.requires_research,
            requires_browser=route.agent_name in {"BrowserSupportAgent", "SupportCaseAgent"},
            needs_manual_login=self._policy.requires_manual_login(message),
        )

    def route(self, message: str, profile: OEMProfile) -> AgentRoute:
        lowered = message.lower()
        risk = self._policy.detect_risk(message)
        # Phase 7: smart-home keywords. Checked before SupportCase so that
        # "turn off the kitchen lights" doesn't get pulled into ticketing
        # by the "turn off" verb.
        if any(
            term in lowered
            for term in (
                # devices
                "light", "lamp", "lights", "bulb", "dimmer",
                "thermostat", "temperature", "climate", "heat",
                "lock", "unlock", "deadbolt", "door",
                "alarm", "arm ", "disarm", "security system",
                "scene", "mood", "movie mode", "away mode", "home mode",
                "vacuum", "robot vacuum", "roomba",
                "blind", "blinds", "curtain", "curtains", "shade",
                # hubs
                "home assistant", "homeassistant", "hue bridge", "philips hue",
                "mqtt", "zigbee", "smart home", "smart-home", "smarthome",
                "smart plug", "smart switch",
            )
        ):
            return AgentRoute("SmartHomeAgent", "Smart-home workflow", "smart_home", risk, True)
        if any(
            term in lowered
            for term in (
                "ticket", "case", "contact support", "support request", "follow up",
                # Phase 4b: case status / follow-up check-in triggers.
                "any updates", "check in", "heard back", "case status",
                "any word",
            )
        ):
            return AgentRoute("SupportCaseAgent", "Support workflow requested", "support", risk, True)
        if any(
            term in lowered
            for term in (
                "facebook", "form", "website", "portal", "browser", "login", "sign in",
                # Phase 2: meeting + community tech support triggers.
                "zoom", "teams meeting", "join meeting", "meet.google", "google meet",
                "stack overflow", "stackoverflow", "superuser", "reddit",
                "community help", "how do i fix", "error message",
            )
        ):
            return AgentRoute("BrowserSupportAgent", "Browser or support site workflow", "browser", risk, True)
        if any(term in lowered for term in ("dell", "supportassist", "command update", "hp ", "hpia", "lenovo", "vantage", "thin installer", "driver", "bios", "hardware check")):
            return AgentRoute("OEMAgent", "OEM tooling or hardware workflow", "oem", risk, True)
        if any(
            term in lowered
            for term in (
                "dark mode", "settings", "windows update", "bluetooth",
                "default browser", "power plan", "volume",
                # Phase 3: device pairing, Phone Link, installer wizards.
                "pair", "airpods", "headphones", "earbuds",
                "phone link", "link phone", "connect my phone",
                "install setup", "install the", "run setup", "run installer",
                "setup.exe", "installer",
            )
        ):
            return AgentRoute("WindowsAgent", "Windows settings workflow", "windows", risk, True)
        if any(term in lowered for term in ("file", "folder", "find", "downloads", "desktop", "documents", "organize")):
            return AgentRoute("FilesAgent", "File organization or search", "files", "low", True)
        if any(term in lowered for term in ("click", "open", "navigate", "screen")):
            return AgentRoute("DesktopNavigationAgent", "Desktop navigation request", "navigation", risk, True)
        if profile.vendor_slug in {"dell", "hp", "lenovo"} and any(term in lowered for term in ("scan", "diagnostic", "driver update")):
            return AgentRoute("OEMAgent", "OEM-aware support path", "oem", risk, True)
        return AgentRoute("WindowsAgent", "Default Windows help path", "windows", risk, True)

    def _extract_target_file(self, message: str) -> str:
        match = re.search(r"(?:file|document|pdf|photo|picture)\s+(?:called|named)?\s*['\"]?([^'\"]+)['\"]?", message, re.I)
        return match.group(1).strip() if match else ""

    def _extract_domain(self, lowered: str) -> str:
        for domain in ("facebook", "gmail", "outlook", "support", "portal", "microsoft", "dell", "hp", "lenovo"):
            if domain in lowered:
                return domain
        return ""

    def _extract_app_hint(self, lowered: str, profile: OEMProfile) -> str:
        if profile.vendor_slug == "dell" and any(term in lowered for term in ("driver", "supportassist", "command update")):
            return "SupportAssist"
        if profile.vendor_slug == "hp" and any(term in lowered for term in ("driver", "support assistant", "hpia")):
            return "HP Support Assistant"
        if profile.vendor_slug == "lenovo" and any(term in lowered for term in ("driver", "vantage", "thin installer")):
            return "Lenovo Vantage"
        return ""
