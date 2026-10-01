from typing import List, Dict, Any, Callable
from .base import BaseTool
import json

class ToolRouter:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        
    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool
        
    def get_schemas(self) -> List[Dict[str, Any]]:
        return [tool.to_schema() for tool in self._tools.values()]
        
    def execute(self, name: str, arguments_json: str) -> str:
        if name not in self._tools:
            return f"Error: Tool '{name}' not found."
            
        try:
            arguments = json.loads(arguments_json)
        except json.JSONDecodeError:
            return f"Error: Invalid JSON arguments for tool '{name}'."
            
        import inspect
        tool = self._tools[name]
        
        try:
            # Check if tool.execute accepts **kwargs or specific parameters
            sig = inspect.signature(tool.execute)
            has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
            if has_var_keyword:
                call_args = arguments
            else:
                accepted = set(sig.parameters.keys())
                call_args = {k: v for k, v in arguments.items() if k in accepted}
            
            return tool.execute(**call_args)
        except Exception as e:
            return f"Error executing tool '{name}': {str(e)}"
