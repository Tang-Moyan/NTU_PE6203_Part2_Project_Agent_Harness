"""
Full-approve baseline policy.

Every tool call is unconditionally auto-approved without human intervention.
This corresponds to an unguarded agent execution baseline.
"""

from __future__ import annotations

from core.base import BaseApprovalPolicy
from core.budget import BudgetTracker
from core.models import DecisionType, PolicyDecision, TaskContext, ToolCall


class FullApprovePolicy(BaseApprovalPolicy):
    """
    Baseline policy that auto-approves all tool calls.
    
    Owner: 张琼文
    Characteristics:
        - Human escalation count: 0 (HITL Load = 0)
        - Safety: Lowest (unguarded execution)
        - Attention budget k: Ignored
    """

    def evaluate(
        self,
        tool_call: ToolCall,
        context: TaskContext,
        budget: BudgetTracker,
    ) -> PolicyDecision:
        """Approve unconditionally, including when the review budget is zero.

        Evaluating a baseline never consumes human attention or model tokens.
        """
        return PolicyDecision(
            decision=DecisionType.AUTO_APPROVE,
            reason="Full-approve baseline: all tool calls are auto-approved unconditionally.",
            confidence=1.0,
            token_cost=0,
            metadata={"baseline": "full_approve"},
        )
