import os
import json
import requests
from typing import List, Dict, Any, Optional
from .base import LLMProvider
from .types import Message, ToolCall, LLMResponse

class AnthropicProvider(LLMProvider):
    def __init__(self, model: str, api_key: str, base_url: str = None):
        super().__init__(model, api_key, base_url or "https://api.anthropic.com/v1")

    def _convert_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        anthropic_tools = []
        for t in (tools or []):
            anthropic_tools.append({
                "name": t.get("name"),
                "description": t.get("description", ""),
                "input_schema": t.get("parameters", {"type": "object", "properties": {}})
            })
        return anthropic_tools

    def generate(self, messages: List[Message], tools: List[Dict[str, Any]] = None) -> LLMResponse:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        system_prompt = ""
        user_messages = []
        for m in messages:
            if m.role == "system":
                system_prompt += (m.content or "") + "\n"
            elif m.role == "assistant":
                content = []
                if m.content:
                    content.append({"type": "text", "text": m.content})
                if m.tool_calls:
                    for tc in m.tool_calls:
                        try:
                            args = json.loads(tc.arguments)
                        except Exception:
                            args = {"raw": tc.arguments}
                        content.append({
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": args
                        })
                user_messages.append({"role": "assistant", "content": content})
            elif m.role == "tool":
                user_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m.tool_call_id or "call_unknown",
                        "content": str(m.content)
                    }]
                })
            else:
                user_messages.append({"role": m.role, "content": m.content or ""})

        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": user_messages
        }
        if system_prompt.strip():
            payload["system"] = system_prompt.strip()
        if tools:
            payload["tools"] = self._convert_tools(tools)

        resp = requests.post(f"{self.base_url}/messages", headers=headers, json=payload, timeout=120)
        if resp.status_code != 200:
            raise Exception(f"Anthropic API error ({resp.status_code}): {resp.text}")

        data = resp.json()
        text_parts = []
        tool_calls = []

        for block in data.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.get("id"),
                    name=block.get("name"),
                    arguments=json.dumps(block.get("input", {}))
                ))

        finish_reason = data.get("stop_reason", "stop")
        if finish_reason == "tool_use":
            finish_reason = "tool_calls"

        return LLMResponse(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls if tool_calls else None,
            finish_reason=finish_reason
        )
