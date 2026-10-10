"""
AgentDojo Integration package.
"""

from agentdojo_integration.adapter import (
    AgentDojoApprovalInterceptor,
    ToolExecutionDeniedError,
    wrap_agentdojo_tool,
)

__all__ = [
    "AgentDojoApprovalInterceptor",
    "ToolExecutionDeniedError",
    "wrap_agentdojo_tool",
]
