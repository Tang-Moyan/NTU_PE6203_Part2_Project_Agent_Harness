"""
End-to-end integration tests for the Approval Policy Gate harness.
"""

import unittest
from agentdojo_integration.adapter import AgentDojoApprovalInterceptor
from core.budget import BudgetTracker
from core.gate import ApprovalGate
from core.models import GateAction, TaskContext, ToolCall
from policies.smart.smart_policy import SmartApprovalPolicy
from reviewer.llm_reviewer import MockReviewer


class TestEndToEndPipeline(unittest.TestCase):
    def test_mock_environment_tool_interception(self):
        # 1. Setup mock environment tool
        execution_count = 0

        def sample_environment_tool(query: str) -> str:
            nonlocal execution_count
            execution_count += 1
            return f"Query '{query}' executed successfully."

        # 2. Setup Approval Gate with Smart Policy skeleton and Mock Reviewer
        policy = SmartApprovalPolicy()
        reviewer = MockReviewer(default_approved=True)
        gate = ApprovalGate(policy=policy, reviewer=reviewer)
        interceptor = AgentDojoApprovalInterceptor(gate=gate)

        context = TaskContext(
            task_id="e2e_task_1",
            task_description="Search and update user database",
        )
        budget = BudgetTracker(initial_budget=1)

        # Step A: Read-only call (Policy auto-approves)
        read_call = ToolCall(
            call_id="call_1",
            tool_name="sample_environment_tool",
            arguments={"query": "SELECT * FROM users;"},
            is_read_only=True,
        )
        res_a = interceptor.intercept_and_execute(
            sample_environment_tool, read_call, context, budget
        )
        self.assertIn("executed successfully", res_a)
        self.assertEqual(execution_count, 1)
        self.assertEqual(budget.remaining_budget, 1)  # Budget not consumed

        # Step B: Write call (Policy escalates, budget is 1 -> escalated to Reviewer -> Approved)
        write_call_1 = ToolCall(
            call_id="call_2",
            tool_name="sample_environment_tool",
            arguments={"query": "UPDATE users SET active=1;"},
            is_read_only=False,
        )
        res_b = interceptor.intercept_and_execute(
            sample_environment_tool, write_call_1, context, budget
        )
        self.assertIn("executed successfully", res_b)
        self.assertEqual(execution_count, 2)
        self.assertEqual(budget.remaining_budget, 0)  # Budget consumed

        # Step C: Another write call (Policy escalates, but budget is 0 -> Degradation to Auto-Deny)
        write_call_2 = ToolCall(
            call_id="call_3",
            tool_name="sample_environment_tool",
            arguments={"query": "UPDATE users SET active=0;"},
            is_read_only=False,
        )
        res_c = interceptor.intercept_and_execute(
            sample_environment_tool, write_call_2, context, budget
        )
        # Verify tool was NOT executed and denial message was returned
        self.assertIn("[Permission Denied]", res_c)
        self.assertEqual(execution_count, 2)  # execution_count remained 2

        # Step D: Verify audit logs
        self.assertEqual(len(gate.audit_log), 3)
        self.assertEqual(gate.audit_log[0].action, GateAction.EXECUTE)
        self.assertFalse(gate.audit_log[0].was_escalated)

        self.assertEqual(gate.audit_log[1].action, GateAction.EXECUTE)
        self.assertTrue(gate.audit_log[1].was_escalated)

        self.assertEqual(gate.audit_log[2].action, GateAction.BLOCK)
        self.assertTrue(gate.audit_log[2].budget_exhausted_fallback)


if __name__ == "__main__":
    unittest.main()
