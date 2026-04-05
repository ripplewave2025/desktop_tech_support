"""
Research aggregation and source ranking.
"""

from __future__ import annotations

from typing import Dict, List
import re

from .knowledge import KnowledgeLoader
from .policy import PolicyEngine
from .task_types import AgentRoute, OEMProfile, ResearchPacket, SourceAttribution, TaskIntent


class ResearchService:
    def __init__(self, knowledge: KnowledgeLoader, policy: PolicyEngine, executor):
        self._knowledge = knowledge
        self._policy = policy
        self._executor = executor

    async def gather(
        self,
        intent: TaskIntent,
        route: AgentRoute,
        profile: OEMProfile,
    ) -> ResearchPacket:
        packet = self._knowledge.build_research_packet(intent, route.agent_name, profile)
        query = self._build_query(intent, route, profile)
        packet.query = query
        matched = self._knowledge.select_playbook(intent, route.agent_name, profile)
        if matched is not None:
            packet.matched_playbook_id = matched.issue_id
            packet.playbook_steps = list(matched.steps)
        web_result = await self._executor.execute("web_search", {"query": query})
        for item in web_result.get("results", []):
            url = item.get("url", "")
            officialness = self._policy.classify_url(url)
            confidence = 0.25 + self._policy.confidence_bonus(url)
            confidence += self._message_overlap(intent.raw_message, item.get("title", ""), item.get("snippet", ""))
            packet.candidates.append(
                SourceAttribution(
                    title=item.get("title", "Search result"),
                    url=url,
                    snippet=item.get("snippet", ""),
                    officialness=officialness,
                    confidence=round(min(confidence, 0.98), 2),
                    source_type="web",
                    risk="low" if officialness in {"official", "local"} else "medium",
                )
            )
        packet.candidates = self._rank(packet.candidates)
        packet.selected_index = 0 if packet.candidates else -1
        return packet

    def _build_query(self, intent: TaskIntent, route: AgentRoute, profile: OEMProfile) -> str:
        parts = [intent.normalized_goal]
        if profile.vendor_slug != "generic":
            parts.append(profile.vendor_slug)
            if route.agent_name == "OEMAgent":
                parts.append("support tool")
        if intent.target_app:
            parts.append(intent.target_app)
        if intent.target_domain:
            parts.append(intent.target_domain)
        return " ".join(part for part in parts if part)

    def _message_overlap(self, message: str, title: str, snippet: str) -> float:
        tokens = {token for token in re.findall(r"[a-z0-9]+", message.lower()) if len(token) > 2}
        if not tokens:
            return 0.0
        text = f"{title} {snippet}".lower()
        hits = sum(1 for token in tokens if token in text)
        return min(hits * 0.05, 0.25)

    def _rank(self, candidates: List[SourceAttribution]) -> List[SourceAttribution]:
        deduped: Dict[str, SourceAttribution] = {}
        for candidate in candidates:
            key = candidate.url or candidate.title
            current = deduped.get(key)
            if current is None or candidate.confidence > current.confidence:
                deduped[key] = candidate
        return sorted(deduped.values(), key=lambda item: item.confidence, reverse=True)
