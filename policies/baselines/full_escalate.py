"""
Full-escalate baseline policy.

Every tool call is unconditionally escalated to the human reviewer.
When the escalation budget k is exhausted, the Approval Gate degrades subsequent
decisions to auto-deny.
"""

from __future__ import annotations

from core.base import BaseApprovalPolicy
from core.budget import BudgetTracker
from core.models import DecisionType, PolicyDecision, TaskContext, ToolCall


class FullEscalatePolicy(BaseApprovalPolicy):
    """
    Baseline policy that requests human escalation for all tool calls.
    
    Owner: 张琼文
    Characteristics:
        - Safety: Highest while budget k > 0
        - HITL Load: Maximum (up to k per task)
        - Degradation: Once k is exhausted, all subsequent calls are auto-denied by the Gate.
    """

    def evaluate(
        self,
        tool_call: ToolCall,
        context: TaskContext,
        budget: BudgetTracker,
    ) -> PolicyDecision:
        """Request review even at zero budget; the gate owns budget enforcement.

        This method neither calls the reviewer nor consumes the review budget.
        """
        return PolicyDecision(
            decision=DecisionType.ESCALATE,
            reason="Full-escalate baseline: escalating all tool calls to human reviewer.",
            confidence=1.0,
            token_cost=0,
            metadata={"baseline": "full_escalate"},
        )
