"""Base agent class for Neural Pipeline.

All agents (ego, managers, workers, monitor) inherit from this.
Provides: SDK client init, JSONL conversation logging, tool execution,
and a run() method that subclasses override.
"""
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic

from .config import Config
from .credentials import get_api_key


class AgentBase:
    """Common base for all pipeline agents."""

    def __init__(
        self,
        role: str,
        log_dir: Path,
        config: Config | None = None,
        system_prompt: str = "",
        tools: list[dict] | None = None,
    ):
        self.role = role
        self.config = config or Config()
        self.model = self.config.model_for(role)
        self.max_tokens = self.config.max_tokens_for(role)
        self.system_prompt = system_prompt
        self.tools = tools or []

        # Logging
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        self.log_path = self.log_dir / f"{ts}-{role}.jsonl"
        self._log_file = None

        # SDK client -- lazy init so we don't need a key for unit tests
        self._client: anthropic.Anthropic | None = None

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            api_key = get_api_key(self.config.credential_key)

            # Set env vars required by the proxy
            for k, v in self.config.env_vars.items():
                os.environ[k] = v

            # Set ANTHROPIC_AUTH_TOKEN (same key, needed by TrendMicro proxy)
            os.environ["ANTHROPIC_AUTH_TOKEN"] = api_key

            kwargs: dict[str, Any] = {"api_key": api_key}
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url

            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    # -- JSONL Logging --

    def _open_log(self):
        if self._log_file is None:
            self._log_file = open(self.log_path, "a", encoding="utf-8")

    def log(self, entry_type: str, content: Any, **extra):
        """Append one JSONL line to the conversation log."""
        self._open_log()
        record = {
            "type": entry_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content": content,
        }
        record.update(extra)
        self._log_file.write(json.dumps(record, default=str) + "\n")
        self._log_file.flush()

    def close_log(self):
        if self._log_file:
            self._log_file.close()
            self._log_file = None

    def move_log_to_archive(self, archive_dir: Path):
        """Move the log file from active/ to archive/."""
        self.close_log()
        archive_dir.mkdir(parents=True, exist_ok=True)
        if self.log_path.exists():
            shutil.move(str(self.log_path), str(archive_dir / self.log_path.name))

    # -- SDK Calls --

    def send_message(
        self,
        messages: list[dict],
        system: str | None = None,
        tools: list[dict] | None = None,
    ) -> anthropic.types.Message:
        """Send a message to the Claude API and log the exchange."""
        sys_prompt = system or self.system_prompt
        use_tools = tools if tools is not None else self.tools

        self.log("user", messages[-1].get("content", ""))

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if sys_prompt:
            kwargs["system"] = sys_prompt
        if use_tools:
            kwargs["tools"] = use_tools

        response = self.client.messages.create(**kwargs)

        # Log assistant response
        self.log(
            "assistant",
            _extract_text(response),
            tool_calls=_extract_tool_calls(response),
            stop_reason=response.stop_reason,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        )
        return response

    # -- Tool Execution --

    def execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool call and return the result string.

        Subclasses override this to add phase-specific tool handlers.
        Base implementation provides filesystem tools.
        """
        from .tools import execute_tool
        result = execute_tool(tool_name, tool_input, project_root=self.config.root)
        self.log("tool_result", result, tool=tool_name)
        return result

    def run_agentic_loop(
        self,
        initial_messages: list[dict],
        max_turns: int = 20,
    ) -> list[dict]:
        """Run an agentic tool-use loop until the model stops calling tools.

        Returns the full message history.
        """
        messages = list(initial_messages)

        for _ in range(max_turns):
            response = self.send_message(messages)

            # Build assistant message from response content blocks
            assistant_content = []
            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason != "tool_use":
                break

            # Execute tool calls and build tool results
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    try:
                        result = self.execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                    except Exception as e:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Error: {e}",
                            "is_error": True,
                        })

            messages.append({"role": "user", "content": tool_results})

        return messages

    # -- Lifecycle --

    def run(self, **kwargs) -> Any:
        """Override in subclasses. Main entry point for agent execution."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement run()")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close_log()


def _extract_text(response: anthropic.types.Message) -> str:
    """Pull text content from a response."""
    parts = []
    for block in response.content:
        if block.type == "text":
            parts.append(block.text)
    return "\n".join(parts)


def _extract_tool_calls(response: anthropic.types.Message) -> list[dict]:
    """Pull tool call info from a response."""
    calls = []
    for block in response.content:
        if block.type == "tool_use":
            calls.append({"name": block.name, "input": block.input, "id": block.id})
    return calls
