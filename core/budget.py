"""
Budget tracking module for human attention budget k per task.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BudgetTracker(BaseModel):
    """
    Tracks and enforces the escalation budget k for a single task.
    
    Once the budget is exhausted (remaining == 0), no further escalations
    are permitted, and any policy decision requiring escalation will degrade
    to an automatic denial.
    """
    initial_budget: int = Field(ge=0, description="Initial escalation budget k")
    remaining_budget: int = Field(ge=0, description="Remaining escalation allowance")
    total_escalations: int = Field(default=0, ge=0, description="Total escalations performed")

    def __init__(self, initial_budget: int = 0, **data):
        if "remaining_budget" not in data:
            data["remaining_budget"] = max(0, initial_budget)
        super().__init__(initial_budget=max(0, initial_budget), **data)

    @property
    def is_exhausted(self) -> bool:
        """Returns True if the human escalation budget has reached 0."""
        return self.remaining_budget <= 0

    def can_escalate(self) -> bool:
        """Checks whether an escalation can be granted within the budget."""
        return self.remaining_budget > 0

    def consume(self) -> bool:
        """
        Consumes one unit of escalation budget if available.
        
        Returns:
            True if budget was available and consumed; False if already exhausted.
        """
        if self.remaining_budget > 0:
            self.remaining_budget -= 1
            self.total_escalations += 1
            return True
        return False

    def reset(self, new_budget: int | None = None) -> None:
        """Resets the budget tracker for a new task or new budget parameter."""
        if new_budget is not None:
            self.initial_budget = max(0, new_budget)
        self.remaining_budget = self.initial_budget
        self.total_escalations = 0
