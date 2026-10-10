"""
Core data models for the Approval Policy Gate.

This module defines all shared schemas between the Approval Gate,
Policy implementations, Human Reviewer simulation, and Evaluation pipeline.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DecisionType(str, Enum):
    """Three-way decision type emitted by an approval policy."""
    AUTO_APPROVE = "auto_approve"
    AUTO_DENY = "auto_deny"
    ESCALATE = "escalate"


class GateAction(str, Enum):
    """Final action decided by the Approval Gate."""
    EXECUTE = "execute"
    BLOCK = "block"


class Message(BaseModel):
    """Represents a conversation message in the agent's context."""
    role: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    """
    Normalized representation of a tool call issued by an AI agent.
    
    Attributes:
        call_id: Unique identifier for the tool call.
        tool_name: The name/function identifier of the tool.
        arguments: Parsed dictionary of arguments supplied by the agent.
        is_read_only: Heuristic metadata indicating whether the tool only reads state.
        is_local: Whether the tool acts on local environment vs remote API / network.
        raw_call: Original tool call payload from the framework (e.g. AgentDojo / OpenAI format).
        metadata: Arbitrary additional metadata (e.g. documentation, risk level).
    """
    call_id: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    is_read_only: bool = False
    is_local: bool = True
    raw_call: Optional[Any] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskContext(BaseModel):
    """
    Contextual information available at the time of a tool call decision.
    
    IMPORTANT: In keeping with benchmark isolation requirements, TaskContext
    must NOT contain ground-truth labels, attack annotations, or oracle data.
    """
    task_id: str
    task_description: str
    history_messages: List[Message] = Field(default_factory=list)
    trajectory: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PolicyDecision(BaseModel):
    """
    Decision produced by an Approval Policy.
    
    Attributes:
        decision: One of AUTO_APPROVE, AUTO_DENY, or ESCALATE.
        reason: Explanation or thought trace behind the policy decision.
        confidence: Optional confidence score in [0.0, 1.0].
        token_cost: Number of tokens consumed by the policy to make this decision.
        metadata: Extra debugging or classification details.
    """
    decision: DecisionType
    reason: str = ""
    confidence: Optional[float] = None
    token_cost: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReviewerDecision(BaseModel):
    """
    Decision produced by the Human Reviewer (or LLM-simulated Human Reviewer).
    
    Attributes:
        approved: True if the reviewer permits execution, False if denied.
        reason: Human/LLM rationale for approving or denying.
        token_cost: Number of tokens consumed by the simulated reviewer.
        metadata: Extra auditing information.
    """
    approved: bool
    reason: str = ""
    token_cost: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GateResult(BaseModel):
    """
    Final decision and audit trail produced by the Approval Gate for a tool call.
    
    Attributes:
        action: Final gate action (EXECUTE or BLOCK).
        policy_decision: The preliminary decision from the approval policy.
        was_escalated: Whether this call was forwarded to human reviewer.
        reviewer_decision: The reviewer's decision if escalated.
        budget_exhausted_fallback: True if ESCALATE was degraded to AUTO_DENY because k == 0.
        final_reason: Combined rationale for the final action.
        timestamp: Epoch timestamp when the decision was finalized.
    """
    action: GateAction
    policy_decision: PolicyDecision
    was_escalated: bool = False
    reviewer_decision: Optional[ReviewerDecision] = None
    budget_exhausted_fallback: bool = False
    final_reason: str = ""
    timestamp: float = Field(default_factory=time.time)
