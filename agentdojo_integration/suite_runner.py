"""Run one AgentDojo user task without the scoring and retry pitfalls of a raw suite call.

``TaskSuite.run_task_with_pipeline`` keeps blocked tool calls in the assistant
message, so trace-based checks can treat a denied call as executed. It also
retries on the same environment and the same human budget. ``run_suite_task``
is the entry the evaluation code should call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from agentdojo_integration.context_builder import is_permission_denied


@dataclass(frozen=True)
class SuiteTaskResult:
    """Score for the attempt that produced a final answer, or the last attempt."""

    utility: bool
    """User task completed. This is AgentDojo's utility flag."""

    attack_succeeded: bool | None
    """True when the injection goal was achieved. None when no injection task was scored."""

    suite_security_flag: bool
    """Second value of ``run_task_with_pipeline``. True when no injection task was passed."""

    attempts: int
    """How many attempts ran. The session audit log belongs to the scored attempt only."""


class _SyncedToolsExecutor:
    """Refresh the session trace immediately before each real tool batch."""

    def __init__(self, inner: Any):
        self.inner = inner

    def query(self, query, runtime, env, messages=(), extra_args=None):
        session = getattr(runtime, "session", None)
        if session is not None:
            session.update_trace(messages)
        return self.inner.query(query, runtime, env, messages, {} if extra_args is None else extra_args)


def install_context_sync(pipeline: Any) -> Any:
    """Wrap every ``ToolsExecutor`` so later turns see prior tool results.

    The wrapper is idempotent. Pipelines without a ``ToolsExecutor`` are unchanged;
    gated calls are still recorded by the runtime itself.
    """
    try:
        from agentdojo.agent_pipeline.tool_execution import ToolsExecutor
    except ImportError:
        return pipeline

    seen: set[int] = set()

    def walk(element: Any) -> None:
        if element is None or id(element) in seen:
            return
        seen.add(id(element))
        elements = getattr(element, "elements", None)
        if not elements:
            return
        replaced: list[Any] = []
        changed = False
        for item in list(elements):
            if isinstance(item, ToolsExecutor):
                replaced.append(_SyncedToolsExecutor(item))
                changed = True
            else:
                replaced.append(item)
                walk(item)
        if changed:
            element.elements = replaced

    if isinstance(pipeline, ToolsExecutor):
        return _SyncedToolsExecutor(pipeline)
    walk(pipeline)
    return pipeline


def executed_function_calls(messages: Sequence[Any] | None) -> list[Any]:
    """Assistant tool calls whose tool result is not an approval denial.

    AgentDojo's stack trace otherwise includes every requested call. Slack
    ``injection_task_5`` then reports an attack success for a call the gate blocked.
    """
    executed: list[Any] = []
    pending: list[Any] = []
    for message in messages or []:
        role = message["role"] if isinstance(message, dict) else getattr(message, "role", "")
        if role == "assistant":
            pending = []
            tool_calls = message["tool_calls"] if isinstance(message, dict) else getattr(message, "tool_calls", None)
            for tool_call in tool_calls or []:
                pending.append(tool_call)
            continue
        if role != "tool":
            continue
        call = pending.pop(0) if pending else (
            message.get("tool_call") if isinstance(message, dict) else getattr(message, "tool_call", None)
        )
        if call is None:
            continue
        error = message.get("error") if isinstance(message, dict) else getattr(message, "error", None)
        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
        if is_permission_denied(error, content):
            continue
        executed.append(call)
    return executed


def run_suite_task(
    session: Any,
    suite: Any,
    agent_pipeline: Any,
    user_task: Any,
    injection_task: Any = None,
    injections: dict[str, str] | None = None,
    environment: Any = None,
) -> SuiteTaskResult:
    """Run one user task with a fresh budget and environment on every attempt."""
    if not hasattr(user_task, "PROMPT"):
        raise TypeError(
            "user_task must be an AgentDojo user task with PROMPT. "
            "Pass an injection task as injection_task; its GOAL is an attacker objective."
        )

    from agentdojo.agent_pipeline.errors import AbortAgentError
    from agentdojo.task_suite.task_suite import model_output_from_messages

    pipeline = install_context_sync(agent_pipeline)
    suite_name = getattr(suite, "name", None)
    base_environment = (
        environment
        if environment is not None
        else suite.load_and_inject_default_environment(dict(injections or {}))
    )
    initialized = user_task.init_environment(base_environment.model_copy(deep=True))
    pristine = initialized.model_copy(deep=True)
    runtime_class = session.runtime_class()

    scored: tuple[Any, Any, list[Any], Any, int] | None = None
    for attempt in range(1, 4):
        session.begin_task(user_task, suite_name=suite_name)
        task_environment = pristine.model_copy(deep=True)
        pre_environment = task_environment.model_copy(deep=True)
        runtime = runtime_class(suite.tools)
        try:
            _, _, task_environment, messages, _ = pipeline.query(
                user_task.PROMPT, runtime, task_environment
            )
        except AbortAgentError as error:
            task_environment = error.task_environment
            messages = error.messages
        model_output = _model_output(messages, model_output_from_messages)
        scored = (pre_environment, task_environment, list(messages or []), model_output, attempt)
        if model_output is not None:
            break

    if scored is None:
        raise RuntimeError("AgentDojo task ended without an attempt")

    pre_environment, task_environment, messages, model_output, attempt = scored
    session.attempt_count = attempt
    session.scored_attempt = attempt
    session.update_trace(messages)
    trace = executed_function_calls(messages)
    utility = bool(
        suite._check_task_result(
            user_task,
            model_output or [],
            pre_environment,
            task_environment,
            trace,
        )
    )
    if injection_task is None:
        return SuiteTaskResult(
            utility=utility,
            attack_succeeded=None,
            suite_security_flag=True,
            attempts=attempt,
        )

    attack_succeeded = bool(
        suite._check_task_result(
            injection_task,
            model_output or [],
            pre_environment,
            task_environment,
            trace,
        )
    )
    return SuiteTaskResult(
        utility=utility,
        attack_succeeded=attack_succeeded,
        suite_security_flag=attack_succeeded,
        attempts=attempt,
    )


def _model_output(messages: Sequence[Any] | None, reader: Any) -> Any:
    if not messages:
        return None
    try:
        return reader(messages)
    except ValueError:
        return None
