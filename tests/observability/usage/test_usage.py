# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Focused provider usage parsing tests."""

import dataclasses
import sys
import unittest
from unittest.mock import patch

from orchestrator.observability.usage import (
    metrics as _metrics,
    request_coverage as _request_coverage,
    request_normalization as _request_normalization,
    request_scan as _request_scan,
    skills as _skills,
    trajectory as _trajectory,
)
from tests.observability.usage import (
    usage_claude_events as _claude,
    usage_codex_events as _codex,
    usage_jsonl_helpers as _jsonl,
    usage_serialization_cases as _serialization,
    usage_test_values as _usage_cases,
)
from tests.support import agy_stream as _agy_stream

# A line the decoder refuses although it parses: a number past the interpreter's digit limit.
_REFUSED_DIGITS = "1" * (sys.get_int_max_str_digits() + 1)
_REFUSED_LINE = f'{{"unrelated": {_REFUSED_DIGITS}}}'
_REQUEST_USAGE = "request_usage"

_CLAUDE_USAGE = _claude.usage(input=10, output=2, cache_read=5)
_CLAUDE_FRAMES = (_claude.assistant(usage=_CLAUDE_USAGE), _claude.terminal_result())
_CODEX_FRAME = _codex.turn_complete(input=10, cached=5, output=2)
# One stream per backend that reports request usage, which a request collector could read were one to run.
_USAGE_BEARING_STREAMS = (
    (_usage_cases.CLAUDE, _jsonl.jsonl(*_CLAUDE_FRAMES)),
    (_usage_cases.CODEX, _jsonl.jsonl(_CODEX_FRAME)),
    (_agy_stream.BACKEND, _agy_stream.resumed_stream()),
)


class DispatcherTest(unittest.TestCase):
    """``_metrics.parse_agent_usage`` is a thin dispatcher over the per-backend parsers."""

    def test_routes_claude(self) -> None:
        metrics = _metrics.parse_agent_usage(_usage_cases.CLAUDE, "")
        self.assertEqual(metrics.backend, _usage_cases.CLAUDE)

    def test_routes_codex(self) -> None:
        metrics = _metrics.parse_agent_usage(_usage_cases.CODEX, "")
        self.assertEqual(metrics.backend, _usage_cases.CODEX)

    def test_unknown_backend_raises(self) -> None:
        with self.assertRaises(ValueError):
            _metrics.parse_agent_usage("gemini", "")

    def test_a_refused_line_refuses_the_stream(self) -> None:
        # The run parsers never skip a refused line: its usage could be the run's total, so a total read without it
        # is no total at all. Only request collection catches the refusal, for its own scan.
        for backend in (_usage_cases.CLAUDE, _usage_cases.CODEX, _agy_stream.BACKEND):
            with self.subTest(backend), self.assertRaises(ValueError):
                _metrics.parse_agent_usage(backend, _REFUSED_LINE)
            with self.subTest(backend), self.assertRaises(ValueError):
                _trajectory.parse_agent_trajectory(backend, _REFUSED_LINE)


class UsageMetricsTest(unittest.TestCase):
    def test_to_dict_round_trips_via_json(self) -> None:
        decoded = _serialization.serialize(_serialization.build_usage_metrics())
        self.assertEqual(decoded["backend"], _usage_cases.CODEX)
        self.assertEqual(decoded["models"], [_usage_cases.GPT_FIVE_CODEX])
        self.assertEqual(decoded[_usage_cases.TURNS_FIELD], 3)
        self.assertEqual(decoded["cost_source"], _usage_cases.ESTIMATED_COST_SOURCE)


class SkillDispatcherTest(unittest.TestCase):
    """``_skills.parse_agent_skills`` routes by backend, mirroring ``_metrics.parse_agent_usage``."""

    def test_routes_claude(self) -> None:
        # An assistant/tool_use stream is recognized only by the claude path.
        stdout = _jsonl.jsonl(
            _claude.assistant(
                id=_usage_cases.MESSAGE_FIXTURE_ID, content_blocks=[_claude.skill_use(_usage_cases.DEVELOP)]
            )
        )
        self.assertEqual(_skills.parse_agent_skills(_usage_cases.CLAUDE, stdout).triggered, _usage_cases.DEVELOP_ONLY)

    def test_routes_codex(self) -> None:
        # A codex SKILL.md-read command_execution is recognized only by the
        # codex path; the claude parser returns empty on it, so a non-empty
        # result here proves the codex parser ran.
        stdout = _jsonl.jsonl(_codex.command(_usage_cases.ITEM_ONE_ID, "/bin/bash -lc 'cat skills/review/SKILL.md'"))
        self.assertEqual(_skills.parse_agent_skills(_usage_cases.CODEX, stdout).triggered, (_usage_cases.REVIEW,))
        self.assertEqual(_skills.parse_claude_skills(stdout), _skills.SkillTriggers())

    def test_unknown_backend_raises(self) -> None:
        with self.assertRaises(ValueError):
            _skills.parse_agent_skills("gemini", "")


class TrajectoryDispatcherTest(unittest.TestCase):
    """``_trajectory.parse_agent_trajectory`` routes by backend, mirroring the siblings."""

    def test_routes_claude(self) -> None:
        self.assertEqual(_trajectory.parse_agent_trajectory(_usage_cases.CLAUDE, "").backend, _usage_cases.CLAUDE)

    def test_routes_codex(self) -> None:
        self.assertEqual(_trajectory.parse_agent_trajectory(_usage_cases.CODEX, "").backend, _usage_cases.CODEX)

    def test_unknown_backend_raises(self) -> None:
        with self.assertRaises(ValueError):
            _trajectory.parse_agent_trajectory("gemini", "")

    def test_parsing_collects_no_request_usage(self) -> None:
        # Reconstructing a timeline is not collecting its requests: every backend's trajectory leaves the field
        # uncollected, and parsing scans and normalizes nothing for it, however much usage the stream reports.
        for backend, stdout in _USAGE_BEARING_STREAMS:
            with (
                self.subTest(backend),
                patch.object(_request_scan, "scan_events") as scanned,
                patch.object(_request_normalization, "normalize") as normalized,
            ):
                parsed = _trajectory.parse_agent_trajectory(backend, stdout)
                self.assertIsNone(parsed.request_usage)
                self.assertIsNone(parsed.to_dict()[_REQUEST_USAGE])
                scanned.assert_not_called()
                normalized.assert_not_called()


class AgentTrajectoryTest(unittest.TestCase):
    def test_to_dict_round_trips_via_json(self) -> None:
        decoded = _serialization.serialize(
            _serialization.build_agent_trajectory(),
        )
        self.assertEqual(
            _serialization.trajectory_summary(decoded),
            (
                _usage_cases.CLAUDE,
                [_usage_cases.BASH_TOOL, _usage_cases.READ_TOOL],
                (None, _usage_cases.FINAL_OUTPUT),
                ([_usage_cases.DEVELOP], [_usage_cases.DEVELOP, _usage_cases.REVIEW]),
            ),
        )
        self.assertEqual(
            _serialization.trajectory_steps(decoded),
            (
                2,
                (_usage_cases.BASH_TOOL, 0),
                (_usage_cases.TOOL_RESULT_STEP, None),
            ),
        )
        self.assertEqual(
            _serialization.trajectory_turns(decoded),
            (
                1,
                (
                    _usage_cases.OPUS_FOUR_EIGHT,
                    _usage_cases.CLAUDE_TURN_CACHE_READ_TOKENS,
                    _usage_cases.ESTIMATED_COST_SOURCE,
                ),
            ),
        )

    def test_request_usage_rides_apart_from_the_turns(self) -> None:
        trajectory = _serialization.build_agent_trajectory()
        failed = _request_coverage.RequestUsage.failed()
        decoded = _serialization.serialize(dataclasses.replace(trajectory, request_usage=failed))
        self.assertEqual(decoded[_REQUEST_USAGE], failed.to_dict())
        without = _serialization.serialize(trajectory)
        self.assertEqual(decoded[_usage_cases.TURNS_FIELD], without[_usage_cases.TURNS_FIELD])
