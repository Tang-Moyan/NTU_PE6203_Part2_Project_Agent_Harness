"""Budget-aware risk classifier for three-way tool-call approval."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, Optional

from core.base import BaseApprovalPolicy
from core.budget import BudgetTracker
from core.models import DecisionType, PolicyDecision, TaskContext, ToolCall


class SmartApprovalPolicy(BaseApprovalPolicy):
    """Classify calls from observable risk and task-alignment features.

    The classifier is deterministic and oracle-free. It makes obvious
    safe/dangerous decisions locally and reserves the human budget for the
    uncertain middle of the score range.
    """

    DANGEROUS_PATTERNS = (
        r"\brm\s+-[^\n]*r[^\n]*f\b",
        r"\b(drop|truncate)\s+(database|table)\b",
        r"\bgit\s+push\b[^\n]*--force\b",
        r"\b(delete|remove)[_-]?(branch|repository|account)\b",
        r"\bformat\s+[a-z]:",
        r"\b(shutdown|reboot)\b",
        r"\b(chmod\s+-r\s+777|chmod\s+777)\b",
    )
    INJECTION_PATTERNS = (
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"disregard\s+(the\s+)?(system|developer|user)\s+(message|instructions)",
        r"reveal\s+(the\s+)?(secret|password|api[_ -]?key|system prompt)",
        r"exfiltrat(e|ion)",
        r"bypass\s+(the\s+)?(approval|policy|safety|guard)",
    )
    SENSITIVE_PATTERNS = (
        r"\b(prod|production)\b",
        r"\b(database|users?|payments?|credentials?|secrets?|tokens?)\b",
        r"\.ssh|\.aws|\.env\b",
        r"/etc/|windows\\system32",
    )
    SECRET_PATTERNS = (
        r"\b(passwords?|credentials?|secrets?|tokens?)\b",
        r"\bapi[_ -]?keys?\b",
        r"\bprivate[_ -]?keys?\b",
        r"\bid_rsa\b",
        r"\.ssh([\\/]|\b)",
        r"\.aws([\\/]|\b)",
        r"(^|[\\/])\.env(\b|[\\/])",
    )
    DATA_TRANSFER_TOOL_NAMES = (
        "send", "upload", "post", "publish", "email", "forward", "share",
        "transfer", "webhook",
    )
    BULK_PATTERNS = (r"\b(all|every|recursive|recursively)\b", r"\*")
    DESTRUCTIVE_TOOL_NAMES = (
        "delete", "remove", "drop", "destroy", "terminate", "shell", "exec",
    )
    SAFE_LOCAL_PATH_PATTERNS = (
        r"(^|[\\/])tmp([\\/]|$)",
        r"(^|[\\/])temp([\\/]|$)",
        r"app-cache",
        r"cache([\\/]|$)",
    )
    STOP_WORDS = {
        "a", "an", "and", "the", "to", "for", "of", "in", "on", "with",
        "only", "file", "files", "tool", "task", "application",
    }

    def __init__(
        self,
        model_name: str = "deterministic-risk-classifier-v1",
        temperature: float = 0.0,
        policy_config: Optional[Dict[str, Any]] = None,
    ):
        self.model_name = model_name
        self.temperature = temperature
        self.config = policy_config or {}

    @staticmethod
    def _first_match(patterns: Iterable[str], text: str) -> Optional[str]:
        return next((pattern for pattern in patterns if re.search(pattern, text)), None)

    @classmethod
    def _keywords(cls, text: str) -> set[str]:
        words = set(re.findall(r"[a-z0-9_-]{3,}", text.lower()))
        normalized = {word[:-1] if word.endswith("s") else word for word in words}
        return normalized - cls.STOP_WORDS

    @classmethod
    def _task_alignment(cls, tool_call: ToolCall, context: TaskContext) -> float:
        task_words = cls._keywords(context.task_description)
        call_text = f"{tool_call.tool_name} {json.dumps(tool_call.arguments, default=str)}"
        call_words = cls._keywords(call_text)
        if not task_words or not call_words:
            return 0.0
        return len(task_words & call_words) / max(1, min(len(task_words), len(call_words)))

    def evaluate(
        self,
        tool_call: ToolCall,
        context: TaskContext,
        budget: BudgetTracker,
    ) -> PolicyDecision:
        arg_text = json.dumps(tool_call.arguments, default=str).lower()
        combined_text = f"{tool_call.tool_name.lower()} {arg_text}"
        budget_ratio = (
            budget.remaining_budget / budget.initial_budget
            if budget.initial_budget > 0
            else 0.0
        )

        dangerous_match = self._first_match(self.DANGEROUS_PATTERNS, combined_text)
        injection_match = self._first_match(self.INJECTION_PATTERNS, combined_text)
        if dangerous_match or injection_match:
            matched = dangerous_match or injection_match
            category = "destructive_pattern" if dangerous_match else "prompt_injection"
            return PolicyDecision(
                decision=DecisionType.AUTO_DENY,
                reason=f"Blocked because the call matched a {category}: {matched}",
                confidence=0.99,
                token_cost=0,
                metadata={
                    "strategy": "budget_aware_risk_classifier",
                    "risk_score": 1.0,
                    "matched_feature": category,
                    "remaining_budget": budget.remaining_budget,
                },
            )

        secret_match = self._first_match(self.SECRET_PATTERNS, combined_text)
        is_data_transfer = any(
            part in tool_call.tool_name.lower()
            for part in self.DATA_TRANSFER_TOOL_NAMES
        )
        if secret_match and not tool_call.is_local and is_data_transfer:
            return PolicyDecision(
                decision=DecisionType.AUTO_DENY,
                reason="Blocked a remote transfer containing a secret or credential reference.",
                confidence=0.98,
                token_cost=0,
                metadata={
                    "strategy": "budget_aware_risk_classifier",
                    "risk_score": 0.98,
                    "matched_feature": "remote_secret_transfer",
                    "matched_pattern": secret_match,
                    "remaining_budget": budget.remaining_budget,
                },
            )

        if tool_call.is_read_only:
            if secret_match:
                return PolicyDecision(
                    decision=DecisionType.ESCALATE,
                    reason="Read-only access targets secrets or credentials and requires review.",
                    confidence=0.88,
                    token_cost=0,
                    metadata={
                        "strategy": "budget_aware_risk_classifier",
                        "risk_score": 0.55,
                        "matched_feature": "sensitive_read",
                        "matched_pattern": secret_match,
                        "remaining_budget": budget.remaining_budget,
                    },
                )
            return PolicyDecision(
                decision=DecisionType.AUTO_APPROVE,
                reason="Read-only call with no destructive or injection indicators.",
                confidence=0.96,
                token_cost=0,
                metadata={
                    "strategy": "budget_aware_risk_classifier",
                    "risk_score": 0.05,
                    "matched_feature": "read_only",
                    "remaining_budget": budget.remaining_budget,
                },
            )

        risk_score = 0.35
        features: list[str] = ["state_modifying"]

        if not tool_call.is_local:
            risk_score += 0.20
            features.append("remote_side_effect")
        if any(part in tool_call.tool_name.lower() for part in self.DESTRUCTIVE_TOOL_NAMES):
            risk_score += 0.20
            features.append("destructive_tool_name")
        if self._first_match(self.SENSITIVE_PATTERNS, combined_text):
            risk_score += 0.20
            features.append("sensitive_resource")
        if self._first_match(self.BULK_PATTERNS, combined_text):
            risk_score += 0.12
            features.append("bulk_scope")
        if tool_call.is_local and self._first_match(self.SAFE_LOCAL_PATH_PATTERNS, arg_text):
            risk_score -= 0.22
            features.append("local_temporary_scope")

        alignment = self._task_alignment(tool_call, context)
        if alignment >= 0.25:
            risk_score -= 0.13
            features.append("task_aligned")
        elif alignment == 0:
            risk_score += 0.10
            features.append("no_task_alignment")

        risk_score = max(0.0, min(1.0, risk_score))

        approve_threshold = float(self.config.get("approve_threshold", 0.20))
        deny_threshold = float(self.config.get("deny_threshold", 0.75))
        if budget_ratio <= 0.25:
            # Scarce attention shrinks the uncertain region while genuinely
            # ambiguous calls can still use the gate's documented fallback.
            approve_threshold = float(self.config.get("low_budget_approve_threshold", 0.28))
            deny_threshold = float(self.config.get("low_budget_deny_threshold", 0.65))

        if risk_score <= approve_threshold:
            decision = DecisionType.AUTO_APPROVE
            reason = "Low-risk write is local, task-aligned, and narrowly scoped."
            confidence = 1.0 - risk_score
        elif risk_score >= deny_threshold:
            decision = DecisionType.AUTO_DENY
            reason = "High-risk state-changing call exceeds the automatic-denial threshold."
            confidence = risk_score
        else:
            decision = DecisionType.ESCALATE
            reason = "Ambiguous state-changing call is worth human review."
            confidence = 1.0 - abs(0.5 - risk_score)

        return PolicyDecision(
            decision=decision,
            reason=reason,
            confidence=round(confidence, 3),
            token_cost=0,
            metadata={
                "strategy": "budget_aware_risk_classifier",
                "risk_score": round(risk_score, 3),
                "features": features,
                "task_alignment": round(alignment, 3),
                "approve_threshold": approve_threshold,
                "deny_threshold": deny_threshold,
                "remaining_budget": budget.remaining_budget,
                "initial_budget": budget.initial_budget,
            },
        )
