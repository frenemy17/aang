from .base import BaseTool
from aang.sandbox.base import SandboxEnvironment
from typing import Dict, Any

class GitStatusTool(BaseTool):
    name = "git_status"
    description = "Get the current git status of the repository."
    parameters = {
        "type": "object",
        "properties": {}
    }
    category = "OBSERVE"
    
    def __init__(self, sandbox: SandboxEnvironment):
        self.sandbox = sandbox
        
    def execute(self) -> str:
        code, stdout, stderr = self.sandbox.run_command("git status -s")
        if code != 0:
            return f"Error running git status: {stderr}"
        return stdout if stdout else "Working directory clean."

class GitDiffTool(BaseTool):
    name = "git_diff"
    description = "Get the git diff of the repository."
    parameters = {
        "type": "object",
        "properties": {}
    }
    category = "OBSERVE"
    
    def __init__(self, sandbox: SandboxEnvironment):
        self.sandbox = sandbox
        
    def execute(self) -> str:
        code, stdout, stderr = self.sandbox.run_command("git diff")
        if code != 0:
            return f"Error running git diff: {stderr}"
        return stdout if stdout else "No unstaged changes."

class GitCheckpointTool(BaseTool):
    name = "git_checkpoint"
    description = "Create a safe restore checkpoint before making experimental or risky edits."
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Optional name for the checkpoint"
            }
        }
    }
    category = "MODIFY"

    def __init__(self, sandbox: SandboxEnvironment):
        self.sandbox = sandbox

    def execute(self, name: str = "auto", label: Optional[str] = None, message: Optional[str] = None, **kwargs) -> str:
        checkpoint_name = label or message or name or "auto"
        # Create a git stash checkpoint without clearing working tree
        code, stdout, stderr = self.sandbox.run_command("git stash create")
        if code == 0 and stdout.strip():
            sha = stdout.strip()
            self.sandbox.run_command(f"git update-ref refs/checkpoints/{checkpoint_name} {sha}")
            return f"Checkpoint '{checkpoint_name}' created at {sha[:8]}"
        return "Working tree clean, baseline checkpoint marked as HEAD."

class GitRollbackTool(BaseTool):
    name = "git_rollback"
    description = "Revert working tree changes back to HEAD or to the last safe checkpoint."
    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Optional checkpoint name or 'HEAD'"
            }
        }
    }
    category = "MODIFY"

    def __init__(self, sandbox: SandboxEnvironment):
        self.sandbox = sandbox

    def execute(self, target: str = "HEAD", **kwargs) -> str:
        code, stdout, stderr = self.sandbox.run_command("git checkout HEAD -- . && git clean -fd")
        if code == 0:
            return "Successfully rolled back working directory to clean HEAD state."
        return f"Rollback failed: {stderr or stdout}"
