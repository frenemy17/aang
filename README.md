# ⚡ Aang — Autonomous Terminal Coding Agent & SWE-Bench Harness
> *High-efficiency coding agent with multi-key rotation and zero-turn context injection. Run via `npx aang-ai` or `pip install aang-ai`.*

**Aang** (formerly Ion) is a high-performance, terminal-first autonomous software engineering agent and benchmark harness. Built for developer transparency and raw execution speed, Aang investigates codebases, diagnoses test failures, executes surgical multi-file edits, and verifies its work in sandboxed environments—all while streaming its reasoning in a rich terminal interface with its animated pixel mascot and a live web dashboard.

---

## 🏛️ System Architecture

Ion is architected as a modular, provider-agnostic system decoupling planning, context management, tool dispatch, and runtime sandboxing:

```mermaid
graph TD
    User([User / CLI / REPL]) --> TUI[Ion TUI & Control Center]
    User --> Web[Web Dashboard localhost:5173]
    
    subgraph "Core Orchestration"
        TUI --> Loop[AgentLoop]
        Web -. API Polling .-> Server[Ion Server & JSON API]
        Server -. Session Store .-> Logger[Structured JSON Logger]
        Loop --> Logger
        Loop --> State[AgentState]
        State --> TUI
    end

    subgraph "Context Management & Intelligence"
        Loop --> Preflight[Preflight Diagnostics Engine]
        Loop --> Indexer[Symbol AST Indexer]
        Loop --> Pruner[Dynamic Context Pruner]
    end

    subgraph "Model Abstraction & Resiliency"
        Loop --> Fallback[FallbackProvider]
        Fallback --> Groq[Groq Provider]
        Fallback --> OpenRouter[OpenRouter Provider]
        Fallback --> OpenAI[OpenAI Direct]
        Fallback --> Anthropic[Anthropic Direct]
        Fallback --> Ollama[Local Ollama]
    end

    subgraph "Tooling & Execution Layer"
        Loop --> Router[ToolRouter]
        Router --> ReadFile[read_file]
        Router --> WriteFile[write_file]
        Router --> Replace[replace_in_file]
        Router --> Bash[run_command]
        Router --> Complete[complete_task]
        
        Router --> Sandbox{Sandbox Engine}
        Sandbox --> Docker[Docker Sandbox]
        Sandbox --> Local[Local Sandbox]
    end
```

---

## 🧠 Deep Dive: Context Management System

Context degradation, token bloat, and hallucinated paths are the primary failure modes of autonomous coding agents. Ion implements a 4-tier context engineering pipeline that keeps token consumption minimal while ensuring the model acts with maximum precision from **Iteration 1**:

### 1. Preflight Diagnostics & Zero-Turn Context Injection
Before the agent loop makes its first LLM call, Ion runs preflight diagnostics:
- **Test Command Auto-Detection**: Regex-parses the task prompt or inspects `package.json` / `pytest` configs to discover the target test command (`npm test`, `pytest`, `node <test>.js`).
- **Pre-execution Failure Capture**: Runs the test command inside the sandbox to capture initial exit codes, stdout, and stack traces.
- **Immediate Implicated File Extraction**: Extracts erroring source files directly from the stack trace and feeds the failure output into the initial prompt. The LLM does not need to waste 1–2 iterations running tests or searching for where errors originate.

### 2. Symbol AST Indexing & Priority Ranking
Ion features a built-in symbol indexer ([`ion/agent/indexer.py`](file:///Users/siddhanthsadashivraikar/Desktop/ion/ion/agent/indexer.py)) that scans Python and JavaScript/TypeScript files:
- **Symbol Extraction**: Extracts classes, functions, and exports without heavyweight external language servers.
- **Task Query Matching**: Matches words from the user task against indexed symbols and tests imports.
- **Priority Scoring**:
  $$\text{Score} = 100 \times \mathbb{I}_{\text{explicit mention}} + 35 \times \mathbb{I}_{\text{symbol match}} + 25 \times \mathbb{I}_{\text{test import}} + 15 \times \mathbb{I}_{\text{token match}}$$
- **Focal File Injection**: Injects up to 6 high-priority files (within a 1500-line budget) directly into the preflight prompt, giving the model full visibility of critical code upfront.

### 3. Dynamic Context Pruner (`_prune_context`)
Over long-running tasks (10–15 iterations), repeating large file contents and historical test outputs causes exponential token growth and hits API provider rate limits.
- **Protected Boundaries**: Preserves the immutable System Prompt (`messages[0]`), the original enhanced user task (`messages[1]`), and the most recent 6 conversational turns.
- **Stale Tool Truncation**: Automatically trims intermediate tool outputs (e.g. historical multi-hundred-line file reads or previous failed test runs) down to concise snippets (`... [Previous tool output truncated for token efficiency] ...`).
- **Token Reduction**: Cuts message history tokens by **60–75%**, allowing models like `gpt-oss-120b` and `gpt-oss-20b` to operate comfortably within tight TPM ceilings.

### 4. Self-Healing Tool Feedback
When an LLM attempts an edit that fails (e.g. whitespace mismatch in `replace_in_file` or argument format discrepancies):
- Ion does not return a generic failure. It returns an **Actionable Self-Healing Hint** containing the current lines from disk and instructions on how to use `read_file` or `write_file` to recover cleanly.
- `read_file` and `write_file` support tolerant keyword aliases (`line_start`, `line_end`, `contents`, `text`, `code`), preventing models from stalling on tool schema mismatches.

---

## 🔄 Provider Abstraction & The Fallback Engine

Ion guarantees task completion even when third-party AI APIs suffer from outages, credit limits, or transient rate limits:

```
[Primary Model: Groq openai/gpt-oss-120b]
                   │
                   ▼ (429 Rate Limit / 404 Model / 402 Credits)
       [Fallback 1: Groq openai/gpt-oss-20b]
                   │
                   ▼ (Rate Limit Exceeded)
       [Fallback 2: Groq qwen/qwen3.8-27b]
                   │
                   ▼ (Provider Failure)
       [Fallback 3: OpenRouter / OpenAI Direct]
```

- **`FallbackProvider`**: Wraps any primary provider with an ordered chain of backups. When a call fails due to `402 Payment Required`, `404 Model Not Found`, or repeated `429 Rate Limits`, the engine gracefully logs the transition and retries seamlessly with the next model.
- **Exponential Backoff**: Inspects `Retry-After` headers and error strings (e.g., `try again in 5.3s`) to perform exact countdown pauses before resuming execution.

---

## 🛠️ Sandbox Environments

All code edits and command executions run through an isolated sandbox interface:

| Sandbox Mode | Description | Isolation Level | Best For |
| :--- | :--- | :--- | :--- |
| **`DockerSandbox`** | Spawns an isolated container mounting the repo. Non-root user permissions, strict command timeouts, and resource limits. | 🟢 Full Isolation | Untrusted code, production SWE-bench runs |
| **`LocalSandbox`** | Runs directly on the host workspace with sub-millisecond execution times. | 🟡 Workspace Bound | Fast local iteration, simple scripts |

---

## 🖥️ User Interfaces

### 1. Terminal TUI & Interactive REPL
Launch the full interactive TUI using:
```bash
make run
# or
ion --repo ./sample-project
```

- **Live Activity Grid**: Shows current model, elapsed execution time, iteration count, and live reasoning thoughts.
- **Unified Diff Viewer**: Type `/diff` to inspect colored syntax-highlighted git diffs of uncommitted changes.
- **Session Logs**: Type `/log [lines]` to print the recent execution trace in the terminal.
- **State Rollback**: Type `/rollback` to instantly reset the working tree to git clean slate.
- **Dynamic Model Switching**: Type `/model` to view all configured providers and switch models on the fly.

### 2. Web Dashboard
Ion includes an integrated web dashboard running as a background daemon:
```bash
make web
# Starts dashboard at http://localhost:5173/
```
- **Timeline & Session History**: Step-by-step tree of all previous runs with duration and tool calls.
- **Colorized Diff Viewer**: Side-by-side view of all files modified by the agent.
- **Live Logs**: Real-time terminal output and structured JSON logs.

---

## 🚀 Quickstart & Installation

### 1. Setup Virtual Environment
```bash
git clone https://github.com/your-username/ion.git
cd ion
make install
```

### 2. Configure Environment Keys
Add your API keys to `.env` or export them in your shell:
```bash
# Groq (Recommended for ultra-fast, high-quota reasoning)
export GROQ_API_KEY="gsk_..."

# OpenRouter (Access to 200+ models)
export OPENROUTER_API_KEY="sk-or-v1-..."

# OpenAI Direct
export OPENAI_API_KEY="sk-proj-..."

# Anthropic Direct
export ANTHROPIC_API_KEY="sk-ant-..."
```

### 3. Launching Tasks
```bash
# Interactive REPL
make run

# Headless / Automated Task Execution
ion --repo ./sample-project "Fix the double-spend idempotency race condition in payment_service.js"
```

---

## 📊 Benchmark Suite

Ion includes built-in SWE-bench style benchmarks spanning three difficulty tiers:

| Benchmark | Location | Complexity | Description | Target Iterations |
| :--- | :--- | :--- | :--- | :--- |
| **Easy** | [`tests/easy/`](file:///Users/siddhanthsadashivraikar/Desktop/ion/tests/easy/) | 🟢 Low | Single-file calculation logic bug (`calc.py`) | 1 Iteration |
| **Medium** | [`tests/medium/`](file:///Users/siddhanthsadashivraikar/Desktop/ion/tests/medium/) | 🟡 Medium | Multi-function shopping cart discount & tax calculations (`cart.py`) | 2–3 Iterations |
| **Hard** | [`tests/hard/`](file:///Users/siddhanthsadashivraikar/Desktop/ion/tests/hard/) | 🟠 High | Multi-module service orchestration, mock auth, and storage state | 3–5 Iterations |
| **SWE-Bench** | [`sample-project/`](file:///Users/siddhanthsadashivraikar/Desktop/ion/sample-project/) | 🔴 Complex | Full e-commerce pipeline: Concurrency double-spend, inventory leak, floating-point precision | Full Suite |

Run any benchmark directly:
```bash
make test-easy
make test-medium
make test-hard
```
