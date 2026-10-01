import docker
import os
import tarfile
import io
from typing import Tuple
from .base import SandboxEnvironment

class DockerSandbox(SandboxEnvironment):
    def __init__(self, repo_path: str, base_image: str = "python:3.11-slim"):
        self.repo_path = os.path.abspath(repo_path)
        self.client = docker.from_env()
        
        # Check if pre-baked cached image exists for instant startup (<0.5s)
        image = base_image
        try:
            self.client.images.get("ion-sandbox:latest")
            image = "ion-sandbox:latest"
        except Exception:
            try:
                self.client.images.get(base_image)
            except docker.errors.ImageNotFound:
                self.client.images.pull(base_image)
            
        self.container = self.client.containers.run(
            image,
            command="tail -f /dev/null", # keep alive
            volumes={self.repo_path: {'bind': '/workspace', 'mode': 'rw'}},
            working_dir="/workspace",
            detach=True,
            remove=True
        )
        
        # Check if tools are already installed; install only if missing
        c_git, _, _ = self.run_command("command -v git && command -v node", timeout=5)
        if c_git != 0:
            self.run_command("DEBIAN_FRONTEND=noninteractive apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y git nodejs 2>/dev/null", timeout=60)
            self.run_command("ln -sf /usr/bin/nodejs /usr/bin/node 2>/dev/null || true", timeout=5)
            # Add lightweight npm shim for test runner
            npm_shim = (
                "printf '#!/bin/bash\\nif [ \"$1\" = \"test\" ]; then\\n  if [ -f test_auth.js ]; then exec node test_auth.js; fi\\n  exec node test*.js 2>/dev/null || exit 1\\nfi\\nexec node \"$@\"\\n' > /usr/local/bin/npm && chmod +x /usr/local/bin/npm"
            )
            self.run_command(npm_shim, timeout=5)
            
        c_py, _, _ = self.run_command("command -v pytest", timeout=5)
        if c_py != 0:
            self.run_command("pip install pytest 2>/dev/null", timeout=60)
            
        # Commit to cache image if we installed on base
        if image != "ion-sandbox:latest" and c_git != 0:
            try:
                self.container.commit(repository="ion-sandbox", tag="latest")
            except Exception:
                pass
        
    def run_command(self, command: str, timeout: int = 30) -> Tuple[int, str, str]:
        try:
            # We use exec_run. Note: docker-py exec_run doesn't natively support timeout easily in a blocking way
            # without demuxing. We'll do a simple implementation.
            exec_res = self.container.exec_run(
                ["/bin/bash", "-c", command],
                demux=True
            )
            exit_code = exec_res.exit_code
            stdout = exec_res.output[0] if exec_res.output[0] else b""
            stderr = exec_res.output[1] if exec_res.output[1] else b""
            
            return exit_code, stdout.decode('utf-8', errors='replace'), stderr.decode('utf-8', errors='replace')
        except Exception as e:
            return -1, "", str(e)
            
    def read_file(self, path: str) -> str:
        code, stdout, stderr = self.run_command(f"cat '{path}'")
        if code != 0:
            raise FileNotFoundError(f"Could not read {path}: {stderr}")
        return stdout
        
    def write_file(self, path: str, content: str) -> None:
        # Instead of echo or python scripts, we can use docker api put_archive or base64 decode
        import base64
        b64_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        code, _, stderr = self.run_command(f"mkdir -p $(dirname '{path}') && echo '{b64_content}' | base64 -d > '{path}'")
        if code != 0:
            raise Exception(f"Failed to write file {path}: {stderr}")

    def list_files(self, path: str) -> str:
        code, stdout, stderr = self.run_command(f"find '{path}' -type f -not -path '*/.git/*'")
        if code != 0:
            raise Exception(f"Failed to list files: {stderr}")
        return stdout

    def cleanup(self):
        try:
            self.container.stop()
        except:
            pass
