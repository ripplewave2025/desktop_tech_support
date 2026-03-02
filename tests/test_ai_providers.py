"""
Tests for AI provider abstraction layer.

Tests the data classes, provider factory, message conversion,
and tool definition format — all without making real API calls.
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.providers import AIProvider, AIMessage, ToolCall, AIResponse
from ai.provider_factory import get_provider
from ai.tools import TOOL_DEFINITIONS, DIAGNOSTIC_CATEGORIES


class TestDataClasses(unittest.TestCase):
    """Test the core data structures."""

    def test_ai_message_defaults(self):
        msg = AIMessage(role="user", content="hello")
        self.assertEqual(msg.role, "user")
        self.assertEqual(msg.content, "hello")
        self.assertEqual(msg.tool_calls, [])
        self.assertIsNone(msg.tool_call_id)
        self.assertIsNone(msg.name)

    def test_ai_message_with_tool_calls(self):
        tc = ToolCall(id="call_123", name="run_diagnostic", arguments={"category": "audio"})
        msg = AIMessage(role="assistant", content="", tool_calls=[tc])
        self.assertEqual(len(msg.tool_calls), 1)
        self.assertEqual(msg.tool_calls[0].name, "run_diagnostic")
        self.assertEqual(msg.tool_calls[0].arguments["category"], "audio")

    def test_tool_call(self):
        tc = ToolCall(id="call_abc", name="get_system_info", arguments={})
        self.assertEqual(tc.id, "call_abc")
        self.assertEqual(tc.name, "get_system_info")

    def test_ai_response(self):
        msg = AIMessage(role="assistant", content="I'll check that.")
        resp = AIResponse(message=msg, finish_reason="stop", usage={"input_tokens": 10, "output_tokens": 5})
        self.assertEqual(resp.finish_reason, "stop")
        self.assertEqual(resp.usage["input_tokens"], 10)

    def test_ai_response_with_tool_calls(self):
        tc = ToolCall(id="call_1", name="run_diagnostic", arguments={"category": "printer"})
        msg = AIMessage(role="assistant", content="", tool_calls=[tc])
        resp = AIResponse(message=msg, finish_reason="tool_calls")
        self.assertEqual(resp.finish_reason, "tool_calls")
        self.assertEqual(len(resp.message.tool_calls), 1)

    def test_tool_message(self):
        msg = AIMessage(role="tool", content='{"result": "ok"}', tool_call_id="call_1", name="run_diagnostic")
        self.assertEqual(msg.role, "tool")
        self.assertEqual(msg.tool_call_id, "call_1")


class TestToolDefinitions(unittest.TestCase):
    """Test tool definitions are well-formed."""

    def test_tool_definitions_not_empty(self):
        self.assertGreater(len(TOOL_DEFINITIONS), 0)

    def test_all_tools_have_required_fields(self):
        for tool in TOOL_DEFINITIONS:
            self.assertEqual(tool["type"], "function")
            func = tool["function"]
            self.assertIn("name", func)
            self.assertIn("description", func)
            self.assertIn("parameters", func)
            self.assertIsInstance(func["name"], str)
            self.assertIsInstance(func["description"], str)

    def test_diagnostic_categories_match(self):
        """Ensure tool definitions reference valid categories."""
        expected = {"printer", "internet", "software", "hardware", "files", "display", "audio", "security"}
        self.assertEqual(set(DIAGNOSTIC_CATEGORIES), expected)

    def test_run_diagnostic_tool_has_enum(self):
        """The run_diagnostic tool should list all categories."""
        diag_tool = None
        for tool in TOOL_DEFINITIONS:
            if tool["function"]["name"] == "run_diagnostic":
                diag_tool = tool
                break
        self.assertIsNotNone(diag_tool)
        categories = diag_tool["function"]["parameters"]["properties"]["category"]["enum"]
        self.assertEqual(set(categories), set(DIAGNOSTIC_CATEGORIES))

    def test_key_tools_exist(self):
        tool_names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
        expected = {
            "run_diagnostic", "apply_fix", "get_system_info",
            "list_processes", "kill_process", "read_screen",
            "list_windows", "focus_window", "launch_app",
            "type_text", "press_hotkey", "run_powershell",
            "web_search",
        }
        self.assertTrue(expected.issubset(tool_names), f"Missing tools: {expected - tool_names}")


class TestProviderFactory(unittest.TestCase):
    """Test the provider factory."""

    def test_unknown_provider_raises(self):
        with self.assertRaises(ValueError) as ctx:
            get_provider({"ai": {"provider": "unknown_provider"}})
        self.assertIn("Unknown AI provider", str(ctx.exception))

    def test_claude_without_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            # Remove env vars that might provide keys
            env = os.environ.copy()
            env.pop("ANTHROPIC_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                with self.assertRaises(ValueError) as ctx:
                    get_provider({"ai": {"provider": "claude", "api_key": ""}})
                self.assertIn("API key required", str(ctx.exception))

    def test_openai_without_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            env = os.environ.copy()
            env.pop("OPENAI_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                with self.assertRaises(ValueError) as ctx:
                    get_provider({"ai": {"provider": "openai", "api_key": ""}})
                self.assertIn("API key required", str(ctx.exception))

    def test_ollama_no_key_needed(self):
        """Ollama should work without any API key."""
        from ai.ollama_provider import OllamaProvider
        provider = get_provider({"ai": {"provider": "ollama", "model": "llama3.1"}})
        self.assertIsInstance(provider, OllamaProvider)
        self.assertEqual(provider.name(), "ollama (llama3.1)")

    def test_claude_with_key(self):
        from ai.claude_provider import ClaudeProvider
        provider = get_provider({"ai": {"provider": "claude", "api_key": "sk-test-key"}})
        self.assertIsInstance(provider, ClaudeProvider)
        self.assertIn("claude", provider.name())

    def test_openai_with_key(self):
        from ai.openai_provider import OpenAIProvider
        provider = get_provider({"ai": {"provider": "openai", "api_key": "sk-test-key", "model": "gpt-4o"}})
        self.assertIsInstance(provider, OpenAIProvider)
        self.assertIn("openai", provider.name())

    def test_env_var_fallback(self):
        """Provider should pick up API key from environment."""
        from ai.claude_provider import ClaudeProvider
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key-test"}):
            provider = get_provider({"ai": {"provider": "claude"}})
            self.assertIsInstance(provider, ClaudeProvider)


class TestClaudeProviderConversion(unittest.TestCase):
    """Test Claude provider message/tool conversion without API calls."""

    def setUp(self):
        from ai.claude_provider import ClaudeProvider
        self.provider = ClaudeProvider(api_key="test-key")

    def test_convert_tools(self):
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "A test tool",
                    "parameters": {"type": "object", "properties": {"x": {"type": "string"}}},
                },
            }
        ]
        converted = self.provider._convert_tools(openai_tools)
        self.assertEqual(len(converted), 1)
        self.assertEqual(converted[0]["name"], "test_tool")
        self.assertEqual(converted[0]["description"], "A test tool")
        self.assertIn("input_schema", converted[0])

    def test_convert_messages_splits_system(self):
        messages = [
            AIMessage(role="system", content="You are helpful"),
            AIMessage(role="user", content="Hi"),
        ]
        system, api_msgs = self.provider._convert_messages(messages)
        self.assertEqual(system, "You are helpful")
        self.assertEqual(len(api_msgs), 1)
        self.assertEqual(api_msgs[0]["role"], "user")

    def test_convert_messages_with_tool_calls(self):
        tc = ToolCall(id="call_1", name="test", arguments={"x": 1})
        messages = [
            AIMessage(role="user", content="test"),
            AIMessage(role="assistant", content="", tool_calls=[tc]),
            AIMessage(role="tool", content='{"ok": true}', tool_call_id="call_1", name="test"),
        ]
        system, api_msgs = self.provider._convert_messages(messages)
        self.assertEqual(len(api_msgs), 3)
        # Assistant message should have tool_use content blocks
        assistant_content = api_msgs[1]["content"]
        self.assertIsInstance(assistant_content, list)
        self.assertEqual(assistant_content[0]["type"], "tool_use")


class TestOpenAIProviderConversion(unittest.TestCase):
    """Test OpenAI provider message conversion without API calls."""

    def setUp(self):
        from ai.openai_provider import OpenAIProvider
        self.provider = OpenAIProvider(api_key="test-key")

    def test_convert_messages_basic(self):
        messages = [
            AIMessage(role="system", content="You are helpful"),
            AIMessage(role="user", content="Hi"),
        ]
        api_msgs = self.provider._convert_messages(messages)
        self.assertEqual(len(api_msgs), 2)
        self.assertEqual(api_msgs[0]["role"], "system")
        self.assertEqual(api_msgs[1]["role"], "user")

    def test_convert_messages_with_tool_calls(self):
        tc = ToolCall(id="call_1", name="test", arguments={"x": 1})
        messages = [
            AIMessage(role="assistant", content="", tool_calls=[tc]),
            AIMessage(role="tool", content='{"ok": true}', tool_call_id="call_1"),
        ]
        api_msgs = self.provider._convert_messages(messages)
        self.assertEqual(len(api_msgs), 2)
        self.assertIn("tool_calls", api_msgs[0])
        self.assertEqual(api_msgs[1]["tool_call_id"], "call_1")


if __name__ == "__main__":
    unittest.main()
