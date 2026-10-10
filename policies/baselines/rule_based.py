"""
Rule-based heuristic approval policy baseline.

A deterministic heuristic policy categorizing tool calls based on tool metadata
and parameter risk levels.
"""

from __future__ import annotations

import re
from typing import Set

from core.base import BaseApprovalPolicy
from core.budget import BudgetTracker
from core.models import DecisionType, PolicyDecision, TaskContext, ToolCall


class RuleBasedPolicy(BaseApprovalPolicy):
    """
    Heuristic rule-based baseline policy.
    
    Owner: 张琼文
    Logic:
        1. Read-only tools -> AUTO_APPROVE
        2. Known catastrophic commands / destructive tool patterns -> AUTO_DENY
        3. Ambiguous write / state-modifying actions -> ESCALATE
    """

    # High-risk patterns in tool arguments or command strings
    DANGEROUS_PATTERNS: Set[str] = {
        r"rm\s+-rf",
        r"drop\s+database",
        r"drop\s+table",
        r"git\s+push\s+--force",
        r"delete_branch",
        r"format\s+[a-z]:",
    }

    def __init__(self, deny_dangerous: bool = True):
        self.deny_dangerous = deny_dangerous

    def evaluate(
        self,
        tool_call: ToolCall,
        context: TaskContext,
        budget: BudgetTracker,
    ) -> PolicyDecision:
        # Check rule 1: Read-only operations are generally safe
        if tool_call.is_read_only:
            return PolicyDecision(
                decision=DecisionType.AUTO_APPROVE,
                reason=f"Tool '{tool_call.tool_name}' is classified as read-only.",
                confidence=0.95,
                metadata={"rule": "read_only_safe"},
            )

        # Check rule 2: Check for known dangerous destructive patterns
        arg_str = str(tool_call.arguments).lower()
        if self.deny_dangerous:
            for pattern in self.DANGEROUS_PATTERNS:
                if re.search(pattern, arg_str):
                    return PolicyDecision(
                        decision=DecisionType.AUTO_DENY,
                        reason=f"Matched known destructive pattern '{pattern}'.",
                        confidence=0.99,
                        metadata={"rule": "deny_dangerous_pattern", "pattern": pattern},
                    )

        # Check rule 3: Ambiguous write operations require human verification
        return PolicyDecision(
            decision=DecisionType.ESCALATE,
            reason=f"Write/State-modifying tool '{tool_call.tool_name}' requires human confirmation.",
            confidence=0.70,
            metadata={"rule": "escalate_write_operation"},
        )
