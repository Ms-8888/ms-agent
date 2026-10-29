"""Failure-path tests for the agent loop and tools. The model is fully mocked."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ms_agent.agent import run
from ms_agent.tools import execute_tool


@pytest.fixture(autouse=True)
def set_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


class _Stream:
    def __init__(self, events):
        self._events = events

    def __enter__(self):
        return iter(self._events)

    def __exit__(self, *args):
        pass


def _tool_turn(name: str, raw_json: str, tool_id: str = "toolu_1", text: str = "") -> list:
    events = []
    if text:
        events += [
            SimpleNamespace(type="content_block_start", content_block=SimpleNamespace(type="text")),
            SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(text=text)),
            SimpleNamespace(type="content_block_stop"),
        ]
    events += [
        SimpleNamespace(
            type="content_block_start",
            content_block=SimpleNamespace(type="tool_use", id=tool_id, name=name),
        ),
        SimpleNamespace(
            type="content_block_delta", delta=SimpleNamespace(partial_json=raw_json)
        ),
        SimpleNamespace(type="content_block_stop"),
    ]
    return events


def _text_turn(text: str) -> list:
    return [
        SimpleNamespace(type="content_block_start", content_block=SimpleNamespace(type="text")),
        SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(text=text)),
        SimpleNamespace(type="content_block_stop"),
    ]


def _run_scripted(turns, target: Path, max_iterations: int = 5, validation: str = "0.9"):
    """Run the agent against scripted turns. Returns (result, snapshots of messages per call)."""
    snapshots: list[list] = []
    remaining = list(turns)

    def fake_create(**kwargs):
        if kwargs.get("stream"):
            snapshots.append(copy.deepcopy(kwargs["messages"]))
            events = remaining.pop(0) if len(remaining) > 1 else remaining[0]
            return _Stream(events)
        return SimpleNamespace(content=[SimpleNamespace(text=validation)])

    with patch("ms_agent.agent.Anthropic") as MockClient:
        MockClient.return_value.messages.create.side_effect = fake_create
        result = run("what is here?", target, max_iterations=max_iterations)
    return result, snapshots


def _last_tool_result(snapshot: list) -> str:
    return snapshot[-1]["content"][-1]["content"]


def test_tool_error_is_fed_back_and_loop_continues(sample_project):
    turns = [
        _tool_turn("read_file", json.dumps({"path": "missing.py"})),
        _tool_turn("submit_answer", json.dumps({"summary": "ok", "findings": [], "confidence": "LOW"})),
    ]
    result, snaps = _run_scripted(turns, sample_project)
    assert "File not found" in _last_tool_result(snaps[1])
    assert result.summary == "ok"
    assert result.iterations == 2


def test_path_traversal_rejected_inside_agent_loop(sample_project):
    outside = sample_project.parent / "secret.txt"
    outside.write_text("top secret")
    turns = [
        _tool_turn("read_file", json.dumps({"path": "../secret.txt"})),
        _tool_turn("read_file", json.dumps({"path": str(outside)})),
        _tool_turn("submit_answer", json.dumps({"summary": "done", "findings": [], "confidence": "LOW"})),
    ]
    _, snaps = _run_scripted(turns, sample_project)
    assert "Access denied" in _last_tool_result(snaps[1])
    assert "Access denied" in _last_tool_result(snaps[2])
    assert "top secret" not in json.dumps(snaps)


def test_path_traversal_rejected_for_search_directory(sample_project):
    result = execute_tool(
        "search_pattern", {"pattern": "root", "directory": "../.."}, sample_project
    )
    assert "Access denied" in result


def test_malformed_tool_arguments_do_not_crash_the_loop(sample_project):
    turns = [
        _tool_turn("read_file", '{"path": "app.'),
        _tool_turn("submit_answer", json.dumps({"summary": "recovered", "findings": [], "confidence": "LOW"})),
    ]
    result, snaps = _run_scripted(turns, sample_project)
    assert "Invalid arguments" in _last_tool_result(snaps[1])
    assert result.summary == "recovered"


def test_tool_call_missing_required_argument_returns_error(sample_project):
    assert "Invalid arguments" in execute_tool("read_file", {}, sample_project)
    assert "Invalid arguments" in execute_tool("search_pattern", {}, sample_project)


def test_unknown_tool_name_from_model_is_reported_back(sample_project):
    turns = [
        _tool_turn("delete_everything", "{}"),
        _tool_turn("submit_answer", json.dumps({"summary": "x", "findings": [], "confidence": "LOW"})),
    ]
    _, snaps = _run_scripted(turns, sample_project)
    assert "Unknown tool" in _last_tool_result(snaps[1])


def test_step_limit_without_answer_returns_low_confidence(sample_project):
    turns = [_tool_turn("list_directory", "{}")]
    result, snaps = _run_scripted(turns, sample_project, max_iterations=3)
    assert len(snaps) == 3
    assert result.iterations == 3
    assert result.confidence == "LOW"
    assert "max iterations" in result.summary


def test_step_limit_falls_back_to_last_text_block(sample_project):
    turns = [_tool_turn("list_directory", "{}", text="Still looking at the layout.")]
    result, _ = _run_scripted(turns, sample_project, max_iterations=2)
    assert result.summary == "Still looking at the layout."
    assert result.confidence == "LOW"
    assert result.findings == []


def test_empty_model_response_gives_inconclusive_result(sample_project):
    result, _ = _run_scripted([[]], sample_project, max_iterations=1)
    assert "max iterations" in result.summary
    assert result.confidence == "LOW"


def test_submit_answer_with_empty_arguments_is_treated_as_no_answer(sample_project):
    turns = [_tool_turn("submit_answer", "{}")]
    result, snaps = _run_scripted(turns, sample_project, max_iterations=5)
    assert len(snaps) == 1
    assert "max iterations" in result.summary


def test_submit_answer_with_empty_summary_is_returned_as_is(sample_project):
    turns = [_tool_turn("submit_answer", json.dumps({"summary": "", "findings": [], "confidence": "HIGH"}))]
    result, _ = _run_scripted(turns, sample_project)
    assert result.summary == ""
    assert result.confidence == "HIGH"


@pytest.mark.parametrize("reply", ["not a number", ""])
def test_unparseable_validation_score_defaults_to_half(sample_project, reply):
    turns = [_tool_turn("submit_answer", json.dumps({"summary": "s", "findings": [], "confidence": "LOW"}))]
    result, _ = _run_scripted(turns, sample_project, validation=reply)
    assert result.validation_score == 0.5


def test_validation_call_failure_defaults_to_half(sample_project):
    answer = _tool_turn("submit_answer", json.dumps({"summary": "s", "findings": [], "confidence": "LOW"}))

    def fake_create(**kwargs):
        if kwargs.get("stream"):
            return _Stream(answer)
        raise RuntimeError("validation API down")

    with patch("ms_agent.agent.Anthropic") as MockClient:
        MockClient.return_value.messages.create.side_effect = fake_create
        result = run("q", sample_project)
    assert result.validation_score == 0.5
    assert result.summary == "s"


def test_api_error_during_stream_propagates(sample_project):
    with patch("ms_agent.agent.Anthropic") as MockClient:
        MockClient.return_value.messages.create.side_effect = ConnectionError("network down")
        with pytest.raises(ConnectionError):
            run("q", sample_project)


def test_missing_api_key_exits(sample_project, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        run("q", sample_project)


def test_read_file_skips_binary_and_truncates_large_files(sample_project):
    (sample_project / "logo.png").write_bytes(b"\x89PNG\r\n")
    (sample_project / "big.txt").write_text("a" * 20_000)
    assert "Binary file skipped" in execute_tool("read_file", {"path": "logo.png"}, sample_project)
    big = execute_tool("read_file", {"path": "big.txt"}, sample_project)
    assert "truncated" in big
    assert len(big) < 20_000


def test_read_file_on_directory_and_invalid_regex_do_not_crash(sample_project):
    assert "Not a file" in execute_tool("read_file", {"path": "utils"}, sample_project)
    result = execute_tool("search_pattern", {"pattern": "verify_token("}, sample_project)
    assert "app.py" in result
