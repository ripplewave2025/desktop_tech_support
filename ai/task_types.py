"""
Typed models for the multi-agent orchestration layer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
import copy
import datetime as dt


def _utcnow() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


@dataclass
class SourceAttribution:
    title: str
    url: str
    snippet: str = ""
    officialness: str = "unofficial"
    confidence: float = 0.0
    applicable: bool = True
    risk: str = "medium"
    source_type: str = "web"
    recency: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceAttribution":
        return cls(**data)


@dataclass
class OEMTool:
    vendor: str
    name: str
    status: str
    executable: str = ""
    path: str = ""
    launch_args: List[str] = field(default_factory=list)
    notes: str = ""
    official_url: str = ""
    automation_mode: str = "gui"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OEMTool":
        return cls(**data)


@dataclass
class OEMProfile:
    manufacturer: str = "Unknown"
    model: str = "Unknown"
    serial_number: str = ""
    bios_version: str = ""
    detected_at: str = field(default_factory=_utcnow)
    tools: List[OEMTool] = field(default_factory=list)

    @property
    def vendor_slug(self) -> str:
        normalized = self.manufacturer.lower()
        if "dell" in normalized:
            return "dell"
        if "hp" in normalized or "hewlett" in normalized:
            return "hp"
        if "lenovo" in normalized:
            return "lenovo"
        return "generic"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["vendor_slug"] = self.vendor_slug
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OEMProfile":
        payload = dict(data)
        payload.pop("vendor_slug", None)
        payload["tools"] = [
            OEMTool.from_dict(item) if not isinstance(item, OEMTool) else item
            for item in payload.get("tools", [])
        ]
        return cls(**payload)


@dataclass
class TaskIntent:
    raw_message: str
    normalized_goal: str
    route_hint: str
    risk: str = "medium"
    target_app: str = ""
    target_domain: str = ""
    target_file: str = ""
    requires_web: bool = False
    requires_browser: bool = False
    needs_manual_login: bool = False
    clarifying_question: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskIntent":
        return cls(**data)


@dataclass
class AgentRoute:
    agent_name: str
    reason: str
    domain: str
    risk: str = "medium"
    requires_research: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentRoute":
        return cls(**data)


@dataclass
class ResearchPacket:
    query: str
    candidates: List[SourceAttribution] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    selected_index: int = 0
    generated_at: str = field(default_factory=_utcnow)
    matched_playbook_id: str = ""
    playbook_steps: List["ExecutionStep"] = field(default_factory=list)

    @property
    def selected(self) -> Optional[SourceAttribution]:
        if 0 <= self.selected_index < len(self.candidates):
            return self.candidates[self.selected_index]
        return None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["selected"] = self.selected.to_dict() if self.selected else None
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResearchPacket":
        payload = dict(data)
        payload.pop("selected", None)
        payload["candidates"] = [
            SourceAttribution.from_dict(item) if not isinstance(item, SourceAttribution) else item
            for item in payload.get("candidates", [])
        ]
        payload["playbook_steps"] = [
            ExecutionStep.from_dict(item) if not isinstance(item, ExecutionStep) else item
            for item in payload.get("playbook_steps", [])
        ]
        return cls(**payload)


@dataclass
class ExecutionStep:
    step_id: str
    title: str
    description: str
    kind: str
    agent_name: str
    tool_name: str = ""
    tool_args: Dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    irreversible: bool = False
    manual_gate: bool = False
    status: str = "pending"
    # Phase 5: conditional execution + retry polish.
    # ``skip_if`` is a simpleeval expression evaluated against {prev, user,
    # oem, intent}; if truthy, the step is skipped. ``continue_on_error``
    # keeps the plan moving past a failing step. ``retry`` re-runs the
    # tool up to N additional times on failure.
    skip_if: str = ""
    continue_on_error: bool = False
    retry: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionStep":
        # Tolerate older persisted plans that don't have the new fields.
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class ConsentGate:
    step_id: str
    reason: str
    risk: str
    required: bool = True
    status: str = "pending"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConsentGate":
        return cls(**data)


@dataclass
class EvidenceItem:
    kind: str
    title: str
    path: str = ""
    content: str = ""
    created_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceItem":
        return cls(**data)


@dataclass
class FollowUp:
    title: str
    due_at: str
    status: str = "open"
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FollowUp":
        return cls(**data)


@dataclass
class CaseRecord:
    case_id: str
    issue_summary: str
    portal_url: str = ""
    ticket_number: str = ""
    status: str = "draft"
    source_url: str = ""
    evidence: List[EvidenceItem] = field(default_factory=list)
    follow_ups: List[FollowUp] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "issue_summary": self.issue_summary,
            "portal_url": self.portal_url,
            "ticket_number": self.ticket_number,
            "status": self.status,
            "source_url": self.source_url,
            "evidence": [item.to_dict() for item in self.evidence],
            "follow_ups": [item.to_dict() for item in self.follow_ups],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CaseRecord":
        payload = dict(data)
        payload["evidence"] = [
            EvidenceItem.from_dict(item) if not isinstance(item, EvidenceItem) else item
            for item in payload.get("evidence", [])
        ]
        payload["follow_ups"] = [
            FollowUp.from_dict(item) if not isinstance(item, FollowUp) else item
            for item in payload.get("follow_ups", [])
        ]
        return cls(**payload)


@dataclass
class ExecutionPlan:
    task_id: str
    summary: str
    intent: TaskIntent
    route: AgentRoute
    steps: List[ExecutionStep]
    research: ResearchPacket
    oem_profile: OEMProfile
    consent_gates: List[ConsentGate] = field(default_factory=list)
    sources: List[SourceAttribution] = field(default_factory=list)
    case_record: Optional[CaseRecord] = None
    status: str = "planned"
    auto_execute: bool = False
    created_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "summary": self.summary,
            "intent": self.intent.to_dict(),
            "route": self.route.to_dict(),
            "steps": [step.to_dict() for step in self.steps],
            "research": self.research.to_dict(),
            "oem_profile": self.oem_profile.to_dict(),
            "consent_gates": [gate.to_dict() for gate in self.consent_gates],
            "sources": [source.to_dict() for source in self.sources],
            "case_record": self.case_record.to_dict() if self.case_record else None,
            "status": self.status,
            "auto_execute": self.auto_execute,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionPlan":
        payload = copy.deepcopy(data)
        payload["intent"] = TaskIntent.from_dict(payload["intent"])
        payload["route"] = AgentRoute.from_dict(payload["route"])
        payload["steps"] = [ExecutionStep.from_dict(item) for item in payload.get("steps", [])]
        payload["research"] = ResearchPacket.from_dict(payload["research"])
        payload["oem_profile"] = OEMProfile.from_dict(payload["oem_profile"])
        payload["consent_gates"] = [ConsentGate.from_dict(item) for item in payload.get("consent_gates", [])]
        payload["sources"] = [SourceAttribution.from_dict(item) for item in payload.get("sources", [])]
        if payload.get("case_record"):
            payload["case_record"] = CaseRecord.from_dict(payload["case_record"])
        return cls(**payload)
