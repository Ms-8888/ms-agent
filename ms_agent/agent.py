from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from anthropic import Anthropic

from ms_agent.tools import TOOLS, execute_tool
from ms_agent.output import (
    print_step_header,
    print_reasoning,
    print_tool_call,
    print_tool_result,
)

MODEL = "claude-sonnet-4-6"

_SYSTEM = """\
You are a codebase analyst. Your task is to answer a question about a software project \
by reading its source files and searching for patterns.

Work methodically:
1. Call list_directory first to understand the project layout.
2. Use read_file and search_pattern to gather specific evidence.
3. When you have enough information to answer with confidence, call submit_answer.

Be specific — cite exact file paths and line numbers in your findings. \
If you cannot find sufficient evidence, say so honestly and call submit_answer with confidence LOW."""


@dataclass
class AgentResult:
    question: str
    summary: str
    findings: list[str] = field(default_factory=list)
    confidence: str = "LOW"
    iterations: int = 0
    validation_score: float = 0.0


def run(question: str, target: Path, max_iterations: int = 5) -> AgentResult:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("Error: ANTHROPIC_API_KEY not set. Add it to .env or export it.")

    client = Anthropic(api_key=api_key)
    messages: list[dict] = [
        {
            "role": "user",
            "content": f"Question: {question}\n\nTarget directory: {target}",
        }
    ]

    final: dict = {}
    last_iteration = 0

    for iteration in range(1, max_iterations + 1):
        last_iteration = iteration
        print_step_header(iteration, max_iterations)

        response_blocks: list[dict] = []
        current_block: dict = {}
        in_tool = False
        tool_json: list[str] = []

        with client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=_SYSTEM,
            messages=messages,
            tools=TOOLS,
            tool_choice={"type": "auto"},
            stream=True,
        ) as stream:
            for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "text":
                        in_tool = False
                        current_block = {"type": "text", "text": ""}
                        response_blocks.append(current_block)
                    elif block.type == "tool_use":
                        in_tool = True
                        tool_json = []
                        current_block = {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": {},
                        }
                        response_blocks.append(current_block)
                        print_tool_call(block.name)

                elif event.type == "content_block_delta":
                    if not in_tool and hasattr(event.delta, "text"):
                        current_block["text"] += event.delta.text
                        print_reasoning(event.delta.text)
                    elif in_tool and hasattr(event.delta, "partial_json"):
                        tool_json.append(event.delta.partial_json)

                elif event.type == "content_block_stop" and in_tool:
                    raw = "".join(tool_json)
                    if raw:
                        current_block["input"] = json.loads(raw)
                    in_tool = False

        messages.append({"role": "assistant", "content": response_blocks})

        tool_results: list[dict] = []
        done = False

        for block in response_blocks:
            if block.get("type") != "tool_use":
                continue
            name = block["name"]
            args = block.get("input", {})

            if name == "submit_answer":
                final = args
                done = True
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": "Answer recorded.",
                })
            else:
                result = execute_tool(name, args, target)
                print_tool_result(name, args, result)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": result,
                })

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

        if done:
            break

    if not final:
        # Max iterations reached without submit_answer — use last text block
        for block in reversed(response_blocks):
            if block.get("type") == "text" and block.get("text", "").strip():
                final = {
                    "summary": block["text"].strip(),
                    "findings": [],
                    "confidence": "LOW",
                }
                break
        else:
            final = {
                "summary": "Investigation reached max iterations without a conclusive answer.",
                "findings": [],
                "confidence": "LOW",
            }

    score = _validate(client, question, final)

    return AgentResult(
        question=question,
        summary=final.get("summary", ""),
        findings=final.get("findings", []),
        confidence=final.get("confidence", "LOW"),
        iterations=last_iteration,
        validation_score=score,
    )


def _validate(client: Anthropic, question: str, answer: dict) -> float:
    """Separate reflection call — LLM grades its own answer quality."""
    prompt = (
        f"Question asked: {question}\n\n"
        f"Answer given: {answer.get('summary', '')}\n\n"
        f"Findings cited: {json.dumps(answer.get('findings', []))}\n\n"
        "Rate the quality of this answer from 0.0 to 1.0. "
        "Consider: Is it specific? Does it cite file paths or line numbers? Is it complete? "
        "Reply with a single decimal number only, e.g. 0.85"
    )
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=32,
            messages=[{"role": "user", "content": prompt}],
        )
        return round(float(response.content[0].text.strip()), 2)
    except (ValueError, IndexError, Exception):
        return 0.5
