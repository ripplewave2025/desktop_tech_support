"""
OpenAI API provider (GPT-4o, etc.).

OpenAI's chat completions API is the closest to our internal format,
so conversion is minimal.
"""

import json
from typing import List, Dict, Any, Optional, AsyncIterator

from .providers import AIProvider, AIMessage, AIResponse, ToolCall


class OpenAIProvider(AIProvider):
    """OpenAI-compatible API provider (works with OpenAI, Grok/xAI, Groq, etc.)."""

    def __init__(self, api_key: str, model: str = "gpt-4o", base_url: str = None):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url  # None = default OpenAI, or custom endpoint
        self._client = None

    def _get_client(self):
        if not self._client:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ImportError(
                    "openai package required: pip install openai"
                )
            kwargs = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    def _convert_messages(self, messages: List[AIMessage]) -> List[Dict]:
        """Convert AIMessage list to OpenAI format."""
        api_messages = []

        for msg in messages:
            if msg.role == "tool":
                api_messages.append({
                    "role": "tool",
                    "content": msg.content,
                    "tool_call_id": msg.tool_call_id,
                })
            elif msg.role == "assistant" and msg.tool_calls:
                m = {"role": "assistant", "content": msg.content or None}
                m["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ]
                api_messages.append(m)
            else:
                api_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        return api_messages

    def _parse_response(self, response) -> AIResponse:
        """Convert OpenAI response to unified AIResponse."""
        choice = response.choices[0]
        msg = choice.message

        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        finish = "tool_calls" if choice.finish_reason == "tool_calls" else "stop"

        return AIResponse(
            message=AIMessage(
                role="assistant",
                content=msg.content or "",
                tool_calls=tool_calls,
            ),
            finish_reason=finish,
            usage={
                "input_tokens": getattr(response.usage, "prompt_tokens", 0),
                "output_tokens": getattr(response.usage, "completion_tokens", 0),
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
        api_messages = self._convert_messages(messages)

        kwargs = {
            "model": self._model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools

        response = await client.chat.completions.create(**kwargs)
        return self._parse_response(response)

    async def chat_stream(
        self,
        messages: List[AIMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        client = self._get_client()
        api_messages = self._convert_messages(messages)

        kwargs = {
            "model": self._model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        stream = await client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def name(self) -> str:
        return f"openai ({self._model})"
