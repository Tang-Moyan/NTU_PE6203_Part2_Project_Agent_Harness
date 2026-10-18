
"""Validate and parse the simulated reviewer's JSON response."""

import json
from core.models import ReviewerDecision


def parse_reviewer_response(text: str, token_cost: int = 0) -> ReviewerDecision:
    try:
        data = json.loads(text)

        if not isinstance(data, dict):
            raise ValueError("Response must be a JSON object.")

        if set(data) != {"approved", "reason"}:
            raise ValueError("Response must contain exactly approved and reason.")

        if type(data["approved"]) is not bool:
            raise ValueError("approved must be a JSON boolean.")

        if not isinstance(data["reason"], str) or not data["reason"].strip():
            raise ValueError("reason must be a non-empty string.")

        return ReviewerDecision(
            approved=data["approved"],
            reason=data["reason"].strip(),
            token_cost=token_cost,
            metadata={"status": "parsed"},
        )

    except (ValueError, TypeError) as error:
        return ReviewerDecision(
            approved=False,
            reason="Review response was invalid; approval could not be established.",
            token_cost=token_cost,
            metadata={
                "status": "parse_error",
                "error": str(error),
            },
        )
