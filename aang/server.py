import http.server
import json
import os
import sys
import threading
import time
import subprocess
import urllib.parse
from typing import Optional

from aang.agent.logger import AangLogger
from aang.agent.prompts import SYSTEM_PROMPT
from aang.config.settings import settings

PORT = 5173
HTML_FILE_PATH = os.path.join(os.path.dirname(__file__), "web", "index.html")

# Track active background run if any
_current_run = {
    "active": False,
    "task": "",
    "type": "",
    "start_time": 0
}

def execute_agent_task(task: str, repo: Optional[str] = None):
    """Executes an agent task in a separate process/thread so the UI remains responsive."""
    global _current_run
    _current_run["active"] = True
    _current_run["task"] = task
    _current_run["type"] = "agent"
    _current_run["start_time"] = time.time()
    
    aang_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    venv_python = os.path.join(aang_root, "venv", "bin", "python")
    if not os.path.exists(venv_python):
        venv_python = sys.executable
        
    env = os.environ.copy()
    if not env.get("GROQ_API_KEY") and settings.api_key:
        env["GROQ_API_KEY"] = settings.api_key
        
    target_repo = os.path.abspath(repo) if repo else aang_root
    try:
        cmd = [
            venv_python, "-m", "aang.main",
            "--repo", target_repo,
            "--log", os.path.join(aang_root, "aang.log"),
            task
        ]
        subprocess.run(cmd, cwd=target_repo, env=env, capture_output=True, text=True)
    finally:
        _current_run["active"] = False

class AangAPIHandler(http.server.SimpleHTTPRequestHandler):
    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        ASSETS_DIR = os.path.join(os.path.dirname(__file__), "web", "assets")
        if path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            return
        elif path in ("/favicon.ico", "/favicon.png"):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            return
        elif path.startswith("/assets/"):
            filename = os.path.basename(path)
            asset_path = os.path.join(ASSETS_DIR, filename)
            if os.path.exists(asset_path) and os.path.isfile(asset_path):
                self.send_response(200)
                self.end_headers()
                return
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        ASSETS_DIR = os.path.join(os.path.dirname(__file__), "web", "assets")

        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            if os.path.exists(HTML_FILE_PATH):
                with open(HTML_FILE_PATH, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.wfile.write(b"<h1>Aang Log Dashboard HTML not found.</h1>")
            return

        elif path in ("/favicon.ico", "/favicon.png"):
            favicon_path = os.path.join(ASSETS_DIR, "favicon.png")
            if os.path.exists(favicon_path):
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                with open(favicon_path, "rb") as f:
                    self.wfile.write(f.read())
                return

        elif path.startswith("/assets/"):
            filename = os.path.basename(path)
            asset_path = os.path.join(ASSETS_DIR, filename)
            if os.path.exists(asset_path) and os.path.isfile(asset_path):
                ext = os.path.splitext(filename)[1].lower()
                mime_map = {
                    ".webp": "image/webp",
                    ".gif": "image/gif",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".svg": "image/svg+xml",
                    ".css": "text/css",
                    ".js": "application/javascript"
                }
                content_type = mime_map.get(ext, "application/octet-stream")
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                with open(asset_path, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_response(404)
                self.end_headers()
                return
            
        elif path == "/api/status":
            run_info = dict(_current_run)
            latest_path = os.path.join(".aang", "latest_session.json")
            active_model = settings.model
            active_provider = settings.provider
            if os.path.exists(latest_path):
                try:
                    with open(latest_path, 'r') as f:
                        latest_data = json.load(f)
                    if latest_data.get("status") == "running":
                        run_info["active"] = True
                        run_info["type"] = "agent"
                        run_info["task"] = latest_data.get("task", "")
                        run_info["session_id"] = latest_data.get("id", "")
                    else:
                        run_info["last_session_id"] = latest_data.get("id", "")
                        run_info["last_status"] = latest_data.get("status", "")
                    if latest_data.get("model"):
                        active_model = latest_data.get("model")
                    if latest_data.get("provider"):
                        active_provider = latest_data.get("provider")
                except Exception:
                    pass
            self._send_json({
                "status": "ok",
                "current_run": run_info,
                "model": active_model,
                "provider": active_provider
            })
            return
            
        elif path == "/api/sessions":
            sessions = AangLogger.list_sessions()
            self._send_json(sessions)
            return
            
        elif path.startswith("/api/sessions/"):
            session_id = path.replace("/api/sessions/", "").strip()
            data = AangLogger.get_session(session_id)
            if data:
                self._send_json(data)
            else:
                self._send_json({"error": "Session not found"}, 404)
            return
            
        elif path == "/api/latest":
            latest = None
            latest_path = os.path.join(".aang", "latest_session.json")
            if os.path.exists(latest_path):
                try:
                    with open(latest_path, 'r') as f:
                        latest = json.load(f)
                except Exception:
                    pass
            if not latest:
                sessions = AangLogger.list_sessions()
                if sessions:
                    latest = AangLogger.get_session(sessions[0]["id"])
            self._send_json(latest or {"error": "No sessions yet"})
            return
            
        elif path == "/api/raw-log":
            content = ""
            if os.path.exists("aang.log"):
                with open("aang.log", "r") as f:
                    content = f.read()
            self._send_json({"log": content})
            return
            
        elif path == "/api/prompts":
            self._send_json({
                "system_prompt": SYSTEM_PROMPT,
                "model": settings.model,
                "provider": settings.provider
            })
            return

        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        if path == "/api/run":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
            except Exception:
                data = {}
                
            task = data.get("task") or "Analyze repository code structure and verify health"
            repo = data.get("repo")
            
            if _current_run["active"]:
                self._send_json({"error": "A task run is already in progress"}, 409)
                return
                
            thread = threading.Thread(target=execute_agent_task, args=(task, repo), daemon=True)
            thread.start()
            
            self._send_json({
                "status": "started",
                "task": task,
                "message": f"Agent task initiated: {task}"
            })
            return

        self._send_json({"error": "Not Found"}, 404)

    def _send_json(self, data: Any, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

def run_server(port: int = PORT):
    os.makedirs(os.path.dirname(HTML_FILE_PATH), exist_ok=True)
    server_address = ("", port)
    
    # Try port, if in use try port + 1
    for attempt in range(5):
        target_port = port + attempt
        try:
            httpd = http.server.ThreadingHTTPServer(("", target_port), AangAPIHandler)
            print(f"==================================================")
            print(f"🚀 Aang Log & Harness Dashboard running on:")
            print(f"   http://localhost:{target_port}")
            print(f"==================================================")
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\nShutting down server...")
                httpd.server_close()
            return
        except OSError as e:
            if "Address already in use" in str(e):
                continue
            raise

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    run_server(port)
