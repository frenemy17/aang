from typing import List
from dataclasses import dataclass, field
from aang.llm.types import Message

@dataclass
class AgentState:
    task: str
    messages: List[Message] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 15
    is_complete: bool = False
    status_message: str = "Initializing..."
    files_modified: set = field(default_factory=set)
    
    def add_message(self, message: Message):
        self.messages.append(message)
