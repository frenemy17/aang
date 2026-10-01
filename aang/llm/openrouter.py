import re
import json
import requests
from typing import List, Dict, Any, Optional
from .openai import OpenAICompatibleProvider
from .types import Message, LLMResponse, ToolCall

class OpenRouterProvider(OpenAICompatibleProvider):
    def __init__(self, model: str = "openai/gpt-4o-mini", api_key: str = "", base_url: str = "https://openrouter.ai/api/v1"):
        super().__init__(model=model, api_key=api_key, base_url=base_url or "https://openrouter.ai/api/v1")

    def generate(self, messages: List[Message], tools: List[Dict[str, Any]] = None) -> LLMResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/frenemy17/aang",
            "X-Title": "Aang Autonomous Coding Agent"
        }

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": self._serialize_messages(messages),
            "max_tokens": 2048
        }

        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
            payload["tool_choice"] = "auto"

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )

        # Handle OpenRouter token credit limit (402) by adapting max_tokens dynamically
        if response.status_code == 402:
            retry_tokens = None
            if "can only afford" in response.text:
                match = re.search(r"can only afford (\d+)", response.text)
                if match:
                    retry_tokens = max(256, int(match.group(1)) - 50)
            elif "in_flight_budget_exhausted" in response.text or "exceed your available credits" in response.text:
                # Halve max_tokens to 1024 or 512 so in-flight credit hold is dramatically smaller
                retry_tokens = 1024 if payload.get("max_tokens", 2048) > 1024 else 512

            if retry_tokens:
                import time
                time.sleep(2.0)
                payload["max_tokens"] = retry_tokens
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=120
                )

        if response.status_code != 200:
            raise Exception(f"OpenRouter API error ({response.status_code}): {response.text}")

        data = response.json()
        choice = data["choices"][0]
        message_data = choice["message"]
        
        tool_calls = None
        if "tool_calls" in message_data and message_data["tool_calls"]:
            tool_calls = [
                ToolCall(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=tc["function"]["arguments"]
                )
                for tc in message_data["tool_calls"]
            ]

        return LLMResponse(
            text=message_data.get("content") or "",
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason")
        )
