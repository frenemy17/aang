import os
import sys
import requests
from typing import Dict, Any, Optional, Tuple
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.text import Text

GLOBAL_ENV_DIR = os.path.expanduser("~/.aang")
GLOBAL_ENV_FILE = os.path.join(GLOBAL_ENV_DIR, ".env")
LOCAL_ENV_FILE = os.path.abspath(".env")

PROVIDERS_INFO = {
    "groq": {
        "name": "Groq",
        "description": "Ultra-fast inference with free tier available",
        "env_key": "GROQ_API_KEY",
        "default_model": "openai/gpt-oss-120b",
        "signup_url": "https://console.groq.com/keys",
        "needs_key": True
    },
    "openrouter": {
        "name": "OpenRouter",
        "description": "Unified access to 200+ models (Claude 3.5 Sonnet, GPT-4o, etc.)",
        "env_key": "OPENROUTER_API_KEY",
        "default_model": "openai/gpt-4o-mini",
        "signup_url": "https://openrouter.ai/keys",
        "needs_key": True
    },
    "openai": {
        "name": "OpenAI",
        "description": "Direct OpenAI access (GPT-4o, o1, etc.)",
        "env_key": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
        "signup_url": "https://platform.openai.com/api-keys",
        "needs_key": True
    },
    "anthropic": {
        "name": "Anthropic",
        "description": "Direct Anthropic access (Claude 3.5 Sonnet)",
        "env_key": "ANTHROPIC_API_KEY",
        "default_model": "claude-3-5-sonnet-20241022",
        "signup_url": "https://console.anthropic.com/settings/keys",
        "needs_key": True
    },
    "ollama": {
        "name": "Ollama (Local)",
        "description": "100% offline & private, running locally on your hardware",
        "env_key": "",
        "default_model": "llama3.1",
        "signup_url": "https://ollama.com",
        "needs_key": False
    }
}

def has_any_api_key() -> bool:
    """Returns True if any supported LLM API key is present in environment."""
    keys_to_check = [
        "AANG_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY",
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ION_API_KEY"
    ]
    return any(bool(os.getenv(k, "").strip()) for k in keys_to_check)

def save_env_config(key_dict: Dict[str, str], save_global: bool = True, target_path: Optional[str] = None) -> str:
    """Write or update key-value pairs in either global ~/.aang/.env, local .env, or a custom target path."""
    if target_path is None:
        target_path = GLOBAL_ENV_FILE if save_global else LOCAL_ENV_FILE
    if save_global and target_path == GLOBAL_ENV_FILE:
        os.makedirs(GLOBAL_ENV_DIR, exist_ok=True)
    elif os.path.dirname(target_path):
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

    existing_lines = []
    if os.path.exists(target_path):
        with open(target_path, "r", encoding="utf-8") as f:
            existing_lines = f.readlines()

    line_map = {}
    other_lines = []
    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, v = stripped.split("=", 1)
            line_map[k.strip()] = v.strip()
        else:
            other_lines.append(line)

    for k, v in key_dict.items():
        line_map[k] = v
        os.environ[k] = v

    with open(target_path, "w", encoding="utf-8") as f:
        f.write("# Aang Configuration\n")
        for k, v in sorted(line_map.items()):
            f.write(f"{k}={v}\n")

    return target_path

def verify_provider_connection(provider: str, api_key: str) -> Tuple[bool, str]:
    """Test API connection with a fast network ping."""
    try:
        if provider == "groq":
            res = requests.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=5
            )
            if res.status_code == 200:
                return True, "Connected to Groq API successfully."
            return False, f"Groq HTTP {res.status_code}: {res.text[:120]}"

        elif provider == "openrouter":
            res = requests.get(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=5
            )
            if res.status_code == 200:
                return True, "Connected to OpenRouter API successfully."
            return False, f"OpenRouter HTTP {res.status_code}: {res.text[:120]}"

        elif provider == "openai":
            res = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=5
            )
            if res.status_code == 200:
                return True, "Connected to OpenAI API successfully."
            return False, f"OpenAI HTTP {res.status_code}: {res.text[:120]}"

        elif provider == "anthropic":
            res = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={"model": "claude-3-5-sonnet-20241022", "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]},
                timeout=6
            )
            if res.status_code == 200:
                return True, "Connected to Anthropic API successfully."
            return False, f"Anthropic HTTP {res.status_code}: {res.text[:120]}"

        elif provider == "ollama":
            res = requests.get("http://localhost:11434/api/version", timeout=3)
            if res.status_code == 200:
                return True, "Connected to local Ollama instance."
            return False, "Ollama daemon not responding on http://localhost:11434"

        return True, "Provider configured."
    except Exception as e:
        return False, f"Network check failed ({type(e).__name__}): {e}"

def run_onboarding_wizard(console: Console, force: bool = False) -> Dict[str, str]:
    """Interactive wizard to configure LLM provider and API keys."""
    welcome_text = Text()
    welcome_text.append("⚡ Welcome to Aang! ⚡\n", style="bold cyan")
    welcome_text.append("Autonomous Terminal Coding Agent & SWE-Bench Harness\n", style="bold white")
    welcome_text.append("\nLet's configure your AI provider in 30 seconds so you can start coding.\n", style="dim")

    console.print()
    console.print(Panel(welcome_text, border_style="cyan", padding=(1, 2)))
    console.print()

    table = Table(title="Select an AI Provider", show_header=True, header_style="bold magenta", border_style="dim")
    table.add_column("#", style="bold yellow", width=4)
    table.add_column("Provider", style="bold white", width=16)
    table.add_column("Description", style="dim", width=42)
    table.add_column("Free Tier", style="cyan", width=12)

    table.add_row("1", "Groq (Recommended)", "Ultra-fast reasoning (Llama 3.3, gpt-oss)", "✓ Available")
    table.add_row("2", "OpenRouter", "200+ models (Claude 3.5, GPT-4o, DeepSeek)", "Credits required")
    table.add_row("3", "OpenAI", "Direct OpenAI (GPT-4o, o1)", "Paid")
    table.add_row("4", "Anthropic", "Direct Claude 3.5 Sonnet", "Paid")
    table.add_row("5", "Local Ollama", "Runs 100% locally on your machine", "✓ 100% Free")

    console.print(table)
    console.print()

    choice = Prompt.ask("[bold cyan]Enter choice (1-5)[/bold cyan]", choices=["1", "2", "3", "4", "5"], default="1")
    prov_map = {"1": "groq", "2": "openrouter", "3": "openai", "4": "anthropic", "5": "ollama"}
    selected_provider = prov_map[choice]
    prov_info = PROVIDERS_INFO[selected_provider]

    console.print(f"\n[green]Selected: [bold]{prov_info['name']}[/bold][/green]")
    if prov_info["needs_key"]:
        console.print(f"[dim]Need a key? Get one at: [link={prov_info['signup_url']}]{prov_info['signup_url']}[/link][/dim]\n")

    api_key = ""
    if prov_info["needs_key"]:
        while not api_key:
            api_key = Prompt.ask(f"[bold yellow]Enter your {prov_info['name']} API Key[/bold yellow]", password=True).strip()
            if not api_key:
                console.print("[red]API key cannot be empty.[/red]")
                continue

            console.print("[cyan]Verifying connection with provider...[/cyan]")
            ok, msg = verify_provider_connection(selected_provider, api_key)
            if ok:
                console.print(f"[bold green]✓ {msg}[/bold green]\n")
                break
            else:
                console.print(f"[yellow]⚠ Verification warning: {msg}[/yellow]")
                proceed = Confirm.ask("Would you like to save this key anyway?", default=True)
                if proceed:
                    break
                else:
                    api_key = ""

    # Choose save location
    console.print("[bold]Where would you like to save your configuration?[/bold]")
    console.print("  [1] Global (~/.aang/.env) — [dim]Recommended, works everywhere across all repositories[/dim]")
    console.print("  [2] Local project (.env) — [dim]Current directory only[/dim]")
    save_choice = Prompt.ask("Select location", choices=["1", "2"], default="1")
    save_global = (save_choice == "1")

    config_dict = {
        "AANG_PROVIDER": selected_provider,
        "AANG_MODEL": prov_info["default_model"]
    }
    if api_key:
        config_dict[prov_info["env_key"]] = api_key
        config_dict["AANG_API_KEY"] = api_key

    saved_path = save_env_config(config_dict, save_global=save_global)
    console.print(f"[bold green]✓ Configuration saved to {saved_path}![/bold green]\n")

    return config_dict

def print_startup_guide(console: Console):
    """Print quick navigation and example tasks for interactive users."""
    guide_table = Table.grid(padding=(0, 2))
    guide_table.add_column(style="bold yellow", width=18)
    guide_table.add_column()

    guide_table.add_row("[bold cyan]Try asking:[/bold cyan]", "[dim]Type naturally in plain English or try:[/dim]")
    guide_table.add_row("  \"Fix failing tests\"", "[dim]Auto-detects test runners (pytest, npm test) and fixes errors[/dim]")
    guide_table.add_row("  \"Refactor auth module\"", "[dim]Cleans code, validates types, and runs tests[/dim]")
    guide_table.add_row("  \"Explain project architecture\"", "[dim]Inspects code AST symbols and diagrams modules[/dim]")
    guide_table.add_row("", "")
    guide_table.add_row("[bold cyan]Commands:[/bold cyan]", "")
    guide_table.add_row("  /help", "[dim]Show full command cheatsheet[/dim]")
    guide_table.add_row("  /model [id]", "[dim]View and switch active AI models[/dim]")
    guide_table.add_row("  /diff", "[dim]Inspect syntax-highlighted git diff of pending edits[/dim]")
    guide_table.add_row("  /log [n]", "[dim]Display recent execution trace in terminal[/dim]")
    guide_table.add_row("  /rollback", "[dim]Instantly undo all uncommitted changes[/dim]")
    guide_table.add_row("  /setup", "[dim]Re-run setup wizard to change providers or keys[/dim]")
    guide_table.add_row("  /web", "[dim]Launch live web dashboard (http://localhost:5173)[/dim]")
    guide_table.add_row("  /exit", "[dim]Quit Aang session[/dim]")

    panel = Panel(
        guide_table,
        title="[bold cyan]Quick Navigation & Examples[/bold cyan]",
        border_style="dim",
        padding=(1, 2)
    )
    console.print(panel)

def run_doctor(console: Console):
    """Comprehensive environment diagnostics to verify system readiness."""
    console.print(Panel("[bold cyan]Aang System Diagnostics (Doctor)[/bold cyan]", border_style="cyan"))

    table = Table(show_header=True, header_style="bold magenta", border_style="dim")
    table.add_column("Component", style="bold white", width=22)
    table.add_column("Status", width=16)
    table.add_column("Details", style="dim")

    # 1. Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 11):
        table.add_row("Python Version", "[green]✓ Ready[/green]", f"Python {py_ver} (>= 3.11)")
    else:
        table.add_row("Python Version", "[red]✗ Upgrade Needed[/red]", f"Python {py_ver} (< 3.11 required)")

    # 2. Git
    git_code = os.system("git --version >/dev/null 2>&1")
    if git_code == 0:
        table.add_row("Git CLI", "[green]✓ Installed[/green]", "Git is available on PATH")
    else:
        table.add_row("Git CLI", "[red]✗ Missing[/red]", "Git not found on system")

    # 3. Docker Sandbox
    docker_status = "[yellow]⚠ Local Sandbox (Active)[/yellow]"
    docker_detail = "Docker not detected; using fast local workspace sandbox"
    try:
        import docker
        client = docker.from_env()
        client.ping()
        docker_status = "[green]✓ Docker Ready[/green]"
        docker_detail = "Docker daemon active; container isolation available"
    except Exception:
        pass
    table.add_row("Sandbox Engine", docker_status, docker_detail)

    # 4. API Keys & Providers
    keys = [
        ("Groq", "GROQ_API_KEY", "https://console.groq.com/keys"),
        ("OpenRouter", "OPENROUTER_API_KEY", "https://openrouter.ai/keys"),
        ("OpenAI", "OPENAI_API_KEY", "https://platform.openai.com"),
        ("Anthropic", "ANTHROPIC_API_KEY", "https://console.anthropic.com")
    ]
    for name, env_var, signup in keys:
        val = os.getenv(env_var, "").strip()
        if val:
            masked = val[:7] + "..." + val[-4:] if len(val) > 12 else "***"
            table.add_row(f"{name} Key", "[green]✓ Configured[/green]", f"Key active: {masked}")
        else:
            table.add_row(f"{name} Key", "[dim]Not Set[/dim]", f"Optional ({signup})")

    # 5. Global Config File
    if os.path.exists(GLOBAL_ENV_FILE):
        table.add_row("Global Config", "[green]✓ Found[/green]", GLOBAL_ENV_FILE)
    else:
        table.add_row("Global Config", "[dim]Not created[/dim]", f"Run 'aang setup' to create {GLOBAL_ENV_FILE}")

    console.print(table)
    console.print("\n[dim]To add or change API keys anytime, run: [bold cyan]aang setup[/bold cyan][/dim]\n")
