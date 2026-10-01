import requests
from typing import List, Dict, Any
from .base import LLMProvider
from .types import Message, LLMResponse, ToolCall
import json

class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, model: str, api_key: str, base_url: str):
        super().__init__(model, api_key, base_url)

    def _serialize_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Serialize messages into the OpenAI-compatible format.
        
        Crucially, assistant messages with tool_calls must use the nested format:
        {"type": "function", "function": {"name": ..., "arguments": ...}}
        """
        result = []
        for m in messages:
            msg: Dict[str, Any] = {"role": m.role}
            
            if m.content is not None:
                msg["content"] = m.content
            elif m.role == "assistant":
                # OpenAI API requires content to be null (not missing) for assistant tool-call messages
                msg["content"] = None
                
            if m.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments
                        }
                    }
                    for tc in m.tool_calls
                ]
                
            if m.tool_call_id is not None:
                msg["tool_call_id"] = m.tool_call_id
                
            if m.name is not None:
                msg["name"] = m.name
                
            result.append(msg)
        return result

    def generate(self, messages: List[Message], tools: List[Dict[str, Any]] = None) -> LLMResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": self._serialize_messages(messages),
            "max_tokens": 8192
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
        
        if response.status_code != 200:
            if response.status_code == 400 and any(err_sig in response.text for err_sig in ["tool_use_failed", "output_parse_failed", "Parsing failed"]):
                salvaged = self._try_salvage_groq_tool_call(response.text)
                if salvaged:
                    return salvaged
            raise Exception(f"Provider API error ({response.status_code}): {response.text}")
            
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
            text=message_data.get("content"),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason")
        )

    def _try_salvage_groq_tool_call(self, text: str) -> Optional[LLMResponse]:
        import re, time
        try:
            err_json = json.loads(text)
            fg = err_json.get("error", {}).get("failed_generation", "")
            if not fg:
                return None
            m_name = re.search(r'\"name\":\s*\"([a-zA-Z0-9_]+)\"', fg)
            if not m_name:
                # If there's no function name in failed_generation, Groq rejected conversational
                # text because tools were enabled. Salvage it as normal text response!
                clean_text = fg.strip()
                if clean_text:
                    return LLMResponse(
                        text=clean_text,
                        tool_calls=None,
                        finish_reason="stop"
                    )
                return None
            name = m_name.group(1)
            # Try cleaning trailing brackets / bogus fields emitted by model
            cleaned = re.sub(r'\\\"\\]\s*,\s*\\\"timeout\\\".*$', '\"}}', fg)
            cleaned = re.sub(r'\"\]\s*,\s*\"timeout\".*$', '\"}}', cleaned)
            cleaned = re.sub(r',\s*\"timeout\"\s*:\s*\d+.*$', '}}', cleaned)
            try:
                p = json.loads(cleaned)
                args = p.get("arguments", {})
                args_str = json.dumps(args) if isinstance(args, dict) else str(args)
                return LLMResponse(
                    text=None,
                    tool_calls=[ToolCall(id=f"call_salvaged_{int(time.time())}", name=name, arguments=args_str)],
                    finish_reason="tool_calls"
                )
            except Exception:
                pass
        except Exception:
            pass
        return None

class OpenAIProvider(OpenAICompatibleProvider):
    def __init__(self, model: str, api_key: str, base_url: str = None):
        super().__init__(model, api_key, base_url or "https://api.openai.com/v1")

