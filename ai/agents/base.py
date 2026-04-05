"""
Base specialist agent contract.
"""

from __future__ import annotations

import copy
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}")

from ..task_types import AgentRoute, ExecutionStep, OEMProfile, ResearchPacket, TaskIntent


class SafeDict(dict):
    """A dict that returns an empty string for missing keys instead of raising KeyError.

    Used for placeholder substitution in playbook tool_args — a missing field like
    {intent.target_file} becomes "" rather than crashing the plan.
    """

    def __missing__(self, key: str) -> str:
        return ""


def _flatten_for_placeholders(
    intent: TaskIntent,
    route: AgentRoute,
    research: ResearchPacket,
    profile: OEMProfile,
) -> SafeDict:
    """Build the flat namespace used for {placeholder} substitution in playbook args.

    Namespaces exposed:
      intent.*     — fields from TaskIntent
      route.*      — fields from AgentRoute
      research.*   — selected source fields plus query
      oem.*        — profile fields, vendor_slug, and the first installed tool via
                     oem.preferred_tool_name / _path / _exe / _vendor (empty if none).
    """
    ns: Dict[str, Any] = {}

    for key, value in intent.to_dict().items():
        ns[f"intent.{key}"] = "" if value is None else value
    for key, value in route.to_dict().items():
        ns[f"route.{key}"] = "" if value is None else value

    ns["research.query"] = research.query or ""
    selected = research.selected
    ns["research.selected_url"] = selected.url if selected else ""
    ns["research.selected_title"] = selected.title if selected else ""
    ns["research.selected_snippet"] = selected.snippet if selected else ""

    ns["oem.manufacturer"] = profile.manufacturer or ""
    ns["oem.model"] = profile.model or ""
    ns["oem.vendor_slug"] = profile.vendor_slug
    ns["oem.serial_number"] = profile.serial_number or ""
    ns["oem.bios_version"] = profile.bios_version or ""

    preferred = next((tool for tool in profile.tools if tool.status == "installed"), None)
    ns["oem.preferred_tool_name"] = preferred.name if preferred else ""
    ns["oem.preferred_tool_path"] = (preferred.path or preferred.executable) if preferred else ""
    ns["oem.preferred_tool_exe"] = preferred.executable if preferred else ""
    ns["oem.preferred_tool_vendor"] = preferred.vendor if preferred else ""

    return SafeDict(ns)


def _substitute(value: Any, namespace: SafeDict) -> Any:
    """Recursively substitute {placeholder} tokens in strings inside tool_args.

    Unlike str.format_map, this treats {a.b.c} as a single flat dict key lookup
    so that namespaces like ``oem.preferred_tool_name`` work without attribute
    access on the stored value. Placeholders not present in the namespace are
    left intact (instead of being blanked) so that late-binding namespaces
    like ``user.*`` can be resolved by the orchestrator at execute time.
    """
    def _replace(match: "re.Match[str]") -> str:
        key = match.group(1)
        if key in namespace:
            return str(namespace[key])
        return match.group(0)

    if isinstance(value, str):
        if "{" in value and "}" in value:
            return _PLACEHOLDER_RE.sub(_replace, value)
        return value
    if isinstance(value, list):
        return [_substitute(item, namespace) for item in value]
    if isinstance(value, dict):
        return {key: _substitute(item, namespace) for key, item in value.items()}
    return value


class SpecialistAgent(ABC):
    name = "SpecialistAgent"
    system_prompt = ""
    allowed_tools: List[str] = []

    @abstractmethod
    async def build_steps(
        self,
        intent: TaskIntent,
        route: AgentRoute,
        research: ResearchPacket,
        profile: OEMProfile,
    ) -> List[ExecutionStep]:
        raise NotImplementedError

    async def hydrate_steps(
        self,
        playbook_steps: List[ExecutionStep],
        intent: TaskIntent,
        route: AgentRoute,
        research: ResearchPacket,
        profile: OEMProfile,
    ) -> List[ExecutionStep]:
        """Clone a playbook's step template and substitute {placeholder} tokens in tool_args.

        Agents can override this to:
          • Inject computed arguments that YAML cannot express.
          • Fall back to build_steps() when required inputs are missing
            (e.g. OEMAgent falling back when no vendor tool is installed).
        """
        namespace = _flatten_for_placeholders(intent, route, research, profile)
        hydrated: List[ExecutionStep] = []
        for template in playbook_steps:
            step = copy.deepcopy(template)
            step.title = _substitute(step.title, namespace)
            step.description = _substitute(step.description, namespace)
            step.tool_args = _substitute(step.tool_args, namespace) if step.tool_args else {}
            step.status = "pending"
            hydrated.append(step)
        return hydrated
