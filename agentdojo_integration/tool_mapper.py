"""Infer tool metadata and strip oracle fields from AgentDojo payloads.

The heuristics mirror the v1 tool semantics documented in
``policies/baselines/RULE_BASED_POLICY.md``. They are not a second policy:
they only fill ``ToolCall.is_read_only`` and ``ToolCall.is_local`` when the
benchmark function object does not carry those flags.
"""

from __future__ import annotations

from typing import Any, Mapping

# Reads that mutate suite state. A true read-only flag must not hide that.
SIDE_EFFECT_READ_TOOLS = frozenset({"get_unread_emails", "get_webpage"})

READ_PREFIXES = ("get_", "read_", "list_", "search_", "check_")
WRITE_PREFIXES = (
    "write_",
    "create_",
    "delete_",
    "remove_",
    "update_",
    "append_",
    "send_",
    "share_",
    "post_",
    "reserve_",
    "cancel_",
    "reschedule_",
    "add_",
    "invite_",
    "schedule_",
    "execute_",
    "run_",
    "set_",
    "upload_",
    "move_",
    "copy_",
)
REMOTE_TOOLS = frozenset({"get_webpage", "post_webpage"})
REMOTE_PREFIXES = ("send_", "post_", "upload_", "share_")

# Substrings that mark benchmark answers. "goal" is exact-matched separately
# so an argument such as "goal_amount" stays visible to the policy.
ORACLE_KEY_FRAGMENTS = (
    "ground_truth",
    "placeholder_args",
    "attack_annotation",
    "is_attack",
    "injection_vector",
    "benchmark_label",
    "target_state",
    "malicious_intent",
    "oracle",
)
ORACLE_EXACT_KEYS = frozenset({"goal"})


def is_oracle_key(key: str) -> bool:
    """Return True when a mapping key is benchmark-only information."""
    lowered = str(key).lower()
    if lowered in ORACLE_EXACT_KEYS:
        return True
    return any(fragment in lowered for fragment in ORACLE_KEY_FRAGMENTS)


def infer_tool_flags(tool_name: str, description: str = "") -> tuple[bool, bool]:
    """Return ``(is_read_only, is_local)`` for an AgentDojo function name.

    Unknown tools are treated as state-changing and local. That keeps a missing
    name from being auto-approved merely because the flag defaulted to safe.
    """
    name = tool_name.strip().lower()
    if name in SIDE_EFFECT_READ_TOOLS:
        is_read_only = False
    elif name.startswith(WRITE_PREFIXES):
        is_read_only = False
    elif name.startswith(READ_PREFIXES):
        is_read_only = True
    else:
        lowered_doc = description.lower()
        is_read_only = "read-only" in lowered_doc or "does not modify" in lowered_doc

    is_local = name not in REMOTE_TOOLS and not name.startswith(REMOTE_PREFIXES)
    return is_read_only, is_local


def normalize_args(value: Any) -> Any:
    """Copy arguments, dropping nested oracle keys and placeholder payloads."""
    if isinstance(value, Mapping):
        return {
            str(key): normalize_args(item)
            for key, item in value.items()
            if not is_oracle_key(str(key))
        }
    if isinstance(value, list):
        return [normalize_args(item) for item in value]
    if hasattr(value, "function") and hasattr(value, "args"):
        nested = getattr(value, "args", {}) or {}
        return {
            "function": getattr(value, "function"),
            "args": normalize_args(nested if isinstance(nested, Mapping) else {}),
        }
    return value
