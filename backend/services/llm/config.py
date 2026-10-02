"""
LLM Configuration — Provider configs, model limits, and routing rules.

All provider credentials come from environment variables.
This module defines the static configuration for model capabilities,
context windows, and routing preferences.
"""

import os
from typing import Dict, Any

# ── Provider Model Configurations ────────────────────────────────────────────
# context_window is in tokens. cost_per_1k_tokens is relative (for routing).

MODEL_CONFIGS: Dict[str, Dict[str, Any]] = {
    "gemini": {
        "models": {
            "gemini-2.5-flash": {
                "context_window": 1048576,
                "max_output_tokens": 65536,
                "cost_per_1k_tokens": 0.15,
                "supports_long_context": True,
            },
            "gemini-2.5-pro": {
                "context_window": 1048576,
                "max_output_tokens": 65536,
                "cost_per_1k_tokens": 1.25,
                "supports_long_context": True,
            },
            "gemini-3.6-flash": {
                "context_window": 1048576,
                "max_output_tokens": 65536,
                "cost_per_1k_tokens": 0.10,
                "supports_long_context": True,
            },
        },
        "env_key": "GEMINI_API_KEY",
        "env_model": "GEMINI_MODEL",
        "default_model": "gemini-3.6-flash",
    },
    "openai": {
        "models": {
            "gpt-4o": {
                "context_window": 128000,
                "max_output_tokens": 16384,
                "cost_per_1k_tokens": 2.50,
                "supports_long_context": True,
            },
            "gpt-4o-mini": {
                "context_window": 128000,
                "max_output_tokens": 16384,
                "cost_per_1k_tokens": 0.15,
                "supports_long_context": True,
            },
            "gpt-4.1-nano": {
                "context_window": 1048576,
                "max_output_tokens": 32768,
                "cost_per_1k_tokens": 0.10,
                "supports_long_context": True,
            },
        },
        "env_key": "OPENAI_API_KEY",
        "env_model": "OPENAI_MODEL",
        "default_model": "gpt-4o-mini",
    },
    "anthropic": {
        "models": {
            "claude-sonnet-4-20250514": {
                "context_window": 200000,
                "max_output_tokens": 16384,
                "cost_per_1k_tokens": 3.00,
                "supports_long_context": True,
            },
            "claude-3-5-haiku-20241022": {
                "context_window": 200000,
                "max_output_tokens": 8192,
                "cost_per_1k_tokens": 0.80,
                "supports_long_context": True,
            },
        },
        "env_key": "ANTHROPIC_API_KEY",
        "env_model": "ANTHROPIC_MODEL",
        "default_model": "claude-sonnet-4-20250514",
    },
    "deepseek": {
        "models": {
            "deepseek-chat": {
                "context_window": 65536,
                "max_output_tokens": 8192,
                "cost_per_1k_tokens": 0.14,
                "supports_long_context": False,
            },
            "deepseek-reasoner": {
                "context_window": 65536,
                "max_output_tokens": 8192,
                "cost_per_1k_tokens": 0.55,
                "supports_long_context": False,
            },
        },
        "env_key": "DEEPSEEK_API_KEY",
        "env_model": "DEEPSEEK_MODEL",
        "default_model": "deepseek-chat",
    },
    "nemotron": {
        "models": {
            "nvidia/nemotron-3-ultra-550b-a55b": {
                "context_window": 32768,
                "max_output_tokens": 4096,
                "cost_per_1k_tokens": 0.00,
                "supports_long_context": False,
            },
        },
        "env_key": "NVIDIA_API_KEY",
        "env_model": "NVIDIA_MODEL",
        "default_model": "nvidia/nemotron-3-ultra-550b-a55b",
    },
}

# ── Routing Configuration ────────────────────────────────────────────────────

def get_provider_priority() -> list:
    """
    Get the ordered list of provider names for routing/failover.
    Reads from LLM_PROVIDER_PRIORITY env var (comma-separated).
    Falls back to a sensible default order.
    """
    raw = os.environ.get("LLM_PROVIDER_PRIORITY", "")
    if raw.strip():
        return [p.strip().lower() for p in raw.split(",") if p.strip()]
    return ["gemini", "openai", "anthropic", "deepseek", "nemotron"]


def get_default_provider() -> str:
    """Get the default provider name."""
    return os.environ.get("LLM_DEFAULT_PROVIDER", 
                          os.environ.get("LLM_PROVIDER", "gemini")).lower()


def is_failover_enabled() -> bool:
    """Check if cross-provider failover is enabled."""
    return os.environ.get("LLM_FAILOVER_ENABLED", "true").lower() in ("true", "1", "yes")


def get_answer_token_reserve() -> int:
    """Tokens reserved for the model's answer output."""
    try:
        return int(os.environ.get("LLM_ANSWER_TOKEN_RESERVE", "4096"))
    except ValueError:
        return 4096


def get_max_context_ratio() -> float:
    """
    Maximum fraction of the context window to use.
    Keeps a safety margin to avoid exceeding limits.
    """
    try:
        return float(os.environ.get("LLM_MAX_CONTEXT_RATIO", "0.85"))
    except ValueError:
        return 0.85


def get_model_config(provider_name: str, model_name: str = None) -> Dict[str, Any]:
    """
    Get the configuration for a specific provider/model.
    If model_name is not specified, uses the environment-configured model
    or the default model for that provider.
    """
    provider_config = MODEL_CONFIGS.get(provider_name, {})
    if not provider_config:
        return {}

    if model_name is None:
        env_model_key = provider_config.get("env_model", "")
        model_name = os.environ.get(env_model_key, provider_config.get("default_model", ""))

    models = provider_config.get("models", {})
    model_config = models.get(model_name, {})

    if not model_config:
        # If the exact model isn't in our config, return defaults
        return {
            "context_window": 32768,
            "max_output_tokens": 4096,
            "cost_per_1k_tokens": 1.0,
            "supports_long_context": False,
            "model_name": model_name,
        }

    return {**model_config, "model_name": model_name}


def get_available_providers() -> list:
    """
    Return list of provider info dicts for providers that have API keys configured.
    Does NOT include the actual keys.
    """
    available = []
    for name, config in MODEL_CONFIGS.items():
        env_key = config.get("env_key", "")
        api_key = os.environ.get(env_key, "")
        has_key = bool(api_key) and api_key not in ("", "your_api_key_here")

        env_model = config.get("env_model", "")
        model = os.environ.get(env_model, config.get("default_model", ""))

        available.append({
            "provider": name,
            "available": has_key,
            "model": model,
            "models": list(config.get("models", {}).keys()),
        })

    return available
