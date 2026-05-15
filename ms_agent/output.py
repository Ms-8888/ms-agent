from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass

_GREY = "\033[90m"
_CYAN = "\033[96m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RED = "\033[91m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"

_CONFIDENCE_COLOR = {"HIGH": _GREEN, "MEDIUM": _YELLOW, "LOW": _RED}


def print_step_header(iteration: int, max_iter: int) -> None:
    print(f"\n{_BOLD}── Step {iteration}/{max_iter} {_RESET}", flush=True)


def print_reasoning(chunk: str) -> None:
    print(f"{_GREY}{chunk}{_RESET}", end="", flush=True)


def print_tool_call(name: str) -> None:
    print(f"\n{_CYAN}  ⟶ {name}{_RESET}", end=" ", flush=True)


def print_tool_result(name: str, args: dict, result: str) -> None:
    preview = result.replace("\n", " ")[:120]
    if len(result) > 120:
        preview += "…"
    arg_str = ", ".join(f"{k}={repr(v)}" for k, v in list(args.items())[:2])
    print(f"\n{_DIM}     ({arg_str}){_RESET}")
    print(f"{_DIM}     → {preview}{_RESET}")


def print_final(summary: str, findings: list[str], confidence: str, score: float, iterations: int) -> None:
    color = _CONFIDENCE_COLOR.get(confidence, _GREY)
    print(f"\n{_BOLD}── Answer {_RESET}")
    print(f"{summary}\n")
    if findings:
        print(f"{_BOLD}Findings:{_RESET}")
        for f in findings:
            print(f"  • {f}")
    print(
        f"\n{color}Confidence: {confidence}{_RESET}  "
        f"{_GREY}Validation: {score:.2f}  Iterations: {iterations}{_RESET}\n"
    )


def write_markdown(
    question: str,
    summary: str,
    findings: list[str],
    confidence: str,
    score: float,
    iterations: int,
    path: Path,
) -> None:
    lines = [
        "# Agent Report\n",
        f"**Question:** {question}\n",
        f"**Confidence:** {confidence} &nbsp; **Validation score:** {score:.2f} &nbsp; **Iterations:** {iterations}\n",
        "## Answer\n",
        f"{summary}\n",
    ]
    if findings:
        lines.append("## Findings\n")
        for f in findings:
            lines.append(f"- {f}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
