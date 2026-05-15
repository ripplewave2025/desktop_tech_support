"""
Tests for the Expert/Novice mode toggle.

Coverage:
  * get_tools_for_model honors expert_mode (full catalog regardless of size)
  * ZoraAgent appends EXPERT_MODE_ADDENDUM when expert_mode=True
  * Default is novice mode (no addendum, size-based tool selection)
  * SettingsUpdate Pydantic model accepts expert_mode round-trip
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.tools import (
    TOOL_DEFINITIONS,
    CORE_TOOL_NAMES,
    get_tools_for_model,
)
from ai.agent import ZoraAgent, SYSTEM_PROMPT, EXPERT_MODE_ADDENDUM
from ai.providers import AIProvider, AIResponse, AIMessage


class StubProvider(AIProvider):
    """Tiny no-op provider for agent construction tests."""

    def __init__(self, name: str = "qwen2.5:7b"):
        self._name = name

    def name(self) -> str:
        return self._name

    async def chat(self, messages, tools=None, temperature=0.4):
        return AIResponse(message=AIMessage(role="assistant", content=""), tool_calls=[])

    async def chat_stream(self, messages, tools=None, temperature=0.4):
        yield ""


class TestToolSelection(unittest.TestCase):
    def test_small_model_default_returns_core_only(self):
        tools = get_tools_for_model("qwen2.5:7b", expert_mode=False)
        names = {t["function"]["name"] for t in tools}
        # Core set is a subset, none of the non-core ones leak in.
        self.assertTrue(names.issubset(set(CORE_TOOL_NAMES)) or names == set(CORE_TOOL_NAMES))
        self.assertGreater(len(names), 0)

    def test_small_model_expert_returns_full_catalog(self):
        novice = get_tools_for_model("qwen2.5:7b", expert_mode=False)
        expert = get_tools_for_model("qwen2.5:7b", expert_mode=True)
        self.assertGreater(len(expert), len(novice),
                           "expert mode must expose strictly more tools than novice on a small model")
        self.assertEqual(len(expert), len(TOOL_DEFINITIONS))

    def test_large_model_returns_full_in_both_modes(self):
        novice = get_tools_for_model("claude-sonnet-4", expert_mode=False)
        expert = get_tools_for_model("claude-sonnet-4", expert_mode=True)
        self.assertEqual(len(novice), len(TOOL_DEFINITIONS))
        self.assertEqual(len(expert), len(TOOL_DEFINITIONS))

    def test_default_is_novice(self):
        # Calling without the kwarg should behave exactly like expert_mode=False.
        with_default = get_tools_for_model("qwen2.5:7b")
        with_explicit = get_tools_for_model("qwen2.5:7b", expert_mode=False)
        self.assertEqual(
            {t["function"]["name"] for t in with_default},
            {t["function"]["name"] for t in with_explicit},
        )


class TestAgentSystemPrompt(unittest.TestCase):
    def test_default_agent_uses_base_prompt(self):
        agent = ZoraAgent(StubProvider())
        self.assertEqual(agent._system_prompt, SYSTEM_PROMPT)
        self.assertFalse(agent.expert_mode)

    def test_expert_agent_appends_addendum(self):
        agent = ZoraAgent(StubProvider(), expert_mode=True)
        self.assertTrue(agent.expert_mode)
        # Addendum is appended, not replacing.
        self.assertTrue(agent._system_prompt.startswith(SYSTEM_PROMPT))
        self.assertIn("EXPERT MODE", agent._system_prompt)
        self.assertIn("Power User", agent._system_prompt)

    def test_expert_addendum_contains_safety_assurance(self):
        # The addendum must explicitly state that safety gates remain in force,
        # otherwise the model might infer "expert mode = bypass safety".
        self.assertIn("Security gates", EXPERT_MODE_ADDENDUM)
        self.assertIn("STILL apply", EXPERT_MODE_ADDENDUM)

    def test_expert_agent_exposes_more_tools_on_small_model(self):
        novice_agent = ZoraAgent(StubProvider("qwen2.5:7b"), expert_mode=False)
        expert_agent = ZoraAgent(StubProvider("qwen2.5:7b"), expert_mode=True)
        self.assertGreater(len(expert_agent._tools), len(novice_agent._tools))

    def test_explicit_system_prompt_still_gets_addendum(self):
        # If a caller passes a custom system_prompt AND expert_mode=True, the
        # addendum still applies — the toggle is about behavior, not content.
        custom = "You are a test agent."
        agent = ZoraAgent(StubProvider(), system_prompt=custom, expert_mode=True)
        self.assertTrue(agent._system_prompt.startswith(custom))
        self.assertIn("EXPERT MODE", agent._system_prompt)


class TestSettingsModel(unittest.TestCase):
    def test_settings_update_accepts_expert_mode(self):
        from api.server import SettingsUpdate
        s = SettingsUpdate(expert_mode=True)
        self.assertEqual(s.expert_mode, True)

    def test_settings_update_expert_mode_optional(self):
        from api.server import SettingsUpdate
        s = SettingsUpdate(provider="ollama")
        # Optional field — None means "don't change".
        self.assertIsNone(s.expert_mode)


if __name__ == "__main__":
    unittest.main()
