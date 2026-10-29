"""Path policy and search limits. The model is not involved."""
from pathlib import Path

import pytest

from ms_agent import tools
from ms_agent.tools import execute_tool


@pytest.fixture
def secret_project(sample_project: Path) -> Path:
    p = sample_project
    (p / ".env").write_text("API_KEY=topsecret-env\n")
    (p / ".env.production").write_text("API_KEY=topsecret-prod\n")
    (p / ".env.example").write_text("API_KEY=changeme\n")
    (p / "id_rsa").write_text("topsecret-rsa\n")
    (p / "server.pem").write_text("topsecret-pem\n")
    (p / "tls.key").write_text("topsecret-key\n")
    (p / "credentials.json").write_text('{"topsecret": "cred"}\n')
    (p / ".git").mkdir()
    (p / ".git" / "config").write_text("topsecret-git\n")
    (p / "node_modules" / "pkg").mkdir(parents=True)
    (p / "node_modules" / "pkg" / "index.js").write_text("topsecret-node\n")
    (p / "myenv").mkdir()
    (p / "myenv" / "pyvenv.cfg").write_text("home = /usr\n")
    (p / "myenv" / "mod.py").write_text("topsecret-venv\n")
    (p / "sub").mkdir()
    (p / "sub" / ".env").write_text("topsecret-nested\n")
    return p


@pytest.mark.parametrize(
    "path",
    [
        ".env", ".env.production", "id_rsa", "server.pem", "tls.key",
        "credentials.json", ".git/config", "node_modules/pkg/index.js",
        "myenv/mod.py", "sub/.env", "./.env", "utils/../.env",
    ],
)
def test_read_file_denies_secret_paths(secret_project: Path, path: str) -> None:
    result = execute_tool("read_file", {"path": path}, secret_project)
    assert "Access denied" in result
    assert "topsecret" not in result


def test_read_file_allows_env_example(secret_project: Path) -> None:
    assert "changeme" in execute_tool("read_file", {"path": ".env.example"}, secret_project)


def test_search_skips_secret_files_silently(secret_project: Path) -> None:
    result = execute_tool("search_pattern", {"pattern": "topsecret"}, secret_project)
    assert result == "No matches found."


def test_search_still_finds_normal_files(secret_project: Path) -> None:
    result = execute_tool("search_pattern", {"pattern": "verify_token"}, secret_project)
    assert "app.py" in result


def test_search_denied_directory_is_refused(secret_project: Path) -> None:
    result = execute_tool(
        "search_pattern", {"pattern": "topsecret", "directory": ".git"}, secret_project
    )
    assert "Access denied" in result
    assert "topsecret" not in result


def _symlink(link: Path, dest: Path) -> None:
    try:
        link.symlink_to(dest)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available")


def test_symlink_outside_root_is_not_read(sample_project: Path, tmp_path_factory) -> None:
    outside = tmp_path_factory.mktemp("outside")
    (outside / "notes.txt").write_text("topsecret-outside\n")
    _symlink(sample_project / "link.txt", outside / "notes.txt")
    assert "Access denied" in execute_tool("read_file", {"path": "link.txt"}, sample_project)
    result = execute_tool("search_pattern", {"pattern": "topsecret"}, sample_project)
    assert "topsecret" not in result


def test_symlinked_dir_outside_root_is_not_searched(sample_project: Path, tmp_path_factory) -> None:
    outside = tmp_path_factory.mktemp("outside_dir")
    (outside / "notes.txt").write_text("topsecret-outside\n")
    _symlink(sample_project / "linkdir", outside)
    result = execute_tool("search_pattern", {"pattern": "topsecret"}, sample_project)
    assert "topsecret" not in result


def test_symlink_to_env_inside_root_is_denied(secret_project: Path) -> None:
    _symlink(secret_project / "innocent.txt", secret_project / ".env")
    assert "Access denied" in execute_tool("read_file", {"path": "innocent.txt"}, secret_project)
    result = execute_tool("search_pattern", {"pattern": "topsecret-env"}, secret_project)
    assert "topsecret" not in result


def test_pattern_too_long_is_rejected(sample_project: Path) -> None:
    result = execute_tool("search_pattern", {"pattern": "a" * 201}, sample_project)
    assert "Pattern too long" in result


def test_pattern_at_limit_is_accepted(sample_project: Path) -> None:
    result = execute_tool("search_pattern", {"pattern": "a" * 200}, sample_project)
    assert "Pattern too long" not in result


def test_overlong_lines_are_skipped(sample_project: Path) -> None:
    (sample_project / "minified.js").write_text("needle " + "x" * 3000 + "\nneedle short\n")
    result = execute_tool("search_pattern", {"pattern": "needle"}, sample_project)
    assert "minified.js:2" in result
    assert "minified.js:1:" not in result


def test_match_cap(sample_project: Path) -> None:
    (sample_project / "many.txt").write_text("hit\n" * 100)
    result = execute_tool("search_pattern", {"pattern": "hit"}, sample_project)
    assert "truncated at 30 matches" in result
    assert len(result.splitlines()) == 31


def test_large_files_are_skipped(sample_project: Path, monkeypatch) -> None:
    monkeypatch.setattr(tools, "_MAX_SEARCH_FILE_BYTES", 10)
    (sample_project / "big.txt").write_text("needle " + "y" * 50)
    assert "big.txt" not in execute_tool("search_pattern", {"pattern": "needle"}, sample_project)


def test_lines_scanned_cap(sample_project: Path, monkeypatch) -> None:
    monkeypatch.setattr(tools, "_MAX_LINES_SCANNED", 5)
    (sample_project / "zzz.txt").write_text("filler\n" * 20 + "needle\n")
    result = execute_tool("search_pattern", {"pattern": "needle"}, sample_project)
    assert "stopped after scanning" in result


def test_time_budget(sample_project: Path, monkeypatch) -> None:
    monkeypatch.setattr(tools, "_SEARCH_TIME_BUDGET_S", -1.0)
    result = execute_tool("search_pattern", {"pattern": "verify_token"}, sample_project)
    assert "time budget" in result
