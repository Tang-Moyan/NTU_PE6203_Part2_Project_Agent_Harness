"""Run one real AgentDojo suite tool through the approval runtime.

From the repository root:

    pip install -r requirements-agentdojo.txt
    python scripts/smoke_agentdojo.py

The script loads the upstream workspace suite. It does not score utility or
security and it does not write benchmark results.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentdojo_integration.session import DEFAULT_BENCHMARK_VERSION, ApprovalSession
from policies.baselines.full_escalate import FullEscalatePolicy
from reviewer.llm_reviewer import MockReviewer


def main() -> int:
    try:
        from agentdojo_integration.session import load_suite
    except ImportError:
        print("[SKIP] agentdojo is not installed")
        print("Install with: pip install -r requirements-agentdojo.txt")
        print("=== Done ===")
        return 0

    try:
        suite = load_suite("workspace", DEFAULT_BENCHMARK_VERSION)
    except ImportError:
        print("[SKIP] agentdojo is not installed")
        print("Install with: pip install -r requirements-agentdojo.txt")
        print("=== Done ===")
        return 0

    user_task = next(iter(suite.user_tasks.values()))
    session = ApprovalSession(
        FullEscalatePolicy(),
        MockReviewer(default_approved=True),
        budget_k=0,
        suite_name=suite.name,
    )
    session.begin_task(user_task, suite_name=suite.name)
    context = session.current_context()
    if context.task_description != user_task.PROMPT:
        print("[FAIL] TaskContext did not keep the user prompt")
        return 1
    hidden = getattr(user_task, "GROUND_TRUTH_OUTPUT", "") or ""
    if hidden.strip() and hidden in context.model_dump_json():
        print("[FAIL] Ground-truth output leaked into TaskContext")
        return 1

    environment = user_task.init_environment(suite.load_and_inject_default_environment({}))
    before = environment.model_dump()
    runtime = session.create_runtime(suite.tools)
    tool_name = next(iter(runtime.functions))
    value, error = runtime.run_function(environment, tool_name, {})
    if environment.model_dump() != before:
        print("[FAIL] Blocked tool changed the suite environment")
        return 1
    if not str(error).startswith("PermissionDenied") or "[Permission Denied]" not in str(value):
        print(f"[FAIL] Expected a permission denial, got value={value!r} error={error!r}")
        return 1
    if not session.gate.audit_log[-1].budget_exhausted_fallback:
        print("[FAIL] k=0 did not degrade ESCALATE to BLOCK")
        return 1

    print(f"[PASS] Loaded AgentDojo suite {suite.name} {DEFAULT_BENCHMARK_VERSION}")
    print(f"[PASS] User prompt kept ({user_task.ID}); oracle output was not copied")
    print(f"[PASS] {tool_name} blocked before execution; environment unchanged")
    print(f"       tools={len(runtime.functions)} audit_entries={len(session.gate.audit_log)}")
    print("=== Done ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
