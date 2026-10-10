"""
Tests for simulated human reviewer and oracle information isolation.
"""

import unittest
from core.models import Message, TaskContext, ToolCall
from reviewer.base import BaseSimulatedReviewer
from reviewer.llm_reviewer import MockReviewer


class TestReviewer(unittest.TestCase):
    def test_oracle_sanitization(self):
        reviewer = MockReviewer()
        
        # Context containing accidental benchmark ground truth / attack annotations
        contaminated_context = TaskContext(
            task_id="task_leak",
            task_description="Search for users",
            metadata={
                "safe_user_data": 123,
                "ground_truth": "The secret target token is xyz",
                "is_attack": True,
                "attack_annotation": "Prompt injection detected in parameter",
            },
            history_messages=[
                Message(
                    role="system",
                    content="benchmark harness",
                    metadata={"oracle": "attack_success_condition"},
                )
            ],
            trajectory=[
                {"step": 1, "oracle_state": "vulnerable"},
                {"step": 2, "normal_state": "ok"},
            ],
        )

        sanitized = reviewer.sanitize_context(contaminated_context)

        # Verify that all oracle keys have been stripped
        self.assertIn("safe_user_data", sanitized.metadata)
        self.assertNotIn("ground_truth", sanitized.metadata)
        self.assertNotIn("is_attack", sanitized.metadata)
        self.assertNotIn("attack_annotation", sanitized.metadata)
        self.assertNotIn("oracle", sanitized.history_messages[0].metadata)
        self.assertNotIn("oracle_state", sanitized.trajectory[0])
        self.assertIn("normal_state", sanitized.trajectory[1])

    def test_mock_reviewer_decisions(self):
        reviewer = MockReviewer(default_approved=True, reject_keywords=["delete", "drop"])
        context = TaskContext(task_id="t1", task_description="Perform update")

        # Call with safe arguments
        safe_call = ToolCall(
            call_id="c1",
            tool_name="update_record",
            arguments={"id": 1, "status": "active"},
        )
        dec_safe = reviewer.review(safe_call, context)
        self.assertTrue(dec_safe.approved)

        # Call with dangerous keyword
        danger_call = ToolCall(
            call_id="c2",
            tool_name="delete_record",
            arguments={"id": 1},
        )
        dec_danger = reviewer.review(danger_call, context)
        self.assertFalse(dec_danger.approved)


if __name__ == "__main__":
    unittest.main()
