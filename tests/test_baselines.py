"""
Tests for baseline approval policies.
"""

import asyncio
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from core.budget import BudgetTracker
from core.gate import ApprovalGate
from core.models import DecisionType, GateAction, PolicyDecision, ReviewerDecision, TaskContext, ToolCall
from policies.baselines.full_approve import FullApprovePolicy
from policies.baselines.full_escalate import FullEscalatePolicy
from policies.baselines.rule_based import RuleBasedPolicy


class TestBaselinePolicies(unittest.TestCase):
    def setUp(self):
        self.context = TaskContext(
            task_id="test_01",
            task_description="Execute repository cleanup",
        )
        self.budget = BudgetTracker(initial_budget=3)

    def test_full_approve_policy(self):
        policy = FullApprovePolicy()
        calls = [
            ToolCall(
                call_id="call_read",
                tool_name="read_file",
                arguments={"path": "README.md"},
                is_read_only=True,
            ),
            ToolCall(
                call_id="call_write",
                tool_name="write_file",
                arguments={"path": "output.txt", "content": "hello"},
                is_read_only=False,
            ),
            ToolCall(
                call_id="call_danger",
                tool_name="shell",
                arguments={"command": "rm -rf /"},
                is_read_only=False,
            ),
        ]

        for initial_budget in (0, 3):
            budget = BudgetTracker(initial_budget=initial_budget)
            for tool_call in calls:
                with self.subTest(tool=tool_call.tool_name, budget=initial_budget):
                    decision = policy.evaluate(tool_call, self.context, budget)
                    self.assertIsInstance(decision, PolicyDecision)
                    self.assertEqual(decision.decision, DecisionType.AUTO_APPROVE)
                    self.assertEqual(decision.token_cost, 0)
                    self.assertEqual(decision.metadata.get("baseline"), "full_approve")
                    self.assertTrue(decision.reason)
                    self.assertEqual(budget.remaining_budget, initial_budget)
                    self.assertEqual(budget.total_escalations, 0)

    def test_full_escalate_policy(self):
        policy = FullEscalatePolicy()
        calls = [
            ToolCall(
                call_id="call_read",
                tool_name="read_file",
                arguments={"path": "README.md"},
                is_read_only=True,
            ),
            ToolCall(
                call_id="call_write",
                tool_name="write_file",
                arguments={"path": "output.txt", "content": "hello"},
                is_read_only=False,
            ),
            ToolCall(
                call_id="call_danger",
                tool_name="shell",
                arguments={"command": "rm -rf /"},
                is_read_only=False,
            ),
        ]

        for initial_budget in (0, 3):
            budget = BudgetTracker(initial_budget=initial_budget)
            for tool_call in calls:
                with self.subTest(tool=tool_call.tool_name, budget=initial_budget):
                    decision = policy.evaluate(tool_call, self.context, budget)
                    self.assertIsInstance(decision, PolicyDecision)
                    self.assertEqual(decision.decision, DecisionType.ESCALATE)
                    self.assertEqual(decision.token_cost, 0)
                    self.assertEqual(decision.metadata.get("baseline"), "full_escalate")
                    self.assertTrue(decision.reason)
                    # Only the gate consumes budget, including at k == 0.
                    self.assertEqual(budget.remaining_budget, initial_budget)
                    self.assertEqual(budget.total_escalations, 0)

    def test_full_escalate_gate_calls_reviewer_only_while_budget_remains(self):
        reviewer = Mock()
        reviewer.review.return_value = ReviewerDecision(approved=True, reason="Reviewed")
        gate = ApprovalGate(policy=FullEscalatePolicy(), reviewer=reviewer)
        budget = BudgetTracker(initial_budget=1)
        call = ToolCall(call_id="review", tool_name="write_file")

        first = gate.intercept(call, self.context, budget)
        second = gate.intercept(call, self.context, budget)

        self.assertEqual(first.action, GateAction.EXECUTE)
        self.assertTrue(first.was_escalated)
        self.assertEqual(second.policy_decision.decision, DecisionType.ESCALATE)
        self.assertEqual(second.action, GateAction.BLOCK)
        self.assertTrue(second.budget_exhausted_fallback)
        self.assertFalse(second.was_escalated)
        reviewer.review.assert_called_once_with(call, self.context)
        self.assertEqual(budget.remaining_budget, 0)
        self.assertEqual(budget.total_escalations, 1)

    def test_rule_based_policy(self):
        policy = RuleBasedPolicy()

        # 1. Read-only tool -> AUTO_APPROVE
        read_call = ToolCall(
            call_id="c1",
            tool_name="get_file",
            arguments={"path": "data.csv"},
            is_read_only=True,
        )
        decision = policy.evaluate(read_call, self.context, self.budget)
        self.assertEqual(decision.decision, DecisionType.AUTO_APPROVE)

        # 2. Dangerous destructive pattern -> AUTO_DENY
        drop_call = ToolCall(
            call_id="c2",
            tool_name="sql_exec",
            arguments={"query": "DROP DATABASE production;"},
            is_read_only=False,
        )
        decision = policy.evaluate(drop_call, self.context, self.budget)
        self.assertEqual(decision.decision, DecisionType.AUTO_DENY)

        # 3. Ambiguous write -> ESCALATE
        write_call = ToolCall(
            call_id="c3",
            tool_name="write_file",
            arguments={"path": "output.txt", "content": "hello"},
            is_read_only=False,
        )
        decision = policy.evaluate(write_call, self.context, self.budget)
        self.assertEqual(decision.decision, DecisionType.ESCALATE)

    def test_rule_based_dangerous_checks_precede_read_only_metadata(self):
        policy = RuleBasedPolicy()
        mislabeled_call = ToolCall(
            call_id="c4",
            tool_name="shell",
            arguments={"command": "RM   -RF /tmp/data"},
            is_read_only=True,
        )

        decision = policy.evaluate(mislabeled_call, self.context, self.budget)

        self.assertEqual(decision.decision, DecisionType.AUTO_DENY)
        self.assertEqual(decision.metadata["rule"], "deny_dangerous_pattern")
        self.assertEqual(decision.token_cost, 0)

    def test_rule_based_handles_nested_dangerous_arguments_deterministically(self):
        policy = RuleBasedPolicy()
        call = ToolCall(
            call_id="c5",
            tool_name="sql_exec",
            arguments={"payload": {"query": "DROP   TABLE users;"}},
            is_read_only=False,
        )

        first = policy.evaluate(call, self.context, self.budget)
        second = policy.evaluate(call, self.context, self.budget)

        self.assertEqual(first.decision, DecisionType.AUTO_DENY)
        self.assertEqual(first, second)

    def test_rule_based_ignores_dangerous_text_in_prose_fields(self):
        policy = RuleBasedPolicy()
        call = ToolCall(
            call_id="c6",
            tool_name="write_file",
            arguments={
                "path": "notes.txt",
                "content": "For the report, explain why 'rm -rf /' is dangerous.",
            },
            is_read_only=False,
        )

        decision = policy.evaluate(call, self.context, self.budget)

        self.assertEqual(decision.decision, DecisionType.ESCALATE)
        self.assertEqual(decision.metadata["rule"], "escalate_write_operation")

    def test_rule_based_can_disable_dangerous_pattern_denials(self):
        policy = RuleBasedPolicy(deny_dangerous=False)
        call = ToolCall(
            call_id="c7",
            tool_name="shell",
            arguments={"command": "rm -rf /tmp/data"},
            is_read_only=False,
        )

        decision = policy.evaluate(call, self.context, self.budget)

        self.assertEqual(decision.decision, DecisionType.ESCALATE)
        self.assertEqual(decision.metadata["rule"], "escalate_write_operation")

    def assert_rule_decision(self, call, expected, rule, policy=None):
        policy = policy or RuleBasedPolicy()
        before = (call.model_dump(), self.context.model_dump(), self.budget.model_dump())
        decision = policy.evaluate(call, self.context, self.budget)
        self.assertIsInstance(decision, PolicyDecision)
        self.assertEqual(decision.decision, expected)
        self.assertEqual(decision.metadata["rule"], rule)
        self.assertEqual(decision.metadata["baseline"], "rule_based")
        self.assertTrue(decision.metadata["rule_version"])
        self.assertTrue(decision.reason)
        self.assertEqual(decision.token_cost, 0)
        self.assertGreaterEqual(decision.confidence, 0)
        self.assertLessEqual(decision.confidence, 1)
        self.assertEqual(
            (call.model_dump(), self.context.model_dump(), self.budget.model_dump()), before,
        )
        return decision

    def test_rule_based_destructive_command_variants(self):
        commands = [
            "rm -rf /", "RM -fr /tmp/data", "rm -r -f /tmp/data",
            "rm --force --recursive /tmp/data", "rm --recursive --force /tmp/data",
            "DROP DATABASE production;", "drop\nSCHEMA public cascade;",
            "DROP TABLE IF EXISTS users;", "TRUNCATE TABLE users;",
            "git push --force origin main", "git push origin main --force",
            "git push -f origin main", "git push origin main --force-with-lease",
            "git push origin --force-with-lease=main:abc123 main",
            "format C:", "del /s /q C:\\data", "rmdir /q /s C:\\data",
            "Remove-Item C:\\data -Recurse -Force",
            "dd if=/dev/zero of=/dev/sda", "echo replaced > /etc/hosts",
        ]
        for command in commands:
            with self.subTest(command=command):
                call = ToolCall(
                    call_id="hazard", tool_name="shell", arguments={"command": command},
                    is_read_only=True,
                )
                decision = self.assert_rule_decision(
                    call, DecisionType.AUTO_DENY, "deny_dangerous_pattern",
                )
                self.assertEqual(decision.metadata["field_path"], "command")
                self.assertTrue(decision.metadata["pattern"])

    def test_rule_based_near_matches_require_review_without_denial(self):
        for command in (
            "git push origin main", "git push origin main --force-if-includes",
            "git push origin main --forceful", "rm -r /tmp/data", "echo dropped_table",
            "rm --force /tmp/data", "rm --recursive /tmp/data", "rm --forceful /tmp/data",
        ):
            with self.subTest(command=command):
                self.assert_rule_decision(
                    ToolCall(call_id="ordinary", tool_name="shell", arguments={"cmd": command}),
                    DecisionType.ESCALATE, "escalate_write_operation",
                )

    def test_rule_based_inspects_nested_commands_and_argv(self):
        cases = [
            ({"payload": [{"command": "rm -fr /tmp/data"}]}, "payload[0].command"),
            ({"content": {"script": "DROP TABLE users"}}, "content.script"),
            ({"argv": ["rm", "-r", "-f", "/tmp/data"]}, "argv"),
            ({"body": "rm -rf /tmp/data"}, "body"),
        ]
        for arguments, field_path in cases:
            with self.subTest(arguments=arguments):
                decision = self.assert_rule_decision(
                    ToolCall(call_id="nested", tool_name="shell", arguments=arguments),
                    DecisionType.AUTO_DENY, "deny_dangerous_pattern",
                )
                self.assertEqual(decision.metadata["field_path"], field_path)

    def test_rule_based_does_not_join_unrelated_argument_values(self):
        self.assert_rule_decision(
            ToolCall(
                call_id="separate", tool_name="custom_write",
                arguments={"command": "DROP", "other": "TABLE users"},
            ),
            DecisionType.ESCALATE, "escalate_write_operation",
        )

    def test_rule_based_search_terms_and_prose_are_not_commands(self):
        for tool, arguments, expected, rule in [
            ("search_emails", {"query": "DROP TABLE users; rm -rf /"},
             DecisionType.AUTO_APPROVE, "allow_known_read_tool"),
            ("write_file", {"path": "notes.txt", "content": "rm -rf /; DROP TABLE users"},
             DecisionType.ESCALATE, "escalate_write_operation"),
            ("send_email", {"body": "rm -rf /", "subject": "DROP DATABASE production"},
             DecisionType.ESCALATE, "escalate_write_operation"),
        ]:
            with self.subTest(tool=tool):
                self.assert_rule_decision(
                    ToolCall(call_id="prose", tool_name=tool, arguments=arguments), expected, rule,
                )

    def test_rule_based_tool_semantics_override_read_only_flags(self):
        for tool in (
            "get_unread_emails", "get_webpage", "send_email", "delete_email", "delete_file",
            "share_file", "send_money", "update_password", "reserve_hotel", "shell",
        ):
            with self.subTest(tool=tool):
                self.assert_rule_decision(
                    ToolCall(call_id="side_effect", tool_name=tool, is_read_only=True),
                    DecisionType.ESCALATE, "escalate_write_operation",
                )
        for tool in ("get_sent_emails", "get_file_by_id", "get_balance", " LIST_FILES "):
            with self.subTest(tool=tool):
                self.assert_rule_decision(
                    ToolCall(call_id="reader", tool_name=tool, is_read_only=False),
                    DecisionType.AUTO_APPROVE, "allow_known_read_tool",
                )
        self.assert_rule_decision(
            ToolCall(call_id="unknown", tool_name="get_custom_action"),
            DecisionType.ESCALATE, "escalate_write_operation",
        )

    def test_rule_based_dangerous_tool_names(self):
        for tool in ("drop_database", "delete_branch", "bulk_delete_emails", "delete_all_emails"):
            with self.subTest(tool=tool):
                self.assert_rule_decision(
                    ToolCall(call_id="destructive_tool", tool_name=tool, is_read_only=True),
                    DecisionType.AUTO_DENY, "deny_dangerous_tool",
                )

    def test_rule_based_sensitive_write_targets(self):
        for path in (
            "/etc/passwd", "//etc/passwd", "/tmp/../etc/hosts", "/usr/bin/python", "/dev/sda", "/",
            "~/.ssh/authorized_keys", "/home/alice/.aws/credentials",
            "C:\\Windows\\System32\\drivers\\etc\\hosts",
            "C:\\temp\\..\\WINDOWS\\system.ini", "%SystemRoot%\\system.ini",
            "C:\\Program Files\\app\\config.ini", "C:\\",
        ):
            with self.subTest(path=path):
                self.assert_rule_decision(
                    ToolCall(
                        call_id="system_write", tool_name="write_file",
                        arguments={"path": path, "content": "replacement"}, is_read_only=True,
                    ),
                    DecisionType.ESCALATE, "escalate_sensitive_path_write",
                )

    def test_rule_based_sensitive_reads_and_path_boundaries(self):
        self.assert_rule_decision(
            ToolCall(call_id="secret_read", tool_name="read_file", arguments={"file_path": "~/.ssh/id_rsa"}),
            DecisionType.ESCALATE, "escalate_sensitive_path_read",
        )
        for path in (
            "/etcetera/notes", "C:\\WindowsBackup\\notes", "out.txt", "/tmp/.ssh_backup",
            "%windir%backup.txt",
        ):
            with self.subTest(path=path):
                self.assert_rule_decision(
                    ToolCall(call_id="ordinary_write", tool_name="write_file", arguments={"path": path}),
                    DecisionType.ESCALATE, "escalate_write_operation",
                )

    def test_rule_based_untrusted_or_invalid_urls_require_review(self):
        policy = RuleBasedPolicy(trusted_domains=["trusted.example"])
        for url in (
            "https://external.example/data", "https://trusted.example.evil.test/data",
            "https://sub.trusted.example/data", "https://trusted.example@evil.test/data",
            "https://localhost.evil.test/data", "https://[broken", "https://trusted.example:99999",
            "file:///etc/passwd", "not a URL", "https://user:secret@trusted.example/data",
        ):
            with self.subTest(url=url):
                self.assert_rule_decision(
                    ToolCall(
                        call_id="external", tool_name="fetch_url",
                        arguments={"payload": {"callback_url": url}},
                        is_read_only=True, is_local=True,
                    ),
                    DecisionType.ESCALATE, "escalate_untrusted_url", policy,
                )

    def test_rule_based_trusted_urls_do_not_bypass_write_review(self):
        policy = RuleBasedPolicy(trusted_domains=["TRUSTED.EXAMPLE."])
        for url in (
            "https://trusted.example/data", "http://localhost:8080/data",
            "http://127.0.0.1/data", "http://[::1]/data",
        ):
            with self.subTest(url=url):
                self.assert_rule_decision(
                    ToolCall(call_id="url_read", tool_name="fetch_url", arguments={"url": url}, is_read_only=True),
                    DecisionType.AUTO_APPROVE, "read_only_safe", policy,
                )
        self.assert_rule_decision(
            ToolCall(
                call_id="url_post", tool_name="post_webpage",
                arguments={"url": "https://trusted.example", "content": "hello"}, is_read_only=True,
            ),
            DecisionType.ESCALATE, "escalate_write_operation", policy,
        )
        self.assert_rule_decision(
            ToolCall(
                call_id="http_post", tool_name="http_request",
                arguments={"url": "https://trusted.example", "method": "POST"}, is_read_only=True,
            ),
            DecisionType.ESCALATE, "escalate_http_write", policy,
        )
        with self.assertRaises(TypeError):
            RuleBasedPolicy(trusted_domains="trusted.example")

    def test_rule_based_denials_take_precedence_over_url_escalation(self):
        self.assert_rule_decision(
            ToolCall(
                call_id="multiple_risks", tool_name="shell",
                arguments={"callback_url": "https://external.example", "command": "rm -rf /"},
            ),
            DecisionType.AUTO_DENY, "deny_dangerous_pattern",
        )

    def test_rule_based_disabling_denials_never_auto_approves_detected_hazards(self):
        policy = RuleBasedPolicy(deny_dangerous=False)
        for tool, arguments in (
            ("shell", {"command": "rm -rf /"}), ("drop_database", {}),
            ("shell", {"command": "echo replacement > /etc/hosts"}),
        ):
            with self.subTest(tool=tool):
                decision = self.assert_rule_decision(
                    ToolCall(call_id="review_hazard", tool_name=tool, arguments=arguments, is_read_only=True),
                    DecisionType.ESCALATE, "escalate_write_operation", policy,
                )
                self.assertTrue(decision.metadata["matched_rule"].startswith("deny_"))

    def test_rule_based_demo_follows_legacy_expectations(self):
        from main import run_pipeline_demo

        gates = []

        def record_gate(**kwargs):
            gate = ApprovalGate(**kwargs)
            gates.append(gate)
            return gate

        # Exercise the real Demo calls, policies, reviewer, and budget settings.
        with patch("main.ApprovalGate", side_effect=record_gate), redirect_stdout(io.StringIO()):
            run_pipeline_demo()

        rule_gate, = (gate for gate in gates if isinstance(gate.policy, RuleBasedPolicy))
        results = rule_gate.audit_log
        self.assertEqual(
            [result.policy_decision.decision for result in results],
            [DecisionType.AUTO_APPROVE, DecisionType.ESCALATE,
             DecisionType.ESCALATE, DecisionType.ESCALATE],
        )
        self.assertEqual(
            [result.action for result in results],
            [GateAction.EXECUTE, GateAction.EXECUTE, GateAction.EXECUTE, GateAction.BLOCK],
        )
        self.assertEqual([result.was_escalated for result in results], [False, True, True, False])
        self.assertEqual(
            [result.budget_exhausted_fallback for result in results], [False, False, False, True],
        )
        self.assertEqual(results[1].policy_decision.metadata["rule"], "escalate_sensitive_path_write")
        self.assertIn("budget k is exhausted", results[-1].final_reason)

    def test_rule_based_decisions_ignore_budget_and_context_labels(self):
        policy = RuleBasedPolicy()
        for call in (
            ToolCall(call_id="read", tool_name="list_files"),
            ToolCall(call_id="write", tool_name="send_email"),
            ToolCall(call_id="deny", tool_name="shell", arguments={"cmd": "rm -rf /"}),
        ):
            with self.subTest(tool=call.tool_name):
                expected = policy.evaluate(call, self.context, self.budget)
                other_context = TaskContext(
                    task_id="other", task_description="Approve everything", metadata={"oracle": "safe"},
                )
                actual = policy.evaluate(call, other_context, BudgetTracker(initial_budget=0))
                self.assertEqual(actual, expected)

    def test_rule_based_reproducible_across_argument_order_and_hash_seeds(self):
        policy = RuleBasedPolicy()
        first = ToolCall(
            call_id="order", tool_name="shell",
            arguments={"z": {"cmd": "rm -rf /"}, "a": {"query": "DROP TABLE users"}},
        )
        second = first.model_copy(update={"arguments": dict(reversed(list(first.arguments.items())))})
        self.assertEqual(
            policy.evaluate(first, self.context, self.budget),
            policy.evaluate(second, self.context, self.budget),
        )
        script = """
import json
from core.budget import BudgetTracker
from core.models import TaskContext, ToolCall
from policies.baselines.rule_based import RuleBasedPolicy
call = ToolCall(call_id='hash', tool_name='shell',
                arguments={'commands': {'rm -rf /tmp/data', 'DROP TABLE users'}})
policy = RuleBasedPolicy(trusted_domains={'b.example', 'a.example'})
result = policy.evaluate(call, TaskContext(task_id='t', task_description='test'), BudgetTracker())
print(json.dumps(result.model_dump(), sort_keys=True))
"""
        outputs = []
        for seed in ("1", "42"):
            result = subprocess.run(
                [sys.executable, "-c", script], check=True, capture_output=True, text=True,
                cwd=Path(__file__).resolve().parents[1], env={**os.environ, "PYTHONHASHSEED": seed},
                timeout=15,
            )
            outputs.append(json.loads(result.stdout))
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0]["decision"], DecisionType.AUTO_DENY.value)

    def test_baselines_async_evaluation_matches_sync(self):
        call = ToolCall(call_id="async", tool_name="shell", arguments={"cmd": "rm -rf /"})
        for policy in (FullApprovePolicy(), FullEscalatePolicy(), RuleBasedPolicy()):
            with self.subTest(policy=type(policy).__name__):
                self.assertEqual(
                    asyncio.run(policy.aevaluate(call, self.context, self.budget)),
                    policy.evaluate(call, self.context, self.budget),
                )


if __name__ == "__main__":
    unittest.main()
