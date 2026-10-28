from __future__ import annotations

from pathlib import Path

import typer
from dotenv import load_dotenv

from ms_agent.agent import run
from ms_agent.output import print_final, write_markdown

load_dotenv()

app = typer.Typer(
    help="ms-agent — autonomous codebase analyst powered by Claude.",
    add_completion=False,
)


@app.callback()
def main() -> None:
    """ms-agent — autonomous codebase analyst powered by Claude."""


@app.command()
def ask(
    question: str = typer.Argument(..., help="Question to answer about the codebase"),
    target: Path = typer.Option(
        Path("."),
        "--target", "-t",
        help="Directory to investigate",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Save report to a markdown file"
    ),
    max_iterations: int = typer.Option(
        5,
        "--iterations", "-n",
        help="Maximum investigation steps (1–10)",
        min=1,
        max=10,
    ),
) -> None:
    """Investigate a codebase and answer a question using a ReAct agent loop."""
    result = run(question, target, max_iterations)
    print_final(
        result.summary,
        result.findings,
        result.confidence,
        result.validation_score,
        result.iterations,
    )
    if output:
        write_markdown(
            result.question,
            result.summary,
            result.findings,
            result.confidence,
            result.validation_score,
            result.iterations,
            output,
        )
        print(f"Report saved → {output}")
