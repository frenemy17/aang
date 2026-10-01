from .base import BaseTool
from aang.sandbox.base import SandboxEnvironment
from typing import Dict, Any

class RunCommandTool(BaseTool):
    name = "run_command"
    description = "Execute a shell command in the project environment. Returns stdout and stderr."
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to run (e.g., 'npm test', 'pytest', 'python main.py')"
            }
        },
        "required": ["command"]
    }
    category = "EXECUTE"
    
    def __init__(self, sandbox: SandboxEnvironment):
        self.sandbox = sandbox
        
    def execute(self, command: str) -> str:
        exit_code, stdout, stderr = self.sandbox.run_command(command)
        return f"Exit Code: {exit_code}\nStdout:\n{stdout}\nStderr:\n{stderr}"
