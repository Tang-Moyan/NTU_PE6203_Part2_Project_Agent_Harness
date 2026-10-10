"""
Approval Gate implementation.

The ApprovalGate intercepts tool calls prior to execution and enforces
the policy, human escalation budget k, and simulated reviewer routing.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from core.base import BaseApprovalPolicy, BaseHumanReviewer
from core.budget import BudgetTracker
from core.models import (
    DecisionType,
    GateAction,
    GateResult,
    PolicyDecision,
    ReviewerDecision,
    TaskContext,
    ToolCall,
)

logger = logging.getLogger(__name__)


class ApprovalGate:
    """
    Central mediation gate for all agent tool executions.
    
    Attributes:
        policy: The active approval policy (baseline or smart).
        reviewer: The human reviewer (simulated LLM or real human).
        audit_log: History of all gate decisions across intercepted calls.
    """

    def __init__(
        self,
        policy: BaseApprovalPolicy,
        reviewer: BaseHumanReviewer,
    ):
        self.policy = policy
        self.reviewer = reviewer
        self.audit_log: List[GateResult] = []

    def intercept(
        self,
        tool_call: ToolCall,
        context: TaskContext,
        budget: BudgetTracker,
    ) -> GateResult:
        """
        Intercepts a tool call, evaluates it with the policy, handles escalation,
        and enforces the degradation rule when budget k is exhausted.
        
        Args:
            tool_call: The agent tool call to be examined.
            context: The oracle-free task context.
            budget: The budget tracker for the current task.
            
        Returns:
            GateResult indicating whether to EXECUTE or BLOCK the tool call.
        """
        # Step 1: Query the approval policy
        policy_decision = self.policy.evaluate(tool_call, context, budget)

        # Step 2: Route based on policy decision
        if policy_decision.decision == DecisionType.AUTO_APPROVE:
            result = GateResult(
                action=GateAction.EXECUTE,
                policy_decision=policy_decision,
                was_escalated=False,
                reviewer_decision=None,
                budget_exhausted_fallback=False,
                final_reason=policy_decision.reason or "Auto-approved by policy.",
            )

        elif policy_decision.decision == DecisionType.AUTO_DENY:
            result = GateResult(
                action=GateAction.BLOCK,
                policy_decision=policy_decision,
                was_escalated=False,
                reviewer_decision=None,
                budget_exhausted_fallback=False,
                final_reason=policy_decision.reason or "Auto-denied by policy.",
            )

        elif policy_decision.decision == DecisionType.ESCALATE:
            # Check escalation budget k
            if budget.can_escalate():
                budget.consume()
                reviewer_decision = self.reviewer.review(tool_call, context)
                
                action = GateAction.EXECUTE if reviewer_decision.approved else GateAction.BLOCK
                final_reason = (
                    f"Escalated to human reviewer. Verdict: "
                    f"{'Approved' if reviewer_decision.approved else 'Denied'}. "
                    f"Reviewer rationale: {reviewer_decision.reason}"
                )
                
                result = GateResult(
                    action=action,
                    policy_decision=policy_decision,
                    was_escalated=True,
                    reviewer_decision=reviewer_decision,
                    budget_exhausted_fallback=False,
                    final_reason=final_reason,
                )
            else:
                # Degradation rule: escalation budget exhausted -> treated as auto-deny
                fallback_reason = (
                    f"Policy requested ESCALATE, but human escalation budget k is exhausted "
                    f"({budget.remaining_budget}/{budget.initial_budget} remaining). "
                    f"Degrading to AUTO_DENY."
                )
                logger.warning(fallback_reason)
                
                result = GateResult(
                    action=GateAction.BLOCK,
                    policy_decision=policy_decision,
                    was_escalated=False,
                    reviewer_decision=None,
                    budget_exhausted_fallback=True,
                    final_reason=fallback_reason,
                )
        else:
            raise ValueError(f"Unknown policy decision type: {policy_decision.decision}")

        self.audit_log.append(result)
        return result

    async def aintercept(
        self,
        tool_call: ToolCall,
        context: TaskContext,
        budget: BudgetTracker,
    ) -> GateResult:
        """
        Asynchronous variant of intercept for non-blocking execution pipelines.
        """
        policy_decision = await self.policy.aevaluate(tool_call, context, budget)

        if policy_decision.decision == DecisionType.AUTO_APPROVE:
            result = GateResult(
                action=GateAction.EXECUTE,
                policy_decision=policy_decision,
                was_escalated=False,
                reviewer_decision=None,
                budget_exhausted_fallback=False,
                final_reason=policy_decision.reason or "Auto-approved by policy.",
            )
        elif policy_decision.decision == DecisionType.AUTO_DENY:
            result = GateResult(
                action=GateAction.BLOCK,
                policy_decision=policy_decision,
                was_escalated=False,
                reviewer_decision=None,
                budget_exhausted_fallback=False,
                final_reason=policy_decision.reason or "Auto-denied by policy.",
            )
        elif policy_decision.decision == DecisionType.ESCALATE:
            if budget.can_escalate():
                budget.consume()
                reviewer_decision = await self.reviewer.areview(tool_call, context)
                action = GateAction.EXECUTE if reviewer_decision.approved else GateAction.BLOCK
                final_reason = (
                    f"Escalated to human reviewer. Verdict: "
                    f"{'Approved' if reviewer_decision.approved else 'Denied'}. "
                    f"Reviewer rationale: {reviewer_decision.reason}"
                )
                result = GateResult(
                    action=action,
                    policy_decision=policy_decision,
                    was_escalated=True,
                    reviewer_decision=reviewer_decision,
                    budget_exhausted_fallback=False,
                    final_reason=final_reason,
                )
            else:
                fallback_reason = (
                    f"Policy requested ESCALATE, but human escalation budget k is exhausted. "
                    f"Degrading to AUTO_DENY."
                )
                result = GateResult(
                    action=GateAction.BLOCK,
                    policy_decision=policy_decision,
                    was_escalated=False,
                    reviewer_decision=None,
                    budget_exhausted_fallback=True,
                    final_reason=fallback_reason,
                )
        else:
            raise ValueError(f"Unknown policy decision type: {policy_decision.decision}")

        self.audit_log.append(result)
        return result

    def clear_audit_log(self) -> None:
        """Clears the recorded audit log."""
        self.audit_log.clear()
