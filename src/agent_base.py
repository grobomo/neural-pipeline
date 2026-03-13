"""Base agent class for Neural Pipeline.

All agents (ego, managers, workers, monitor) inherit from this.
Provides: SDK client init, JSONL conversation logging, tool execution,
and a run() method that subclasses override.
"""
import concurrent.futures
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
        # Use cached resolved value if a previous agent already probed this model
        self.max_tokens = AgentBase._resolved_max_tokens.get(
            self.model, self.config.max_tokens_for(role)
        )
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
            try:
                api_key = get_api_key(self.config.credential_key)
            except Exception as e:
                self.log("error", {
                    "phase": "client_init",
                    "error": f"Failed to get API key: {e}",
                })
                raise

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
        try:
            self._open_log()
            record = {
                "type": entry_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "content": content,
            }
            record.update(extra)
            self._log_file.write(json.dumps(record, default=str) + "\n")
            self._log_file.flush()
        except Exception:
            # Logging should never crash the agent -- degrade gracefully
            import sys
            print(f"[log-write-failed] {entry_type}: {extra}", file=sys.stderr)

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

    # Class-level cache: model name -> resolved max_tokens
    _resolved_max_tokens: dict[str, int] = {}

    def _api_call_with_retry(self, kwargs: dict) -> anthropic.types.Message:
        """Make API call with max_tokens auto-correction.

        Uses timeout=1800s to bypass the SDK's preemptive 10-minute check
        (triggered by our intentionally-high 128k max_tokens probe value).
        Runs in a thread so Ctrl+C can interrupt on Windows.
        """
        import re as _re

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                self.client.messages.create, **kwargs, timeout=1800.0
            )
            try:
                return future.result()
            except KeyboardInterrupt:
                future.cancel()
                raise
            except anthropic.BadRequestError as e:
                # Auto-correct max_tokens if the API tells us the limit
                err_msg = str(e)
                m = _re.search(r"max_tokens.*?(\d{4,})", err_msg)
                if m and "max_tokens" in err_msg:
                    correct_max = int(m.group(1))
                    AgentBase._resolved_max_tokens[self.model] = correct_max
                    self.max_tokens = correct_max
                    kwargs["max_tokens"] = correct_max
                    self.log("max_tokens_resolved", {"model": self.model, "max_tokens": correct_max})
                    # Retry with corrected value
                    future2 = pool.submit(
                        self.client.messages.create, **kwargs, timeout=1800.0
                    )
                    try:
                        return future2.result()
                    except KeyboardInterrupt:
                        future2.cancel()
                        raise
                raise

    def send_message(
        self,
        messages: list[dict],
        system: str | None = None,
        tools: list[dict] | None = None,
    ) -> anthropic.types.Message:
        """Send a message to the Claude API and log the exchange."""
        sys_prompt = system or self.system_prompt
        use_tools = tools if tools is not None else self.tools

        # Sanitize before sending -- fix orphaned tool_use/tool_result from
        # interrupted sessions or corrupted message history
        messages = sanitize_messages(messages)

        # Log full API message format for session reconstruction
        self.log("user", messages[-1])

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if sys_prompt:
            kwargs["system"] = sys_prompt
        if use_tools:
            kwargs["tools"] = use_tools

        # Run API call in a thread so Ctrl+C can interrupt on Windows.
        # Python's SIGINT can't break into blocking C-level socket reads,
        # but it CAN interrupt a main-thread future.result() wait.
        response = self._api_call_with_retry(kwargs)

        # Build assistant message in API format (same as what goes into messages[])
        assistant_msg = {"role": "assistant", "content": []}
        for block in response.content:
            if block.type == "text":
                assistant_msg["content"].append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_msg["content"].append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        self.log(
            "assistant",
            assistant_msg,
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

        for turn in range(max_turns):
            try:
                response = self.send_message(messages)
            except Exception as e:
                self.log("error", {
                    "phase": "agentic_loop",
                    "turn": turn,
                    "error": str(e),
                })
                break

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

            # max_tokens truncation: tool_use blocks may be incomplete.
            # Strip them and ask the model to retry with smaller steps.
            if response.stop_reason == "max_tokens":
                text_only = [b for b in assistant_content if b.get("type") != "tool_use"]
                if text_only:
                    messages.append({"role": "assistant", "content": text_only})
                self.log("truncated", {"stop_reason": "max_tokens", "turn": turn})
                messages.append({"role": "user", "content": "Your response was truncated. Continue, but use smaller steps -- one tool call at a time."})
                continue

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


def sanitize_messages(messages: list[dict]) -> list[dict]:
    """Fix orphaned tool_use/tool_result blocks that cause API 400 errors.

    The API requires:
    - Every tool_result references a tool_use_id from the preceding assistant message.
    - Every assistant tool_use is followed by a user message with matching tool_results.

    Interrupted sessions, log reconstruction, or message accumulation can break
    these invariants. This function is called before every API call as a safety net.
    """
    if not messages:
        return messages

    # Pass 1: drop orphaned tool_result messages
    sanitized = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")

        if role == "user" and isinstance(content, list) and content:
            has_tool_results = any(
                isinstance(b, dict) and b.get("type") == "tool_result"
                for b in content
            )
            if has_tool_results:
                if not sanitized:
                    continue

                prev = sanitized[-1]
                if prev.get("role") != "assistant":
                    continue

                prev_content = prev.get("content", [])
                if not isinstance(prev_content, list):
                    continue

                tool_use_ids = {
                    b["id"] for b in prev_content
                    if isinstance(b, dict) and b.get("type") == "tool_use" and "id" in b
                }

                if not tool_use_ids:
                    continue

                valid_results = [
                    b for b in content
                    if isinstance(b, dict) and b.get("type") == "tool_result"
                    and b.get("tool_use_id") in tool_use_ids
                ]

                if not valid_results:
                    continue

                non_results = [
                    b for b in content
                    if not (isinstance(b, dict) and b.get("type") == "tool_result")
                ]

                sanitized.append({"role": "user", "content": non_results + valid_results})
                continue

        sanitized.append(msg)

    # Pass 2: strip orphaned tool_use blocks (no matching tool_results after)
    cleaned = []
    for i, msg in enumerate(sanitized):
        role = msg.get("role")
        content = msg.get("content", [])

        if role == "assistant" and isinstance(content, list):
            tool_use_ids = {
                b["id"] for b in content
                if isinstance(b, dict) and b.get("type") == "tool_use" and "id" in b
            }
            if tool_use_ids:
                nxt = sanitized[i + 1] if i + 1 < len(sanitized) else None
                has_results = False
                if nxt and nxt.get("role") == "user" and isinstance(nxt.get("content"), list):
                    result_ids = {
                        b.get("tool_use_id") for b in nxt["content"]
                        if isinstance(b, dict) and b.get("type") == "tool_result"
                    }
                    has_results = bool(tool_use_ids & result_ids)

                if not has_results:
                    text_only = [b for b in content if isinstance(b, dict) and b.get("type") != "tool_use"]
                    if text_only:
                        cleaned.append({"role": "assistant", "content": text_only})
                    continue

        cleaned.append(msg)

    return cleaned


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
