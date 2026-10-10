"""
Tests for core data models and budget tracker.
"""

import unittest
from core.models import ToolCall, TaskContext, Message, DecisionType, GateAction
from core.budget import BudgetTracker


class TestCoreModels(unittest.TestCase):
    def test_tool_call_creation(self):
        call = ToolCall(
            call_id="call_001",
            tool_name="read_file",
            arguments={"path": "/etc/hosts"},
            is_read_only=True,
            is_local=True,
        )
        self.assertEqual(call.call_id, "call_001")
        self.assertEqual(call.tool_name, "read_file")
        self.assertTrue(call.is_read_only)
        self.assertTrue(call.is_local)

    def test_task_context_creation(self):
        context = TaskContext(
            task_id="task_42",
            task_description="Clean temporary log files",
            history_messages=[
                Message(role="user", content="Please remove logs older than 7 days"),
            ],
        )
        self.assertEqual(context.task_id, "task_42")
        self.assertEqual(len(context.history_messages), 1)


class TestBudgetTracker(unittest.TestCase):
    def test_budget_consumption(self):
        tracker = BudgetTracker(initial_budget=2)
        self.assertEqual(tracker.remaining_budget, 2)
        self.assertEqual(tracker.total_escalations, 0)
        self.assertTrue(tracker.can_escalate())
        self.assertFalse(tracker.is_exhausted)

        # First consumption
        consumed = tracker.consume()
        self.assertTrue(consumed)
        self.assertEqual(tracker.remaining_budget, 1)
        self.assertEqual(tracker.total_escalations, 1)
        self.assertTrue(tracker.can_escalate())

        # Second consumption
        consumed = tracker.consume()
        self.assertTrue(consumed)
        self.assertEqual(tracker.remaining_budget, 0)
        self.assertEqual(tracker.total_escalations, 2)
        self.assertTrue(tracker.is_exhausted)
        self.assertFalse(tracker.can_escalate())

        # Third consumption (exhausted)
        consumed = tracker.consume()
        self.assertFalse(consumed)
        self.assertEqual(tracker.remaining_budget, 0)
        self.assertEqual(tracker.total_escalations, 2)

    def test_budget_reset(self):
        tracker = BudgetTracker(initial_budget=1)
        tracker.consume()
        self.assertTrue(tracker.is_exhausted)

        tracker.reset(new_budget=5)
        self.assertEqual(tracker.initial_budget, 5)
        self.assertEqual(tracker.remaining_budget, 5)
        self.assertEqual(tracker.total_escalations, 0)
        self.assertFalse(tracker.is_exhausted)


if __name__ == "__main__":
    unittest.main()
