from pathlib import Path

import pytest


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    (tmp_path / "app.py").write_text(
        "import hashlib\n\n"
        "def verify_token(token: str, stored: str) -> bool:\n"
        "    return token == stored  # timing attack\n\n"
        "def hash_password(pw: str) -> str:\n"
        "    return hashlib.md5(pw.encode()).hexdigest()  # weak hash\n"
    )
    (tmp_path / "config.py").write_text(
        'SECRET_KEY = "hardcoded-secret-do-not-use"\n'
        'DATABASE_URL = "postgresql://user:pass@localhost/db"\n'
    )
    (tmp_path / "README.md").write_text(
        "# Sample Project\n\nA demo project for testing ms-agent.\n"
    )
    sub = tmp_path / "utils"
    sub.mkdir()
    (sub / "helpers.py").write_text("def add(a, b):\n    return a + b\n")
    return tmp_path
