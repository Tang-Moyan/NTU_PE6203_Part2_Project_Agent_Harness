"""
Evaluation pipeline runner.

Owners: 李易臻 & 朱茵
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from core.base import BaseApprovalPolicy, BaseHumanReviewer
from core.budget import BudgetTracker
from core.gate import ApprovalGate
from evaluation.metrics import BenchmarkSummary, TaskEvaluationResult, summarize_task_results

logger = logging.getLogger(__name__)


class EvaluationRunner:
    """
    Executes benchmark evaluations across varying human attention budgets k.
    
    Generates data required to plot the TCR@k curve vs budget k.
    """

    def __init__(
        self,
        policy: BaseApprovalPolicy,
        reviewer: BaseHumanReviewer,
        budgets_to_test: Optional[List[int]] = None,
    ):
        self.policy = policy
        self.reviewer = reviewer
        self.gate = ApprovalGate(policy=policy, reviewer=reviewer)
        self.budgets_to_test = budgets_to_test or [0, 1, 2, 5, 10]

    def run_benchmark_for_budget(
        self,
        budget_k: int,
        tasks: List[Dict[str, Any]],
    ) -> BenchmarkSummary:
        """
        Runs evaluation on a task dataset under a fixed budget k.
        
        Args:
            budget_k: Human attention budget per task.
            tasks: List of benchmark task definitions / environments.
            
        Returns:
            BenchmarkSummary containing aggregated TCR, HITL Load, and failure counts.
        """
        task_results: List[TaskEvaluationResult] = []

        # =====================================================================
        # TODO (李易臻 & 朱茵): 对每个 AgentDojo 用户任务调用
        #   result = ApprovalSession(self.policy, self.reviewer, budget_k).run_suite_task(...)
        # 不要直接调用 suite.run_task_with_pipeline。字段口径见
        # team_guides/06_评测组接入注意.md。
        # task_completed = result.utility
        # unauthorized_executed = result.attack_succeeded is True
        # escalations 读本次计分尝试的 session.budget.total_escalations。
        # =====================================================================

        # 框架留空占位：tasks 循环填充后，统一走 summarize_task_results 汇总
        # 当前 task_results 仍为空列表时，也会返回合法的 BenchmarkSummary（TCR=0）
        _ = tasks  # AgentDojo 任务集将在此接入
        return summarize_task_results(budget_k=budget_k, task_results=task_results)

    def evaluate_tcr_curve(
        self,
        tasks: List[Dict[str, Any]],
    ) -> Dict[int, BenchmarkSummary]:
        """
        Evaluates the policy across all configured budgets in self.budgets_to_test.
        Produces the full dataset needed for plotting the TCR@k curve.
        """
        summaries: Dict[int, BenchmarkSummary] = {}
        for k in self.budgets_to_test:
            logger.info(f"Starting benchmark evaluation for budget k={k}...")
            summary = self.run_benchmark_for_budget(k, tasks)
            summaries[k] = summary
        return summaries
