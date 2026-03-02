"""
Tests for the ZoraAgent loop — verifies reasoning loop behavior
with mocked AI provider (no real API calls).
"""

import os
import sys
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.providers import AIProvider, AIMessage, AIResponse, ToolCall
from ai.agent import ZoraAgent


def run_async(coro):
    """Helper to run async functions in tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class MockProvider(AIProvider):
    """Mock AI provider that returns pre-programmed responses."""

    def __init__(self, responses):
        """responses: list of AIResponse objects to return in sequence."""
        self._responses = list(responses)
        self._call_count = 0

    async def chat(self, messages, tools=None, temperature=0.7, max_tokens=4096):
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
            self._call_count += 1
            return resp
        # Default: return a stop response
        return AIResponse(
            message=AIMessage(role="assistant", content="Done."),
            finish_reason="stop",
        )

    async def chat_stream(self, messages, tools=None, temperature=0.7, max_tokens=4096):
        # Simple streaming mock - yield the last response content character by character
        content = "Streaming response."
        for char in content:
            yield char

    def name(self):
        return "mock-provider"


class MockExecutor:
    """Mock tool executor that returns canned results."""

    def __init__(self, results=None):
        self._results = results or {}
        self.calls = []

    async def execute(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        if tool_name in self._results:
            return self._results[tool_name]
        return {"result": "mock_ok"}


class TestAgentBasicChat(unittest.TestCase):
    """Test basic chat without tool calls."""

    def test_simple_response(self):
        provider = MockProvider([
            AIResponse(
                message=AIMessage(role="assistant", content="Hello! How can I help?"),
                finish_reason="stop",
            )
        ])
        agent = ZoraAgent(provider)
        result = run_async(agent.chat("Hi"))
        self.assertEqual(result, "Hello! How can I help?")

    def test_conversation_builds_up(self):
        provider = MockProvider([
            AIResponse(
                message=AIMessage(role="assistant", content="Response 1"),
                finish_reason="stop",
            ),
            AIResponse(
                message=AIMessage(role="assistant", content="Response 2"),
                finish_reason="stop",
            ),
        ])
        agent = ZoraAgent(provider)

        run_async(agent.chat("Message 1"))
        run_async(agent.chat("Message 2"))

        history = agent.get_conversation_history()
        # Should have: user1, assistant1, user2, assistant2
        self.assertEqual(len(history), 4)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[0]["content"], "Message 1")

    def test_reset_conversation(self):
        provider = MockProvider([
            AIResponse(
                message=AIMessage(role="assistant", content="Hi"),
                finish_reason="stop",
            )
        ])
        agent = ZoraAgent(provider)
        run_async(agent.chat("Hello"))
        self.assertGreater(agent.conversation_length, 1)

        agent.reset_conversation()
        # Should only have system prompt
        self.assertEqual(agent.conversation_length, 1)

    def test_provider_name(self):
        provider = MockProvider([])
        agent = ZoraAgent(provider)
        self.assertEqual(agent.provider_name, "mock-provider")


class TestAgentToolCalls(unittest.TestCase):
    """Test the agent loop with tool calls."""

    def test_single_tool_call(self):
        """Agent calls one tool, then responds."""
        provider = MockProvider([
            # First call: AI wants to use a tool
            AIResponse(
                message=AIMessage(
                    role="assistant",
                    content="",
                    tool_calls=[ToolCall(id="call_1", name="get_system_info", arguments={})],
                ),
                finish_reason="tool_calls",
            ),
            # Second call: AI responds with text
            AIResponse(
                message=AIMessage(role="assistant", content="Your CPU is at 45%."),
                finish_reason="stop",
            ),
        ])

        executor = MockExecutor({"get_system_info": {"cpu_percent": 45}})
        agent = ZoraAgent(provider, executor=executor)

        result = run_async(agent.chat("How's my computer?"))
        self.assertEqual(result, "Your CPU is at 45%.")
        self.assertEqual(len(executor.calls), 1)
        self.assertEqual(executor.calls[0][0], "get_system_info")

    def test_multiple_tool_calls_in_sequence(self):
        """Agent calls tool, gets result, calls another tool, then responds."""
        provider = MockProvider([
            # Round 1: run diagnostic
            AIResponse(
                message=AIMessage(
                    role="assistant",
                    content="",
                    tool_calls=[ToolCall(id="call_1", name="run_diagnostic", arguments={"category": "audio"})],
                ),
                finish_reason="tool_calls",
            ),
            # Round 2: apply fix
            AIResponse(
                message=AIMessage(
                    role="assistant",
                    content="",
                    tool_calls=[ToolCall(id="call_2", name="apply_fix", arguments={"category": "audio", "issue_name": "Audio Service"})],
                ),
                finish_reason="tool_calls",
            ),
            # Round 3: final response
            AIResponse(
                message=AIMessage(role="assistant", content="Fixed your audio!"),
                finish_reason="stop",
            ),
        ])

        executor = MockExecutor({
            "run_diagnostic": {"results": [{"name": "Audio Service", "status": "warning", "fix_available": True}]},
            "apply_fix": {"success": True},
        })
        agent = ZoraAgent(provider, executor=executor)

        result = run_async(agent.chat("My sound isn't working"))
        self.assertEqual(result, "Fixed your audio!")
        self.assertEqual(len(executor.calls), 2)

    def test_max_rounds_limit(self):
        """Agent should stop after max_tool_rounds."""
        # Create a provider that always returns tool calls
        infinite_tool_responses = [
            AIResponse(
                message=AIMessage(
                    role="assistant",
                    content="",
                    tool_calls=[ToolCall(id=f"call_{i}", name="get_system_info", arguments={})],
                ),
                finish_reason="tool_calls",
            )
            for i in range(15)
        ]
        # Add a final response for the summary request
        infinite_tool_responses.append(
            AIResponse(
                message=AIMessage(role="assistant", content="Summary of findings."),
                finish_reason="stop",
            )
        )

        provider = MockProvider(infinite_tool_responses)
        executor = MockExecutor()
        agent = ZoraAgent(provider, executor=executor, max_tool_rounds=3)

        result = run_async(agent.chat("Check everything"))
        # Should have stopped at 3 rounds + summary
        self.assertLessEqual(len(executor.calls), 3)

    def test_on_tool_call_callback(self):
        """Verify the on_tool_call callback is invoked."""
        provider = MockProvider([
            AIResponse(
                message=AIMessage(
                    role="assistant",
                    content="",
                    tool_calls=[ToolCall(id="call_1", name="get_system_info", arguments={})],
                ),
                finish_reason="tool_calls",
            ),
            AIResponse(
                message=AIMessage(role="assistant", content="Done."),
                finish_reason="stop",
            ),
        ])

        executor = MockExecutor()
        agent = ZoraAgent(provider, executor=executor)

        callback_calls = []

        def on_tool(name, args):
            callback_calls.append((name, args))

        run_async(agent.chat("test", on_tool_call=on_tool))
        self.assertEqual(len(callback_calls), 1)
        self.assertEqual(callback_calls[0][0], "get_system_info")


class TestAgentStreaming(unittest.TestCase):
    """Test streaming chat."""

    def test_stream_events(self):
        """Streaming should yield text and done events."""
        provider = MockProvider([
            AIResponse(
                message=AIMessage(role="assistant", content="Streaming response."),
                finish_reason="stop",
            ),
        ])

        agent = ZoraAgent(provider)

        events = []

        async def collect():
            async for event in agent.chat_stream("Hi"):
                events.append(event)

        run_async(collect())

        # Should have text events and a done event
        self.assertTrue(any(e["type"] == "done" for e in events))
        text_events = [e for e in events if e["type"] == "text"]
        self.assertGreater(len(text_events), 0)


if __name__ == "__main__":
    unittest.main()
