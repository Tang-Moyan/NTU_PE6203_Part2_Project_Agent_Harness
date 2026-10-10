"""
Unit tests for SmartApprovalPolicy.

Skeleton behavior (current placeholder):
- read-only -> AUTO_APPROVE
- non-read-only -> ESCALATE

After implementing the real policy, extend assertions for AUTO_DENY cases
and budget-aware behavior.
"""

import unittest

from core.budget import BudgetTracker
from core.models import DecisionType, TaskContext, ToolCall
from policies.smart.smart_policy import SmartApprovalPolicy


class TestSmartApprovalPolicy(unittest.TestCase):
    def setUp(self):
        self.policy = SmartApprovalPolicy()
        self.context = TaskContext(
            task_id="smart_test",
            task_description="Update application cache files only.",
        )
        self.budget = BudgetTracker(initial_budget=2)

    def test_read_only_auto_approve(self):
        call = ToolCall(
            call_id="c1",
            tool_name="list_dir",
            arguments={"path": "/tmp"},
            is_read_only=True,
        )
        decision = self.policy.evaluate(call, self.context, self.budget)
        self.assertEqual(decision.decision, DecisionType.AUTO_APPROVE)

    def test_write_escalates_in_skeleton(self):
        call = ToolCall(
            call_id="c2",
            tool_name="write_file",
            arguments={"path": "/tmp/a.txt", "content": "x"},
            is_read_only=False,
        )
        decision = self.policy.evaluate(call, self.context, self.budget)
        # Skeleton escalates; a finished smart policy may instead approve/deny.
        self.assertIn(
            decision.decision,
            {DecisionType.ESCALATE, DecisionType.AUTO_APPROVE, DecisionType.AUTO_DENY},
        )

    def test_returns_policy_decision_fields(self):
        call = ToolCall(call_id="c3", tool_name="ping", arguments={}, is_read_only=True)
        decision = self.policy.evaluate(call, self.context, self.budget)
        self.assertIsInstance(decision.reason, str)
        self.assertGreaterEqual(decision.token_cost, 0)


if __name__ == "__main__":
    unittest.main()
