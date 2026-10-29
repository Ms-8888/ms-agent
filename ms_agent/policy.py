"""One path policy shared by every tool: what the agent may never read."""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path

DENIED_DIRS = {
    ".git", ".ssh", ".aws", ".gnupg", "node_modules", "venv", ".venv",
}
DENIED_FILE_PATTERNS = (
    ".env", ".env.*", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore",
    "credentials", "credentials.*", ".netrc", ".npmrc", ".pypirc",
)
# Templates that are meant to be committed and hold no real secrets.
ALLOWED_FILES = {".env.example", ".env.sample", ".env.template"}


def is_denied_dir(path: Path) -> bool:
    """A directory is denied by name, or because it is a Python virtualenv."""
    return path.name.lower() in DENIED_DIRS or (path / "pyvenv.cfg").is_file()


def is_denied_name(name: str) -> bool:
    lowered = name.lower()
    if lowered in ALLOWED_FILES:
        return False
    return any(fnmatch.fnmatch(lowered, pat) for pat in DENIED_FILE_PATTERNS)


def denial_reason(path: str | os.PathLike, root: Path) -> str | None:
    """Return why `path` must not be read, or None if it is allowed.

    Checks the path as written and again after resolving symlinks, so a
    harmless-looking link to .env or to a file outside the root is refused.
    """
    root_resolved = root.resolve()
    lexical = Path(os.path.normpath(root / path))
    resolved = lexical.resolve()
    if not resolved.is_relative_to(root_resolved):
        return "path is outside the target directory"
    for candidate, base in ((lexical, root), (resolved, root_resolved)):
        try:
            rel = candidate.relative_to(base)
        except ValueError:
            continue
        current = base
        for part in rel.parts[:-1] if not candidate.is_dir() else rel.parts:
            current = current / part
            if is_denied_dir(current):
                return f"'{part}' is a protected directory"
        if not candidate.is_dir() and rel.parts and is_denied_name(rel.parts[-1]):
            return f"'{rel.parts[-1]}' looks like a secret or credentials file"
    return None
