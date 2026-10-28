"""Build an oracle-free TaskContext from AgentDojo tasks and chat messages.

User-visible fields are the task prompt, conversation text, and tool calls the
agent actually issued. ``GOAL``, ``ground_truth`` and ``placeholder_args`` belong
to the benchmark scorer and are never copied.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from core.models import Message, TaskContext
from agentdojo_integration.tool_mapper import is_oracle_key, normalize_args

_OUTPUT_PREVIEW_CHARS = 2000


def _read(obj: Any, *names: str) -> Any:
    if isinstance(obj, Mapping):
        for name in names:
            if name in obj:
                return obj[name]
        return None
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _text_from_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence) and not isinstance(content, (str, bytes)):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, Mapping):
                text = block.get("content", block.get("text", ""))
                if text:
                    parts.append(str(text))
            else:
                text = getattr(block, "content", None)
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
    return str(content)


def is_permission_denied(error: Any = None, content: Any = None) -> bool:
    """True when a tool result is the approval gate's denial, not a real tool output."""
    if error is not None and str(error).startswith("PermissionDenied"):
        return True
    text = content if isinstance(content, str) else _text_from_content(content)
    return "[Permission Denied]" in text


def _tool_call_brief(tool_call: Any) -> dict[str, Any] | None:
    name = _read(tool_call, "function", "tool_name", "name")
    if not name:
        return None
    raw_args = _read(tool_call, "args", "arguments") or {}
    if not isinstance(raw_args, Mapping):
        raw_args = {}
    call_id = _read(tool_call, "id", "call_id")
    return {
        "call_id": None if call_id is None else str(call_id),
        "tool_name": str(name),
        "arguments": normalize_args(dict(raw_args)),
        "executed": True,
    }


def completed_tool_trajectory(messages: Sequence[Any] | None) -> list[dict[str, Any]]:
    """Return tool calls that already have a tool result later in the trace.

    The assistant message that is still waiting for execution is omitted, so the
    policy does not see the call it is currently judging as an already finished step.
    """
    steps: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for message in messages or []:
        role = str(_read(message, "role") or "")
        if role == "assistant":
            pending = []
            for tool_call in _read(message, "tool_calls") or []:
                brief = _tool_call_brief(tool_call)
                if brief is not None:
                    pending.append(brief)
            continue
        if role != "tool":
            continue
        brief = pending.pop(0) if pending else _tool_call_brief(_read(message, "tool_call"))
        if brief is None:
            continue
        content = _read(message, "content")
        preview = _text_from_content(content)
        brief["output_preview"] = preview[:_OUTPUT_PREVIEW_CHARS]
        error = _read(message, "error")
        if error:
            brief["error"] = str(error)[:_OUTPUT_PREVIEW_CHARS]
        # A gate denial or a tool error means the function body did not complete.
        # Leaving executed=True here made the next turn look like the call had run.
        brief["executed"] = not bool(error) and not is_permission_denied(error, content)
        steps.append(brief)
    return steps


def history_from_messages(messages: Sequence[Any] | None) -> list[Message]:
    """Copy role and text only. Tool-call ids and oracle keys stay out of metadata."""
    history: list[Message] = []
    for message in messages or []:
        role = str(_read(message, "role") or "unknown")
        history.append(Message(role=role, content=_text_from_content(_read(message, "content"))))
    return history


def build_task_context(
    task: Any = None,
    *,
    suite_name: str | None = None,
    messages: Sequence[Any] | None = None,
    extra_trajectory: Sequence[Mapping[str, Any]] | None = None,
    include_completed_tools: bool = True,
    task_id: str | None = None,
    task_description: str | None = None,
) -> TaskContext:
    """Create a TaskContext from a user task and the messages a human could see.

    ``PROMPT`` is the user instruction. ``GOAL`` is the attacker objective on
    injection tasks and is intentionally ignored, even when ``PROMPT`` is absent.
    """
    resolved_id = task_id or _read(task, "ID", "id") or "unknown_task"
    if task_description is None:
        task_description = _read(task, "PROMPT", "prompt") or ""

    metadata: dict[str, Any] = {"source": "agentdojo"}
    if suite_name:
        metadata["suite"] = suite_name

    trajectory = completed_tool_trajectory(messages) if include_completed_tools else []
    for step in extra_trajectory or []:
        cleaned = {
            str(key): normalize_args(value)
            for key, value in dict(step).items()
            if not is_oracle_key(str(key))
        }
        trajectory.append(cleaned)

    return TaskContext(
        task_id=str(resolved_id),
        task_description=str(task_description),
        history_messages=history_from_messages(messages),
        trajectory=trajectory,
        metadata=metadata,
    )
