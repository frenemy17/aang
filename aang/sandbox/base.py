from abc import ABC, abstractmethod
from typing import Tuple

class SandboxEnvironment(ABC):
    @abstractmethod
    def run_command(self, command: str, timeout: int = 30) -> Tuple[int, str, str]:
        """Runs a command and returns (exit_code, stdout, stderr)"""
        pass
        
    @abstractmethod
    def read_file(self, path: str) -> str:
        pass
        
    @abstractmethod
    def write_file(self, path: str, content: str) -> None:
        pass
        
    @abstractmethod
    def list_files(self, path: str) -> str:
        pass

    @abstractmethod
    def cleanup(self):
        pass
