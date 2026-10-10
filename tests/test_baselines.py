"""
Tests for baseline approval policies.
"""

import unittest
from core.budget import BudgetTracker
from core.models import DecisionType, TaskContext, ToolCall
from policies.baselines.full_approve import FullApprovePolicy
from policies.baselines.full_escalate import FullEscalatePolicy
from policies.baselines.rule_based import RuleBasedPolicy


class TestBaselinePolicies(unittest.TestCase):
    def setUp(self):
        self.context = TaskContext(
            task_id="test_01",
            task_description="Execute repository cleanup",
        )
        self.budget = BudgetTracker(initial_budget=3)

    def test_full_approve_policy(self):
        policy = FullApprovePolicy()
        dangerous_call = ToolCall(
            call_id="call_danger",
            tool_name="shell",
            arguments={"command": "rm -rf /"},
            is_read_only=False,
        )
        decision = policy.evaluate(dangerous_call, self.context, self.budget)
        self.assertEqual(decision.decision, DecisionType.AUTO_APPROVE)

    def test_full_escalate_policy(self):
        policy = FullEscalatePolicy()
        safe_call = ToolCall(
            call_id="call_safe",
            tool_name="read_file",
            arguments={"path": "README.md"},
            is_read_only=True,
        )
        decision = policy.evaluate(safe_call, self.context, self.budget)
        self.assertEqual(decision.decision, DecisionType.ESCALATE)

    def test_rule_based_policy(self):
        policy = RuleBasedPolicy()

        # 1. Read-only tool -> AUTO_APPROVE
        read_call = ToolCall(
            call_id="c1",
            tool_name="get_file",
            arguments={"path": "data.csv"},
            is_read_only=True,
        )
        decision = policy.evaluate(read_call, self.context, self.budget)
        self.assertEqual(decision.decision, DecisionType.AUTO_APPROVE)

        # 2. Dangerous destructive pattern -> AUTO_DENY
        drop_call = ToolCall(
            call_id="c2",
            tool_name="sql_exec",
            arguments={"query": "DROP DATABASE production;"},
            is_read_only=False,
        )
        decision = policy.evaluate(drop_call, self.context, self.budget)
        self.assertEqual(decision.decision, DecisionType.AUTO_DENY)

        # 3. Ambiguous write -> ESCALATE
        write_call = ToolCall(
            call_id="c3",
            tool_name="write_file",
            arguments={"path": "output.txt", "content": "hello"},
            is_read_only=False,
        )
        decision = policy.evaluate(write_call, self.context, self.budget)
        self.assertEqual(decision.decision, DecisionType.ESCALATE)


if __name__ == "__main__":
    unittest.main()
