"""
User-facing narration helpers.
"""

from __future__ import annotations

from ..providers import AIMessage
from ..task_types import ExecutionPlan


class ConciergeAgent:
    SYSTEM_PROMPT = (
        "You are Zora's concierge agent. Summarize plans in plain English for a "
        "non-technical Windows user. Mention the selected specialist, what will "
        "happen next, and whether a confirmation will be required. Keep it to "
        "three short sentences."
    )

    def _default_summary(self, plan: ExecutionPlan) -> str:
        if plan.consent_gates:
            return (
                f"I routed this to {plan.route.agent_name}. "
                f"I found {len(plan.sources)} trusted source(s) and planned {len(plan.steps)} step(s). "
                "I will stop before anything sensitive and ask you first."
            )
        return (
            f"I routed this to {plan.route.agent_name}. "
            f"I found {len(plan.sources)} source(s) and planned {len(plan.steps)} step(s). "
            "This path is safe to run automatically."
        )

    async def summarize(self, plan: ExecutionPlan, provider=None) -> str:
        fallback = self._default_summary(plan)
        if provider is None:
            return fallback

        try:
            summary = await provider.chat(
                messages=[
                    AIMessage(role="system", content=self.SYSTEM_PROMPT),
                    AIMessage(role="user", content=str(plan.to_dict())),
                ],
                temperature=0.2,
                max_tokens=220,
            )
            return summary.message.content.strip() or fallback
        except Exception:
            return fallback
