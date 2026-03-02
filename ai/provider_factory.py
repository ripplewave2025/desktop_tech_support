"""
Factory to create AI provider instances from configuration.

Supported providers:
    - ollama   : Free, local, no API key (default)
    - claude   : Anthropic Claude (needs ANTHROPIC_API_KEY)
    - openai   : OpenAI GPT-4o etc. (needs OPENAI_API_KEY)
    - grok     : xAI Grok (needs XAI_API_KEY, uses OpenAI-compatible API)
    - groq     : Groq fast inference (needs GROQ_API_KEY, OpenAI-compatible)
    - custom   : Any OpenAI-compatible API (needs api_key + base_url)
"""

import os
from typing import Dict

from .providers import AIProvider
from .claude_provider import ClaudeProvider
from .openai_provider import OpenAIProvider
from .ollama_provider import OllamaProvider

# ── Provider defaults ──
PROVIDER_DEFAULTS = {
    "ollama":  {"model": "qwen2.5:7b",               "env_key": None,              "base_url": "http://localhost:11434"},
    "claude":  {"model": "claude-sonnet-4-20250514",  "env_key": "ANTHROPIC_API_KEY", "base_url": None},
    "openai":  {"model": "gpt-4o",                    "env_key": "OPENAI_API_KEY",    "base_url": None},
    "grok":    {"model": "grok-3-latest",             "env_key": "XAI_API_KEY",       "base_url": "https://api.x.ai/v1"},
    "groq":    {"model": "llama-3.3-70b-versatile",   "env_key": "GROQ_API_KEY",      "base_url": "https://api.groq.com/openai/v1"},
    "custom":  {"model": "",                          "env_key": None,              "base_url": ""},
}

SUPPORTED_PROVIDERS = list(PROVIDER_DEFAULTS.keys())


def get_provider(config: Dict) -> AIProvider:
    """Create an AI provider from config.

    Config structure expected:
        {
            "ai": {
                "provider": "ollama" | "claude" | "openai" | "grok" | "groq" | "custom",
                "model": "...",
                "api_key": "" (or use env vars),
                "base_url": "" (for ollama/grok/groq/custom)
            }
        }

    Environment variable fallbacks:
        ANTHROPIC_API_KEY, OPENAI_API_KEY, XAI_API_KEY, GROQ_API_KEY
    """
    ai_config = config.get("ai", {})
    provider_name = ai_config.get("provider", "ollama")
    defaults = PROVIDER_DEFAULTS.get(provider_name, PROVIDER_DEFAULTS["custom"])

    # ── Resolve API key ──
    api_key = ai_config.get("api_key") or ""
    if not api_key and defaults["env_key"]:
        api_key = os.environ.get(defaults["env_key"], "")

    model = ai_config.get("model") or defaults["model"]
    base_url = ai_config.get("base_url") or defaults.get("base_url") or ""

    # ── Claude (Anthropic) ──
    if provider_name == "claude":
        if not api_key:
            raise ValueError(
                "Claude API key required. Set 'ai.api_key' in config.json "
                "or ANTHROPIC_API_KEY environment variable."
            )
        return ClaudeProvider(api_key=api_key, model=model)

    # ── Ollama (Local) ──
    elif provider_name == "ollama":
        if not base_url:
            base_url = "http://localhost:11434"
        return OllamaProvider(model=model, base_url=base_url)

    # ── OpenAI / Grok / Groq / Custom (all OpenAI-compatible) ──
    elif provider_name in ("openai", "grok", "groq", "custom"):
        if not api_key:
            label = provider_name.capitalize()
            env_hint = defaults["env_key"] or "API key"
            raise ValueError(
                f"{label} API key required. Set 'ai.api_key' in config.json "
                f"or {env_hint} environment variable."
            )
        return OpenAIProvider(
            api_key=api_key,
            model=model,
            base_url=base_url if base_url else None,
        )

    else:
        raise ValueError(
            f"Unknown AI provider: '{provider_name}'. "
            f"Supported: {', '.join(SUPPORTED_PROVIDERS)}"
        )
