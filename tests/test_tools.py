from pathlib import Path
from ms_agent.tools import execute_tool


def test_read_file_returns_content(sample_project: Path) -> None:
    result = execute_tool("read_file", {"path": "app.py"}, sample_project)
    assert "verify_token" in result
    assert "timing attack" in result


def test_read_file_missing(sample_project: Path) -> None:
    result = execute_tool("read_file", {"path": "nonexistent.py"}, sample_project)
    assert "not found" in result.lower()


def test_read_file_path_traversal_blocked(sample_project: Path) -> None:
    result = execute_tool("read_file", {"path": "../../../etc/passwd"}, sample_project)
    assert "Access denied" in result


def test_search_pattern_finds_match(sample_project: Path) -> None:
    result = execute_tool("search_pattern", {"pattern": "SECRET_KEY"}, sample_project)
    assert "config.py" in result
    assert "SECRET_KEY" in result


def test_search_pattern_no_match(sample_project: Path) -> None:
    result = execute_tool("search_pattern", {"pattern": "zzz_not_present_zzz"}, sample_project)
    assert "No matches" in result


def test_search_pattern_with_glob(sample_project: Path) -> None:
    result = execute_tool(
        "search_pattern",
        {"pattern": "def ", "file_glob": "*.py"},
        sample_project,
    )
    assert "app.py" in result


def test_list_directory(sample_project: Path) -> None:
    result = execute_tool("list_directory", {}, sample_project)
    assert "app.py" in result
    assert "config.py" in result
    assert "utils/" in result


def test_list_directory_recursive(sample_project: Path) -> None:
    result = execute_tool("list_directory", {"recursive": True}, sample_project)
    assert "utils/helpers.py" in result


def test_list_directory_path_traversal_blocked(sample_project: Path) -> None:
    result = execute_tool("list_directory", {"path": "../.."}, sample_project)
    assert "Access denied" in result


def test_unknown_tool(sample_project: Path) -> None:
    result = execute_tool("nonexistent_tool", {}, sample_project)
    assert "Unknown tool" in result
