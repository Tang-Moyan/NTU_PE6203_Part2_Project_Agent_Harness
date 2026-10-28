"""Per-task binding of a policy, reviewer and human budget to AgentDojo.

Evaluation code should construct one session per task:

    session = ApprovalSession(policy, reviewer, budget_k)
    session.begin_task(user_task, suite_name=suite.name)
    runtime = session.create_runtime(suite.tools)

``runtime_class()`` is the object expected by
``TaskSuite.run_task_with_pipeline(..., runtime_class=...)``.
"""

from __future__ import annotations

from typing import Any, Sequence

from core.base import BaseApprovalPolicy, BaseHumanReviewer
from core.budget import BudgetTracker
from core.gate import ApprovalGate
from core.models import TaskContext, ToolCall
from agentdojo_integration.context_builder import build_task_context, completed_tool_trajectory

DEFAULT_BENCHMARK_VERSION = "v1.2.2"
_OUTPUT_PREVIEW_CHARS = 2000


class ApprovalSession:
    """Holds the gate state for a single AgentDojo task."""

    def __init__(
        self,
        policy: BaseApprovalPolicy,
        reviewer: BaseHumanReviewer,
        budget_k: int,
        *,
        suite_name: str | None = None,
        task: Any = None,
        task_id: str | None = None,
        task_description: str | None = None,
    ):
        if budget_k < 0:
            raise ValueError("budget_k must be >= 0")
        self.policy = policy
        self.reviewer = reviewer
        self.budget_k = budget_k
        self.budget = BudgetTracker(initial_budget=budget_k)
        self.gate = ApprovalGate(policy=policy, reviewer=reviewer)
        self.suite_name = suite_name
        self.task = task
        self.task_id_override = task_id
        self.task_description_override = task_description
        self.messages: list[Any] = []
        self.live_trajectory: list[dict[str, Any]] = []
        self._call_index = 0
        self.attempt_count = 0
        self.scored_attempt = 0

    def begin_task(
        self,
        task: Any,
        *,
        suite_name: str | None = None,
        task_id: str | None = None,
        task_description: str | None = None,
    ) -> TaskContext:
        """Reset budget, audit log and trace for a new user task.

        Pass the AgentDojo user task. Do not pass an injection task here:
        its ``GOAL`` is an attacker objective and is not a user instruction.
        """
        self.task = task
        self.task_id_override = task_id
        self.task_description_override = task_description
        if suite_name is not None:
            self.suite_name = suite_name
        self.messages = []
        self.live_trajectory = []
        self._call_index = 0
        self.budget.reset(self.budget_k)
        self.gate.clear_audit_log()
        return self.current_context()

    def current_context(self) -> TaskContext:
        """Context visible to the policy and reviewer at this moment."""
        return build_task_context(
            self.task,
            suite_name=self.suite_name,
            messages=self.messages,
            extra_trajectory=self.live_trajectory,
            include_completed_tools=False,
            task_id=self.task_id_override,
            task_description=self.task_description_override,
        )

    def update_trace(self, messages: Sequence[Any] | None) -> None:
        """Replace the stored trace with messages the agent has already produced."""
        self.messages = list(messages or [])
        self.live_trajectory = completed_tool_trajectory(self.messages)

    def note_call(self, tool_call: ToolCall, *, executed: bool, output: Any = None) -> None:
        """Record a gated call so the next decision can see it."""
        preview = None if output is None else str(output)[:_OUTPUT_PREVIEW_CHARS]
        self.live_trajectory.append(
            {
                "call_id": tool_call.call_id,
                "tool_name": tool_call.tool_name,
                "arguments": tool_call.arguments,
                "executed": executed,
                "output_preview": preview,
            }
        )

    def next_call_id(self, tool_name: str) -> str:
        self._call_index += 1
        return f"{tool_name}-{self._call_index}"

    def runtime_class(self) -> type:
        """Class accepted by ``run_task_with_pipeline(runtime_class=...)``.

        The class closes over this session. Call ``begin_task`` before each task
        so the same class picks up the new prompt and a fresh budget.
        """
        from agentdojo_integration.runtime import gated_runtime_type

        base = gated_runtime_type()
        session = self

        class BoundApprovalRuntime(base):
            def __init__(self, functions=()):
                super().__init__(functions, session=session)

        BoundApprovalRuntime.__name__ = "BoundApprovalRuntime"
        return BoundApprovalRuntime

    def create_runtime(self, tools: Any) -> Any:
        """Wrap a suite tool list or an existing function mapping."""
        if isinstance(tools, dict):
            tool_list = list(tools.values())
        else:
            tool_list = list(tools)
        return self.runtime_class()(tool_list)

    def run_suite_task(
        self,
        suite: Any,
        agent_pipeline: Any,
        user_task: Any,
        injection_task: Any = None,
        injections: dict[str, str] | None = None,
        environment: Any = None,
    ) -> Any:
        """Run one user task. Prefer this over ``suite.run_task_with_pipeline``.

        Each attempt gets a new budget and a copy of the initial environment.
        Blocked tool calls are omitted from the trace used for utility and security.
        """
        from agentdojo_integration.suite_runner import run_suite_task

        return run_suite_task(
            self,
            suite,
            agent_pipeline,
            user_task,
            injection_task=injection_task,
            injections=injections,
            environment=environment,
        )


def load_suite(suite_name: str, benchmark_version: str = DEFAULT_BENCHMARK_VERSION) -> Any:
    """Load an upstream AgentDojo suite. Requires the ``agentdojo`` package."""
    from agentdojo.task_suite.load_suites import get_suite

    return get_suite(benchmark_version, suite_name)
