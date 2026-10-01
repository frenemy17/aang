from abc import ABC, abstractmethod
from typing import List, Dict, Any
from .types import Message, LLMResponse

class LLMProvider(ABC):
    def __init__(self, model: str, api_key: str, base_url: str = None):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    def generate(self, messages: List[Message], tools: List[Dict[str, Any]] = None) -> LLMResponse:
        pass
