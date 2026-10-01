from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseTool(ABC):
    name: str
    description: str
    parameters: Dict[str, Any]
    category: str # "OBSERVE", "MODIFY", "EXECUTE"
    
    @abstractmethod
    def execute(self, **kwargs) -> str:
        pass

    def to_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters
        }
