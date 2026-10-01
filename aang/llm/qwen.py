from .openai import OpenAICompatibleProvider

class QwenProvider(OpenAICompatibleProvider):
    def __init__(self, model: str, api_key: str, base_url: str = None):
        # Qwen API often uses DashScope or is hosted directly
        # For OpenAI-compatible Qwen endpoints (like via litellm/vllm or DashScope API)
        super().__init__(model, api_key, base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1")
