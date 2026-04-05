"""
Knowledge-pack loading and playbook matching.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml

from .task_types import ExecutionStep, OEMProfile, ResearchPacket, SourceAttribution, TaskIntent


def _tag_matches(tag: str, lowered_message: str) -> bool:
    """Return True if ``tag`` is present in ``lowered_message`` at word boundaries.

    We use word-boundary matching (rather than plain substring) to avoid
    the ``lock`` / ``unlock`` collision — otherwise a tag of ``"lock the
    front"`` would erroneously match an ``"unlock the front door"``
    query because the substring happens to appear inside ``unlock``.

    Tags that contain characters regex doesn't treat as word chars on
    both sides (e.g. ``"support.microsoft.com"``) still work because
    ``\\b`` matches between any word char and any non-word char.
    """
    if not tag:
        return False
    t = tag.lower()
    try:
        pattern = r"\b" + re.escape(t) + r"\b"
        return re.search(pattern, lowered_message) is not None
    except re.error:
        return t in lowered_message


@dataclass
class KnowledgePlaybook:
    issue_id: str
    title: str
    route: str
    summary: str
    tags: List[str] = field(default_factory=list)
    oems: List[str] = field(default_factory=list)
    sources: List[SourceAttribution] = field(default_factory=list)
    steps: List[ExecutionStep] = field(default_factory=list)

    def score(self, message: str, route: str, vendor_slug: str) -> float:
        lowered = message.lower()
        tag_hits = sum(1 for tag in self.tags if _tag_matches(tag, lowered))
        score = tag_hits * 0.15
        if self.route == route:
            score += 0.25
        if not self.oems or vendor_slug in self.oems or "generic" in self.oems:
            score += 0.20
        return score


@dataclass
class KnowledgePack:
    name: str
    version: str
    issuer: str
    signature: str
    hash: str
    playbooks: List[KnowledgePlaybook]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "issuer": self.issuer,
            "signature": self.signature,
            "hash": self.hash,
            "playbooks": [playbook.issue_id for playbook in self.playbooks],
        }


class KnowledgeLoader:
    def __init__(self, base_dir: str | None = None):
        root = Path(base_dir or Path(__file__).resolve().parents[1] / "knowledge" / "packs")
        self._base_dir = root
        self._packs: List[KnowledgePack] = []
        self._load()

    @property
    def packs(self) -> List[KnowledgePack]:
        return list(self._packs)

    def _load(self) -> None:
        self._packs = []
        if not self._base_dir.exists():
            return
        for manifest_path in self._base_dir.glob("*/manifest.json"):
            pack_dir = manifest_path.parent
            # Tolerate UTF-8 BOM on Windows-authored manifests.
            payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            playbook_path = pack_dir / payload.get("playbooks_file", "playbooks.yaml")
            if not playbook_path.exists():
                continue
            raw_text = playbook_path.read_text(encoding="utf-8-sig")
            digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
            loaded = yaml.safe_load(raw_text) or []
            playbooks: List[KnowledgePlaybook] = []
            for item in loaded:
                sources = [SourceAttribution(**source) for source in item.get("sources", [])]
                steps = [ExecutionStep(**step) for step in item.get("steps", [])]
                playbooks.append(
                    KnowledgePlaybook(
                        issue_id=item["issue_id"],
                        title=item["title"],
                        route=item["route"],
                        summary=item["summary"],
                        tags=item.get("tags", []),
                        oems=item.get("oems", []),
                        sources=sources,
                        steps=steps,
                    )
                )
            self._packs.append(
                KnowledgePack(
                    name=payload["name"],
                    version=payload["version"],
                    issuer=payload.get("issuer", "unknown"),
                    signature=payload.get("signature", ""),
                    hash=digest,
                    playbooks=playbooks,
                )
            )

    def current_version(self) -> Dict[str, Any]:
        return {
            "packs": [pack.to_dict() for pack in self._packs],
            "total_playbooks": sum(len(pack.playbooks) for pack in self._packs),
        }

    def match_playbooks(
        self,
        intent: TaskIntent,
        route_name: str,
        profile: OEMProfile,
    ) -> List[KnowledgePlaybook]:
        scored: List[tuple[float, KnowledgePlaybook]] = []
        for pack in self._packs:
            for playbook in pack.playbooks:
                score = playbook.score(intent.raw_message, route_name, profile.vendor_slug)
                if score >= 0.25:
                    scored.append((score, playbook))
        # Stable sort: by score desc, then by issue_id asc for deterministic tiebreaking.
        scored.sort(key=lambda item: (-item[0], item[1].issue_id))
        return [playbook for _, playbook in scored[:5]]

    def select_playbook(
        self,
        intent: TaskIntent,
        route_name: str,
        profile: OEMProfile,
    ) -> "KnowledgePlaybook | None":
        """Return the top-scoring playbook for this intent, if any, that has steps."""
        matches = self.match_playbooks(intent, route_name, profile)
        for playbook in matches:
            if playbook.steps:
                return playbook
        return None

    def build_research_packet(
        self,
        intent: TaskIntent,
        route_name: str,
        profile: OEMProfile,
    ) -> ResearchPacket:
        playbooks = self.match_playbooks(intent, route_name, profile)
        candidates: List[SourceAttribution] = []
        for playbook in playbooks:
            if playbook.sources:
                for source in playbook.sources:
                    candidates.append(source)
            else:
                candidates.append(
                    SourceAttribution(
                        title=playbook.title,
                        url="local://knowledge-pack/" + playbook.issue_id,
                        snippet=playbook.summary,
                        officialness="local",
                        confidence=0.9,
                        source_type="knowledge_pack",
                        risk="low",
                    )
                )
        return ResearchPacket(
            query=intent.normalized_goal,
            candidates=candidates,
            notes=[playbook.summary for playbook in playbooks],
            selected_index=0,
        )
