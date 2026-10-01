from .base import BaseTool
from ion.sandbox.base import SandboxEnvironment
from typing import Dict, Any

class SearchCodeTool(BaseTool):
    name = "search_code"
    description = "Search for a text pattern in the repository."
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The text pattern to search for"
            },
            "path": {
                "type": "string",
                "description": "Optional subdirectory or file path to search within (default: .)"
            }
        },
        "required": ["query"]
    }
    category = "OBSERVE"
    
    def __init__(self, sandbox: SandboxEnvironment):
        self.sandbox = sandbox
        
    def execute(self, query: str, path: str = ".", **kwargs) -> str:
        search_path = path.strip() if path and path.strip() else "."
        # Escape single quotes in query safely
        safe_query = query.replace("'", "'\\''")
        code, stdout, stderr = self.sandbox.run_command(f"grep -rn '{safe_query}' {search_path}")
        if code != 0 and not stdout:
            return f"No matches found for '{query}'"
        return stdout
