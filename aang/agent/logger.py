import json
import time
import os
import re
from datetime import datetime
from typing import Any, Optional, Dict, List

class AangLogger:
    """Comprehensive operation logger that writes human-readable logs and structured JSON for the web frontend."""
    
    def __init__(self, log_path: str = "aang.log", session_id: Optional[str] = None, sessions_dir: str = ".aang/sessions"):
        self.log_path = log_path
        self.sessions_dir = sessions_dir
        os.makedirs(self.sessions_dir, exist_ok=True)
        
        self.start_time = time.time()
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_id = session_id or f"session_{timestamp_str}"
        
        # In-memory structured session data
        self.session_data: Dict[str, Any] = {
            "id": self.session_id,
            "task": "",
            "repo_path": "",
            "provider": "",
            "model": "",
            "start_time": datetime.now().isoformat(),
            "end_time": None,
            "duration": 0.0,
            "status": "running",
            "target_iterations": 1,
            "iterations": 0,
            "files_modified": [],
            "summary": "",
            "preflight": None,
            "steps": [],
            "diff": ""
        }
        
        self._current_step: Optional[Dict[str, Any]] = None
        
        # Write initial text header
        with open(self.log_path, 'w') as f:
            f.write(f"{'='*80}\n")
            f.write(f"AANG SESSION LOG — {self.session_id}\n")
            f.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*80}\n\n")
            
        self._flush_json()

    def _elapsed(self) -> str:
        elapsed = time.time() - self.start_time
        return f"{elapsed:.2f}s"
    
    def _write_text(self, entry: str):
        with open(self.log_path, 'a') as f:
            f.write(entry)

    def _flush_json(self):
        """Write current session state to disk for live frontend polling."""
        try:
            self.session_data["duration"] = round(time.time() - self.start_time, 2)
            session_file = os.path.join(self.sessions_dir, f"{self.session_id}.json")
            with open(session_file, 'w') as f:
                json.dump(self.session_data, f, indent=2)
            
            # Also write latest pointer
            latest_file = os.path.join(os.path.dirname(self.sessions_dir), "latest_session.json")
            with open(latest_file, 'w') as f:
                json.dump(self.session_data, f, indent=2)
        except Exception:
            pass

    def start_new_session(self, task: str, repo_path: str, model: str, provider: str, target_iterations: int = 1) -> str:
        """Start a completely new session with fresh timestamps, steps, and session ID."""
        self.start_time = time.time()
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_id = f"session_{timestamp_str}"
        self.session_data = {
            "id": self.session_id,
            "task": task,
            "repo_path": repo_path,
            "provider": provider,
            "model": model,
            "start_time": datetime.now().isoformat(),
            "end_time": None,
            "duration": 0.0,
            "status": "running",
            "target_iterations": target_iterations,
            "iterations": 0,
            "files_modified": [],
            "summary": "",
            "preflight": None,
            "steps": [],
            "diff": ""
        }
        self._current_step = None
        
        entry = (
            f"\n\n{'='*80}\n"
            f"AANG SESSION — {self.session_id}\n"
            f"Task: {task}\n"
            f"Repo: {repo_path}\n"
            f"Model: {model} ({provider})\n"
            f"Target Iterations: {target_iterations}\n"
            f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"{'='*80}\n\n"
        )
        self._write_text(entry)
        self._flush_json()
        return self.session_id

    def log_session_start(self, task: str, repo_path: str, model: str, provider: str, target_iterations: int = 1):
        if not self.session_data.get("task") or self.session_data.get("status") != "running":
            self.start_new_session(task, repo_path, model, provider, target_iterations)
        else:
            self.session_data["task"] = task
            self.session_data["repo_path"] = repo_path
            self.session_data["model"] = model
            self.session_data["provider"] = provider
            self.session_data["target_iterations"] = target_iterations
            
            entry = (
                f"SESSION CONFIG:\n"
                f"  Task: {task}\n"
                f"  Repo: {repo_path}\n"
                f"  Model: {model} ({provider})\n"
                f"  Target Iterations: {target_iterations}\n"
                f"{'-'*80}\n\n"
            )
            self._write_text(entry)
            self._flush_json()

    def log_preflight(self, command: str, exit_code: int, stdout: str, stderr: str, repo_files: List[str], focal_files: List[str]):
        preflight_info = {
            "command": command,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "repo_files": repo_files,
            "focal_files": focal_files
        }
        self.session_data["preflight"] = preflight_info
        
        entry = (
            f"[{self._elapsed()}] ── PREFLIGHT DIAGNOSTICS ──\n"
            f"  Command: {command} (Exit: {exit_code})\n"
            f"  Repository files ({len(repo_files)}): {', '.join(repo_files[:6])}\n"
            f"  Focal source files: {', '.join(focal_files)}\n"
        )
        if stdout:
            truncated = stdout[:800].replace('\n', '\n  │ ')
            entry += f"  Stdout preview:\n  │ {truncated}\n"
        entry += f"{'-'*80}\n\n"
        self._write_text(entry)
        self._flush_json()

    def log_llm_request(self, iteration: int, message_count: int, tool_count: int, messages: Optional[List[Any]] = None):
        self._current_step = {
            "iteration": iteration,
            "timestamp": datetime.now().isoformat(),
            "llm_request": {
                "message_count": message_count,
                "tool_count": tool_count,
                "messages": [
                    {
                        "role": getattr(m, "role", "unknown"),
                        "content": getattr(m, "content", "")[:2000] if getattr(m, "content", None) else "",
                        "name": getattr(m, "name", None)
                    } for m in (messages or [])
                ] if messages else []
            },
            "llm_response": None,
            "tool_executions": [],
            "verification": None
        }
        
        entry = (
            f"[{self._elapsed()}] ── LLM REQUEST (iteration {iteration}) ──\n"
            f"  Messages in context: {message_count}\n"
            f"  Tools available: {tool_count}\n\n"
        )
        self._write_text(entry)
        self._flush_json()

    def log_llm_response(self, iteration: int, text: Optional[str], tool_calls: Optional[list], finish_reason: str, duration: float):
        parsed_tools = []
        for tc in (tool_calls or []):
            tc_dict = {
                "id": getattr(tc, "id", ""),
                "name": getattr(tc, "name", ""),
                "arguments": getattr(tc, "arguments", "")
            }
            try:
                tc_dict["parsed_args"] = json.loads(getattr(tc, "arguments", "{}"))
            except Exception:
                tc_dict["parsed_args"] = getattr(tc, "arguments", "")
            parsed_tools.append(tc_dict)

        if self._current_step:
            self._current_step["llm_response"] = {
                "duration": round(duration, 3),
                "text": text or "",
                "finish_reason": finish_reason,
                "tool_calls": parsed_tools
            }

        entry = f"[{self._elapsed()}] ── LLM RESPONSE (iteration {iteration}, {duration:.2f}s) ──\n"
        if text:
            display = text[:500].replace('\n', '\n  │ ')
            entry += f"  │ {display}\n"
            if len(text) > 500:
                entry += f"  │ ... ({len(text)} chars total)\n"
        
        if tool_calls:
            entry += f"  Tool calls ({len(tool_calls)}):\n"
            for tc in tool_calls:
                try:
                    args_pretty = json.dumps(json.loads(tc.arguments), indent=2)
                    args_display = args_pretty.replace('\n', '\n    │ ')
                except:
                    args_display = tc.arguments
                entry += f"    ├─ {tc.name}()\n"
                entry += f"    │ {args_display}\n"
        
        entry += f"  Finish reason: {finish_reason}\n\n"
        self._write_text(entry)
        self._flush_json()

    def log_tool_execution(self, tool_name: str, arguments: str, result: str, duration: float):
        tool_data = {
            "tool_name": tool_name,
            "arguments": arguments,
            "result": result,
            "duration": round(duration, 3)
        }
        try:
            tool_data["parsed_args"] = json.loads(arguments)
        except Exception:
            pass

        if self._current_step:
            self._current_step["tool_executions"].append(tool_data)

        entry = f"[{self._elapsed()}] ── TOOL: {tool_name} ({duration:.2f}s) ──\n"
        try:
            args_pretty = json.dumps(json.loads(arguments), indent=2)
            entry += f"  Args: {args_pretty}\n"
        except:
            entry += f"  Args: {arguments}\n"
        
        if len(result) > 1000:
            entry += f"  Result ({len(result)} chars):\n"
            entry += f"  │ {result[:1000].replace(chr(10), chr(10) + '  │ ')}\n"
            entry += f"  │ ... (truncated)\n"
        else:
            entry += f"  Result:\n"
            entry += f"  │ {result.replace(chr(10), chr(10) + '  │ ')}\n"
        
        entry += "\n"
        self._write_text(entry)
        self._flush_json()

    def log_step_finish(self):
        """Commit the current step to the session history."""
        if self._current_step:
            self.session_data["steps"].append(self._current_step)
            self._current_step = None
            self._flush_json()

    def log_verification(self, command: str, exit_code: int, stdout: str, stderr: str, passed: bool):
        verification_data = {
            "command": command,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "passed": passed
        }
        if self._current_step:
            self._current_step["verification"] = verification_data
        
        entry = (
            f"[{self._elapsed()}] ── VERIFICATION: {command} ──\n"
            f"  Result: {'PASSED ✓' if passed else 'FAILED ✗'} (Exit: {exit_code})\n"
        )
        if stdout:
            entry += f"  Stdout: {stdout.strip()[:300]}\n"
        entry += "\n"
        self._write_text(entry)
        self._flush_json()

    def log_llm_error(self, iteration: int, error: str):
        entry = (
            f"[{self._elapsed()}] ── LLM ERROR (iteration {iteration}) ──\n"
            f"  {error}\n\n"
        )
        self._write_text(entry)
        if self._current_step:
            self._current_step["error"] = error
        self._flush_json()

    def log_complete(self, summary: str, iterations: int, files_changed: int, diff: str = "", status: str = "completed", files_modified: Optional[List[str]] = None):
        self.session_data["end_time"] = datetime.now().isoformat()
        self.session_data["duration"] = round(time.time() - self.start_time, 2)
        self.session_data["status"] = status
        self.session_data["iterations"] = iterations
        self.session_data["summary"] = summary
        self.session_data["diff"] = diff
        if files_modified is not None:
            self.session_data["files_modified"] = list(files_modified)
        
        if self._current_step:
            self.session_data["steps"].append(self._current_step)
            self._current_step = None
            
        entry = (
            f"\n{'='*80}\n"
            f"SESSION COMPLETE: {status.upper()}\n"
            f"  Duration: {self._elapsed()}\n"
            f"  Iterations: {iterations} (Target: {self.session_data['target_iterations']})\n"
            f"  Files changed: {files_changed}\n"
            f"  Summary: {summary}\n"
        )
        if diff:
            entry += f"\n--- DIFF ---\n{diff}\n"
        entry += f"{'='*80}\n"
        self._write_text(entry)
        self._flush_json()

    @staticmethod
    def list_sessions(sessions_dir: str = ".aang/sessions") -> List[Dict[str, Any]]:
        """List all saved sessions, sorted newest first."""
        if not os.path.exists(sessions_dir):
            return []
        sessions = []
        for fname in os.listdir(sessions_dir):
            if fname.endswith(".json"):
                try:
                    fpath = os.path.join(sessions_dir, fname)
                    with open(fpath, 'r') as f:
                        data = json.load(f)
                        sessions.append({
                            "id": data.get("id", fname.replace(".json", "")),
                            "task": data.get("task", ""),
                            "status": data.get("status", "unknown"),
                            "iterations": data.get("iterations", 0),
                            "target_iterations": data.get("target_iterations", 1),
                            "duration": data.get("duration", 0),
                            "model": data.get("model", ""),
                            "start_time": data.get("start_time", ""),
                            "files_modified_count": len(data.get("files_modified", [])),
                            "files_modified": data.get("files_modified", [])
                        })
                except Exception:
                    continue
        sessions.sort(key=lambda s: s.get("start_time", ""), reverse=True)
        return sessions

    @staticmethod
    def get_session(session_id: str, sessions_dir: str = ".aang/sessions") -> Optional[Dict[str, Any]]:
        if session_id == "latest":
            latest_file = os.path.join(os.path.dirname(sessions_dir), "latest_session.json")
            if os.path.exists(latest_file):
                try:
                    with open(latest_file, 'r') as f:
                        return json.load(f)
                except Exception:
                    pass
            sessions = AangLogger.list_sessions(sessions_dir)
            if sessions:
                return AangLogger.get_session(sessions[0]["id"], sessions_dir)
            return None

        fpath = os.path.join(sessions_dir, f"{session_id}.json")
        if not os.path.exists(fpath):
            # Check latest
            latest_file = os.path.join(os.path.dirname(sessions_dir), "latest_session.json")
            if os.path.exists(latest_file):
                try:
                    with open(latest_file, 'r') as f:
                        data = json.load(f)
                        if data.get("id") == session_id:
                            return data
                except Exception:
                    pass
            return None
        try:
            with open(fpath, 'r') as f:
                return json.load(f)
        except Exception:
            return None
