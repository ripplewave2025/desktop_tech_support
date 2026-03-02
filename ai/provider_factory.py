"""
Factory to create AI provider instances from configuration.

Reads the 'ai' section of config.json and environment variables
to determine which provider to instantiate and with what credentials.
"""

import os
from typing import Dict

from .providers import AIProvider
from .claude_provider import ClaudeProvider
from .openai_provider import OpenAIProvider
from .ollama_provider import OllamaProvider


def get_provider(config: Dict) -> AIProvider:
    """Create an AI provider from config.

    Config structure expected:
        {
            "ai": {
                "provider": "claude" | "openai" | "ollama",
                "model": "claude-sonnet-4-20250514" | "gpt-4o" | "llama3.1",
                "api_key": "" (or use env vars),
                "base_url": "" (for ollama)
            }
        }

    Environment variable fallbacks:
        ANTHROPIC_API_KEY, OPENAI_API_KEY, OLLAMA_BASE_URL
    """
    ai_config = config.get("ai", {})
    provider_name = ai_config.get("provider", "claude")

    if provider_name == "claude":
        api_key = (
            ai_config.get("api_key")
            or os.environ.get("ANTHROPIC_API_KEY", "")
        )
        if not api_key:
            raise ValueError(
                "Claude API key required. Set 'ai.api_key' in config.json "
                "or ANTHROPIC_API_KEY environment variable."
            )
        return ClaudeProvider(
            api_key=api_key,
            model=ai_config.get("model", "claude-sonnet-4-20250514"),
        )

    elif provider_name == "openai":
        api_key = (
            ai_config.get("api_key")
            or os.environ.get("OPENAI_API_KEY", "")
        )
        if not api_key:
            raise ValueError(
                "OpenAI API key required. Set 'ai.api_key' in config.json "
                "or OPENAI_API_KEY environment variable."
            )
        return OpenAIProvider(
            api_key=api_key,
            model=ai_config.get("model", "gpt-4o"),
        )

    elif provider_name == "ollama":
        base_url = (
            ai_config.get("base_url")
            or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        )
        return OllamaProvider(
            model=ai_config.get("model", "llama3.1"),
            base_url=base_url,
        )

    else:
        raise ValueError(
            f"Unknown AI provider: '{provider_name}'. "
            f"Supported: claude, openai, ollama"
        )
