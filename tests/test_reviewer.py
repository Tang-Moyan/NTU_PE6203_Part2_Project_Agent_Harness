"""
Tests for simulated human reviewer and oracle information isolation.
"""

import unittest
from core.models import Message, TaskContext, ToolCall
from reviewer.base import BaseSimulatedReviewer
from reviewer.llm_reviewer import MockReviewer


class TestReviewer(unittest.TestCase):
    def test_oracle_sanitization(self):
        reviewer = MockReviewer()
        
        # Context containing accidental benchmark ground truth / attack annotations
        contaminated_context = TaskContext(
            task_id="task_leak",
            task_description="Search for users",
            metadata={
                "safe_user_data": 123,
                "ground_truth": "The secret target token is xyz",
                "is_attack": True,
                "attack_annotation": "Prompt injection detected in parameter",
            },
            history_messages=[
                Message(
                    role="system",
                    content="benchmark harness",
                    metadata={"oracle": "attack_success_condition"},
                )
            ],
            trajectory=[
                {"step": 1, "oracle_state": "vulnerable"},
                {"step": 2, "normal_state": "ok"},
            ],
        )

        sanitized = reviewer.sanitize_context(contaminated_context)

        # Verify that all oracle keys have been stripped
        self.assertIn("safe_user_data", sanitized.metadata)
        self.assertNotIn("ground_truth", sanitized.metadata)
        self.assertNotIn("is_attack", sanitized.metadata)
        self.assertNotIn("attack_annotation", sanitized.metadata)
        self.assertNotIn("oracle", sanitized.history_messages[0].metadata)
        self.assertNotIn("oracle_state", sanitized.trajectory[0])
        self.assertIn("normal_state", sanitized.trajectory[1])

    def test_mock_reviewer_decisions(self):
        reviewer = MockReviewer(default_approved=True, reject_keywords=["delete", "drop"])
        context = TaskContext(task_id="t1", task_description="Perform update")

        # Call with safe arguments
        safe_call = ToolCall(
            call_id="c1",
            tool_name="update_record",
            arguments={"id": 1, "status": "active"},
        )
        dec_safe = reviewer.review(safe_call, context)
        self.assertTrue(dec_safe.approved)

        # Call with dangerous keyword
        danger_call = ToolCall(
            call_id="c2",
            tool_name="delete_record",
            arguments={"id": 1},
        )
        dec_danger = reviewer.review(danger_call, context)
        self.assertFalse(dec_danger.approved)



# LLM reviewer integration tests: no network, API key, or paid calls.
import os
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.budget import BudgetTracker
from core.gate import ApprovalGate
from core.models import GateAction
from policies.baselines.full_escalate import FullEscalatePolicy
from reviewer.llm_reviewer import LLMSimulatedReviewer
from reviewer.prompt_templates import REVIEWER_SYSTEM_PROMPT


class TestLLMSimulatedReviewer(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.reviewer = LLMSimulatedReviewer(model_name="offline-model", client=self.client)
        self.context = TaskContext(
            task_id="TASK_ID_NOT_FOR_PROMPT",
            task_description="Read application logs and summarize errors.",
            metadata={"ground_truth": "TOP_SECRET", "debug": "META_SECRET"},
            history_messages=[Message(
                role="tool", content="Observed log entry: connection failed.",
                metadata={"is_attack": "MESSAGE_SECRET"},
            )],
            trajectory=[{
                "step": 1,
                "details": [{"attack_annotation": "NESTED_SECRET", "observation": "log available"}],
                "benchmark_success_condition": "SUCCESS_SECRET",
            }],
        )
        self.call = ToolCall(
            call_id="c1", tool_name="read_logs", arguments={"path": "/var/log/app.log"},
            is_read_only=True, metadata={"oracle": "TOOL_META_SECRET"},
            raw_call={"benchmark_label": "RAW_SECRET"},
        )
        self.set_response('{"approved": true, "reason": "Authorized log read."}')

    def set_response(self, text, finish="stop", refusal=None, usage=True):
        response = SimpleNamespace(
            choices=[SimpleNamespace(
                finish_reason=finish,
                message=SimpleNamespace(content=text, refusal=refusal),
            )],
            usage=SimpleNamespace(total_tokens=123, prompt_tokens=100, completion_tokens=23)
            if usage else None,
        )
        self.client.chat.completions.create.return_value = response
        return response

    def test_approve_and_token_accounting(self):
        result = self.reviewer.review(self.call, self.context)
        self.assertTrue(result.approved)
        self.assertEqual(result.reason, "Authorized log read.")
        self.assertEqual(result.token_cost, 123)
        self.assertEqual(result.metadata["prompt_tokens"], 100)
        self.assertEqual(result.metadata["completion_tokens"], 23)
        self.assertTrue(result.metadata["usage_available"])

    def test_deny_and_gate_budget_integration(self):
        self.set_response('{"approved": false, "reason": "Outside task scope."}')
        gate = ApprovalGate(FullEscalatePolicy(), self.reviewer)
        budget = BudgetTracker(initial_budget=1)
        result = gate.intercept(self.call, self.context, budget)
        self.assertEqual(result.action, GateAction.BLOCK)
        self.assertTrue(result.was_escalated)
        self.assertEqual(budget.remaining_budget, 0)
        gate.intercept(self.call, self.context, budget)
        self.client.chat.completions.create.assert_called_once()

    def test_actual_prompt_is_sanitized_without_mutation(self):
        before = self.context.model_dump()
        with patch.object(self.reviewer, "sanitize_context", wraps=self.reviewer.sanitize_context) as hook:
            self.reviewer.review(self.call, self.context)
            hook.assert_called_once_with(self.context)
        request = self.client.chat.completions.create.call_args.kwargs
        messages = request["messages"]
        self.assertEqual(messages[0]["content"], REVIEWER_SYSTEM_PROMPT)
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertEqual(request["model"], "offline-model")
        text = messages[1]["content"]
        for expected in [self.context.task_description, "read_logs", "/var/log/app.log", "connection failed", "log available"]:
            self.assertIn(expected, text)
        for forbidden in ["TOP_SECRET", "META_SECRET", "MESSAGE_SECRET", "NESTED_SECRET", "SUCCESS_SECRET", "TOOL_META_SECRET", "RAW_SECRET", "TASK_ID_NOT_FOR_PROMPT"]:
            self.assertNotIn(forbidden, text)
        self.assertEqual(before, self.context.model_dump())

    def test_invalid_json_and_schema_fail_closed(self):
        for text in ["not JSON", "", "[]", '{"approved": true}',
                     '{"approved": "false", "reason": "x"}',
                     '{"approved": 1, "reason": "x"}',
                     '{"approved": true, "reason": " "}',
                     '{"approved": true, "reason": "x", "extra": 1}']:
            with self.subTest(text=text):
                self.set_response(text)
                result = self.reviewer.review(self.call, self.context)
                self.assertFalse(result.approved)
                self.assertTrue(result.metadata["parse_error"])
                self.assertEqual(result.token_cost, 123)

    def test_timeout_is_technical_failure_not_safety_verdict(self):
        self.client.chat.completions.create.side_effect = TimeoutError("PRIVATE_EXCEPTION_DETAIL")
        result = self.reviewer.review(self.call, self.context)
        self.assertFalse(result.approved)
        self.assertEqual(result.metadata["status"], "api_error")
        self.assertFalse(result.metadata["usage_available"])
        self.assertNotIn("PRIVATE_EXCEPTION_DETAIL", str(result))

    def test_refusal_is_denied_with_usage(self):
        self.set_response(None, refusal="Cannot review this request.")
        result = self.reviewer.review(self.call, self.context)
        self.assertFalse(result.approved)
        self.assertEqual(result.metadata["status"], "model_refusal")
        self.assertEqual(result.token_cost, 123)

    def test_incomplete_response_cannot_approve(self):
        self.set_response('{"approved": true, "reason": "x"}', finish="length")
        result = self.reviewer.review(self.call, self.context)
        self.assertFalse(result.approved)
        self.assertEqual(result.metadata["status"], "response_error")

    def test_empty_choices_cannot_approve(self):
        self.client.chat.completions.create.return_value = SimpleNamespace(choices=[], usage=None)
        result = self.reviewer.review(self.call, self.context)
        self.assertFalse(result.approved)
        self.assertEqual(result.metadata["status"], "response_error")

    def test_missing_usage_is_marked_unknown(self):
        self.set_response('{"approved": true, "reason": "Authorized."}', usage=False)
        result = self.reviewer.review(self.call, self.context)
        self.assertTrue(result.approved)
        self.assertEqual(result.token_cost, 0)
        self.assertFalse(result.metadata["usage_available"])
        self.assertIsNone(result.metadata["total_tokens"])

    def test_missing_configuration_never_defaults_to_approve(self):
        with patch.dict(os.environ, {}, clear=True):
            reviewer = LLMSimulatedReviewer()
            result = reviewer.review(self.call, self.context)
        self.assertFalse(result.approved)
        self.assertEqual(result.metadata["status"], "configuration_error")

    def test_environment_config_and_sdk_client_creation(self):
        # Mock the SDK module, not a remote endpoint; tests constructor wiring.
        sdk = SimpleNamespace(OpenAI=Mock(return_value=self.client))
        env = {"REVIEWER_MODEL": "team-model", "REVIEWER_API_KEY": "test-key",
               "REVIEWER_BASE_URL": "https://example.invalid/v1"}
        with patch.dict(os.environ, env, clear=True), patch.dict(sys.modules, {"openai": sdk}):
            reviewer = LLMSimulatedReviewer(temperature=None)
            result = reviewer.review(self.call, self.context)
        sdk.OpenAI.assert_called_once_with(
            api_key="test-key", base_url="https://example.invalid/v1", timeout=30.0, max_retries=0
        )
        request = self.client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], "team-model")
        self.assertNotIn("temperature", request)
        self.assertTrue(result.approved)


if __name__ == "__main__":
    unittest.main()
