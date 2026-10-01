import os
import subprocess
from typing import Tuple
from .base import SandboxEnvironment

class LocalSandbox(SandboxEnvironment):
    """A local sandbox that runs commands directly on the host filesystem.
    
    WARNING: This provides NO isolation. Use for development/testing only.
    For production use, prefer DockerSandbox.
    """
    def __init__(self, repo_path: str):
        self.repo_path = os.path.abspath(repo_path)
        if not os.path.isdir(self.repo_path):
            raise FileNotFoundError(f"Repository path not found: {self.repo_path}")

    def run_command(self, command: str, timeout: int = 30) -> Tuple[int, str, str]:
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"Command timed out after {timeout}s"
        except Exception as e:
            return -1, "", str(e)

    def read_file(self, path: str) -> str:
        full_path = os.path.join(self.repo_path, path) if not os.path.isabs(path) else path
        if not os.path.isfile(full_path):
            raise FileNotFoundError(f"File not found: {path}")
        with open(full_path, 'r') as f:
            return f.read()

    def write_file(self, path: str, content: str) -> None:
        full_path = os.path.join(self.repo_path, path) if not os.path.isabs(path) else path
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w') as f:
            f.write(content)

    def list_files(self, path: str) -> str:
        target = os.path.join(self.repo_path, path) if not os.path.isabs(path) else path
        if os.path.isfile(target):
            return os.path.relpath(target, self.repo_path)
        if not os.path.exists(target):
            return f"Path '{path}' not found."
        results = []
        for root, dirs, files in os.walk(target):
            # Skip .git directory
            dirs[:] = [d for d in dirs if d != '.git']
            for f in files:
                results.append(os.path.relpath(os.path.join(root, f), self.repo_path))
        return '\n'.join(results)

    def cleanup(self):
        pass  # Nothing to clean up for local sandbox
