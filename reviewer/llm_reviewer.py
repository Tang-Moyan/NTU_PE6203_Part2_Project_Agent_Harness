"""
LLM-simulated Human Reviewer implementation.

Owner: 曹晓晗
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from core.models import ReviewerDecision, TaskContext, ToolCall
from reviewer.base import BaseSimulatedReviewer
from reviewer.prompt_templates import REVIEWER_SYSTEM_PROMPT, REVIEWER_USER_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


class LLMSimulatedReviewer(BaseSimulatedReviewer):
    """
    Simulates a human reviewer using an LLM.
    
    Adheres strictly to the oracle-free evaluation constraint.
    """

    def __init__(
        self,
        model_name: str = "gpt-4o",
        temperature: float = 0.0,
        api_key: Optional[str] = None,
    ):
        self.model_name = model_name
        self.temperature = temperature
        self.api_key = api_key
        # TODO: Initialize OpenAI client or other LLM client here

    def review(
        self,
        tool_call: ToolCall,
        context: TaskContext,
    ) -> ReviewerDecision:
        """
        Review an escalated tool call and decide approve/deny.
        
        Args:
            tool_call: The escalated tool call.
            context: Context containing task goal and conversation trace.
            
        Returns:
            ReviewerDecision with approval verdict and reason.
        """
        # Step 1: Strictly sanitize context to prevent any oracle leakage
        sanitized_context = self.sanitize_context(context)

        # =====================================================================
        # TODO (曹晓晗): 实现 LLM 调用与决策解析
        # 1. 使用 REVIEWER_SYSTEM_PROMPT 与 REVIEWER_USER_PROMPT_TEMPLATE 格式化 prompt
        # 2. 调用 LLM (例如 client.chat.completions.create(...))
        # 3. 解析模型返回的结构化输出 (e.g. JSON 解析 approved 与 reason)
        # 4. 统计 token 消耗并记录于 ReviewerDecision
        # =====================================================================

        # 临时占位缺省逻辑（避免未配置 API key 时程序崩溃）：
        logger.info(
            f"[LLMSimulatedReviewer Skeleton] Evaluating escalated tool: {tool_call.tool_name}"
        )
        return ReviewerDecision(
            approved=True,
            reason="[Reviewer Placeholder] Approved by default in skeleton mode.",
            token_cost=0,
            metadata={"status": "skeleton_placeholder"},
        )


class MockReviewer(BaseSimulatedReviewer):
    """
    Deterministic mock reviewer for offline unit testing and pipeline verification.
    Does not require any network or LLM API access.
    """

    def __init__(self, default_approved: bool = True, reject_keywords: Optional[list[str]] = None):
        self.default_approved = default_approved
        self.reject_keywords = reject_keywords or ["delete", "drop", "destroy", "rm -rf"]

    def review(
        self,
        tool_call: ToolCall,
        context: TaskContext,
    ) -> ReviewerDecision:
        sanitized = self.sanitize_context(context)
        args_str = json.dumps(tool_call.arguments).lower()
        tool_str = tool_call.tool_name.lower()

        # Reject if any reject keyword is present in tool name or arguments
        for kw in self.reject_keywords:
            if kw in tool_str or kw in args_str:
                return ReviewerDecision(
                    approved=False,
                    reason=f"MockReviewer rejected due to forbidden keyword '{kw}'.",
                    token_cost=0,
                    metadata={"mock": True},
                )

        return ReviewerDecision(
            approved=self.default_approved,
            reason="MockReviewer verdict based on default configuration.",
            token_cost=0,
            metadata={"mock": True},
        )
