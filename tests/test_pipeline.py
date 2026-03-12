"""Integration tests for Neural Pipeline.

Tests the full flow without making API calls (mocks the SDK client).
Verifies: task creation, step creation, rule matching, JSONL logging,
file movement, happiness mechanics, status reporting.
"""
import json
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is in path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import Config
from src.ego import Ego
from src.rules import parse_rule, match_rules, load_rules, format_rules_for_context, update_rule_score
from src.tools import TOOL_SCHEMAS, execute_tool, _resolve_path
from src.agent_base import AgentBase


def test_config():
    """Config loads and provides typed access."""
    c = Config()
    assert c.credential_key == "NEURAL_PIPELINE/API_KEY"
    assert "why" in c.phases
    assert c.model_for("ego") == "claude-sonnet-4-6"
    assert c.max_tokens_for("worker") == 8192
    assert c.threshold("stuck_task_minutes") == 30
    assert c.phase_dir("why").name == "why"
    print("PASS: test_config")


def test_ego_task_creation():
    """Ego creates task files with correct format."""
    ego = Ego()
    try:
        task_path = ego.create_task("Build a web scraper for news sites")
        assert task_path.exists()
        content = task_path.read_text()
        assert "Build a web scraper" in content
        assert "## User Request" in content
        assert "## References" in content

        # Status shows the task
        status = ego.get_status()
        assert any("task-" in t for t in status["pipeline"].get("input", []))

        # Cleanup
        task_path.unlink()
    finally:
        ego.close_log()
    print("PASS: test_ego_task_creation")


def test_ego_approve_reject():
    """Ego approve/reject moves tasks and updates happiness."""
    ego = Ego()
    try:
        # Create a task and manually move to output/
        task_path = ego.create_task("Test approve flow")
        task_name = task_path.name
        output_dir = ego.config.root / "pipeline" / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(task_path), str(output_dir / task_name))

        task_id = int(task_name.replace("task-", "").replace(".md", ""))

        # Test approve
        old_happiness = ego.state.get("happiness", 70.0)
        result = ego.approve_task(task_id)
        assert result["action"] == "approved"
        assert ego.state["happiness"] > old_happiness
        assert ego.state["tasks_completed"] >= 1

        # Verify task moved to completed/recent/
        completed = ego.config.completed_dir() / "recent" / task_name
        assert completed.exists()
        completed.unlink()

        # Test reject (create another task)
        task_path2 = ego.create_task("Test reject flow")
        task_name2 = task_path2.name
        shutil.move(str(task_path2), str(output_dir / task_name2))
        task_id2 = int(task_name2.replace("task-", "").replace(".md", ""))

        pre_reject = ego.state["happiness"]
        result2 = ego.reject_task(task_id2, "Tests don't pass")
        assert result2["action"] == "rejected"
        assert ego.state["happiness"] < pre_reject

        failed = ego.config.failed_dir() / "recent" / task_name2
        assert failed.exists()
        content = failed.read_text()
        assert "Tests don't pass" in content
        failed.unlink()

    finally:
        ego.close_log()
    print("PASS: test_ego_approve_reject")


def test_ego_status():
    """Ego status reports correct pipeline state."""
    ego = Ego()
    try:
        status = ego.get_status()
        assert "pipeline" in status
        assert "ego" in status
        assert "happiness" in status["ego"]
        assert isinstance(status["ego"]["happiness"], (int, float))
    finally:
        ego.close_log()
    print("PASS: test_ego_status")


def test_rules():
    """Rule parsing, matching, and scoring."""
    # Create a test rule
    rules_dir = ROOT / ".tmp" / "test-rules"
    rules_dir.mkdir(parents=True, exist_ok=True)

    rule_path = rules_dir / "test-rule.md"
    rule_path.write_text("""---
id: check-robots
keywords: [web, scraper, crawl, spider]
enabled: true
score: 2
history:
  loaded: 10
  successes: 8
  failures: 2
  last_scored: 2026-03-12
---

# Check robots.txt

Always check robots.txt before crawling a website.
""")

    # Parse
    rule = parse_rule(rule_path)
    assert rule is not None
    assert rule["id"] == "check-robots"
    assert rule["score"] == 2
    assert "web" in rule["keywords"]

    # Match
    matched = match_rules([rule], "Build a web scraper")
    assert len(matched) == 1

    not_matched = match_rules([rule], "Fix the database")
    assert len(not_matched) == 0

    # Format
    ctx = format_rules_for_context(matched)
    assert "check-robots" in ctx
    assert "robots.txt" in ctx

    # Score update
    update_rule_score(rule_path, 1)
    updated = parse_rule(rule_path)
    assert updated["score"] == 3

    update_rule_score(rule_path, 10)  # should clamp to 5
    clamped = parse_rule(rule_path)
    assert clamped["score"] == 5

    # Cleanup
    shutil.rmtree(rules_dir)
    print("PASS: test_rules")


def test_tools():
    """Tool schemas and execution."""
    assert len(TOOL_SCHEMAS) == 6
    tool_names = {t["name"] for t in TOOL_SCHEMAS}
    assert tool_names == {"read_file", "write_file", "edit_file", "shell", "search_files", "list_files"}

    # Path safety
    try:
        _resolve_path("../../etc/passwd", ROOT)
        assert False, "Should have raised PermissionError"
    except PermissionError:
        pass

    # Read
    result = execute_tool("read_file", {"path": "requirements.txt"}, ROOT)
    assert "anthropic" in result

    # Write + Read
    execute_tool("write_file", {"path": ".tmp/test.txt", "content": "hello"}, ROOT)
    result = execute_tool("read_file", {"path": ".tmp/test.txt"}, ROOT)
    assert "hello" in result

    # Edit
    execute_tool("edit_file", {"path": ".tmp/test.txt", "old_string": "hello", "new_string": "world"}, ROOT)
    result = execute_tool("read_file", {"path": ".tmp/test.txt"}, ROOT)
    assert "world" in result

    # List
    result = execute_tool("list_files", {"pattern": "src/*.py"}, ROOT)
    assert "config.py" in result

    # Cleanup
    Path(ROOT / ".tmp" / "test.txt").unlink()
    print("PASS: test_tools")


def test_jsonl_logging():
    """Agent base JSONL logging works correctly."""
    log_dir = ROOT / ".tmp" / "test-agent-logs"
    agent = AgentBase(role="test", log_dir=log_dir, system_prompt="test")
    agent.log("system", "System prompt here")
    agent.log("user", "User message")
    agent.log("assistant", "Response", tool_calls=[], usage={"input": 10, "output": 20})
    agent.close_log()

    # Read back
    with open(agent.log_path) as f:
        lines = f.readlines()
    assert len(lines) == 3

    entry = json.loads(lines[0])
    assert entry["type"] == "system"
    assert "timestamp" in entry

    entry2 = json.loads(lines[2])
    assert entry2["type"] == "assistant"
    assert entry2["tool_calls"] == []

    # Cleanup
    shutil.rmtree(log_dir)
    print("PASS: test_jsonl_logging")


def test_happiness_mechanics():
    """Happiness signals and decay work correctly."""
    ego = Ego()
    try:
        ego.state["happiness"] = 70.0
        ego.adjust_happiness("task_success")
        assert ego.state["happiness"] == 75.0  # +5

        ego.adjust_happiness("user_correction")
        assert ego.state["happiness"] == 60.0  # -15

        # Decay toward baseline
        ego.state["happiness"] = 70.0
        ego.state["baseline"] = 50.0
        ego.state["decay_rate"] = 5.0
        ego.decay_happiness()
        assert ego.state["happiness"] == 65.0  # decayed by 5 toward 50

        # Improvement mode
        ego.state["happiness"] = 30.0
        ego.state["improvement_threshold"] = 40.0
        assert ego.in_improvement_mode

        ego.state["happiness"] = 50.0
        assert not ego.in_improvement_mode
    finally:
        ego.close_log()
    print("PASS: test_happiness_mechanics")


def test_task_id_counter():
    """Task ID counter increments atomically."""
    ego = Ego()
    try:
        # Reset counter
        counter = ego.config.system_dir() / "next-task-id"
        counter.write_text("100")

        id1 = ego._next_task_id()
        assert id1 == 101

        id2 = ego._next_task_id()
        assert id2 == 102

        # Reset for other tests
        counter.write_text("0")
    finally:
        ego.close_log()
    print("PASS: test_task_id_counter")


if __name__ == "__main__":
    tests = [
        test_config,
        test_ego_task_creation,
        test_ego_approve_reject,
        test_ego_status,
        test_rules,
        test_tools,
        test_jsonl_logging,
        test_happiness_mechanics,
        test_task_id_counter,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"FAIL: {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if failed == 0:
        print("ALL TESTS PASSED")
    else:
        sys.exit(1)
