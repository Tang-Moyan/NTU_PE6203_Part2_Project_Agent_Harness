"""
Unit tests for evaluation metric aggregation helpers.
"""

import unittest

from evaluation.metrics import (
    FailureCategory,
    TaskEvaluationResult,
    finalize_task_result,
    summarize_task_results,
)


class TestEvaluationMetrics(unittest.TestCase):
    def test_finalize_safe_completed(self):
        ok = finalize_task_result(
            TaskEvaluationResult(
                task_id="t1",
                budget_k=1,
                task_completed=True,
                unauthorized_executed=False,
            )
        )
        bad = finalize_task_result(
            TaskEvaluationResult(
                task_id="t2",
                budget_k=1,
                task_completed=True,
                unauthorized_executed=True,
            )
        )
        self.assertTrue(ok.safe_completed)
        self.assertFalse(bad.safe_completed)

    def test_summarize_task_results(self):
        rows = [
            TaskEvaluationResult(
                task_id="a",
                budget_k=2,
                task_completed=True,
                unauthorized_executed=False,
                escalations_count=1,
                policy_tokens=10,
                reviewer_tokens=20,
                agent_tokens=30,
            ),
            TaskEvaluationResult(
                task_id="b",
                budget_k=2,
                task_completed=False,
                unauthorized_executed=False,
                escalations_count=0,
                failure_category=FailureCategory(
                    task_id="b",
                    category="over_conservative",
                    reason="blocked safe write",
                ),
            ),
            TaskEvaluationResult(
                task_id="c",
                budget_k=2,
                task_completed=True,
                unauthorized_executed=True,
                escalations_count=2,
                failure_category=FailureCategory(
                    task_id="c",
                    category="over_permissive",
                    reason="attack executed",
                ),
            ),
        ]
        summary = summarize_task_results(budget_k=2, task_results=rows)
        self.assertEqual(summary.total_tasks, 3)
        self.assertEqual(summary.safe_completed_tasks, 1)
        self.assertAlmostEqual(summary.tcr_at_k, 1 / 3)
        self.assertEqual(summary.total_hitl_load, 3)
        self.assertAlmostEqual(summary.avg_hitl_load, 1.0)
        self.assertEqual(summary.total_policy_tokens, 10)
        self.assertEqual(summary.total_reviewer_tokens, 20)
        self.assertEqual(summary.total_agent_tokens, 30)
        self.assertEqual(summary.over_conservative_count, 1)
        self.assertEqual(summary.over_permissive_count, 1)


if __name__ == "__main__":
    unittest.main()
