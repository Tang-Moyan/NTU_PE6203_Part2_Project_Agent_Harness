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
        # TODO (李易臻 & 朱茵): 填充针对 AgentDojo 任务集的实际评测循环
        # 1. 对每个任务初始化任务环境及上下文 TaskContext
        # 2. 为当前任务创建 BudgetTracker(initial_budget=budget_k)
        # 3. 拦截 Agent 的所有 tool call 并经由 self.gate.intercept(...) 裁决
        # 4. 判断任务是否成功 (task_completed) 以及是否执行了未授权调用 (unauthorized_executed)
        # 5. 记录 safe_completed = task_completed and not unauthorized_executed
        # 6. 收集并归因失败样例 (Over-conservative vs Over-permissive)
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
