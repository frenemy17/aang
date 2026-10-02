import argparse
import sys
import os
import traceback
from dotenv import load_dotenv

load_dotenv()

from rich.console import Console
from aang.config.settings import settings
from aang.llm import get_provider, AVAILABLE_MODELS
from aang.llm.fallback import FallbackProvider
from aang.tools import (
    ToolRouter, ListFilesTool, ReadFileTool, WriteFileTool, ReplaceInFileTool,
    ApplyPatchTool, SearchCodeTool, RunCommandTool, GitStatusTool, GitDiffTool,
    GitCheckpointTool, GitRollbackTool
)
from aang.agent.logger import AangLogger
from aang.tui.app import AangTUI

console = Console()

def create_sandbox(repo_path: str):
    """Try Docker first, fall back to local sandbox."""
    try:
        from aang.sandbox.docker import DockerSandbox
        sandbox = DockerSandbox(repo_path)
        console.print("[green]✓ Docker sandbox initialized[/green]")
        return sandbox
    except Exception as e:
        console.print(f"[yellow]⚠ Docker unavailable ({type(e).__name__}), using local sandbox[/yellow]")
        from aang.sandbox.local import LocalSandbox
        sandbox = LocalSandbox(repo_path)
        console.print("[green]✓ Local sandbox initialized[/green]")
        return sandbox

def main():
    parser = argparse.ArgumentParser(
        description="""\
🌪️  Aang — Autonomous Terminal Coding Agent & SWE-Bench Harness

Interactive TUI:
  aang                   Launch interactive mascot terminal in current directory
  aang --repo ./dir      Launch interactive mascot terminal targeting a directory

Quick Commands:
  aang setup             Run interactive setup wizard to configure API keys
  aang doctor            Diagnose environment (Python, Git, Docker, API connectivity)
  aang web               Launch live web visualizer & session inspector
  aang "Fix bug in X"    Execute an automated coding task directly in current workspace""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  aang setup
  aang doctor
  aang "Add unit tests for payment processing in tests/test_payment.py"
  aang --provider groq --model openai/gpt-oss-120b
  aang web
"""
    )
    parser.add_argument("--repo", type=str, default=".", help="Path to target repository (default: current directory)")
    parser.add_argument("--provider", type=str, default=settings.effective_provider, help="LLM Provider (groq, openrouter, openai, anthropic, ollama)")
    parser.add_argument("--model", type=str, default=settings.effective_model, help="Model name")
    parser.add_argument("--log", type=str, default="aang.log", help="Path to detailed log file")
    parser.add_argument("task", nargs="?", type=str, help="Coding task or subcommand: setup | doctor | web | '<task description>'")
    
    args = parser.parse_args()

    # Check for instant convenience subcommands
    task_arg = (args.task or "").strip().lower()
    if task_arg in ["setup", "config", "init"]:
        from aang.config.onboarding import run_onboarding_wizard
        run_onboarding_wizard(console, force=True)
        return

    if task_arg in ["doctor", "check"]:
        from aang.config.onboarding import run_doctor
        run_doctor(console)
        return

    if task_arg in ["web", "ui", "dashboard"]:
        from aang.server import run_server
        run_server(5173)
        return

    repo_path = os.path.abspath(args.repo)
    
    # Verify repo exists
    if not os.path.isdir(repo_path):
        console.print(f"[red]Error: Repository path not found: {repo_path}[/red]")
        sys.exit(1)
    
    # Setup Logger
    logger = AangLogger(log_path=args.log)
    
    # Setup Sandbox (Docker with local fallback)
    sandbox = create_sandbox(repo_path)
        
    # Setup Tools Router with complete enhanced toolset
    router = ToolRouter()
    router.register(ListFilesTool(sandbox))
    router.register(ReadFileTool(sandbox))
    router.register(WriteFileTool(sandbox))
    router.register(ReplaceInFileTool(sandbox))
    router.register(ApplyPatchTool(sandbox))
    router.register(SearchCodeTool(sandbox))
    router.register(RunCommandTool(sandbox))
    router.register(GitStatusTool(sandbox))
    router.register(GitDiffTool(sandbox))
    router.register(GitCheckpointTool(sandbox))
    router.register(GitRollbackTool(sandbox))
    
    # Setup LLM Provider - resolve API key from multiple sources
    api_key = settings.effective_api_key or settings.api_key or os.getenv(f"{args.provider.upper()}_API_KEY") or os.getenv("AANG_API_KEY") or os.getenv("ION_API_KEY")
    if not api_key and args.provider != "ollama":
        if sys.stdin.isatty():
            from aang.config.onboarding import run_onboarding_wizard
            cfg = run_onboarding_wizard(console)
            args.provider = cfg.get("AANG_PROVIDER", args.provider)
            args.model = cfg.get("AANG_MODEL", args.model)
            api_key = cfg.get("AANG_API_KEY") or os.getenv("GROQ_API_KEY") or os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
            
        if not api_key and args.provider != "ollama":
            console.print(f"[red]Error: API key not configured.[/red]")
            console.print(f"Run [bold cyan]aang setup[/bold cyan] to configure your AI provider, or export:")
            console.print(f"  export GROQ_API_KEY=your-key")
            console.print(f"  export AANG_API_KEY=your-key")
            sandbox.cleanup()
            sys.exit(1)

    base_url = settings.base_url
    primary_provider = get_provider(args.provider, args.model, api_key, base_url)
    
    # Configure resilient multi-provider fallback cascade if keys exist
    backups = []
    if args.provider == "openrouter":
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            backups.append(get_provider("groq", "openai/gpt-oss-120b", groq_key))
            backups.append(get_provider("groq", "openai/gpt-oss-20b", groq_key))
    elif args.provider == "groq":
        groq_key = os.getenv("GROQ_API_KEY") or api_key
        if groq_key:
            backups.append(get_provider("groq", "openai/gpt-oss-20b", groq_key))
            backups.append(get_provider("groq", "qwen/qwen3.8-27b", groq_key))

    provider = FallbackProvider([primary_provider] + backups) if backups else primary_provider
    
    # Setup TUI Control Center
    tui = AangTUI(
        repo_path=repo_path,
        model_name=args.model,
        sandbox=sandbox,
        provider=provider,
        tool_router=router,
        logger=logger
    )
    
    try:
        if args.task:
            tui.run_task(args.task, max_iterations=settings.max_iterations)
            console.print(f"[dim]Session log saved to: {os.path.abspath(args.log)}[/dim]")
        else:
            tui.interactive_shell(default_max_iterations=settings.max_iterations)
    except KeyboardInterrupt:
        console.print("\n[dim]Session terminated by user.[/dim]")
    except Exception as e:
        console.print(f"\n[red]Fatal error: {e}[/red]")
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
    finally:
        sandbox.cleanup()

if __name__ == "__main__":
    main()
