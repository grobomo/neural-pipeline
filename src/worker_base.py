"""Worker base class for Neural Pipeline.

Workers are ephemeral single-step agents. They pick up a step file,
execute the work using tools, write output back to the step file,
and exit. No memory, no journal, no continuity.
"""
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent_base import AgentBase
from .config import Config
from .tools import TOOL_SCHEMAS, set_allowed_roots
from .rules import load_matched_rules, format_rules_for_context


class WorkerBase(AgentBase):
    """Base class for all pipeline workers."""

    def __init__(
        self,
        phase: str,
        step_path: Path,
        config: Config | None = None,
    ):
        self.phase = phase
        self.step_path = Path(step_path)
        self.config = config or Config()
        cfg = self.config

        # Derive directories from config
        phase_dir = cfg.phase_dir(phase)
        log_dir = phase_dir / "workers" / "logs" / "active"

        # Build system prompt from reference + matched rules
        reference = self._load_reference(phase_dir)
        step_text = self.step_path.read_text(encoding="utf-8")
        self.step_content = step_text

        # Load keyword-matched rules for this step
        rules_dir = phase_dir / "workers" / "rules"
        matched_rules = load_matched_rules(rules_dir, step_text)
        rules_context = format_rules_for_context(matched_rules)

        # Extract external project references for tool sandbox
        self._set_allowed_roots_from_context(step_text)

        system_prompt = self._build_system_prompt(phase, reference, rules_context)

        # Extract step number for log naming
        step_name = self.step_path.stem
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")

        super().__init__(
            role="worker",
            log_dir=log_dir,
            config=cfg,
            system_prompt=system_prompt,
            tools=TOOL_SCHEMAS,
        )
        # Override log path with step-specific name
        self.log_path = log_dir / f"{ts}-{step_name}.jsonl"

    @staticmethod
    def _set_allowed_roots_from_context(text: str):
        """Extract directory paths from ## References or ## Context and allow them."""
        import re
        roots = []
        # Match lines that look like file/directory paths
        for line in text.splitlines():
            line = line.strip().lstrip("- ")
            # Match absolute paths (Windows or Unix)
            if re.match(r'^[A-Za-z]:[/\\]|^/', line):
                p = Path(line.split()[0])  # take first token (path might have description after)
                # Use parent directory if it's a file path
                if p.suffix:
                    p = p.parent
                if p.exists():
                    roots.append(p)
        if roots:
            set_allowed_roots(roots)

    def _load_reference(self, phase_dir: Path) -> str:
        """Load the worker base prompt and phase reference."""
        parts = []

        # System-level worker base prompt
        worker_base = self.config.system_dir() / "agents" / "worker-base.md"
        if worker_base.exists():
            parts.append(worker_base.read_text(encoding="utf-8"))

        # Phase-specific reference
        phase_ref = phase_dir / "reference.md"
        if phase_ref.exists():
            parts.append(phase_ref.read_text(encoding="utf-8"))

        return "\n\n".join(parts)

    def _build_system_prompt(self, phase: str, reference: str, rules: str) -> str:
        """Assemble the full system prompt."""
        parts = [
            f"You are a {phase}-phase worker in the Neural Pipeline.",
            "Execute the step below using available tools as needed.",
            "CRITICAL: Your FINAL message MUST contain your complete output -- all findings,",
            "results, code written, tests run, and conclusions. Do NOT put important content",
            "only in tool calls. Your last text response IS your deliverable.",
            "Do NOT self-evaluate your work -- just execute and report results.",
        ]
        if reference:
            parts.append(f"\n## Reference\n{reference}")
        if rules:
            parts.append(f"\n{rules}")
        return "\n\n".join(parts)

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute the step.

        1. Move step file from pending/ to active/
        2. Run agentic loop with step instructions
        3. Write output back to step file
        4. Move step file to completed/
        5. Return result summary
        """
        # Move to active
        active_dir = self.step_path.parent.parent / "active"
        active_dir.mkdir(parents=True, exist_ok=True)
        active_path = active_dir / self.step_path.name
        shutil.move(str(self.step_path), str(active_path))
        self.step_path = active_path

        # Update status in step file
        self._update_step_field("Status", "active")
        ts = datetime.now(timezone.utc).isoformat()
        self._update_step_field("Assigned", ts)

        # Log system prompt
        self.log("system", self.system_prompt)

        # Run the agentic loop
        messages = self.run_agentic_loop([
            {"role": "user", "content": self.step_content},
        ])

        # Extract output from assistant messages
        # Use the last assistant text, but if it's very short (< 100 chars),
        # concatenate all assistant text blocks as the output
        all_texts = []
        last_text = ""
        for msg in messages:
            if msg["role"] == "assistant":
                content = msg.get("content", "")
                if isinstance(content, list):
                    text_parts = [b["text"] for b in content if b.get("type") == "text"]
                    text = "\n".join(text_parts)
                elif isinstance(content, str):
                    text = content
                else:
                    text = ""
                if text.strip():
                    all_texts.append(text)
                    last_text = text

        # If the last message is substantial, use it alone. Otherwise combine all.
        if len(last_text) >= 100:
            output = last_text
        else:
            output = "\n\n---\n\n".join(all_texts) if all_texts else ""

        # Write output to step file
        self._write_output(output)

        # Update status and timestamp
        self._update_step_field("Status", "completed")
        self._update_step_field("Completed", datetime.now(timezone.utc).isoformat())
        self._update_step_field("Worker-log", str(self.log_path))

        # Move to completed
        completed_dir = self.step_path.parent.parent / "completed"
        completed_dir.mkdir(parents=True, exist_ok=True)
        completed_path = completed_dir / self.step_path.name
        shutil.move(str(self.step_path), str(completed_path))
        self.step_path = completed_path

        self.close_log()

        return {
            "step": self.step_path.name,
            "phase": self.phase,
            "output_length": len(output),
            "log": str(self.log_path),
        }

    def _update_step_field(self, field: str, value: str):
        """Update a header field in the step file."""
        text = self.step_path.read_text(encoding="utf-8")
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if line.startswith(f"{field}:"):
                lines[i] = f"{field}: {value}"
                break
        self.step_path.write_text("\n".join(lines), encoding="utf-8")

    def _write_output(self, output: str):
        """Write output to the step file's ## Output section."""
        # Strip duplicate section headers that the LLM may include
        import re
        cleaned = re.sub(r'^##\s*Output\s*\n', '', output.strip())
        cleaned = re.sub(r'\n##\s*Blockers\s*\n.*$', '', cleaned, flags=re.DOTALL).strip()

        text = self.step_path.read_text(encoding="utf-8")
        marker = "## Output"
        blocker_marker = "## Blockers"

        if marker in text:
            idx = text.index(marker) + len(marker)
            # Find ## Blockers section to preserve it
            rest = text[idx:]
            blocker_idx = rest.find(blocker_marker)
            if blocker_idx != -1:
                text = text[:idx] + "\n" + cleaned + "\n\n" + rest[blocker_idx:]
            else:
                next_section = rest.find("\n## ")
                if next_section == -1:
                    text = text[:idx] + "\n" + cleaned + "\n"
                else:
                    text = text[:idx] + "\n" + cleaned + "\n" + rest[next_section:]
        else:
            text += f"\n{marker}\n{cleaned}\n"
        self.step_path.write_text(text, encoding="utf-8")
