# ms-agent

Autonomous codebase analyst powered by Claude — a ReAct agent that investigates a directory, reasons step by step, calls tools to read files and search patterns, then delivers a structured answer with a self-graded confidence score.

> No API key? Read [`examples/sample_run.md`](examples/sample_run.md) to see a full traced run.

---

## Quick start

```bash
git clone https://github.com/Ms-8888/ms-agent
cd ms-agent
pip install -e .
echo "ANTHROPIC_API_KEY=your-key" > .env

ms-agent ask "Are there any security vulnerabilities?" --target ./path/to/project
ms-agent ask "How does the retry logic work?" --target ./path/to/project
ms-agent ask "Summarise the architecture" --target ./path/to/project --output report.md
```

---

## How it works

The agent runs a **ReAct loop** (Reason + Act) — the same pattern used by production AI systems:

```
Question
    │
    ▼
┌─────────────────────────────────────────────┐
│  Step N                                     │
│                                             │
│  Reason ──► decide what to investigate      │  × up to 5 iterations
│  Act    ──► call a tool                     │
│  Observe──► read the result                 │
└─────────────────────────────────────────────┘
    │
    ▼
submit_answer  ──►  Validate (separate LLM call)
    │
    ▼
  Report (summary + findings + confidence score)
```

Each step streams to your terminal in real time — you watch the agent reason, call tools, and read results as they happen.

---

## Tools

| Tool | What it does |
|------|-------------|
| `list_directory` | Explore project structure |
| `read_file` | Read source files, configs, docs |
| `search_pattern` | Grep-like search with regex across files |
| `submit_answer` | Signal completion — structured final answer |

All tools enforce path sandboxing: attempts to read outside the target directory are blocked.

---

## Architecture

```
cli.py          Typer CLI — parses question, target, options
agent.py        ReAct loop — streams each step, executes tools, calls validator
tools.py        Tool definitions (JSON schema) + implementations (pure Python)
output.py       Terminal rendering + markdown export
```

### The loop (`agent.py`)

```python
for iteration in range(1, max_iterations + 1):
    # Stream Claude's response — reasoning text prints live as it arrives
    response = stream_step(messages)

    # Execute any tool calls the model made
    for tool_call in response.tool_calls:
        if tool_call.name == "submit_answer":
            final = tool_call.args   # done
        else:
            result = execute_tool(tool_call.name, tool_call.args, target)
            messages.append(tool_result(result))

    if final:
        break

# Reflection: a separate Claude call scores the answer quality 0.0–1.0
score = validate(question, final)
```

### Validation (`agent.py → _validate`)

After the agent submits its answer, a second Claude call rates the answer quality from 0.0 to 1.0 — checking whether it cited specific evidence (file paths, line numbers) and answered the question completely. This is the self-reflection step that separates a production agent from a one-shot prompt.

---

## Example output

```
── Step 1/5
I'll start by exploring the project structure.
  ⟶ list_directory
     (path='.')
     → app/ deploy/ migrations/ tests/ Dockerfile README.md …

── Step 2/5
Let me examine the authentication code — most security-sensitive area.
  ⟶ read_file
     (path='app/services/auth.py')
     → import hashlib / def hash_api_key(key) → sha256 …

── Step 3/5
  ⟶ search_pattern
     (pattern='hmac|compare_digest')
     → app/services/worker.py:14: sig = hmac.new(secret, payload, sha256) …

── Answer
No critical vulnerabilities found. HMAC-SHA256 delivery signing is in place,
SSRF validation blocks private IP ranges on endpoint registration, and rate
limiting returns accurate Retry-After headers from Redis TTL.

Findings:
  • app/services/worker.py:14 — HMAC-SHA256 used for delivery signature
  • app/routers/endpoints.py — SSRF protection rejects 10.x/192.168.x/127.x ranges
  • app/dependencies.py:31 — Retry-After header reads actual Redis TTL

Confidence: HIGH  Validation: 0.91  Iterations: 3
```

Full traced run → [`examples/sample_run.md`](examples/sample_run.md)

---

## Stack

Python 3.12 · [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python) · Typer · pytest
