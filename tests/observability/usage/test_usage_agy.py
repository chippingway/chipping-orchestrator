# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Antigravity per-run accounting and streamed trajectory reconstruction."""

import unittest

from orchestrator.observability.usage import metrics, skills, trajectory
from tests.support import agy_stream as stream


class AntigravityUsageTest(unittest.TestCase):
    def test_resume_counts_only_current_steps(self) -> None:
        stdout = stream.resumed_stream()
        stdout = "\n".join((stdout, stdout.splitlines()[-2]))
        usage = metrics.parse_agent_usage(stream.BACKEND, stdout)
        self.assertEqual(usage.models, (stream.MODEL,))
        self.assertEqual(usage.turns, 1)
        self.assertEqual((usage.input_tokens, usage.output_tokens, usage.cache_read_tokens),
                         (stream.INPUT_TOKENS, stream.OUTPUT_TOKENS, stream.CACHE_READ_TOKENS))
        self.assertEqual(usage.cost_source, "unknown-price")
        self.assertIsNone(usage.cost_usd)

    def test_missing_usage_and_skill_evidence(self) -> None:
        for stdout in ("", 'warning\n[]\n{"event":"step_update","step_update":null}', stream.terminal()):
            with self.subTest(stdout=stdout):
                usage = metrics.parse_agent_usage(stream.BACKEND, stdout, fallback_model=stream.MODEL)
                self.assertEqual(usage.models, (stream.MODEL,))
                self.assertEqual(usage.input_tokens, 0)
                self.assertEqual(usage.cost_source, "no-usage")
                self.assertEqual(skills.parse_agent_skills(stream.BACKEND, stdout), skills.SkillTriggers())

    def test_completed_step_usage(self) -> None:
        stdout = "\n".join((
            stream.step(1, state="ACTIVE", usage={"input_tokens": 1000}),
            stream.step(1, usage={"input_tokens": "10", "output_tokens": 2}),
            stream.step(2, kind="checkpoint", usage={"input_tokens": 3, "output_tokens": 1}),
        ))
        usage = metrics.parse_agent_usage(stream.BACKEND, stdout)
        self.assertEqual((usage.input_tokens, usage.output_tokens), (13, 3))


class AntigravityTrajectoryTest(unittest.TestCase):
    def test_text_and_tool_timeline(self) -> None:
        tool = {"name": stream.TOOL_NAME, "parameters": {"CommandLine": "echo ok"}}
        stdout = "\n".join((
            stream.resumed_stream(),
            stream.step(5, kind="tool", state="ACTIVE", tool_info=tool),
            stream.step(5, kind="tool", tool_info={**tool, "output": "ok"}),
            stream.step(5, kind="tool", tool_info={**tool, "output": "ok"}),
        ))
        parsed = trajectory.parse_agent_trajectory(stream.BACKEND, stdout)
        self.assertEqual(parsed.backend, stream.BACKEND)
        self.assertEqual(parsed.tools, (stream.TOOL_NAME,))
        self.assertEqual(parsed.final_output, stream.ANSWER)
        self.assertEqual([step.kind for step in parsed.steps], ["assistant_message", "tool_call", "tool_result"])
        self.assertEqual(parsed.steps[0].step_payload, stream.ANSWER)
        self.assertEqual(parsed.steps[1].step_payload, tool["parameters"])
        self.assertEqual(parsed.steps[2].step_payload, "ok")

    def test_only_success_has_final_output(self) -> None:
        for ending in ("", stream.terminal(stream.FAILURE)):
            with self.subTest(ending=ending):
                stdout = "\n".join((
                    stream.step(1, state="ACTIVE", text_delta="partial"), ending,
                ))
                parsed = trajectory.parse_agent_trajectory(
                    stream.BACKEND, stdout,
                )
                self.assertIsNone(parsed.final_output)
                self.assertEqual(parsed.steps[0].step_payload, "partial")
