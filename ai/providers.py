"""
AI Provider abstraction — the contract all providers implement.

All providers normalize to the same AIMessage/ToolCall/AIResponse types.
Tool definitions use OpenAI function-calling format internally;
each provider converts as needed.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncIterator
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    """A single tool call requested by the AI."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class AIMessage:
    """A message in the conversation."""
    role: str  # "system", "user", "assistant", "tool"
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    tool_call_id: Optional[str] = None  # For tool result messages
    name: Optional[str] = None  # Tool name for tool results


@dataclass
class AIResponse:
    """Complete response from an AI provider."""
    message: AIMessage
    finish_reason: str  # "stop", "tool_calls", "length"
    usage: Dict[str, int] = field(default_factory=dict)


class AIProvider(ABC):
    """Abstract base for all AI providers."""

    @abstractmethod
    async def chat(
        self,
        messages: List[AIMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AIResponse:
        """Send a chat completion request. Returns full response."""
        pass

    @abstractmethod
    async def chat_stream(
        self,
        messages: List[AIMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Stream a chat completion. Yields content text deltas."""
        pass

    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""
        pass
