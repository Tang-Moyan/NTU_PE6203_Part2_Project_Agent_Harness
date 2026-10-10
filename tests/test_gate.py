"""
Tests for ApprovalGate decision routing and budget degradation mechanism.
"""

import unittest
from core.budget import BudgetTracker
from core.gate import ApprovalGate
from core.models import DecisionType, GateAction, PolicyDecision, TaskContext, ToolCall
from policies.baselines.full_approve import FullApprovePolicy
from policies.baselines.full_escalate import FullEscalatePolicy
from policies.baselines.rule_based import RuleBasedPolicy
from reviewer.llm_reviewer import MockReviewer


class TestApprovalGate(unittest.TestCase):
    def setUp(self):
        self.context = TaskContext(
            task_id="task_gate_test",
            task_description="Manage workspace resources",
        )
        self.reviewer = MockReviewer(default_approved=True)

    def test_auto_approve_routing(self):
        policy = FullApprovePolicy()
        gate = ApprovalGate(policy=policy, reviewer=self.reviewer)
        budget = BudgetTracker(initial_budget=1)

        tool_call = ToolCall(call_id="c1", tool_name="list_files", is_read_only=True)
        result = gate.intercept(tool_call, self.context, budget)

        self.assertEqual(result.action, GateAction.EXECUTE)
        self.assertFalse(result.was_escalated)
        self.assertEqual(budget.remaining_budget, 1)  # Budget unchanged

    def test_escalation_within_budget(self):
        policy = FullEscalatePolicy()
        gate = ApprovalGate(policy=policy, reviewer=self.reviewer)
        budget = BudgetTracker(initial_budget=2)

        tool_call = ToolCall(call_id="c1", tool_name="create_file")
        result = gate.intercept(tool_call, self.context, budget)

        self.assertEqual(result.action, GateAction.EXECUTE)
        self.assertTrue(result.was_escalated)
        self.assertFalse(result.budget_exhausted_fallback)
        self.assertEqual(budget.remaining_budget, 1)
        self.assertEqual(budget.total_escalations, 1)

    def test_budget_exhaustion_degradation_to_deny(self):
        """
        Critical test: Verify that once budget k is 0, any ESCALATE request
        is automatically degraded to AUTO_DENY and action becomes BLOCK.
        """
        policy = FullEscalatePolicy()
        gate = ApprovalGate(policy=policy, reviewer=self.reviewer)
        budget = BudgetTracker(initial_budget=1)

        # 1st call: uses the 1 available budget unit
        call1 = ToolCall(call_id="c1", tool_name="action_1")
        res1 = gate.intercept(call1, self.context, budget)
        self.assertEqual(res1.action, GateAction.EXECUTE)
        self.assertTrue(res1.was_escalated)
        self.assertEqual(budget.remaining_budget, 0)

        # 2nd call: budget is now exhausted (k=0 left) -> must degrade to auto-deny
        call2 = ToolCall(call_id="c2", tool_name="action_2")
        res2 = gate.intercept(call2, self.context, budget)
        self.assertEqual(res2.action, GateAction.BLOCK)
        self.assertFalse(res2.was_escalated)
        self.assertTrue(res2.budget_exhausted_fallback)
        self.assertIn("budget k is exhausted", res2.final_reason)

    def test_auto_deny_routing(self):
        policy = RuleBasedPolicy()
        gate = ApprovalGate(policy=policy, reviewer=self.reviewer)
        budget = BudgetTracker(initial_budget=5)

        # Known dangerous call
        tool_call = ToolCall(
            call_id="c_danger",
            tool_name="bash",
            arguments={"cmd": "rm -rf /"},
            is_read_only=False,
        )
        result = gate.intercept(tool_call, self.context, budget)

        self.assertEqual(result.action, GateAction.BLOCK)
        self.assertFalse(result.was_escalated)
        self.assertFalse(result.budget_exhausted_fallback)
        self.assertEqual(budget.remaining_budget, 5)  # Budget untouched


if __name__ == "__main__":
    unittest.main()
