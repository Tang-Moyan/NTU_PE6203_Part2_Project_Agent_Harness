"""
AgentDojo Integration Adapter.

Integrates the ApprovalGate into the AgentDojo benchmark execution pipeline.
Intercepts tool calls prior to reaching the environment execution layer.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from core.budget import BudgetTracker
from core.gate import ApprovalGate
from core.models import GateAction, GateResult, TaskContext, ToolCall

logger = logging.getLogger(__name__)


class ToolExecutionDeniedError(PermissionError):
    """Raised or returned when a tool call is blocked by the Approval Gate."""
    def __init__(self, gate_result: GateResult):
        self.gate_result = gate_result
        super().__init__(f"Tool call execution denied by approval gate: {gate_result.final_reason}")


class AgentDojoApprovalInterceptor:
    """
    Middleware interceptor designed for AgentDojo harnesses.
    
    Intercepts candidate tool calls before they are executed against the
    benchmark environment.
    """

    def __init__(self, gate: ApprovalGate):
        self.gate = gate

    def intercept_and_execute(
        self,
        tool_func: Callable[..., Any],
        tool_call: ToolCall,
        context: TaskContext,
        budget: BudgetTracker,
    ) -> Any:
        """
        Intercepts execution. If permitted by the gate, calls tool_func.
        If blocked, halts execution and returns a permission-denied response.
        
        Args:
            tool_func: The original callable tool from AgentDojo.
            tool_call: Structured tool call details.
            context: Current task context.
            budget: Remaining escalation budget tracker.
            
        Returns:
            Output of tool_func if executed, or denial feedback string.
        """
        result: GateResult = self.gate.intercept(tool_call, context, budget)

        if result.action == GateAction.EXECUTE:
            logger.info(f"Gate permitted execution for tool '{tool_call.tool_name}'.")
            return tool_func(**tool_call.arguments)
        else:
            logger.warning(
                f"Gate BLOCKED tool '{tool_call.tool_name}'. Reason: {result.final_reason}"
            )
            # Return feedback suitable for LLM Agent recovery without executing dangerous action
            return (
                f"[Permission Denied] The tool call '{tool_call.tool_name}' was blocked by the safety "
                f"approval policy. Reason: {result.final_reason}"
            )


def wrap_agentdojo_tool(
    tool_func: Callable[..., Any],
    tool_name: str,
    interceptor: AgentDojoApprovalInterceptor,
    context_provider: Callable[[], TaskContext],
    budget_provider: Callable[[], BudgetTracker],
    is_read_only: bool = False,
    is_local: bool = True,
) -> Callable[..., Any]:
    """
    Helper function to wrap an individual AgentDojo tool with approval interception.
    """
    def wrapped(**kwargs):
        tool_call = ToolCall(
            call_id=f"call_{tool_name}",
            tool_name=tool_name,
            arguments=kwargs,
            is_read_only=is_read_only,
            is_local=is_local,
        )
        return interceptor.intercept_and_execute(
            tool_func=tool_func,
            tool_call=tool_call,
            context=context_provider(),
            budget=budget_provider(),
        )

    wrapped.__name__ = getattr(tool_func, "__name__", tool_name)
    wrapped.__doc__ = getattr(tool_func, "__doc__", "")
    return wrapped
