"""
Anthropic Claude API provider.

Converts between the unified AIMessage format and Anthropic's message API.
Key differences: Anthropic separates system prompt, uses content blocks
for tool_use/tool_result, and has different tool definition format.
"""

import json
import uuid
from typing import List, Dict, Any, Optional, AsyncIterator

from .providers import AIProvider, AIMessage, AIResponse, ToolCall


class ClaudeProvider(AIProvider):
    """Anthropic Claude API provider."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self._api_key = api_key
        self._model = model
        self._client = None

    def _get_client(self):
        if not self._client:
            try:
                import anthropic
            except ImportError:
                raise ImportError(
                    "anthropic package required: pip install anthropic"
                )
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        return self._client

    def _convert_tools(self, tools: List[Dict]) -> List[Dict]:
        """Convert OpenAI-style tool defs to Anthropic format.

        OpenAI: {"type": "function", "function": {"name", "description", "parameters"}}
        Anthropic: {"name", "description", "input_schema"}
        """
        converted = []
        for tool in tools:
            func = tool.get("function", tool)
            converted.append({
                "name": func["name"],
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
            })
        return converted

    def _convert_messages(self, messages: List[AIMessage]) -> tuple:
        """Split system prompt and convert messages to Anthropic format.

        Returns (system_prompt, api_messages).
        """
        system_prompt = ""
        api_messages = []

        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
                continue

            if msg.role == "assistant" and msg.tool_calls:
                # Assistant message with tool use blocks
                content = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                api_messages.append({"role": "assistant", "content": content})

            elif msg.role == "tool":
                # Tool result — Anthropic puts these in user messages
                content_block = {
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id,
                    "content": msg.content,
                }
                # Merge into last user message if it exists, else create one
                if api_messages and api_messages[-1]["role"] == "user" and isinstance(api_messages[-1]["content"], list):
                    api_messages[-1]["content"].append(content_block)
                else:
                    api_messages.append({"role": "user", "content": [content_block]})

            elif msg.role == "user":
                api_messages.append({"role": "user", "content": msg.content})

            elif msg.role == "assistant":
                api_messages.append({"role": "assistant", "content": msg.content})

        return system_prompt, api_messages

    def _parse_response(self, response) -> AIResponse:
        """Convert Anthropic response to unified AIResponse."""
        content_text = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else json.loads(block.input),
                ))

        finish = "tool_calls" if response.stop_reason == "tool_use" else "stop"

        return AIResponse(
            message=AIMessage(
                role="assistant",
                content=content_text,
                tool_calls=tool_calls,
            ),
            finish_reason=finish,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        )

    async def chat(
        self,
        messages: List[AIMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AIResponse:
        client = self._get_client()
        system_prompt, api_messages = self._convert_messages(messages)

        kwargs = {
            "model": self._model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        response = await client.messages.create(**kwargs)
        return self._parse_response(response)

    async def chat_stream(
        self,
        messages: List[AIMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        client = self._get_client()
        system_prompt, api_messages = self._convert_messages(messages)

        kwargs = {
            "model": self._model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    def name(self) -> str:
        return f"claude ({self._model})"
