# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Antigravity per-run accounting and streamed trajectory reconstruction."""

import unittest

from orchestrator.observability.usage import agy_events, metrics, skills, trajectory
from tests.support import agy_stream as stream

_ACTIVE = agy_events.ACTIVE
_DONE = agy_events.DONE
_TOOL = agy_events.TOOL


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
            stream.step(1, state=_ACTIVE, usage={"input_tokens": 1000}),
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
            stream.step(5, kind=_TOOL, state=_ACTIVE, tool_info=tool),
            stream.step(5, kind=_TOOL, tool_info={**tool, "output": "ok"}),
            stream.step(5, kind=_TOOL, tool_info={**tool, "output": "ok"}),
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
                    stream.step(1, state=_ACTIVE, text_delta="partial"), ending,
                ))
                parsed = trajectory.parse_agent_trajectory(
                    stream.BACKEND, stdout,
                )
                self.assertIsNone(parsed.final_output)
                self.assertEqual(parsed.steps[0].step_payload, "partial")


class AntigravityLifecycleTest(unittest.TestCase):
    def test_active_command_followed_by_success(self) -> None:
        stdout = stream.ToolStream.active_command()
        incomplete = agy_events.incomplete_tool_steps(stdout)
        self.assertEqual(
            incomplete,
            [agy_events.ToolLifecycle(step_index=1, tool_name=stream.TOOL_NAME, state=_ACTIVE)],
        )

    def test_concurrent_checks_retain_active_command(self) -> None:
        stdout = stream.ToolStream.active_with_checks()
        all_steps = agy_events.tool_lifecycles(stdout)
        self.assertEqual(
            all_steps,
            [
                agy_events.ToolLifecycle(step_index=1, tool_name=stream.TOOL_NAME, state=_ACTIVE),
                agy_events.ToolLifecycle(step_index=2, tool_name=stream.TOOL_TASK, state=_DONE),
                agy_events.ToolLifecycle(step_index=3, tool_name=stream.TOOL_TASK, state=_DONE),
            ],
        )
        incomplete = agy_events.incomplete_tool_steps(stdout)
        self.assertEqual(
            incomplete,
            [agy_events.ToolLifecycle(step_index=1, tool_name=stream.TOOL_NAME, state=_ACTIVE)],
        )

    def test_repeated_and_sparse_updates_for_one_step(self) -> None:
        stdout = stream.ToolStream.repeated_updates()
        all_steps = agy_events.tool_lifecycles(stdout)
        self.assertEqual(
            all_steps,
            [agy_events.ToolLifecycle(step_index=1, tool_name=stream.TOOL_NAME, state=_ACTIVE)],
        )
        self.assertEqual(all_steps[0].name, stream.TOOL_NAME)
        self.assertEqual(all_steps[0].tool_name, stream.TOOL_NAME)

    def test_completed_command_leaves_no_incomplete(self) -> None:
        stdout = stream.ToolStream.completed_command()
        all_steps = agy_events.tool_lifecycles(stdout)
        self.assertEqual(
            all_steps,
            [
                agy_events.ToolLifecycle(step_index=1, tool_name=stream.TOOL_NAME, state=_DONE),
                agy_events.ToolLifecycle(step_index=2, tool_name=stream.TOOL_TASK, state=_DONE),
            ],
        )
        self.assertEqual(agy_events.incomplete_tool_steps(stdout), [])

    def test_prose_and_text_steps_ignored(self) -> None:
        stdout = "\n".join((
            stream.init_event(),
            stream.step(1, kind="user_input"),
            stream.step(2, kind="agent_response", state=_ACTIVE, text_delta="run_command is running"),
            stream.step(2, kind="agent_response", state=_DONE, text_delta="\nDone."),
            stream.terminal(status=stream.SUCCESS, response="I ran the command."),
        ))
        self.assertEqual(agy_events.tool_lifecycles(stdout), [])
        self.assertEqual(agy_events.incomplete_tool_steps(stdout), [])

    def test_sparse_updates_retain_tool_identity(self) -> None:
        stdout = "\n".join((
            stream.step(10, kind=_TOOL, tool_info={"name": "run_command"}),
            stream.step(10, state=_ACTIVE),
            stream.step(10, state=_DONE),
        ))
        steps = agy_events.tool_lifecycles(stdout)
        self.assertEqual(
            steps,
            [agy_events.ToolLifecycle(step_index=10, tool_name="run_command", state=_DONE)],
        )
        self.assertEqual(agy_events.incomplete_tool_steps(stdout), [])
