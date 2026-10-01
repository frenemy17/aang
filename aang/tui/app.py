import os
import sys
import time
import json
import re
from dotenv import load_dotenv

load_dotenv()

from typing import List, Optional, Dict, Any, Callable
from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.prompt import Prompt, Confirm
from rich.live import Live
from rich.text import Text
from rich.spinner import Spinner
from rich.columns import Columns
from rich.markdown import Markdown

from aang.agent.state import AgentState
from aang.llm import AVAILABLE_MODELS, get_provider_by_model_id, get_provider
from aang.llm.types import Message
from aang.agent.loop import AgentLoop
from aang.agent.logger import AangLogger
from aang.sandbox.base import SandboxEnvironment
from aang.tools.router import ToolRouter
from aang.tui.mascot import (
    render_mascot, MASCOT_OPEN, MASCOT_CLOSED, MASCOT_AVATAR,
    MASCOT_HALF_BLINK, MASCOT_HALF_OPEN, MASCOT_GLOW_START,
    MASCOT_AVATAR_PULSE, MASCOT_GLOW_FADE, ANIMATION_CYCLE
)

BANNER = """[bold cyan]
 █████╗   █████╗  ███╗   ██╗ ██████╗ 
██╔══██╗ ██╔══██╗ ████╗  ██║██╔════╝ 
███████║ ███████║ ██╔██╗ ██║██║  ███╗
██╔══██║ ██╔══██║ ██║╚██╗██║██║   ██║
██║  ██║ ██║  ██║ ██║ ╚████║╚██████╔╝
╚═╝  ╚═╝ ╚═╝  ╚═╝ ╚═╝  ╚═══╝ ╚═════╝ [/bold cyan]
[bold white]Autonomous Coding Agent[/bold white] [dim]v2.0[/dim]
"""



class AangTUI:
    def __init__(self, repo_path: str, model_name: str, 
                 sandbox: Optional[SandboxEnvironment] = None,
                 provider: Any = None,
                 tool_router: Optional[ToolRouter] = None,
                 logger: Optional[AangLogger] = None):
        self.console = Console()
        self.repo_path = os.path.abspath(repo_path)
        self.model_name = model_name
        self.provider = provider
        self.sandbox = sandbox
        self.tool_router = tool_router
        self.logger = logger
        
        self.activity_log: List[Dict[str, Any]] = []
        self.live: Optional[Live] = None
        self.current_task = ""
        self.start_time = 0.0
        self.loop: Optional[AgentLoop] = None
        self.last_state: Optional[AgentState] = None
        self.interactive_loop: Optional[AgentLoop] = None

    def _create_banner_panel(self, mascot_grid=MASCOT_OPEN) -> Panel:
        banner_text = Text(""" █████╗   █████╗  ███╗   ██╗ ██████╗ 
██╔══██╗ ██╔══██╗ ████╗  ██║██╔════╝ 
███████║ ███████║ ██╔██╗ ██║██║  ███╗
██╔══██║ ██╔══██║ ██║╚██╗██║██║   ██║
██║  ██║ ██║  ██║ ██║ ╚████║╚██████╔╝
╚═╝  ╚═╝ ╚═╝  ╚═╝ ╚═╝  ╚═══╝ ╚═════╝ """, style="bold cyan")

        sub = Text("Autonomous Coding Agent ", style="bold white")
        sub.append("v2.0", style="dim")

        sb_name = self.sandbox.__class__.__name__ if self.sandbox else "Unknown"
        if "Docker" in sb_name:
            sb_badge = "[bold green]Docker Container[/bold green]"
        else:
            sb_badge = "[bold yellow]Local Workspace[/bold yellow]"
            
        status_table = Table.grid(padding=(0, 2))
        status_table.add_column(style="bold dim")
        status_table.add_column()
        
        status_table.add_row("Repository:", f"[cyan]{self.repo_path}[/cyan]")
        status_table.add_row("Active Model:", f"[bold green]{self.model_name}[/bold green]")
        status_table.add_row("Sandbox:", sb_badge)
        status_table.add_row("Dashboard:", "[link=http://localhost:5173/]http://localhost:5173/[/link]")

        right_group = Group(
            banner_text,
            sub,
            Text(""),
            status_table
        )

        mascot = render_mascot(mascot_grid)
        layout = Table.grid(padding=(0, 3))
        layout.add_column(vertical="middle")
        layout.add_column(vertical="middle")
        layout.add_row(mascot, right_group)

        return Panel(layout, title="[bold white]AANG CONTROL CENTER[/bold white]", border_style="cyan", padding=(1, 2))

    def print_banner(self, animate: bool = True, full_cycle: bool = True):
        """Render stylish Claude Code-style startup banner with pixel mascot, multi-frame blinking & glowing blue eyes."""
        if animate and self.console.is_terminal:
            try:
                cycle_to_play = ANIMATION_CYCLE if full_cycle else [
                    (MASCOT_OPEN, 0.4),
                    (MASCOT_HALF_BLINK, 0.06),
                    (MASCOT_CLOSED, 0.14),
                    (MASCOT_HALF_OPEN, 0.06),
                    (MASCOT_OPEN, 0.1)
                ]
                with Live(self._create_banner_panel(MASCOT_OPEN), console=self.console, refresh_per_second=25) as live:
                    for grid, duration in cycle_to_play:
                        live.update(self._create_banner_panel(grid))
                        time.sleep(duration)
                    live.update(self._create_banner_panel(MASCOT_OPEN))
            except Exception:
                self.console.print(self._create_banner_panel(MASCOT_OPEN))
        else:
            self.console.print(self._create_banner_panel(MASCOT_OPEN))
        
        self.console.print("[dim]Type a message or coding task, or use commands: [/dim][bold cyan]/model[/bold cyan][dim], [/dim][bold cyan]/diff[/bold cyan][dim], [/dim][bold cyan]/rollback[/bold cyan][dim], [/dim][bold cyan]/status[/bold cyan][dim], [/dim][bold cyan]/help[/bold cyan][dim], [/dim][bold cyan]/exit[/bold cyan]\n")

    def show_help(self):
        """Display help panel with available commands."""
        table = Table(title="Aang Interactive Commands", border_style="blue", show_header=True, header_style="bold cyan")
        table.add_column("Command", style="bold yellow", width=22)
        table.add_column("Description", style="white")
        table.add_column("Example", style="dim")

        table.add_row("<input>", "Chat or request code edits (Unified Agent)", "How does auth work? or Check syntax in checkout_service.js")
        table.add_row("/run <task>", "Autonomous batch mode with live timeline", "/run Fix checkout_service.js")
        table.add_row("/model [id]", "List or switch active LLM model", "/model 2 or /model gpt-4o")
        table.add_row("/diff", "View syntax-highlighted git diff", "/diff")
        table.add_row("/log [lines]", "View recent execution log in terminal", "/log 80")
        table.add_row("/rollback", "Revert uncommitted changes in repo", "/rollback")
        table.add_row("/status", "Show repo, git, and sandbox state", "/status")
        table.add_row("/blink", "Quick eyes blinking animation", "/blink")
        table.add_row("/glow", "Avatar State glowing blue eyes", "/glow")
        table.add_row("/loop", "Continuous blinking & glowing animation", "/loop")
        table.add_row("/web", "Show web dashboard URL & status", "/web")
        table.add_row("/stop", "Stop active task (or use Ctrl+C)", "/stop")
        table.add_row("/clear", "Clear terminal screen", "/clear")
        table.add_row("/help", "Show this command reference", "/help")
        table.add_row("/exit, /quit", "Exit Aang session", "/exit")

        self.console.print(table)

    def show_models(self):
        """Display table of available models and API key readiness."""
        table = Table(title="Available AI Models", border_style="cyan", show_header=True, header_style="bold cyan")
        table.add_column("#", style="bold yellow", width=4, justify="right")
        table.add_column("Model Name", style="bold white", width=36)
        table.add_column("Model ID", style="dim", width=28)
        table.add_column("Provider", style="magenta", width=10)
        table.add_column("API Key Status", width=18)
        table.add_column("Active", width=8, justify="center")

        for idx, m in enumerate(AVAILABLE_MODELS, 1):
            # Check key status
            env_key = m.get("env_key", "")
            has_key = bool(env_key and os.getenv(env_key)) or bool(os.getenv("AANG_API_KEY")) or bool(os.getenv("ION_API_KEY"))
            if not env_key:  # e.g. local Ollama
                key_status = "[blue]Local (No Key)[/blue]"
            elif has_key:
                key_status = f"[green]✓ Ready ({env_key})[/green]"
            else:
                key_status = f"[red]✗ Missing {env_key}[/red]"

            is_active = (m["id"] == self.model_name)
            active_marker = "[bold green]● Active[/bold green]" if is_active else "[dim]○[/dim]"

            table.add_row(
                str(idx),
                m["name"],
                m["id"],
                m["provider"].upper(),
                key_status,
                active_marker
            )

        self.console.print(table)

    def switch_model(self, choice_arg: Optional[str] = None):
        """Switch current model by index or model ID."""
        self.show_models()

        if not choice_arg:
            choice_arg = Prompt.ask("\n[bold cyan]Select model number or ID[/bold cyan] (Enter to cancel)", default="")
            if not choice_arg.strip():
                return

        choice_arg = choice_arg.strip()
        selected = None

        # Check if numeric selection
        if choice_arg.isdigit():
            idx = int(choice_arg) - 1
            if 0 <= idx < len(AVAILABLE_MODELS):
                selected = AVAILABLE_MODELS[idx]
        else:
            # Check if match by ID or name
            for m in AVAILABLE_MODELS:
                if choice_arg.lower() in m["id"].lower() or choice_arg.lower() in m["name"].lower():
                    selected = m
                    break

        if not selected:
            self.console.print(f"[red]Error: Model '{choice_arg}' not recognized.[/red]")
            return

        # Check API key for selected model
        env_key = selected.get("env_key", "")
        key = os.getenv(env_key, "") if env_key else ""
        if not key:
            key = os.getenv("OPENROUTER_API_KEY", "") or os.getenv("AANG_API_KEY", "") or os.getenv("ION_API_KEY", "") or os.getenv("GROQ_API_KEY", "")
        if not key and hasattr(self.provider, "api_key"):
            key = getattr(self.provider, "api_key", "")

        if env_key and not key:
            self.console.print(f"[yellow]Warning: {env_key} is not set.[/yellow]")
            if not sys.stdin.isatty():
                self.console.print(f"[red]Cannot prompt for {env_key} in non-interactive environment.[/red]")
                return
            key_input = Prompt.ask(f"Enter your {env_key} (or Enter to cancel)", password=True, default="")
            if not key_input.strip():
                self.console.print("[yellow]Model switch cancelled.[/yellow]")
                return
            key = key_input.strip()
            os.environ[env_key] = key

        # Instantiate provider with automatic fallback protection
        try:
            from aang.llm.fallback import FallbackProvider
            new_provider = get_provider(selected["provider"], selected["id"], key, selected.get("base_url"))
            backups = []
            if selected["provider"] == "groq":
                # Fallback to gpt-oss-20b and qwen3.8-27b on Groq
                if selected["id"] != "openai/gpt-oss-20b":
                    backups.append(get_provider("groq", "openai/gpt-oss-20b", key))
                if selected["id"] != "qwen/qwen3.8-27b":
                    backups.append(get_provider("groq", "qwen/qwen3.8-27b", key))
            elif selected["provider"] == "openrouter":
                groq_key = os.getenv("GROQ_API_KEY")
                if groq_key:
                    backups.append(get_provider("groq", "openai/gpt-oss-120b", groq_key))
                    backups.append(get_provider("groq", "openai/gpt-oss-20b", groq_key))

            self.provider = FallbackProvider([new_provider] + backups) if backups else new_provider
            self.model_name = selected["id"]
            if self.interactive_loop:
                self.interactive_loop.provider = self.provider
            self.console.print(f"[bold green]✓ Successfully switched to {selected['name']} ({selected['id']})[/bold green]\n")
        except Exception as e:
            self.console.print(f"[red]Failed to switch model: {e}[/red]")

    def show_status(self):
        """Display status of repository, git, sandbox, and active session."""
        git_status_out = ""
        branch = "unknown"
        if self.sandbox:
            try:
                _, b_out, _ = self.sandbox.run_command("git rev-parse --abbrev-ref HEAD", timeout=5)
                branch = b_out.strip() or "main"
                _, git_status_out, _ = self.sandbox.run_command("git status --short", timeout=5)
            except Exception:
                pass

        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan", width=18)
        table.add_column()

        table.add_row("Repository Path:", f"[white]{self.repo_path}[/white]")
        table.add_row("Git Branch:", f"[green]{branch}[/green]")
        table.add_row("Active Model:", f"[bold green]{self.model_name}[/bold green]")
        table.add_row("Provider:", f"[magenta]{getattr(self.provider, '__class__', type(None)).__name__}[/magenta]")
        table.add_row("Sandbox Type:", f"[yellow]{self.sandbox.__class__.__name__ if self.sandbox else 'None'}[/yellow]")
        
        dirty_lines = [line for line in git_status_out.splitlines() if line.strip()]
        if dirty_lines:
            status_desc = f"[yellow]{len(dirty_lines)} uncommitted file(s)[/yellow]\n" + "\n".join(f"  {l}" for l in dirty_lines[:8])
        else:
            status_desc = "[green]Working tree clean (no uncommitted changes)[/green]"
        table.add_row("Working Tree:", status_desc)

        if self.last_state:
            last_status = "[green]Completed[/green]" if self.last_state.is_complete else "[yellow]Incomplete[/yellow]"
            table.add_row("Last Task State:", f"{last_status} (Iterations: {self.last_state.iteration})")

        mascot = render_mascot(MASCOT_OPEN)
        layout = Table.grid(padding=(0, 3))
        layout.add_column(vertical="middle")
        layout.add_column(vertical="middle")
        layout.add_row(mascot, table)

        self.console.print(Panel(layout, title="[bold white]AANG SYSTEM STATUS[/bold white]", border_style="cyan"))

    def show_diff(self):
        """Render syntax-highlighted git diff."""
        if not self.sandbox:
            self.console.print("[red]Sandbox not available to run git diff.[/red]")
            return

        code, diff_text, _ = self.sandbox.run_command("git diff", timeout=10)
        if not diff_text.strip():
            self.console.print("[green]No uncommitted changes in working tree (clean diff).[/green]")
            return

        syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=True)
        self.console.print(Panel(syntax, title="[bold cyan]Git Diff (Uncommitted Changes)[/bold cyan]", border_style="blue"))

    def show_log(self, lines: int = 60):
        """Display recent detailed session log output."""
        log_path = getattr(self.logger, "log_path", "aang.log") if self.logger else "aang.log"
        if not os.path.exists(log_path):
            self.console.print(f"[dim]No session log found at {log_path}.[/dim]")
            return

        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            
            if not all_lines:
                self.console.print(f"[dim]Session log at {log_path} is empty.[/dim]")
                return

            recent = "".join(all_lines[-lines:]) if len(all_lines) > lines else "".join(all_lines)
            self.console.print(Panel(
                recent.strip(),
                title=f"[bold cyan]Session Log ({os.path.basename(log_path)} - last {min(lines, len(all_lines))} lines)[/bold cyan]",
                border_style="cyan"
            ))
            self.console.print(f"[dim]Full log at: [bold white]{os.path.abspath(log_path)}[/bold white] (use [cyan]/log 150[/cyan] to view more)[/dim]\n")
        except Exception as e:
            self.console.print(f"[red]Error reading log: {e}[/red]")

    def rollback(self):
        """Rollback uncommitted changes in the sandbox/repo."""
        if not self.sandbox:
            self.console.print("[red]Sandbox not available for rollback.[/red]")
            return

        _, status_out, _ = self.sandbox.run_command("git status --short", timeout=5)
        dirty_lines = [l for l in status_out.splitlines() if l.strip()]
        if not dirty_lines:
            self.console.print("[green]Repository is already clean. Nothing to rollback.[/green]")
            return

        self.console.print(f"[yellow]Uncommitted changes detected in {len(dirty_lines)} files:[/yellow]")
        for l in dirty_lines[:10]:
            self.console.print(f"  [dim]{l}[/dim]")

        confirmed = Confirm.ask("\n[bold red]Discard all uncommitted changes and restore clean git working tree?[/bold red]", default=False)
        if not confirmed:
            self.console.print("[dim]Rollback aborted.[/dim]")
            return

        self.sandbox.run_command("git reset --hard HEAD", timeout=10)
        self.sandbox.run_command("git clean -fd", timeout=10)
        self.interactive_loop = None
        self.console.print("[bold green]✓ Repository rolled back to clean HEAD.[/bold green]")

    def _get_interactive_loop(self) -> AgentLoop:
        """Get or initialize the persistent interactive agent loop."""
        if self.interactive_loop is None:
            self.interactive_loop = AgentLoop(
                provider=self.provider,
                tool_router=self.tool_router,
                ui_callback=None,
                logger=self.logger,
                sandbox=self.sandbox
            )
        else:
            self.interactive_loop.provider = self.provider
            self.interactive_loop.tool_router = self.tool_router
            self.interactive_loop.sandbox = self.sandbox
        return self.interactive_loop

    def handle_interactive_input(self, user_input: str):
        """Unified interactive turn: model receives user input with tools available and decides whether to respond in text or execute tools."""
        loop = self._get_interactive_loop()
        model_tag = self.model_name.split('/')[-1]

        with self.console.status(f"[bold cyan]Aang ({model_tag}) is thinking...[/bold cyan]", spinner="dots") as status:
            def on_tool_start(name: str, args_json: str):
                target = ""
                try:
                    parsed = json.loads(args_json)
                    target = parsed.get("path") or parsed.get("command") or ""
                except Exception:
                    pass
                desc = f"{name} ({target})" if target else name
                status.update(f"[bold yellow]⚡ {desc}...[/bold yellow]")
                self.console.print(f"[dim cyan]  ⚡ {desc}[/dim cyan]")

            def on_tool_end(name: str, result: str, duration: float):
                if name == "run_command":
                    first_line = result.splitlines()[0] if result else ""
                    if "Exit Code: 0" in first_line:
                        self.console.print(f"[dim green]    ✓ Command succeeded ({duration:.1f}s)[/dim green]")
                    elif "Exit Code:" in first_line:
                        self.console.print(f"[dim red]    ✗ {first_line[:80]} ({duration:.1f}s)[/dim red]")
                elif name in ["write_file", "replace_in_file", "apply_patch"]:
                    if "Successfully" in result or "applied" in result:
                        self.console.print(f"[dim green]    ✓ Changes saved ({duration:.1f}s)[/dim green]")
                    elif "Error" in result or "rejected" in result:
                        self.console.print(f"[dim red]    ✗ {result[:80]}[/dim red]")
                status.update(f"[bold cyan]Aang ({model_tag}) is thinking...[/bold cyan]")

            try:
                reply = loop.interactive_turn(
                    user_input,
                    on_tool_start=on_tool_start,
                    on_tool_end=on_tool_end
                )
            except KeyboardInterrupt:
                loop.cancel()
                self.console.print("\n[yellow]Turn cancelled by user (Ctrl+C).[/yellow]")
                return
            except Exception as e:
                self.console.print(f"\n[red]Error in agent loop: {e}[/red]")
                return

        if not reply or not reply.strip():
            reply = "Completed."

        self.console.print()
        self.console.print(Panel(
            Markdown(reply.strip()),
            title=f"[bold cyan]Aang ({model_tag})[/bold cyan]",
            border_style="cyan",
            padding=(1, 2)
        ))
        self.console.print()

    def _generate_layout(self, state: AgentState) -> Panel:
        """Build the dynamic live execution display panel."""
        elapsed = time.time() - self.start_time if self.start_time else 0.0

        # Header info
        header_grid = Table.grid(expand=True)
        header_grid.add_column(ratio=3)
        header_grid.add_column(ratio=1, justify="right")
        
        status_badge = (
            "[bold green]✓ COMPLETE[/bold green]" if state.is_complete 
            else ("[yellow]⚡ WORKING[/yellow]" if state.iteration > 0 else "[dim]INIT[/dim]")
        )
        
        header_grid.add_row(
            f"[bold cyan]AANG AGENT[/bold cyan] [dim]|[/dim] Model: [green]{self.model_name}[/green] [dim]|[/dim] Status: {status_badge}",
            f"[dim]Time: [/dim][bold white]{elapsed:.1f}s[/bold white] [dim]| Iter: [/dim][bold yellow]{state.iteration}/{state.max_iterations}[/bold yellow]"
        )

        task_snippet = self.current_task if len(self.current_task) <= 120 else (self.current_task[:117] + "...")
        task_panel = Text(f"Task: {task_snippet}\n", style="bold white")

        # Activity timeline items
        timeline_items = []
        for msg in state.messages[-12:]:
            if msg.role == "assistant" and msg.content:
                thought = msg.content.strip()
                first_line = thought.splitlines()[0][:140]
                timeline_items.append(Text(f"💭 {first_line}", style="dim cyan"))
            elif msg.role == "assistant" and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc.name == "complete_task":
                        timeline_items.append(Text("🎯 complete_task()", style="bold green"))
                    elif tc.name in ["write_file", "replace_in_file", "apply_patch"]:
                        try:
                            args = json.loads(tc.arguments)
                            target_p = args.get("path", "")
                        except Exception:
                            target_p = ""
                        timeline_items.append(Text(f"✏  {tc.name} ({target_p})", style="bold yellow"))
                    elif tc.name == "run_command":
                        try:
                            args = json.loads(tc.arguments)
                            cmd_str = args.get("command", "")
                        except Exception:
                            cmd_str = ""
                        timeline_items.append(Text(f"⚡ run_command: '{cmd_str}'", style="cyan"))
                    else:
                        timeline_items.append(Text(f"→ Tool: {tc.name}", style="yellow"))
            elif msg.role == "tool":
                content = msg.content.strip()
                if "Exit Code: 0" in content or "Successfully" in content or "applied" in content:
                    timeline_items.append(Text("  ✓ Success", style="green"))
                elif "Exit Code:" in content:
                    timeline_items.append(Text("  ✗ Test / Command failure", style="red"))

        activity_group = Group(*timeline_items) if timeline_items else Text("Initializing preflight & repository scan...", style="dim")

        # Bottom status spinner
        if not state.is_complete:
            current_status = Spinner("dots", text=Text(f"  {state.status_message}", style="bold yellow"))
        else:
            current_status = Text(f"✓ {state.status_message}", style="bold green")

        # Footer
        footer_grid = Table.grid(expand=True)
        footer_grid.add_column(ratio=2)
        footer_grid.add_column(ratio=2, justify="right")
        
        mod_files = list(state.files_modified)
        mod_str = f"Files modified ({len(mod_files)}): {', '.join(mod_files[:3])}" if mod_files else "No files modified yet"
        footer_grid.add_row(
            Text(mod_str, style="dim"),
            Text("Press [Ctrl+C] to stop execution", style="bold red")
        )

        content = Group(
            header_grid,
            Text("─" * 70, style="dim"),
            task_panel,
            activity_group,
            Text("─" * 70, style="dim"),
            current_status,
            footer_grid
        )

        return Panel(content, border_style="cyan", title="[bold cyan]AANG LIVE RUN[/bold cyan]")

    def start(self, task: str):
        self.current_task = task
        self.start_time = time.time()
        self.live = Live(self._generate_layout(AgentState(task=task)), console=self.console, refresh_per_second=4)
        self.live.start()

    def update(self, state: AgentState):
        self.last_state = state
        if self.live:
            self.live.update(self._generate_layout(state))

    def stop(self, state: AgentState):
        self.last_state = state
        if self.live:
            self.live.update(self._generate_layout(state))
            self.live.stop()
            self.live = None

    def print_run_summary(self, state: AgentState):
        """Print post-run card with results and actions."""
        elapsed = time.time() - self.start_time if self.start_time else 0.0

        if getattr(state, "is_complete", False):
            border_style = "green"
            title = "[bold green]✓ TASK COMPLETE[/bold green]"
        elif "Cancelled" in getattr(state, "status_message", "") or "Halted" in getattr(state, "status_message", ""):
            border_style = "yellow"
            title = "[bold yellow]⚠ TASK HALTED BY USER[/bold yellow]"
        else:
            border_style = "red"
            title = "[bold red]✗ TASK INCOMPLETE[/bold red]"

        summary_table = Table.grid(padding=(0, 2))
        summary_table.add_column(style="bold dim", width=18)
        summary_table.add_column()

        summary_table.add_row("Summary:", getattr(state, "summary", state.status_message))
        summary_table.add_row("Iterations:", f"{state.iteration} / {state.max_iterations}")
        summary_table.add_row("Elapsed Time:", f"{elapsed:.1f}s")
        
        mod_files = list(state.files_modified)
        if mod_files:
            summary_table.add_row("Files Modified:", "[cyan]" + ", ".join(mod_files) + "[/cyan]")
        else:
            summary_table.add_row("Files Modified:", "[dim]None[/dim]")

        summary_table.add_row("Execution Log:", "[dim]Saved to [bold white]aang.log[/bold white] • Type [bold cyan]/log[/bold cyan] to view detailed log[/dim]")
        summary_table.add_row("Next Actions:", "[dim]Use [bold cyan]/diff[/bold cyan] to inspect changes, [bold cyan]/rollback[/bold cyan] to revert, or enter another task.[/dim]")

        self.console.print()
        self.console.print(Panel(summary_table, title=title, border_style=border_style))
        self.console.print()

    def run_task(self, task: str, max_iterations: int = 15) -> AgentState:
        """Run an autonomous agent task with full live updates and clean interrupt handling."""
        self.loop = AgentLoop(
            provider=self.provider,
            tool_router=self.tool_router,
            ui_callback=self.update,
            logger=self.logger,
            sandbox=self.sandbox
        )
        
        self.start(task)
        state = None
        try:
            state = self.loop.run(task, max_iterations=max_iterations)
        except KeyboardInterrupt:
            if self.loop:
                self.loop.cancel()
            state = self.loop.state or AgentState(task=task)
            state.status_message = "Halted by user (Ctrl+C)."
        except Exception as e:
            if self.loop:
                self.loop.cancel()
            state = self.loop.state or AgentState(task=task)
            state.status_message = f"Error: {e}"
        finally:
            self.stop(state or AgentState(task=task))

        self.print_run_summary(state or AgentState(task=task))
        return state

    def interactive_shell(self, default_max_iterations: int = 15):
        """Launch the Aang interactive command console REPL."""
        self.print_banner()

        while True:
            try:
                # Dynamic prompt showing active model
                model_tag = self.model_name.split('/')[-1]
                prompt_str = f"[bold cyan]aang[/bold cyan] [dim]({model_tag})[/dim] > "
                user_input = self.console.input(prompt_str).strip()

                if not user_input:
                    continue

                # Instant slash commands & terminal commands
                if user_input in ["/exit", "/quit", "exit", "quit"]:
                    self.console.print("[dim]Exiting Aang. Goodbye![/dim]")
                    break

                if user_input == "/clear":
                    self.console.clear()
                    self.print_banner()
                    continue

                if user_input in ["/help", "help"]:
                    self.show_help()
                    continue

                if user_input in ["/model", "/models", "models"]:
                    self.switch_model()
                    continue

                if user_input.startswith("/model "):
                    arg = user_input[len("/model "):].strip()
                    self.switch_model(arg)
                    continue

                if user_input in ["/diff", "diff"]:
                    self.show_diff()
                    continue

                if user_input in ["/log", "/logs", "log", "logs"]:
                    self.show_log(80)
                    continue

                if user_input.startswith("/log "):
                    arg = user_input[len("/log "):].strip()
                    try:
                        self.show_log(int(arg))
                    except ValueError:
                        self.show_log(80)
                    continue

                if user_input in ["/rollback", "rollback"]:
                    self.rollback()
                    continue

                if user_input in ["/status", "status"]:
                    self.show_status()
                    continue

                if user_input in ["/blink", "blink"]:
                    self.print_banner(animate=True, full_cycle=False)
                    continue

                if user_input in ["/glow", "/avatar", "glow", "avatar"]:
                    self.print_banner(animate=True, full_cycle=True)
                    continue

                if user_input in ["/loop", "/animate", "loop", "animate"]:
                    self.console.print("[dim]Aang continuous animation mode (blinking & glowing blue eyes). Press [bold red]Ctrl+C[/bold red] to stop...[/dim]\n")
                    try:
                        with Live(self._create_banner_panel(MASCOT_OPEN), console=self.console, refresh_per_second=25) as live:
                            while True:
                                for grid, duration in ANIMATION_CYCLE:
                                    live.update(self._create_banner_panel(grid))
                                    time.sleep(duration)
                    except KeyboardInterrupt:
                        self.console.print("\n[dim]Returned to Aang prompt.[/dim]\n")
                    continue

                if user_input in ["/stop", "stop"]:
                    self.console.print("[dim]No task is currently running. During an active task, press Ctrl+C to halt execution.[/dim]")
                    continue

                if user_input in ["/web", "web"]:
                    self.console.print("[cyan]Web Dashboard: [link=http://localhost:5173/]http://localhost:5173/[/link][/cyan]")
                    continue

                cleaned_input = re.sub(r'[^\w\s]', '', user_input.lower()).strip()

                if cleaned_input in ["ls", "dir"]:
                    if self.sandbox:
                        files = self.sandbox.list_files(".")
                        self.console.print(Panel(files.strip(), title=f"Files in {self.repo_path}", border_style="dim"))
                    continue

                if cleaned_input in ["pwd"]:
                    self.console.print(f"[cyan]{self.repo_path}[/cyan]")
                    continue

                if cleaned_input in ["git diff"]:
                    self.show_diff()
                    continue

                if cleaned_input in ["git status"]:
                    self.show_status()
                    continue

                if cleaned_input in ["npm test", "pytest", "python -m pytest", "python3 -m pytest"] or cleaned_input.startswith("node ") or cleaned_input.startswith("python -m unittest"):
                    if self.sandbox:
                        code, out, err = self.sandbox.run_command(user_input, timeout=30)
                        output_display = (out or err or "No output.").strip()
                        border = "green" if code == 0 else "red"
                        self.console.print(Panel(output_display, title=f"[bold]Exit Code: {code}[/bold] ({user_input})", border_style=border))
                    continue

                # Explicit batch task runner with live timeline
                if user_input.startswith("/run "):
                    task_text = user_input[len("/run "):].strip()
                    self.run_task(task_text, max_iterations=default_max_iterations)
                    continue

                # Catch mistyped slash commands before sending to LLM
                if user_input.startswith("/"):
                    self.console.print(f"[yellow]Unknown command '{user_input}'. Type [bold cyan]/help[/bold cyan] for available commands, or type without a leading slash to chat/code.[/yellow]")
                    continue

                # Unified Agent Architecture: natural language turn with tool calling capabilities
                self.handle_interactive_input(user_input)

            except KeyboardInterrupt:
                self.console.print("\n[dim]Press /exit to quit Aang.[/dim]")
            except EOFError:
                self.console.print("\n[dim]Exiting Aang. Goodbye![/dim]")
                break
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")
