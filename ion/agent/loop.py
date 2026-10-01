import json
import time
import re
import os
from typing import Callable, Any, Optional, Dict, List
from ion.agent.state import AgentState
from ion.agent.prompts import SYSTEM_PROMPT
from ion.agent.logger import IonLogger
from ion.agent.indexer import SymbolIndexer
from ion.llm.base import LLMProvider
from ion.llm.types import Message
from ion.tools.router import ToolRouter
from ion.sandbox.base import SandboxEnvironment

class AgentLoop:
    def __init__(self, provider: LLMProvider, tool_router: ToolRouter, 
                 ui_callback: Callable[[AgentState], None] = None,
                 logger: Optional[IonLogger] = None,
                 sandbox: Optional[SandboxEnvironment] = None):
        self.provider = provider
        self.tool_router = tool_router
        self.ui_callback = ui_callback
        self.logger = logger
        self.sandbox = sandbox
        self._is_cancelled = False
        
        # If sandbox not explicitly passed, try resolving from tools
        if not self.sandbox and hasattr(tool_router, "_tools"):
            for tool in tool_router._tools.values():
                if hasattr(tool, "sandbox"):
                    self.sandbox = tool.sandbox
                    break
                    
        self.state = None

    def cancel(self):
        """Signal the agent loop to cancel execution gracefully."""
        self._is_cancelled = True

    def _fold_command_output(self, raw_output: str) -> str:
        """Fold verbose test command output, preserving the exact failure trace and exit code while omitting boilerplate."""
        lines = raw_output.splitlines()
        if len(lines) <= 20:
            return raw_output

        exit_code_line = next((l for l in lines if "Exit Code:" in l or "Command:" in l), "")
        error_lines = []
        capture = False
        for l in lines:
            if any(kw in l for kw in ["FAIL", "Error:", "TypeError:", "ReferenceError:", "SyntaxError:", "AssertionError:", "DEPRECATION", "FAILED:"]):
                capture = True
            if capture:
                error_lines.append(l)
                if len(error_lines) >= 15:
                    break

        passing_count = sum(1 for l in lines if "✓" in l or "PASS" in l or "passed" in l)
        passing_summary = f"[{passing_count} passing tests/checks omitted]" if passing_count > 0 else ""

        folded = []
        if exit_code_line:
            folded.append(exit_code_line)
        if passing_summary:
            folded.append(passing_summary)
        if error_lines:
            folded.append("\n".join(error_lines))
        else:
            folded.append("\n".join(lines[-15:]))

        return "\n".join(folded)

    def _prune_context(self, messages: List[Message], max_token_budget: int = 4000) -> List[Message]:
        """
        Golden Midground Context Optimizer:
        Balances Token Economy (free Groq/OpenRouter TPM limits) vs Context Fidelity (preventing amnesia).
        
        1. Keeps System Prompt and initial task pinned.
        2. Leaves messages untouched if under max_token_budget (~4,000 tokens / ~16k chars).
        3. Uses Observation Folding:
           - Folds verbose command outputs (npm test / pytest / build) into error summaries + passing test counts.
           - Folds older read_file outputs into compact line receipts.
        4. Leaves the most recent 4 messages in full raw fidelity.
        """
        total_chars = sum(len(m.content or "") for m in messages)
        estimated_tokens = total_chars // 4
        
        if estimated_tokens <= max_token_budget and len(messages) <= 8:
            return messages

        # Protect system prompt (0) and user task (1), and the most recent 4 messages
        recent_threshold = max(2, len(messages) - 4)
        pruned = []

        for idx, msg in enumerate(messages):
            if idx < 2 or idx >= recent_threshold:
                pruned.append(msg)
                continue

            # Process older tool outputs
            if msg.role == "tool" and msg.content:
                content = msg.content
                name = msg.name or ""

                # 1. Observation Folding for test / command runs
                if "run_command" in name or "Exit Code:" in content or "npm" in content or "test" in content:
                    pruned_content = self._fold_command_output(content)
                    pruned.append(Message(
                        role="tool",
                        name=msg.name,
                        tool_call_id=msg.tool_call_id,
                        content=pruned_content
                    ))

                # 2. Semantic Compaction for older file reads
                elif "read_file" in name or len(content.splitlines()) > 30:
                    lines = content.splitlines()
                    first_few = "\n".join(lines[:3])
                    pruned_content = f"{first_few}\n... [Remaining {len(lines)-3} lines folded into memory. Use read_file to inspect again if needed] ..."
                    pruned.append(Message(
                        role="tool",
                        name=msg.name,
                        tool_call_id=msg.tool_call_id,
                        content=pruned_content
                    ))

                elif len(content) > 300:
                    pruned.append(Message(
                        role="tool",
                        name=msg.name,
                        tool_call_id=msg.tool_call_id,
                        content=content[:150] + "\n... [Intermediate tool output folded] ..."
                    ))
                else:
                    pruned.append(msg)
            else:
                pruned.append(msg)

        return pruned

    def _call_llm_with_retry(self, messages, schemas, max_retries=5):
        """Call LLM with exponential backoff retry for rate limits."""
        prepared_messages = self._prune_context(messages)
        for attempt in range(max_retries):
            try:
                return self.provider.generate(prepared_messages, tools=schemas)
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "rate_limit" in error_str or "Rate limit" in error_str:
                    wait = 4 * (attempt + 1)  # 4s, 8s, 12s, 16s, 20s
                    # Check for explicit retry-after header / message (e.g. 'try again in 5.3s')
                    match = re.search(r'try again in ([\d\.]+)s', error_str, re.IGNORECASE)
                    if match:
                        try:
                            wait = max(wait, float(match.group(1)) + 1.0)
                        except Exception:
                            pass
                    if self.state:
                        self.state.status_message = f"Rate limited by provider, cooling down for {int(wait)}s (attempt {attempt+1}/{max_retries})..."
                    if self.ui_callback:
                        self.ui_callback(self.state)
                    time.sleep(wait)
                    continue
                elif any(x in error_str for x in ["tool_use_failed", "output_parse_failed", "Parsing failed", "Failed to parse tool call arguments as JSON", "malformed JSON"]):
                    wait = 1.0 + (attempt * 0.5)
                    if self.state:
                        self.state.status_message = f"Tool call format glitch from provider, retrying (attempt {attempt+1}/{max_retries})..."
                    if self.ui_callback:
                        self.ui_callback(self.state)
                    time.sleep(wait)
                    continue
                raise
        raise Exception("LLM call failed after retries")

    def _extract_test_command(self, task: str) -> Optional[str]:
        """Extract a test command mentioned in the task description."""
        patterns = [
            r'Run:\s*([^\n]+)',
            r'run:\s*([^\n]+)',
            r'test:\s*([^\n]+)',
            r'(npm\s+test[^\n]*)',
            r'(node\s+[^\n]+\.js)',
            r'(python\s+-m\s+pytest[^\n]*)',
            r'(pytest[^\n]*)'
        ]
        for pattern in patterns:
            match = re.search(pattern, task, re.IGNORECASE)
            if match:
                cmd = match.group(1).strip()
                # Clean up trailing punctuation
                cmd = re.sub(r'[\.\;]+$', '', cmd)
                return cmd
        return None

    def _run_preflight(self, task: str) -> Dict[str, Any]:
        """Run preflight diagnostics to gather repo files, initial failures, and focal code."""
        preflight_data = {
            "test_cmd": None,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "repo_files": [],
            "focal_files": {},
            "enhanced_prompt": f"Task: {task}"
        }
        
        if not self.sandbox:
            return preflight_data

        # 1. Gather repository files
        try:
            raw_files = self.sandbox.list_files(".")
            repo_files = [
                f.strip() for f in raw_files.splitlines() 
                if f.strip() and not any(part in f for part in ['.git', '__pycache__', '.pytest_cache', 'venv', 'node_modules'])
            ]
            preflight_data["repo_files"] = repo_files
        except Exception:
            repo_files = []

        # 2. Check for test command and run preflight test
        test_cmd = self._extract_test_command(task)
        if not test_cmd:
            # Check for JS test files
            js_test = next((f for f in repo_files if f.endswith("test_auth.js") or f.endswith("test.js") or ("test" in f and f.endswith(".js"))), None)
            if js_test:
                test_cmd = f"node {js_test}"
            elif any("package.json" in f for f in repo_files):
                try:
                    pkg_text = self.sandbox.read_file("package.json")
                    pkg = json.loads(pkg_text)
                    script_cmd = pkg.get("scripts", {}).get("test", "")
                    if script_cmd and "node " in script_cmd:
                        test_cmd = script_cmd
                    else:
                        test_cmd = "npm test"
                except Exception:
                    test_cmd = "npm test"
            elif any(f.startswith("test_") or "/test_" in f for f in repo_files):
                test_cmd = "python -m pytest -q"

        if test_cmd:
            preflight_data["test_cmd"] = test_cmd
            code, stdout, stderr = self.sandbox.run_command(test_cmd, timeout=30)
            preflight_data["exit_code"] = code
            preflight_data["stdout"] = stdout
            preflight_data["stderr"] = stderr

        # 3. Detect focal source files implicated in failures
        focal_files = {}

        def is_test_runner_or_test_file(f: str) -> bool:
            base = os.path.basename(f).lower()
            parts = [p.lower() for p in f.split('/')]
            return (
                base.startswith("test_") or 
                base.startswith("test.") or 
                base.endswith("_test.py") or 
                base.endswith(".test.js") or 
                base == "run_all.js" or
                "test" in parts or 
                "tests" in parts or
                "__tests__" in parts
            )

        candidate_files = []
        task_lower = task.lower()
        
        # Priority A: Files explicitly mentioned in the task prompt (excluding test runners)
        for f in repo_files:
            if is_test_runner_or_test_file(f):
                continue
            base = os.path.basename(f).lower()
            name_no_ext = os.path.splitext(base)[0]
            if base in task_lower or f.lstrip('./').lower() in task_lower or (name_no_ext in task_lower and len(name_no_ext) > 3):
                if f not in candidate_files:
                    candidate_files.append(f)

        # Index repo symbols and match against task query
        symbol_indexer = SymbolIndexer(self.sandbox)
        symbol_indexer.build_index(repo_files)
        relevant_symbols = symbol_indexer.find_relevant_symbols(task)
        symbol_files = {s["file"] for s in relevant_symbols if not is_test_runner_or_test_file(s["file"])}

        # Priority B: Files containing relevant symbols identified by SymbolIndexer
        for f in symbol_files:
            if f in repo_files and f not in candidate_files:
                candidate_files.append(f)

        # Priority C: Look for source files mentioned in stdout/stderr
        output_text = (preflight_data["stdout"] or "") + (preflight_data["stderr"] or "")
        for f in repo_files:
            if is_test_runner_or_test_file(f):
                continue
            fname = os.path.basename(f)
            if fname in output_text and f not in candidate_files:
                candidate_files.append(f)

        # Priority D: If still under 8 candidates, include other non-test source files
        if len(candidate_files) < 8:
            for f in repo_files:
                if is_test_runner_or_test_file(f):
                    continue
                if (f.endswith(".py") or f.endswith(".js") or f.endswith(".ts")) and f not in candidate_files:
                    candidate_files.append(f)

        # Sort candidate files so files matching task words or containing key symbols come first
        task_clean = re.sub(r'[^a-zA-Z0-9_\.]', ' ', task.lower())
        task_tokens = set(task_clean.split())
        
        def match_priority(f: str) -> int:
            base = os.path.basename(f).lower()
            name_no_ext = os.path.splitext(base)[0]
            score = 0
            # Explicit mention in task prompt gets highest priority
            if base in task.lower() or f.lstrip('./').lower() in task.lower():
                score += 100
            elif f in symbol_files:
                score += 50
            elif f"{name_no_ext} js" in task.lower() or f"{name_no_ext} py" in task.lower():
                score += 35
            elif name_no_ext in task_tokens:
                score += 20
            elif any(t in name_no_ext for t in task_tokens if len(t) > 2):
                score += 10
            return score

        candidate_files.sort(key=match_priority, reverse=True)

        # Read top candidate files (up to 6 files with a total line budget of 1500 lines)
        total_focal_lines = 0
        for cf in candidate_files[:6]:
            try:
                content = self.sandbox.read_file(cf)
                lines = content.splitlines()
                # Include file if under 500 lines and within total budget (or if high-priority match)
                prio = match_priority(cf)
                if len(lines) <= 500 and (total_focal_lines + len(lines) <= 1500 or prio >= 100 or len(focal_files) < 3):
                    focal_files[cf] = content
                    total_focal_lines += len(lines)
            except Exception:
                pass
                
        preflight_data["focal_files"] = focal_files

        # 4. Construct enhanced user prompt with preflight context
        task_lower = task.lower()
        is_coding_task = any(w in task_lower for w in [
            "test", "fix", "bug", "code", "run", "auth", "add", "implement",
            "create", "audit", "refactor", "update", "write", "check", "error",
            "make", "build", "frontend", "ui", "page", "html", "css", "js",
            "component", "feature", "endpoint", "api"
        ]) or len(task.split()) > 3

        wants_test_fix = any(w in task_lower for w in ["test", "fix", "failing", "broken", "bug", "audit", "verify", "diagnos"])

        prompt_parts = [f"# Coding Task\n{task}\n"]
        
        if repo_files:
            prompt_parts.append(f"## Repository Files\n" + "\n".join(f"- {f}" for f in repo_files[:15]) + "\n")

        if relevant_symbols and is_coding_task:
            prompt_parts.append("## Key Symbols Identified in Repo")
            for s in relevant_symbols[:8]:
                prompt_parts.append(f"- `{s['name']}` ({s.get('kind', 'symbol')}) -> `{s['file']}:{s.get('line', 1)}`")
            prompt_parts.append("")

        if focal_files and is_coding_task:
            prompt_parts.append("## Target Source Code")
            for fpath, fcontent in focal_files.items():
                prompt_parts.append(f"### `{fpath}`\n```javascript\n{fcontent}\n```\n")

        if not is_coding_task:
            prompt_parts.append(
                "## Directive:\n"
                "- The user gave a conversational input or greeting.\n"
                "- Respond concisely and politely in text explaining what you can do as Ion, without calling any tools."
            )
        elif wants_test_fix and test_cmd and preflight_data["exit_code"] != 0:
            preview_out = (preflight_data["stdout"] or preflight_data["stderr"])
            if len(preview_out) > 2000:
                preview_out = preview_out[:2000] + "\n... (truncated)"
            prompt_parts.append(
                f"## Preflight Test Diagnostics\n"
                f"Test command `{test_cmd}` failed with exit code {preflight_data['exit_code']}:\n"
                f"```text\n{preview_out}\n```\n"
            )
            prompt_parts.append(
                "## Directive for Iteration 1:\n"
                "- Preflight diagnostics and relevant source files are already provided above.\n"
                "- Do NOT re-run tests or list files to discover what failed.\n"
                "- Apply the required fix using `replace_in_file` immediately in Iteration 1.\n"
                "- For simple tasks, you may call `complete_task` in the same iteration or let automatic test verification complete it."
            )
        else:
            prompt_parts.append(
                "## Directive for Iteration 1:\n"
                "- Review the repository structure, source code, and task requirements.\n"
                "- Implement the requested changes, new files, frontend, or tests using `write_file` or `replace_in_file`.\n"
                "- Verify your work and call `complete_task` when finished."
            )

        preflight_data["enhanced_prompt"] = "\n".join(prompt_parts)
        
        if self.logger:
            self.logger.log_preflight(
                command=test_cmd or "none",
                exit_code=preflight_data["exit_code"],
                stdout=preflight_data["stdout"],
                stderr=preflight_data["stderr"],
                repo_files=repo_files,
                focal_files=list(focal_files.keys())
            )
            
        return preflight_data

    def run(self, task: str, max_iterations: int = 15) -> AgentState:
        self._is_cancelled = False
        self.state = AgentState(task=task, max_iterations=max_iterations)
        
        # Determine target iterations based on task hint
        target_iter = 1 if "easy" in task.lower() or "simple" in task.lower() else (2 if "medium" in task.lower() else 3)
        if self.logger:
            repo_display = getattr(self.sandbox, "repo_path", ".")
            self.logger.log_session_start(
                task=task,
                repo_path=str(repo_display),
                model=getattr(self.provider, "model", "default"),
                provider=self.provider.__class__.__name__.lower().replace("provider", ""),
                target_iterations=target_iter
            )

        # 1. Run Preflight Diagnostics
        self.state.status_message = "Running preflight diagnostics..."
        if self.ui_callback:
            self.ui_callback(self.state)
            
        preflight = self._run_preflight(task)
        test_cmd = preflight.get("test_cmd")

        if self._is_cancelled:
            self.state.status_message = "Cancelled before start."
            return self.state

        # 2. Setup Initial Context
        self.state.add_message(Message(role="system", content=SYSTEM_PROMPT))
        self.state.add_message(Message(role="user", content=preflight["enhanced_prompt"]))
        
        self.state.status_message = "Starting agent reasoning..."
        if self.ui_callback:
            self.ui_callback(self.state)

        # 3. Main Agent Loop
        while self.state.iteration < self.state.max_iterations and not self.state.is_complete and not self._is_cancelled:
            if self._is_cancelled:
                break
            self.state.iteration += 1
            self.state.status_message = f"Iteration {self.state.iteration}: Reasoning..."
            if self.ui_callback:
                self.ui_callback(self.state)

            schemas = self.tool_router.get_schemas()
            schemas.append({
                "name": "complete_task",
                "description": "Call this when the task is fully done and verified.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "Summary of the changes made and verification results."
                        }
                    },
                    "required": ["summary"]
                }
            })

            # Log LLM Request
            if self.logger:
                self.logger.log_llm_request(
                    self.state.iteration, 
                    len(self.state.messages), 
                    len(schemas),
                    messages=self.state.messages
                )

            t0 = time.time()
            try:
                response = self._call_llm_with_retry(self.state.messages, schemas)
            except Exception as e:
                self.state.status_message = f"Error: LLM call failed: {str(e)}"
                if self.logger:
                    self.logger.log_llm_error(self.state.iteration, str(e))
                if self.ui_callback:
                    self.ui_callback(self.state)
                break
                
            llm_duration = time.time() - t0

            # Log LLM Response
            if self.logger:
                self.logger.log_llm_response(
                    self.state.iteration, response.text, 
                    response.tool_calls, response.finish_reason, llm_duration
                )

            # Record assistant turn in context
            self.state.add_message(Message(
                role="assistant",
                content=response.text,
                tool_calls=response.tool_calls
            ))

            has_complete_call = False
            modified_in_this_step = False

            if response.tool_calls:
                for tool_call in response.tool_calls:
                    if self._is_cancelled:
                        self.state.status_message = "Cancelled by user."
                        break

                    if tool_call.name == "complete_task":
                        has_complete_call = True
                        try:
                            args = json.loads(tool_call.arguments)
                            summary = args.get("summary", "Task completed.")
                        except Exception:
                            summary = "Task completed."
                            
                        self.state.is_complete = True
                        self.state.status_message = f"✓ Complete: {summary}"
                        self.state.summary = summary
                        self.state.add_message(Message(
                            role="tool", tool_call_id=tool_call.id,
                            name=tool_call.name, content="Task completed successfully."
                        ))
                        break

                    self.state.status_message = f"→ {tool_call.name}"
                    if self.ui_callback:
                        self.ui_callback(self.state)
                        
                    # Protect against truncated file writes when provider hits token limit
                    if response.finish_reason == "length" and tool_call.name in ["write_file", "replace_in_file", "apply_patch"]:
                        result = (
                            f"Error: Tool execution blocked because the provider response was truncated due to output token length limit (finish_reason='length'). "
                            f"Your tool arguments were incomplete and would have corrupted {tool_call.name}. "
                            f"Please provide smaller, targeted changes using replace_in_file or complete your response in smaller increments."
                        )
                        self.state.add_message(Message(
                            role="tool", tool_call_id=tool_call.id,
                            name=tool_call.name, content=result
                        ))
                        continue

                    # Execute tool with timing
                    t_tool = time.time()
                    result = self.tool_router.execute(tool_call.name, tool_call.arguments)
                    tool_duration = time.time() - t_tool
                    
                    if self.logger:
                        self.logger.log_tool_execution(tool_call.name, tool_call.arguments, result, tool_duration)
                    
                    # Track modified files and dynamic test command discovery
                    if tool_call.name in ["write_file", "replace_in_file"]:
                        modified_in_this_step = True
                        try:
                            args = json.loads(tool_call.arguments)
                            target_p = args.get("path", "unknown")
                            self.state.files_modified.add(target_p)
                            if not test_cmd:
                                if target_p.endswith(".js") and ("test" in target_p):
                                    test_cmd = f"node {target_p}"
                                elif target_p.endswith(".py") and ("test" in target_p):
                                    test_cmd = f"python -m pytest {target_p} -q"
                        except Exception:
                            pass
                    elif tool_call.name == "run_command":
                        try:
                            cmd_args = json.loads(tool_call.arguments)
                            cmd_str = cmd_args.get("command", "")
                            if any(runner in cmd_str for runner in ["pytest", "node ", "npm test", "python -m unittest"]):
                                test_cmd = cmd_str
                        except Exception:
                            pass
                    
                    self.state.add_message(Message(
                        role="tool", tool_call_id=tool_call.id,
                        name=tool_call.name, content=result
                    ))

            # Auto-verification if files were modified and a test command is available
            tests_passed = False
            has_source_modified = any(
                not os.path.basename(f).startswith("test_") and not os.path.basename(f).startswith("test.")
                for f in self.state.files_modified
            )
            if modified_in_this_step and test_cmd and self.sandbox and has_source_modified:
                v_code, v_stdout, v_stderr = self.sandbox.run_command(test_cmd, timeout=30)
                if v_code == 127 and "npm" in test_cmd:
                    alt_cmd = "node test_auth.js"
                    v_code2, v_stdout2, v_stderr2 = self.sandbox.run_command(alt_cmd, timeout=30)
                    if v_code2 != 127:
                        test_cmd = alt_cmd
                        v_code, v_stdout, v_stderr = v_code2, v_stdout2, v_stderr2
                tests_passed = (v_code == 0)
                if self.logger:
                    self.logger.log_verification(test_cmd, v_code, v_stdout, v_stderr, tests_passed)
                
                # If tests now pass and agent modified code, we complete!
                if tests_passed:
                    self.state.is_complete = True
                    auto_summary = f"All tests verified passing with '{test_cmd}'."
                    self.state.status_message = f"✓ Complete: {auto_summary}"
                    self.state.summary = auto_summary
                else:
                    # Provide immediate feedback to the agent so it can repair in the next iteration
                    fail_output = (v_stdout or v_stderr)
                    if len(fail_output) > 2000:
                        fail_output = fail_output[:2000] + "\n... (truncated)"
                    self.state.add_message(Message(
                        role="user",
                        content=(
                            f"[Verification Feedback]\nTest command `{test_cmd}` is still failing (Exit code: {v_code}):\n"
                            f"```text\n{fail_output}\n```\n"
                            f"Analyze the error, adjust your fix, and ensure all tests pass.\n"
                            f"- If an edit introduced syntax/runtime issues, use `read_file` to inspect the file or `write_file` to rewrite cleanly.\n"
                            f"- If multiple files are involved, check whether all parts of the flow (e.g. error handling, rollback, concurrency) were updated."
                        )
                    ))

            elif response.finish_reason == "stop" and not response.tool_calls:
                # Agent stopped with text summary
                if self.state.files_modified and response.text:
                    self.state.is_complete = True
                    summary = response.text[:200]
                    self.state.status_message = f"✓ Complete: {summary}"
                    self.state.summary = summary
                else:
                    self.state.add_message(Message(
                        role="user",
                        content="You stopped without calling complete_task. If done, call complete_task. Otherwise, continue."
                    ))

            # Commit current step in logger
            if self.logger:
                self.logger.log_step_finish()
                
            if self.ui_callback:
                self.ui_callback(self.state)

        # Retrieve git diff for final summary and web frontend
        git_diff = ""
        if self.sandbox:
            try:
                _, git_diff, _ = self.sandbox.run_command("git diff", timeout=10)
            except Exception:
                pass

        if self._is_cancelled:
            self.state.status_message = "Cancelled by user."
            if self.logger:
                self.logger.log_complete(
                    summary="Cancelled by user.",
                    iterations=self.state.iteration,
                    files_changed=len(self.state.files_modified),
                    diff=git_diff,
                    status="cancelled",
                    files_modified=list(self.state.files_modified)
                )
        elif self.state.is_complete:
            if self.logger:
                self.logger.log_complete(
                    summary=getattr(self.state, "summary", "Task completed"),
                    iterations=self.state.iteration,
                    files_changed=len(self.state.files_modified),
                    diff=git_diff,
                    status="completed",
                    files_modified=list(self.state.files_modified)
                )
        else:
            if "Error" not in self.state.status_message:
                self.state.status_message = "Reached max iterations without completion."
            fail_summary = (
                f"INCOMPLETE: {self.state.status_message}" 
                if "Error" in self.state.status_message 
                else "INCOMPLETE: Reached max iterations"
            )
            if self.logger:
                self.logger.log_complete(
                    summary=fail_summary,
                    iterations=self.state.iteration,
                    files_changed=len(self.state.files_modified),
                    diff=git_diff,
                    status="failed",
                    files_modified=list(self.state.files_modified)
                )

        if self.ui_callback:
            self.ui_callback(self.state)
            
        return self.state

    def init_interactive_session(self):
        """Initialize a persistent multi-turn conversational session with repository awareness."""
        if not hasattr(self, "_interactive_messages") or not self._interactive_messages:
            repo_summary = ""
            if self.sandbox:
                try:
                    files = self.sandbox.list_files(".")
                    file_list = [f.strip() for f in files.splitlines() if f.strip() and not any(p in f for p in ['.git', 'node_modules', '__pycache__', 'venv'])]
                    repo_summary = f"\n\nRepository Files ({len(file_list)}):\n" + "\n".join(f"- {f}" for f in file_list[:25])
                except Exception:
                    pass

            system_content = (
                "You are Aang, an expert autonomous terminal coding engine.\n"
                "You collaborate with the developer in an interactive terminal REPL.\n"
                f"{repo_summary}\n\n"
                "BEHAVIORAL DIRECTIVES:\n"
                "1. When greeting or conversing about general topics, reply directly in concise markdown without calling tools.\n"
                "2. When the user asks about specific files, issues, or codebase state, always use `read_file`, `search_code`, or `run_command` to inspect the ground truth on disk before answering.\n"
                "3. When the user directs you to fix a bug, refactor code, or implement a feature, use your tools (`read_file`, `write_file`, `replace_in_file`, `run_command`) autonomously to complete the work and verify with tests.\n"
                "4. Never modify files unless the user explicitly directs you to make changes, fixes, or implementations. Prefer `replace_in_file` for targeted changes. All file edits are automatically verified for syntax integrity before saving.\n"
                "5. Context & Turn Independence: Each user prompt defines the current goal. When the user gives a greeting (e.g., 'hey', 'hi', 'hello') or general question, respond naturally in text without restarting or continuing prior tool tasks unless explicitly asked to continue."
            )
            self._interactive_messages = [Message(role="system", content=system_content)]

    def interactive_turn(self, user_input: str, on_tool_start: Callable[[str, str], None] = None, on_tool_end: Callable[[str, str, float], None] = None) -> str:
        """
        Execute one interactive turn in the Unified Agent Architecture.
        The model receives the user's message with tools available.
        - If the model replies in text, returns the text response directly.
        - If the model invokes tools, executes them, updates UI callbacks, and iterates until response is complete.
        """
        self._is_cancelled = False
        self.init_interactive_session()
        self._interactive_messages.append(Message(role="user", content=user_input))

        schemas = self.tool_router.get_schemas()
        turn_iterations = 0
        max_turn_iterations = 10
        final_text = ""
        files_modified = set()

        if self.logger:
            repo_p = self.sandbox.repo_path if self.sandbox else "."
            prov_name = getattr(self.provider, "provider_name", "llm")
            model_name = getattr(self.provider, "model", "model")
            self.logger.start_new_session(
                task=user_input,
                repo_path=str(repo_p),
                model=str(model_name),
                provider=str(prov_name),
                target_iterations=3
            )

        try:
            while turn_iterations < max_turn_iterations and not self._is_cancelled:
                turn_iterations += 1
                t_start_iter = time.time()
                if self.logger:
                    self.logger.log_llm_request(turn_iterations, len(self._interactive_messages), len(schemas), self._interactive_messages)

                response = self._call_llm_with_retry(self._interactive_messages, schemas)
                iter_dur = time.time() - t_start_iter

                if self.logger:
                    self.logger.log_llm_response(turn_iterations, response.text, response.tool_calls, response.finish_reason or "stop", iter_dur)

                # Record assistant turn
                self._interactive_messages.append(Message(
                    role="assistant",
                    content=response.text,
                    tool_calls=response.tool_calls
                ))

                if response.text:
                    final_text = response.text

                # If no tools called, the turn is finished (conversational reply or final explanation)
                if not response.tool_calls:
                    if self.logger:
                        self.logger.log_step_finish()
                    break

                # Execute tool calls
                for tc in response.tool_calls:
                    if self._is_cancelled:
                        break

                    if tc.name == "complete_task":
                        try:
                            args = json.loads(tc.arguments)
                            summary = args.get("summary", "Task completed.")
                        except Exception:
                            summary = "Task completed."
                        self._interactive_messages.append(Message(
                            role="tool", tool_call_id=tc.id,
                            name=tc.name, content="Task completed successfully."
                        ))
                        final_text = summary
                        if self.logger:
                            self.logger.log_tool_execution(tc.name, tc.arguments, "Task completed successfully.", 0.0)
                            self.logger.log_step_finish()
                        break

                    # Protect against length truncation
                    if response.finish_reason == "length" and tc.name in ["write_file", "replace_in_file", "apply_patch"]:
                        res = (
                            f"Error: Tool execution blocked because response was truncated by provider length limit. "
                            f"Please provide smaller, targeted changes."
                        )
                        self._interactive_messages.append(Message(
                            role="tool", tool_call_id=tc.id, name=tc.name, content=res
                        ))
                        continue

                    if on_tool_start:
                        on_tool_start(tc.name, tc.arguments)

                    t0 = time.time()
                    tool_result = self.tool_router.execute(tc.name, tc.arguments)
                    dur = time.time() - t0

                    if on_tool_end:
                        on_tool_end(tc.name, tool_result, dur)

                    if self.logger:
                        self.logger.log_tool_execution(tc.name, tc.arguments, tool_result, dur)

                    if tc.name in ["write_file", "replace_in_file", "apply_patch"]:
                        try:
                            args_p = json.loads(tc.arguments).get("path", "")
                            if args_p:
                                files_modified.add(args_p)
                        except Exception:
                            pass

                    self._interactive_messages.append(Message(
                        role="tool", tool_call_id=tc.id,
                        name=tc.name, content=tool_result
                    ))

                if self.logger:
                    self.logger.log_step_finish()

        except Exception as e:
            if self.logger:
                self.logger.log_llm_error(turn_iterations or 1, str(e))
                self.logger._flush_json()
            raise e

        # Finish turn logging and diff capture
        diff = ""
        if self.sandbox:
            try:
                _, stdout, _ = self.sandbox.run_command("git diff", timeout=5)
                diff = stdout
            except Exception:
                pass

        if self.logger:
            self.logger.log_complete(
                summary=final_text or "Turn completed.",
                iterations=turn_iterations,
                files_changed=len(files_modified),
                diff=diff,
                status="completed" if not self._is_cancelled else "cancelled",
                files_modified=list(files_modified)
            )

        # Episodic Turn Consolidation: prune raw tool call scratchpad so previous
        # tool traces do not confuse future conversational turns or inflate context.
        self._compact_interactive_history(final_text, files_modified)

        return final_text

    def _compact_interactive_history(self, final_reply: str, files_modified: set):
        """Consolidate completed turns into clean, high-level user/assistant dialogue turns."""
        if not self._interactive_messages:
            return

        clean_messages = [self._interactive_messages[0]]  # Preserve system prompt

        # Extract user turns and their resolved assistant replies
        turns = []
        i = 1
        n = len(self._interactive_messages)
        while i < n:
            msg = self._interactive_messages[i]
            if msg.role == "user":
                u_text = msg.content
                # Scan for the assistant's final response for this user turn
                j = i + 1
                asst_reply = ""
                while j < n and self._interactive_messages[j].role != "user":
                    if self._interactive_messages[j].role == "assistant" and self._interactive_messages[j].content:
                        asst_reply = self._interactive_messages[j].content
                    j += 1
                
                # If this was the most recent turn, append file modification info if any
                if j >= n and files_modified:
                    asst_reply = (asst_reply or "Completed.") + f"\n[Files modified: {', '.join(files_modified)}]"
                
                turns.append((u_text, asst_reply or "Completed."))
                i = j
            else:
                i += 1

        # Keep the last 4 clean dialog turns
        for u_text, a_text in turns[-4:]:
            clean_messages.append(Message(role="user", content=u_text))
            clean_messages.append(Message(role="assistant", content=a_text))

        self._interactive_messages = clean_messages
