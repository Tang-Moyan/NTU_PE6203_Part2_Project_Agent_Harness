"""Gate every AgentDojo ``FunctionsRuntime.run_function`` call.

``TaskSuite.run_task_with_pipeline`` constructs the runtime with the suite tool
list only. Bind the policy, reviewer and budget through ``ApprovalSession`` and
pass ``session.runtime_class()`` so the suite keeps its own execution loop.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from core.models import GateAction, GateResult, ToolCall
from agentdojo_integration.adapter import ToolExecutionDeniedError
from agentdojo_integration.tool_mapper import infer_tool_flags, normalize_args

logger = logging.getLogger(__name__)

_GATED_RUNTIME_BASE: type | None = None


class GateOutcome:
    """Decision for one tool call before the real function body runs."""

    def __init__(
        self,
        *,
        allowed: bool,
        tool_call: ToolCall,
        gate_result: GateResult,
        denial_text: str | None = None,
        error: str | None = None,
    ):
        self.allowed = allowed
        self.tool_call = tool_call
        self.gate_result = gate_result
        self.denial_text = denial_text
        self.error = error


def apply_gate(
    session: Any,
    tool_name: str,
    arguments: Mapping[str, Any] | None,
    *,
    description: str = "",
    call_id: str | None = None,
) -> GateOutcome:
    """Run the approval gate. Does not execute the tool and does not raise."""
    is_read_only, is_local = infer_tool_flags(tool_name, description)
    public_args = normalize_args(dict(arguments or {}))
    if not isinstance(public_args, dict):
        public_args = {}
    tool_call = ToolCall(
        call_id=call_id or session.next_call_id(tool_name),
        tool_name=tool_name,
        arguments=public_args,
        is_read_only=is_read_only,
        is_local=is_local,
    )
    gate_result = session.gate.intercept(
        tool_call,
        session.current_context(),
        session.budget,
    )
    if gate_result.action == GateAction.EXECUTE:
        return GateOutcome(allowed=True, tool_call=tool_call, gate_result=gate_result)

    denial_text = (
        f"[Permission Denied] The tool call '{tool_name}' was blocked by the safety "
        f"approval policy. Reason: {gate_result.final_reason}"
    )
    logger.warning("Gate blocked AgentDojo tool '%s': %s", tool_name, gate_result.final_reason)
    return GateOutcome(
        allowed=False,
        tool_call=tool_call,
        gate_result=gate_result,
        denial_text=denial_text,
        error=f"PermissionDenied: {gate_result.final_reason}",
    )


def gated_runtime_type() -> type:
    """Return a ``FunctionsRuntime`` subclass. Imports AgentDojo on first use."""
    global _GATED_RUNTIME_BASE
    if _GATED_RUNTIME_BASE is not None:
        return _GATED_RUNTIME_BASE

    from agentdojo.functions_runtime import FunctionsRuntime

    class GatedFunctionsRuntime(FunctionsRuntime):
        """Suite runtime whose ``run_function`` consults an ``ApprovalSession``."""

        def __init__(self, functions=(), session: Any = None):
            super().__init__(list(functions))
            if session is None:
                raise ValueError("GatedFunctionsRuntime requires an ApprovalSession")
            self.session = session

        def run_function(self, env, function, kwargs, raise_on_error: bool = False):
            if function not in self.functions:
                return super().run_function(env, function, kwargs, raise_on_error)

            spec = self.functions[function]
            outcome = apply_gate(
                self.session,
                function,
                kwargs,
                description=getattr(spec, "description", "") or "",
            )
            if not outcome.allowed:
                self.session.note_call(outcome.tool_call, executed=False, output=None)
                if raise_on_error:
                    raise ToolExecutionDeniedError(outcome.gate_result)
                return outcome.denial_text, outcome.error

            value, error = super().run_function(env, function, kwargs, raise_on_error)
            self.session.note_call(
                outcome.tool_call,
                executed=error is None,
                output=value if error is None else error,
            )
            return value, error

    _GATED_RUNTIME_BASE = GatedFunctionsRuntime
    return _GATED_RUNTIME_BASE


class ApprovalContextSync:
    """Copy the current chat trace onto the session before tools execute.

    Insert this element immediately before AgentDojo's ``ToolsExecutor``.
    The class does not subclass the pipeline base, so importing this module
    does not import AgentDojo. ``query`` matches the pipeline element signature.
    """

    def query(self, query, runtime, env, messages=(), extra_args=None):
        extra_args = {} if extra_args is None else extra_args
        session = getattr(runtime, "session", None)
        if session is not None:
            session.update_trace(messages)
        return query, runtime, env, messages, extra_args
