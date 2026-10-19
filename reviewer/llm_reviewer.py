"""
LLM-simulated Human Reviewer implementation.

Owner: 曹晓晗

Configuration: REVIEWER_MODEL, REVIEWER_API_KEY, REVIEWER_BASE_URL.
The base URL is optional for the OpenAI service; other providers must set it.
Only OpenAI-compatible Chat Completions endpoints are supported by this client.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from core.models import ReviewerDecision, TaskContext, ToolCall
from reviewer.base import BaseSimulatedReviewer
from reviewer.prompt_templates import REVIEWER_SYSTEM_PROMPT, REVIEWER_USER_PROMPT_TEMPLATE


class LLMSimulatedReviewer(BaseSimulatedReviewer):
    """Review an escalated call; return a decision without executing any tool.

    Gate owns escalation routing and budget consumption. A supplied client is
    useful for offline tests. No model or secret is hard-coded in this file.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        temperature: Optional[float] = 0.0,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        client: Any = None,
    ):
        self.model_name = model_name or os.getenv("REVIEWER_MODEL")
        self.temperature = temperature
        self.api_key = api_key or os.getenv("REVIEWER_API_KEY")
        self.base_url = base_url or os.getenv("REVIEWER_BASE_URL")
        self.client = client

    def _clean_history(self, value: Any) -> Any:
        """Remove known oracle keys recursively; never mutate the source trace.

        This is defense in depth, not a semantic scrubber of arbitrary text.
        The context builder must supply only human-visible task/history data.
        """
        forbidden_keys = self.ORACLE_KEYS | {
            "success_condition", "vulnerability_description", "attack_success",
        }
        if isinstance(value, dict):
            return {
                key: self._clean_history(item)
                for key, item in value.items()
                if not any(word in str(key).lower() for word in forbidden_keys)
            }
        if isinstance(value, list):
            return [self._clean_history(item) for item in value]
        return value

    def _deny(self, status: str, reason: str, tokens: int = 0, **metadata) -> ReviewerDecision:
        return ReviewerDecision(
            approved=False,
            reason=reason,
            token_cost=tokens,
            metadata={"model": self.model_name, "status": status, **metadata},
        )

    @staticmethod
    def _usage(response: Any) -> Dict[str, Any]:
        usage = getattr(response, "usage", None)

        def count(name):
            value = getattr(usage, name, None)
            return value if type(value) is int and value >= 0 else None

        prompt = count("prompt_tokens")
        completion = count("completion_tokens")
        total = count("total_tokens")
        if total is None and prompt is not None and completion is not None:
            total = prompt + completion
        return {
            "total_tokens": total,
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "usage_available": total is not None,
        }

    def review(self, tool_call: ToolCall, context: TaskContext) -> ReviewerDecision:
        # Required first step: use the existing context sanitization hook.
        sanitized_context = self.sanitize_context(context)

        # Explicitly select human-visible fields. Do not send task IDs, arbitrary
        # context/tool metadata, raw_call, or benchmark evaluation objects.
        history = self._clean_history({
            "messages": [
                {"role": message.role, "content": message.content}
                for message in sanitized_context.history_messages
            ],
            "trajectory": sanitized_context.trajectory,
        })
        user_prompt = REVIEWER_USER_PROMPT_TEMPLATE.format(
            task_description=sanitized_context.task_description,
            tool_name=tool_call.tool_name,
            tool_arguments=json.dumps(tool_call.arguments, ensure_ascii=False),
            sanitized_history=json.dumps(history, ensure_ascii=False),
        )

        if not self.model_name or (self.client is None and not self.api_key):
            return self._deny(
                "configuration_error",
                "Reviewer model/API key is not configured; no review was performed.",
                usage_available=False,
            )

        request = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": REVIEWER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        }
        if self.temperature is not None:
            request["temperature"] = self.temperature

        try:
            if self.client is None:
                from openai import OpenAI

                options = {"api_key": self.api_key, "timeout": 30.0, "max_retries": 0}
                if self.base_url:
                    options["base_url"] = self.base_url
                self.client = OpenAI(**options)
            response = self.client.chat.completions.create(**request)
        except Exception as error:
            # Do not log the raw exception, prompt, or API key. A timeout can
            # occur after billing, so missing usage is unknown, not free usage.
            return self._deny(
                "api_error", "Reviewer API failed; execution is not approved.",
                error_type=type(error).__name__, usage_available=False,
            )

        usage = self._usage(response)
        tokens = usage["total_tokens"] if usage["usage_available"] else 0
        choices = getattr(response, "choices", None)
        if not choices:
            return self._deny("response_error", "Reviewer returned no choice.", tokens, **usage)

        choice = choices[0]
        message = getattr(choice, "message", None)
        if getattr(message, "refusal", None):
            return self._deny("model_refusal", "The reviewer declined to decide.", tokens, **usage)
        if getattr(choice, "finish_reason", None) != "stop":
            return self._deny(
                "response_error", "Reviewer response was incomplete or filtered.", tokens, **usage
            )

        try:
            data = json.loads(getattr(message, "content", None) or "")
            if not isinstance(data, dict) or set(data) != {"approved", "reason"}:
                raise ValueError("Expected exactly approved and reason.")
            if type(data["approved"]) is not bool:
                raise ValueError("approved must be a JSON boolean.")
            if not isinstance(data["reason"], str) or not data["reason"].strip():
                raise ValueError("reason must be a non-empty string.")
        except (ValueError, TypeError):
            return self._deny(
                "parse_error", "Invalid reviewer JSON; execution is not approved.",
                tokens, parse_error=True, **usage,
            )

        return ReviewerDecision(
            approved=data["approved"],
            reason=data["reason"].strip(),
            token_cost=tokens,
            metadata={"model": self.model_name, "status": "parsed", **usage},
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
