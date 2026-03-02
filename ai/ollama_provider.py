"""
Ollama local LLM provider.

Uses raw httpx to talk to Ollama's /api/chat endpoint.
No external SDK needed — just HTTP. Supports tool calling
for compatible models (llama3.1, mistral-nemo, qwen2.5, etc.).
"""

import json
import uuid
import logging
from typing import List, Dict, Any, Optional, AsyncIterator

from .providers import AIProvider, AIMessage, AIResponse, ToolCall

logger = logging.getLogger("zora.ollama")


class OllamaProvider(AIProvider):
    """Local Ollama provider for offline/privacy-first usage."""

    def __init__(self, model: str = "llama3.1", base_url: str = "http://localhost:11434"):
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import httpx
            except ImportError:
                raise ImportError(
                    "httpx package required: pip install httpx"
                )
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0),
            )
        return self._client

    def _convert_messages(self, messages: List[AIMessage]) -> List[Dict]:
        """Convert to Ollama chat format."""
        api_messages = []
        for msg in messages:
            if msg.role == "tool":
                api_messages.append({
                    "role": "tool",
                    "content": msg.content or "",
                })
            elif msg.role == "assistant" and msg.tool_calls:
                m = {"role": "assistant", "content": msg.content or ""}
                m["tool_calls"] = [
                    {
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        }
                    }
                    for tc in msg.tool_calls
                ]
                api_messages.append(m)
            else:
                api_messages.append({
                    "role": msg.role,
                    "content": msg.content or "",
                })
        return api_messages

    def _convert_tools(self, tools: List[Dict]) -> List[Dict]:
        """Ollama uses the OpenAI tool format directly."""
        return tools

    def _parse_response(self, data: Dict) -> AIResponse:
        """Parse Ollama JSON response (defensively)."""
        msg = data.get("message", {})
        content = msg.get("content", "") or ""

        tool_calls = []
        for tc in msg.get("tool_calls", []) or []:
            try:
                func = tc.get("function", {})
                name = func.get("name", "")
                args = func.get("arguments", {})
                if name:  # Only add valid tool calls
                    tool_calls.append(ToolCall(
                        id=f"call_{uuid.uuid4().hex[:8]}",
                        name=name,
                        arguments=args if isinstance(args, dict) else {},
                    ))
            except Exception as e:
                logger.warning(f"Skipping malformed tool call: {tc} — {e}")
                continue

        finish = "tool_calls" if tool_calls else "stop"

        return AIResponse(
            message=AIMessage(
                role="assistant",
                content=content,
                tool_calls=tool_calls,
            ),
            finish_reason=finish,
            usage={
                "input_tokens": data.get("prompt_eval_count", 0),
                "output_tokens": data.get("eval_count", 0),
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

        payload = {
            "model": self._model,
            "messages": api_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if tools:
            payload["tools"] = self._convert_tools(tools)

        try:
            response = await client.post("/api/chat", json=payload)
            response.raise_for_status()
            return self._parse_response(response.json())
        except Exception as e:
            logger.error(f"Ollama chat error with tools: {type(e).__name__}: {e}")
            # Retry WITHOUT tools — small models often choke on tool schemas
            if tools:
                logger.info("Retrying without tools...")
                payload.pop("tools", None)
                response = await client.post("/api/chat", json=payload)
                response.raise_for_status()
                return self._parse_response(response.json())
            raise

    async def chat_stream(
        self,
        messages: List[AIMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        client = self._get_client()
        api_messages = self._convert_messages(messages)

        payload = {
            "model": self._model,
            "messages": api_messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        # Don't pass tools for streaming — let agent loop handle tool calls via non-streaming
        # This prevents stream parsing issues with tool call chunks

        async with client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue

    def name(self) -> str:
        return f"ollama ({self._model})"
