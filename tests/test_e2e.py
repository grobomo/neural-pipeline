"""End-to-end pipeline test with live SDK calls.

Simulates the monitor's role by manually running manager_runner for each
phase. Tests the complete flow: ego creates task -> why -> scope -> plan ->
execute -> verify -> output -> ego reviews and approves.

Usage: python tests/test_e2e.py
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import Config
from src.ego import Ego


def run_phase(phase: str, task_name: str, config: Config) -> dict:
    """Run a manager for a phase and return the result."""
    task_path = config.phase_dir(phase) / task_name
    if not task_path.exists():
        return {"error": f"Task {task_name} not found in {phase}/"}

    print(f"\n{'='*60}")
    print(f"  PHASE: {phase.upper()} -- processing {task_name}")
    print(f"{'='*60}")

    cmd = [
        sys.executable, "-m", "src.manager_runner",
        "--phase", phase,
        "--task", str(task_path),
        "--root", str(ROOT),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 min per phase (verify can be slow)
            cwd=str(ROOT),
        )
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT: {phase} phase exceeded 300s")
        return {"error": f"{phase} phase timed out after 300s"}

    if result.returncode != 0:
        print(f"  STDERR: {result.stderr[:500]}")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"error": result.stdout[:500] + result.stderr[:500]}

    try:
        data = json.loads(result.stdout)
        print(f"  Steps: {data.get('steps', '?')}")
        reviews = data.get('reviews', [])
        for r in reviews:
            print(f"  Step {r.get('step', '?')}: criteria={r.get('met_criteria', '?')} "
                  f"prediction={r.get('prediction_match', '?')} score={r.get('score', '?')}")
        return data
    except json.JSONDecodeError:
        print(f"  Raw output: {result.stdout[:300]}")
        return {"raw": result.stdout[:500]}


def find_task(task_name: str, config: Config) -> str | None:
    """Find which phase a task is currently in."""
    for phase in config.phases:
        if (config.phase_dir(phase) / task_name).exists():
            return phase
    for folder in ["completed/recent", "completed/archive", "failed/recent",
                    "failed/archive", "paused", "blocked"]:
        if (config.root / folder / task_name).exists():
            return folder
    return None


def main():
    config = Config()
    processing_phases = config.pipeline_phases  # why, scope, plan, execute, verify

    print("=" * 60)
    print("  NEURAL PIPELINE -- END-TO-END TEST")
    print("=" * 60)

    # Step 1: Ego creates task
    print("\n[1/7] Ego creating task...")
    ego = Ego(config=config)
    task_path = ego.create_task(
        "Write a Python function called 'is_prime' that checks if a number is prime. "
        "Include a docstring, type hints, and handle edge cases (0, 1, negative numbers). "
        "Write it to a file called prime.py in the project root."
    )
    ego.close_log()
    task_name = task_path.name
    print(f"  Created: {task_name}")

    # Step 2: Move from input to why (monitor's job)
    print("\n[2/7] Moving task from input/ to why/ (simulating monitor)...")
    why_dir = config.phase_dir("why")
    shutil.move(str(task_path), str(why_dir / task_name))

    # Step 3-7: Run each phase
    results = {}
    for i, phase in enumerate(processing_phases, 3):
        location = find_task(task_name, config)
        if location != phase:
            print(f"\n  Task is in '{location}', expected '{phase}' -- skipping remaining phases")
            break

        result = run_phase(phase, task_name, config)
        results[phase] = result

        if "error" in result:
            print(f"\n  ERROR in {phase}: {result['error']}")
            break

    # Check final location
    final_location = find_task(task_name, config)
    print(f"\n{'='*60}")
    print(f"  PIPELINE COMPLETE")
    print(f"  Task final location: {final_location}")
    print(f"{'='*60}")

    # If task reached output, ego reviews and approves
    if final_location == "output":
        task_id = int(task_name.replace("task-", "").replace(".md", ""))

        print(f"\n[Review] Ego reviewing task {task_id}...")
        ego2 = Ego(config=config)
        review = ego2.review_task(task_id)
        print(f"  Status: {review.get('status', '?')}")

        # Read the task file to show accumulated content
        output_path = config.root / "pipeline" / "output" / task_name
        if output_path.exists():
            content = output_path.read_text()
            print(f"\n  Task file ({len(content)} chars, showing last 500):")
            print(content[-500:])

        print(f"\n[Approve] Ego approving task {task_id}...")
        approval = ego2.approve_task(task_id)
        print(f"  Result: {approval}")
        print(f"  Happiness: {ego2.state.get('happiness', '?')}")
        ego2.close_log()

    # Summary
    print(f"\n{'='*60}")
    print(f"  E2E SUMMARY")
    print(f"{'='*60}")
    print(f"  Phases completed: {list(results.keys())}")
    print(f"  Final location: {find_task(task_name, config)}")

    # Check artifacts
    for phase in processing_phases:
        phase_dir = config.phase_dir(phase)
        steps = list((phase_dir / "workers" / "steps" / "completed").glob("*.md"))
        logs = list((phase_dir / "workers" / "logs" / "active").glob("*.jsonl"))
        mgr_logs = list((phase_dir / "manager" / "logs" / "active").glob("*.jsonl"))
        preds = list((phase_dir / "manager" / "predictions").glob("*.md"))
        print(f"  {phase}: {len(steps)} steps, {len(logs)} worker logs, "
              f"{len(mgr_logs)} mgr logs, {len(preds)} predictions")

    journal = config.phase_dir("why") / "manager" / "journal.md"
    if journal.exists():
        jtext = journal.read_text()
        entries = jtext.count("## Task ")
        print(f"  Why journal entries: {entries}")

    ego_logs = list((config.ego_dir() / "logs").glob("*.jsonl"))
    print(f"  Ego logs: {len(ego_logs)}")

    notifications = list((config.ego_dir() / "notifications").glob("*.md"))
    archived = list((config.ego_dir() / "notifications" / "archive").glob("*.md"))
    print(f"  Notifications: {len(notifications)} pending, {len(archived)} archived")

    if all(phase in results for phase in processing_phases) and final_location in ("output", "completed/recent"):
        print(f"\n  *** E2E TEST PASSED ***")
    else:
        print(f"\n  *** E2E TEST INCOMPLETE -- see above for details ***")


if __name__ == "__main__":
    main()
