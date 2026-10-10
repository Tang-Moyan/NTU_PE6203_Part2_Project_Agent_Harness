"""
Abstract base classes defining the contracts for Approval Policies and Human Reviewers.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Optional

from core.models import ToolCall, TaskContext, PolicyDecision, ReviewerDecision
from core.budget import BudgetTracker


class BaseApprovalPolicy(ABC):
    """
    Abstract contract for an Approval Policy.
    
    Implementations must evaluate a pending tool call against the task context
    and return a three-way decision: AUTO_APPROVE, AUTO_DENY, or ESCALATE.
    """

    @abstractmethod
    def evaluate(
        self,
        tool_call: ToolCall,
        context: TaskContext,
        budget: BudgetTracker,
    ) -> PolicyDecision:
        """
        Synchronously evaluate a tool call and produce an approval decision.
        
        Args:
            tool_call: The tool call issued by the agent.
            context: Current task context and trajectory (oracle-free).
            budget: Tracker representing the remaining escalation budget k.
            
        Returns:
            PolicyDecision with decision type, rationale, and metadata.
        """
        pass

    async def aevaluate(
        self,
        tool_call: ToolCall,
        context: TaskContext,
        budget: BudgetTracker,
    ) -> PolicyDecision:
        """
        Asynchronously evaluate a tool call.
        Defaults to executing the synchronous `evaluate` in a threadpool executor.
        Can be overridden for native async LLM/API calls.
        """
        return await asyncio.to_thread(self.evaluate, tool_call, context, budget)


class BaseHumanReviewer(ABC):
    """
    Abstract contract for the Human Reviewer (or simulated LLM reviewer).
    
    The reviewer receives the tool call details and context (strictly sanitized
    to prevent oracle leakage) and returns an approve/deny verdict.
    """

    @abstractmethod
    def review(
        self,
        tool_call: ToolCall,
        context: TaskContext,
    ) -> ReviewerDecision:
        """
        Synchronously review a high-risk or ambiguous tool call.
        
        Args:
            tool_call: The escalated tool call.
            context: Sanitized task context.
            
        Returns:
            ReviewerDecision indicating approve or deny.
        """
        pass

    async def areview(
        self,
        tool_call: ToolCall,
        context: TaskContext,
    ) -> ReviewerDecision:
        """
        Asynchronously review a tool call.
        Defaults to running `review` in a threadpool executor.
        """
        return await asyncio.to_thread(self.review, tool_call, context)
