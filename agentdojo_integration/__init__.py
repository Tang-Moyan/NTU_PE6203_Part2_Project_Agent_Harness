"""
AgentDojo Integration package.
"""

from agentdojo_integration.adapter import (
    AgentDojoApprovalInterceptor,
    ToolExecutionDeniedError,
    wrap_agentdojo_tool,
)
from agentdojo_integration.context_builder import build_task_context
from agentdojo_integration.runtime import ApprovalContextSync
from agentdojo_integration.session import (
    DEFAULT_BENCHMARK_VERSION,
    ApprovalSession,
    load_suite,
)
from agentdojo_integration.suite_runner import SuiteTaskResult
from agentdojo_integration.tool_mapper import infer_tool_flags

__all__ = [
    "DEFAULT_BENCHMARK_VERSION",
    "AgentDojoApprovalInterceptor",
    "ApprovalContextSync",
    "ApprovalSession",
    "SuiteTaskResult",
    "ToolExecutionDeniedError",
    "build_task_context",
    "infer_tool_flags",
    "load_suite",
    "wrap_agentdojo_tool",
]
