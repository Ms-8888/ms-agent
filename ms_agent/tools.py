from __future__ import annotations

import re
from pathlib import Path

TOOLS = [
    {
        "name": "list_directory",
        "description": "List files and directories at a path. Use this first to understand project structure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path relative to the target root (default: '.')",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Include all subdirectories recursively (default: false)",
                },
            },
        },
    },
    {
        "name": "read_file",
        "description": "Read a file's content. Use to inspect source code, configs, or docs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to the target root",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "search_pattern",
        "description": (
            "Search for a text or regex pattern across files. "
            "Returns matching lines with file paths and line numbers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Text or regex pattern to search for",
                },
                "directory": {
                    "type": "string",
                    "description": "Directory to search in, relative to target root (default: '.')",
                },
                "file_glob": {
                    "type": "string",
                    "description": "Glob to filter files, e.g. '*.py' (default: all files)",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "submit_answer",
        "description": "Submit your final answer once you have gathered sufficient evidence. Ends the investigation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Concise answer to the question with specific details",
                },
                "findings": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of key findings that support the answer (include file:line references)",
                },
                "confidence": {
                    "type": "string",
                    "enum": ["HIGH", "MEDIUM", "LOW"],
                    "description": "Confidence level based on how much direct evidence was found",
                },
            },
            "required": ["summary", "findings", "confidence"],
        },
    },
]

_MAX_FILE_BYTES = 16_000
_MAX_SEARCH_RESULTS = 30
_BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip",
    ".tar", ".gz", ".exe", ".whl", ".pyc",
}
_SKIP_DIRS = {"__pycache__", "node_modules", "dist", "venv", ".venv", "build", ".git"}


def execute_tool(name: str, args: dict, target: Path) -> str:
    if name == "read_file":
        return _read_file(args["path"], target)
    if name == "search_pattern":
        return _search_pattern(
            args["pattern"],
            args.get("directory", "."),
            args.get("file_glob", "*"),
            target,
        )
    if name == "list_directory":
        return _list_directory(args.get("path", "."), bool(args.get("recursive", False)), target)
    return f"Unknown tool: {name}"


def _read_file(path: str, target: Path) -> str:
    full = (target / path).resolve()
    if not full.is_relative_to(target.resolve()):
        return "Access denied: path is outside the target directory."
    if not full.exists():
        return f"File not found: {path}"
    if not full.is_file():
        return f"Not a file: {path}"
    if full.suffix.lower() in _BINARY_EXTENSIONS:
        return f"Binary file skipped: {path}"
    try:
        content = full.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error reading {path}: {e}"
    if len(content) > _MAX_FILE_BYTES:
        content = content[:_MAX_FILE_BYTES] + f"\n... [truncated — {len(content)} chars total]"
    return content


def _search_pattern(pattern: str, directory: str, file_glob: str, target: Path) -> str:
    search_dir = (target / directory).resolve()
    if not search_dir.is_relative_to(target.resolve()):
        return "Access denied: path is outside the target directory."
    if not search_dir.exists():
        return f"Directory not found: {directory}"

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        regex = re.compile(re.escape(pattern), re.IGNORECASE)

    results: list[str] = []
    for filepath in sorted(search_dir.rglob(file_glob)):
        if not filepath.is_file():
            continue
        if filepath.suffix.lower() in _BINARY_EXTENSIONS:
            continue
        try:
            lines = filepath.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines, 1):
            if regex.search(line):
                rel = filepath.relative_to(target)
                results.append(f"{rel.as_posix()}:{i}: {line.strip()}")
                if len(results) >= _MAX_SEARCH_RESULTS:
                    results.append(f"... [truncated at {_MAX_SEARCH_RESULTS} matches]")
                    return "\n".join(results)

    return "\n".join(results) if results else "No matches found."


def _list_directory(path: str, recursive: bool, target: Path) -> str:
    full = (target / path).resolve()
    if not full.is_relative_to(target.resolve()):
        return "Access denied: path is outside the target directory."
    if not full.exists():
        return f"Directory not found: {path}"
    if not full.is_dir():
        return f"Not a directory: {path}"

    lines: list[str] = []
    glob = full.rglob("*") if recursive else full.iterdir()
    for p in sorted(glob):
        rel = p.relative_to(target)
        if any(part.startswith(".") or part in _SKIP_DIRS for part in rel.parts):
            continue
        lines.append(rel.as_posix() + ("/" if p.is_dir() else ""))

    return "\n".join(lines) if lines else "(empty)"
