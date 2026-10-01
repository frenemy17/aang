import os
from typing import List, Dict, Any, Optional
from .base import LLMProvider
from .types import Message, ToolCall, LLMResponse
from .openai import OpenAIProvider
from .qwen import QwenProvider
from .groq import GroqProvider
from .anthropic import AnthropicProvider
from .openrouter import OpenRouterProvider
from .fallback import FallbackProvider

AVAILABLE_MODELS = [
    {
        "id": "openai/gpt-4o-mini",
        "provider": "openrouter",
        "name": "GPT-4o Mini (OpenRouter - Fast & High Quota)",
        "env_key": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1"
    },
    {
        "id": "meta-llama/llama-3.3-70b-instruct",
        "provider": "openrouter",
        "name": "Llama 3.3 70B (OpenRouter)",
        "env_key": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1"
    },
    {
        "id": "deepseek/deepseek-chat",
        "provider": "openrouter",
        "name": "DeepSeek V3 (OpenRouter)",
        "env_key": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1"
    },
    {
        "id": "openai/gpt-oss-120b",
        "provider": "groq",
        "name": "GPT-OSS 120B (Groq - High Reasoning)",
        "env_key": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1"
    },
    {
        "id": "openai/gpt-oss-20b",
        "provider": "groq",
        "name": "GPT-OSS 20B (Groq - Fast & High Quota)",
        "env_key": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1"
    },
    {
        "id": "qwen/qwen3.8-27b",
        "provider": "groq",
        "name": "Qwen 3.8 27B (Groq - Coding & Math)",
        "env_key": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1"
    },
    {
        "id": "gpt-4o",
        "provider": "openai",
        "name": "GPT-4o (OpenAI Direct)",
        "env_key": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1"
    },
    {
        "id": "claude-3-5-sonnet-20241022",
        "provider": "anthropic",
        "name": "Claude 3.5 Sonnet (Anthropic Direct)",
        "env_key": "ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com/v1"
    },
    {
        "id": "llama3.1",
        "provider": "ollama",
        "name": "Llama 3.1 Local (Ollama)",
        "env_key": "",
        "base_url": "http://localhost:11434/v1"
    }
]

def get_provider(name: str, model: str, api_key: str = None, base_url: str = None) -> LLMProvider:
    name_lower = name.lower()
    if name_lower == "openrouter":
        return OpenRouterProvider(model, api_key or os.getenv("OPENROUTER_API_KEY", "") or os.getenv("ION_API_KEY", ""), base_url)
    elif name_lower == "openai":
        return OpenAIProvider(model, api_key or os.getenv("OPENAI_API_KEY", ""), base_url)
    elif name_lower == "anthropic":
        return AnthropicProvider(model, api_key or os.getenv("ANTHROPIC_API_KEY", ""), base_url)
    elif name_lower == "qwen":
        return QwenProvider(model, api_key or os.getenv("QWEN_API_KEY", ""), base_url)
    elif name_lower == "groq":
        return GroqProvider(model, api_key or os.getenv("GROQ_API_KEY", ""), base_url)
    elif name_lower == "ollama":
        return OpenAIProvider(model, api_key="ollama", base_url=base_url or "http://localhost:11434/v1")
    else:
        return OpenAIProvider(model, api_key or "", base_url)

def get_provider_by_model_id(model_id: str, default_api_key: str = None) -> LLMProvider:
    for m in AVAILABLE_MODELS:
        if m["id"] == model_id:
            key = default_api_key or os.getenv(m["env_key"], "") or os.getenv("ION_API_KEY", "")
            return get_provider(m["provider"], m["id"], key, m["base_url"])
    # Default fallback
    if "openrouter" in model_id.lower() or "/" in model_id:
        return get_provider("openrouter", model_id, default_api_key)
    return get_provider("groq", model_id, default_api_key)
