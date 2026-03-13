"""Manager base class for Neural Pipeline.

Managers are persistent across tasks. They break work into steps,
write predictions, delegate to workers, review results, score
prediction errors, and move tasks to the next phase.
"""
import json
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent_base import AgentBase
from .config import Config
from .rules import load_matched_rules, format_rules_for_context


class ManagerBase(AgentBase):
    """Base class for all phase managers."""

    def __init__(
        self,
        phase: str,
        task_path: Path,
        config: Config | None = None,
    ):
        self.phase = phase
        self.task_path = Path(task_path)
        self.config = config or Config()
        cfg = self.config

        phase_dir = cfg.phase_dir(phase)
        log_dir = phase_dir / "manager" / "logs" / "active"

        # Load reference, journal, and matched rules
        self.phase_dir = phase_dir
        reference = self._load_reference()
        task_text = self.task_path.read_text(encoding="utf-8")
        self.task_content = task_text
        self.task_id = self._extract_task_id()

        # Rules
        rules_dir = phase_dir / "manager" / "rules"
        self.matched_rules = load_matched_rules(rules_dir, task_text)
        rules_context = format_rules_for_context(self.matched_rules)

        # Memory
        memory_context = self._load_relevant_memories(task_text)

        # Journal (last N entries for context)
        journal_context = self._load_recent_journal()

        system_prompt = self._build_system_prompt(
            phase, reference, rules_context, memory_context, journal_context
        )

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")

        super().__init__(
            role="manager",
            log_dir=log_dir,
            config=cfg,
            system_prompt=system_prompt,
            tools=[],  # Managers don't use tools directly
        )
        self.log_path = log_dir / f"{ts}-task-{self.task_id}.jsonl"

    def _extract_task_id(self) -> str:
        """Extract task ID from filename (task-NNNN.md -> NNNN)."""
        name = self.task_path.stem
        if name.startswith("task-"):
            return name[5:]
        return name

    def _load_reference(self) -> str:
        """Load manager base prompt + phase reference."""
        parts = []
        manager_base = self.config.system_dir() / "agents" / "manager-base.md"
        if manager_base.exists():
            parts.append(manager_base.read_text(encoding="utf-8"))
        phase_ref = self.phase_dir / "reference.md"
        if phase_ref.exists():
            parts.append(phase_ref.read_text(encoding="utf-8"))
        return "\n\n".join(parts)

    def _load_relevant_memories(self, task_text: str) -> str:
        """Load short-term and long-term memories relevant to this task."""
        parts = []
        for tier in ["short-term", "long-term"]:
            mem_dir = self.phase_dir / "memory" / tier
            if not mem_dir.is_dir():
                continue
            for f in sorted(mem_dir.glob("*.md"))[:20]:
                content = f.read_text(encoding="utf-8", errors="replace")
                # Simple relevance: check if any word from memory appears in task
                words = set(content.lower().split())
                task_words = set(task_text.lower().split())
                overlap = words & task_words
                if len(overlap) > 3:  # at least a few common words
                    parts.append(f"### Memory ({tier}): {f.name}\n{content[:500]}")
        return "\n\n".join(parts[:10])  # cap at 10 memories

    def _load_recent_journal(self, max_entries: int = 5) -> str:
        """Load the last N journal entries."""
        journal = self.phase_dir / "manager" / "journal.md"
        if not journal.exists():
            return ""
        text = journal.read_text(encoding="utf-8")
        # Split by ## Task entries
        entries = text.split("\n## Task ")
        if len(entries) <= 1:
            return ""
        recent = entries[-max_entries:]
        return "\n\n## Task ".join(recent)

    def _build_system_prompt(
        self, phase: str, reference: str, rules: str, memory: str, journal: str
    ) -> str:
        parts = [
            f"You are the {phase}-phase manager in the Neural Pipeline.",
            "Your job: break the task into steps, write predictions, delegate to workers,",
            "review results, score prediction errors, and move the task forward.",
            "You do NOT execute work -- you coordinate and evaluate.",
        ]
        if reference:
            parts.append(f"\n## Reference\n{reference}")
        if rules:
            parts.append(f"\n{rules}")
        if memory:
            parts.append(f"\n## Relevant Memories\n{memory}")
        if journal:
            parts.append(f"\n## Recent Journal\n{journal}")
        return "\n\n".join(parts)

    # -- Pain Detection --

    @property
    def is_pain_task(self) -> bool:
        """Check if the current task is a pain file (pain-NNNN.md)."""
        return self.task_path.name.startswith("pain-")

    def _build_pain_prompt(self) -> str:
        """Build a diagnostic prompt for pain files instead of the standard
        implementation-oriented prompt. Each phase asks a different question."""
        prompts = {
            "why": (
                f"This is a PAIN SIGNAL -- an automated alert about a pipeline problem.\n\n"
                f"{self.task_content}\n\n"
                f"Diagnose WHY this problem occurred. Create steps to:\n"
                f"1. Identify the root cause (not just the symptom)\n"
                f"2. Check if this is a one-off or a systemic issue\n"
            ),
            "scope": (
                f"This is a PAIN SIGNAL being diagnosed.\n\n"
                f"{self.task_content}\n\n"
                f"Determine the SCOPE of this problem. Create steps to:\n"
                f"1. Assess blast radius -- what else is affected?\n"
                f"2. Define what 'fixed' looks like (measurable criteria)\n"
            ),
            "plan": (
                f"This is a PAIN SIGNAL that needs a remediation plan.\n\n"
                f"{self.task_content}\n\n"
                f"Plan the FIX. Create steps to:\n"
                f"1. Identify the specific corrective action\n"
                f"2. Determine if it can be automated or needs manual intervention\n"
            ),
            "execute": (
                f"This is a PAIN SIGNAL -- execute the fix.\n\n"
                f"{self.task_content}\n\n"
                f"Execute the remediation. Create steps to:\n"
                f"1. Apply the fix (re-spawn manager, retry step, adjust config, etc.)\n"
                f"2. Verify the fix took effect\n"
            ),
            "verify": (
                f"This is a PAIN SIGNAL -- verify the fix worked.\n\n"
                f"{self.task_content}\n\n"
                f"Verify the problem is resolved. Create steps to:\n"
                f"1. Check that the original condition no longer exists\n"
                f"2. Confirm no new problems were introduced\n"
            ),
        }

        base = prompts.get(self.phase, prompts["execute"])
        return (
            base
            + f"\nKeep it focused -- 1-2 steps max. This is diagnostics, not a project.\n\n"
            f"Respond in this JSON format:\n"
            f'{{"steps": [{{"description": "...", "instructions": "...", "success_criteria": ["...", "..."]}}]}}'
        )

    # -- Core Manager Operations --

    def create_step(
        self,
        step_number: int,
        description: str,
        instructions: str,
        success_criteria: list[str],
        context: str = "",
    ) -> Path:
        """Create a step file in the pending/ folder."""
        pending_dir = self.phase_dir / "workers" / "steps" / "pending"
        pending_dir.mkdir(parents=True, exist_ok=True)

        step_name = f"step-{self.task_id}-{step_number:02d}.md"
        step_path = pending_dir / step_name

        criteria_text = "\n".join(f"- {c}" for c in success_criteria)
        ts = datetime.now(timezone.utc).isoformat()

        content = f"""# Step {step_number}: {description}
Task: {self.task_id}
Phase: {self.phase}
Status: pending
Assigned:
Completed:
Worker-log:

## Instructions
{instructions}

## Success Criteria
{criteria_text}

## Context
{context}

## Output

## Blockers
"""
        step_path.write_text(content, encoding="utf-8")
        self.log("step_created", {
            "step": step_name,
            "description": description,
            "criteria_count": len(success_criteria),
        })
        return step_path

    def write_prediction(self, step_number: int, prediction: str) -> Path:
        """Write a prediction for a step (not shown to workers)."""
        pred_dir = self.phase_dir / "manager" / "predictions"
        pred_dir.mkdir(parents=True, exist_ok=True)

        pred_name = f"step-{self.task_id}-{step_number:02d}.md"
        pred_path = pred_dir / pred_name

        content = f"""# Prediction: Step {step_number} (Task {self.task_id})
Phase: {self.phase}
Written: {datetime.now(timezone.utc).isoformat()}

## Expected Output
{prediction}
"""
        pred_path.write_text(content, encoding="utf-8")
        self.log("prediction_written", {"step": step_number})
        return pred_path

    def spawn_worker(self, step_path: Path) -> dict[str, Any]:
        """Spawn a worker subprocess for a step."""
        cmd = [
            sys.executable, "-m", "src.worker_runner",
            "--phase", self.phase,
            "--step", str(step_path),
            "--root", str(self.config.root),
        ]
        if self.config._project_slug:
            cmd.extend(["--project-slug", self.config._project_slug])
        self.log("worker_spawned", {"step": step_path.name, "cmd": " ".join(cmd)})

        kwargs = {
            "capture_output": True,
            "text": True,
            "timeout": 300,  # 5 minute timeout per step
            "cwd": str(self.config.root),
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(cmd, **kwargs)

        output = {
            "step": step_path.name,
            "returncode": result.returncode,
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
        }
        self.log("worker_completed", output)
        return output

    def review_step(self, step_path: Path, step_number: int) -> dict[str, Any]:
        """Review a completed step against prediction and criteria.

        Returns a dict with: met_criteria, prediction_match, score, notes.
        """
        step_text = step_path.read_text(encoding="utf-8")
        output = self._extract_section(step_text, "Output")
        criteria = self._extract_section(step_text, "Success Criteria")
        blockers = self._extract_section(step_text, "Blockers")

        # Load prediction
        pred_path = self.phase_dir / "manager" / "predictions" / f"step-{self.task_id}-{step_number:02d}.md"
        prediction = ""
        if pred_path.exists():
            pred_text = pred_path.read_text(encoding="utf-8")
            prediction = self._extract_section(pred_text, "Expected Output")

        # Use LLM to evaluate
        review_prompt = f"""Review this worker output:

## Success Criteria
{criteria}

## Prediction (what I expected)
{prediction}

## Actual Output
{output}

## Blockers
{blockers}

Evaluate:
1. Did the output meet the success criteria? (yes/partial/no)
2. How does it compare to the prediction? (exceeded/met/fell-short)
3. If fell short, is it worker execution or was my criteria unreasonable?

Respond in this exact JSON format:
{{"met_criteria": "yes|partial|no", "prediction_match": "exceeded|met|fell-short", "diagnosis": "worker|manager|na", "notes": "brief explanation"}}"""

        messages = [{"role": "user", "content": review_prompt}]
        response = self.send_message(messages)
        response_text = ""
        for block in response.content:
            if block.type == "text":
                response_text = block.text
                break

        # Parse JSON from response
        try:
            # Find JSON in the response
            start = response_text.index("{")
            end = response_text.rindex("}") + 1
            review = json.loads(response_text[start:end])
        except (ValueError, json.JSONDecodeError):
            review = {
                "met_criteria": "no",
                "prediction_match": "fell-short",
                "diagnosis": "na",
                "notes": f"Could not parse review response: {response_text[:200]}",
            }

        self.log("step_reviewed", {
            "step": step_number,
            "review": review,
        })
        return review

    def score_prediction(self, review: dict) -> int:
        """Calculate dopamine/cortisol score from prediction error."""
        match = review.get("prediction_match", "met")
        criteria = review.get("met_criteria", "no")
        diagnosis = review.get("diagnosis", "na")

        if match == "exceeded" and criteria in ("yes", "partial"):
            return 3  # big dopamine
        elif match == "met" and criteria == "yes":
            return 1  # small dopamine
        elif match == "fell-short":
            if diagnosis == "worker":
                return -2  # worker failed
            elif diagnosis == "manager":
                return -1  # manager miscalibrated
            else:
                return -1
        return 0

    def write_journal_entry(
        self,
        decisions: list[str],
        worker_results: list[dict],
        memories_consulted: list[str],
        rules_loaded: list[str],
        lessons: list[str],
    ):
        """Append a journal entry for this task."""
        journal = self.phase_dir / "manager" / "journal.md"
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        decisions_text = "\n".join(f"- {d}" for d in decisions)
        workers_text = ""
        for wr in worker_results:
            workers_text += (
                f"- Step {wr.get('step', '?')}: {wr.get('description', '')}\n"
                f"  Criteria met: {wr.get('met_criteria', '?')} | "
                f"Prediction: {wr.get('prediction_match', '?')} | "
                f"Score: {wr.get('score', 0):+d}\n"
            )
        mems_text = "\n".join(f"- {m}" for m in memories_consulted) or "- none"
        rules_text = "\n".join(f"- {r}" for r in rules_loaded) or "- none"
        lessons_text = "\n".join(f"- {l}" for l in lessons) or "- none"

        entry = f"""
## Task {self.task_id}: ({date})

### Decisions
{decisions_text}

### Worker Performance
{workers_text}

### Memories Consulted
{mems_text}

### Rules Loaded
{rules_text}

### Lessons
{lessons_text}
"""
        with open(journal, "a", encoding="utf-8") as f:
            f.write(entry)

        self.log("journal_entry", {"task_id": self.task_id})

    def update_stats(self, review_results: list[dict]):
        """Update stats.yaml with task results."""
        import yaml
        stats_path = self.phase_dir / "manager" / "stats.yaml"
        stats = {}
        if stats_path.exists():
            with open(stats_path) as f:
                stats = yaml.safe_load(f) or {}

        stats["tasks_processed"] = stats.get("tasks_processed", 0) + 1

        outcomes = stats.setdefault("outcomes", {})
        all_met = all(r.get("met_criteria") == "yes" for r in review_results)
        any_met = any(r.get("met_criteria") in ("yes", "partial") for r in review_results)
        if all_met:
            outcomes["success"] = outcomes.get("success", 0) + 1
        elif any_met:
            outcomes["partial"] = outcomes.get("partial", 0) + 1
        else:
            outcomes["failure"] = outcomes.get("failure", 0) + 1

        # Prediction accuracy
        pa = stats.setdefault("prediction_accuracy", {})
        for r in review_results:
            pa["total_reviewed"] = pa.get("total_reviewed", 0) + 1
            pm = r.get("prediction_match", "met")
            if pm == "met":
                pa["met_expectations"] = pa.get("met_expectations", 0) + 1
            elif pm == "exceeded":
                pa["exceeded"] = pa.get("exceeded", 0) + 1
            elif pm == "fell-short":
                pa["fell_short"] = pa.get("fell_short", 0) + 1

        total = pa.get("total_reviewed", 0)
        if total > 0:
            pa["accuracy_rate"] = round(pa.get("met_expectations", 0) / total, 3)

        with open(stats_path, "w") as f:
            yaml.dump(stats, f, default_flow_style=False)

        self.log("stats_updated", {"stats_path": str(stats_path)})

    def move_task_to_next_phase(self):
        """Move the task file to the next phase folder."""
        phases = self.config.pipeline_phases
        try:
            idx = phases.index(self.phase)
        except ValueError:
            # If phase not found, try full phases list
            phases = self.config.phases
            idx = phases.index(self.phase)

        if idx + 1 < len(phases):
            next_phase = phases[idx + 1]
            next_dir = self.config.phase_dir(next_phase)
        else:
            # Last processing phase -> output
            next_dir = self.config.phase_dir("output")

        next_dir.mkdir(parents=True, exist_ok=True)
        dest = next_dir / self.task_path.name
        try:
            if not self.task_path.exists():
                self.log("error", {
                    "phase": "move_task",
                    "error": f"Task file missing: {self.task_path}",
                })
                return
            shutil.move(str(self.task_path), str(dest))
            self.task_path = dest
            self.log("task_moved", {"to": str(next_dir), "phase": self.phase})
        except Exception as e:
            self.log("error", {
                "phase": "move_task",
                "error": str(e),
                "src": str(self.task_path),
                "dest": str(dest),
            })
            self.flag_pain_signal("task-move-failed", f"Could not move {self.task_path.name}: {e}")

    def flag_pain_signal(self, signal_type: str, description: str):
        """Create a pain file in the project's input/ dir.

        Pain flows through the normal pipeline with diagnostic prompts.
        Same happiness contract as Monitor.flag_pain_signal.
        """
        severity = self.config.pain_severity(signal_type)

        # Pain enters the pipeline normally via input/
        project_dir = self.task_path.parent.parent
        input_dir = project_dir / "input"
        input_dir.mkdir(parents=True, exist_ok=True)

        # No dedup -- pain compounds. Repeated failures stack pain files,
        # dropping happiness further until urgency forces resolution.

        # Find next pain ID
        max_id = 0
        for phase_dir in project_dir.iterdir():
            if not phase_dir.is_dir():
                continue
            for f in phase_dir.glob("pain-*.md"):
                try:
                    num = int(f.stem.split("-")[1])
                    max_id = max(max_id, num)
                except (IndexError, ValueError):
                    continue
        pain_id = max_id + 1

        ts = datetime.now(timezone.utc).isoformat()
        pain_name = f"pain-{pain_id:04d}.md"
        pain_path = input_dir / pain_name
        slug = project_dir.name

        content = f"""# Pain {pain_id:04d}: {signal_type}
Created: {ts}
Source: {self.phase} manager
Project: {slug}
Task: {self.task_id}
Type: {signal_type}
Severity: {severity}

## Description
{description}

## Resolution Required
Fix the root cause and provide evidence. Severity: {severity}.
Reward on verified fix: +{severity * 1.5:.1f} happiness.
"""
        pain_path.write_text(content, encoding="utf-8")

        # Drop happiness
        try:
            import yaml
            state_path = self.config.ego_dir() / "state.yaml"
            if state_path.exists():
                with open(state_path) as f:
                    state = yaml.safe_load(f) or {}
            else:
                state = {"happiness": 70.0}

            old = state.get("happiness", 70.0)
            state["happiness"] = max(0, old - severity)
            state["last_updated"] = datetime.now(timezone.utc).isoformat()

            with open(state_path, "w") as f:
                yaml.dump(state, f, default_flow_style=False)
        except Exception:
            pass

        self.log("pain_signal", {
            "type": signal_type,
            "task": self.task_id,
            "description": description,
            "severity": severity,
            "pain": pain_name,
        })

    def run(self, **kwargs) -> dict[str, Any]:
        """Process a task through this phase.

        Override in phase-specific managers to customize step creation
        and review logic. Default implementation uses LLM to break
        the task into steps, then processes each one.
        """
        try:
            return self._run_inner(**kwargs)
        except Exception as e:
            self.log("error", {
                "phase": self.phase,
                "task_id": self.task_id,
                "error": str(e),
                "traceback": traceback.format_exc(),
            })
            self.flag_pain_signal("manager-crashed", f"{self.phase} manager crashed on task {self.task_id}: {e}")
            return {"error": str(e), "task_id": self.task_id, "phase": self.phase}
        finally:
            self.close_log()

    def _run_inner(self, **kwargs) -> dict[str, Any]:
        """Inner run logic, wrapped by run() for error handling."""
        self.log("system", self.system_prompt)
        self.log("task_start", {"task_id": self.task_id, "phase": self.phase})

        # Pain files get diagnostic prompts; regular tasks get implementation prompts
        if self.is_pain_task:
            plan_prompt = self._build_pain_prompt()
        else:
            plan_prompt = f"""Here is the task to process in the {self.phase} phase:

{self.task_content}

Break this into concrete steps. For each step, provide:
1. A short description
2. Detailed instructions for the worker
3. Measurable success criteria (2-4 criteria per step)

Respond in this JSON format:
{{"steps": [{{"description": "...", "instructions": "...", "success_criteria": ["...", "..."]}}]}}"""

        messages = [{"role": "user", "content": plan_prompt}]
        response = self.send_message(messages)

        # Parse steps from LLM response
        response_text = ""
        for block in response.content:
            if block.type == "text":
                response_text = block.text
                break

        steps = self._parse_steps(response_text)
        if not steps:
            self.flag_pain_signal("no-steps", f"Could not break task {self.task_id} into steps")
            return {"error": "Failed to create steps", "task_id": self.task_id}

        # Create steps and predictions
        step_paths = []
        review_results = []
        decisions = [f"Broke task into {len(steps)} steps"]

        for i, step in enumerate(steps, 1):
            # Create step file
            path = self.create_step(
                step_number=i,
                description=step["description"],
                instructions=step["instructions"],
                success_criteria=step["success_criteria"],
                context=f"Task {self.task_id}: {self.task_content[:500]}",
            )
            step_paths.append(path)

            # Write prediction
            try:
                pred_prompt = f"""Based on these instructions and criteria, predict what good output looks like:

Instructions: {step['instructions']}
Criteria: {', '.join(step['success_criteria'])}

Write a brief prediction (2-3 sentences) of what the worker will produce."""

                pred_msgs = [{"role": "user", "content": pred_prompt}]
                pred_response = self.send_message(pred_msgs)
                pred_text = ""
                for block in pred_response.content:
                    if block.type == "text":
                        pred_text = block.text
                        break
                self.write_prediction(i, pred_text)
            except Exception as e:
                self.log("error", {"phase": "prediction", "step": i, "error": str(e)})
                self.write_prediction(i, f"(prediction failed: {e})")

            # Spawn worker
            try:
                self.spawn_worker(path)
            except Exception as e:
                self.flag_pain_signal("worker-failed", f"Step {i} worker failed: {e}")
                continue

            # Find completed step file
            completed_path = (
                self.phase_dir / "workers" / "steps" / "completed" / path.name
            )
            if completed_path.exists():
                try:
                    review = self.review_step(completed_path, i)
                except Exception as e:
                    self.log("error", {"phase": "review_step", "step": i, "error": str(e)})
                    review = {
                        "met_criteria": "no",
                        "prediction_match": "fell-short",
                        "diagnosis": "na",
                        "notes": f"Review failed: {e}",
                    }
                score = self.score_prediction(review)
                review["step"] = i
                review["description"] = step["description"]
                review["score"] = score
                review_results.append(review)
            else:
                review_results.append({
                    "step": i,
                    "description": step["description"],
                    "met_criteria": "no",
                    "prediction_match": "fell-short",
                    "score": -2,
                    "notes": "Step file not found in completed/",
                })

        # Synthesize results into task file
        self._synthesize_results(review_results)

        # Write journal
        self.write_journal_entry(
            decisions=decisions,
            worker_results=review_results,
            memories_consulted=[],
            rules_loaded=[r["id"] for r in self.matched_rules],
            lessons=self._extract_lessons(review_results),
        )

        # Update stats
        self.update_stats(review_results)

        # Move task to next phase
        self.move_task_to_next_phase()

        return {
            "task_id": self.task_id,
            "phase": self.phase,
            "steps": len(steps),
            "reviews": review_results,
        }

    def _parse_steps(self, response_text: str) -> list[dict]:
        """Parse step definitions from LLM response."""
        try:
            start = response_text.index("{")
            end = response_text.rindex("}") + 1
            data = json.loads(response_text[start:end])
            return data.get("steps", [])
        except (ValueError, json.JSONDecodeError):
            return []

    def _synthesize_results(self, reviews: list[dict]):
        """Write phase results back to the task file."""
        text = self.task_path.read_text(encoding="utf-8")
        results_text = f"\n## {self.phase.title()}\n"
        results_text += f"Processed by {self.phase} manager on {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
        for r in reviews:
            results_text += (
                f"- Step {r.get('step', '?')}: {r.get('description', '')}\n"
                f"  Criteria: {r.get('met_criteria', '?')} | "
                f"Prediction: {r.get('prediction_match', '?')}\n"
            )
        text += results_text
        self.task_path.write_text(text, encoding="utf-8")

    def _extract_lessons(self, reviews: list[dict]) -> list[str]:
        """Extract lessons from review results."""
        lessons = []
        for r in reviews:
            if r.get("prediction_match") == "exceeded":
                lessons.append(f"(positive) Step {r['step']} exceeded expectations: {r.get('notes', '')}")
            elif r.get("met_criteria") == "no":
                lessons.append(f"(negative) Step {r['step']} failed: {r.get('notes', '')}")
            elif r.get("prediction_match") == "met":
                lessons.append(f"(neutral) Step {r['step']} met expectations")
        return lessons

    @staticmethod
    def _extract_section(text: str, section: str) -> str:
        """Extract content under a ## heading.

        Uses the LAST occurrence of the section header to handle cases
        where the worker's output contains duplicate markdown headers.
        """
        marker = f"## {section}"
        if marker not in text:
            return ""
        # Use last occurrence to skip duplicates from worker output
        idx = text.rindex(marker) + len(marker)
        rest = text[idx:]
        # Find next section that isn't a subsection (### is ok)
        import re
        m = re.search(r'\n## (?!#)', rest)
        if m is None:
            return rest.strip()
        return rest[:m.start()].strip()
