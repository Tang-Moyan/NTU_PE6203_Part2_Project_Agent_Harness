"""
Base reviewer interface and context sanitization logic.

Owner: 曹晓晗
"""

from __future__ import annotations

import copy
from typing import Set

from core.base import BaseHumanReviewer
from core.models import TaskContext, ToolCall


class BaseSimulatedReviewer(BaseHumanReviewer):
    """
    Base class for simulated reviewers with strict oracle-information isolation.
    """

    # Forbidden keys that must NEVER be leaked to the simulated reviewer
    ORACLE_KEYS: Set[str] = {
        "ground_truth",
        "attack_annotation",
        "oracle",
        "is_attack",
        "target_state",
        "malicious_intent",
        "injection_vector",
        "benchmark_label",
    }

    def sanitize_context(self, context: TaskContext) -> TaskContext:
        """
        Strips any benchmark annotations or oracle information from TaskContext.
        Guarantees that the simulated reviewer operates purely under realistic human observation.
        """
        sanitized = copy.deepcopy(context)
        
        # Clean top-level metadata
        for key in list(sanitized.metadata.keys()):
            if any(forbidden in key.lower() for forbidden in self.ORACLE_KEYS):
                sanitized.metadata.pop(key, None)

        # Clean trajectory steps
        for step in sanitized.trajectory:
            if isinstance(step, dict):
                for key in list(step.keys()):
                    if any(forbidden in key.lower() for forbidden in self.ORACLE_KEYS):
                        step.pop(key, None)

        # Clean message metadata
        for msg in sanitized.history_messages:
            for key in list(msg.metadata.keys()):
                if any(forbidden in key.lower() for forbidden in self.ORACLE_KEYS):
                    msg.metadata.pop(key, None)

        return sanitized
