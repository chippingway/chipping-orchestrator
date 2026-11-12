# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A Claude run's `request_usage` as a trajectory record stores it, beside everything the record already carried."""

import json
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.observability.analytics import sink as analytics_sink
from orchestrator.observability.usage import protocol, request_coverage as coverage, trajectory as usage_trajectory
from tests.observability.analytics.trajectories import (
    request_usage_cases as cases,
    trajectories_test_support as support,
)
from tests.observability.usage import (
    usage_claude_request_streams as stream,
    usage_claude_stream_capture as capture,
    usage_request_cases as request_cases,
)

_REQUEST_USAGE = "request_usage"
_COVERAGE = "coverage"
_SAMPLES = "samples"
_STATUS = "status"
_OUTPUT = "output_tokens"
_STDOUT = capture.SUBAGENT_RUN_STDOUT
_RAW_KEYS = frozenset((
    "input_tokens", _OUTPUT, "thinking_tokens", "cache_read_input_tokens", "cache_creation_input_tokens",
    "ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens",
))
# Text the captured run's tool calls, tool output, hand-back, and answer carry, and its scratch path.
_PRIVATE = ("wc -l notes.txt", "3 notes.txt", "[Subagent hand-back]", "calc.py is 32 bytes", "/workspace")
_REQUEST = "request"
_FINAL = "final"
_DELTA = (_FINAL, "message-delta")
# Each captured request: its id, its scope, and its status and the report that settled it.
_REQUESTS = (
    ("msg_lead_0", _REQUEST, *_DELTA),
    ("msg_sub_0", _REQUEST, _FINAL, "model-usage"),
    (f"handback:{capture.SUBAGENT_CALL}", "request-output", _FINAL, "handback"),
    ("msg_lead_1", _REQUEST, *_DELTA),
    ("msg_lead_2", _REQUEST, *_DELTA),
)
_SETTLED = ("id", "scope", _STATUS, "settlement")
_CHECKPOINT_SCOPES = ("lead-thread", "model")
# A run interrupted mid-message: its one message started and never closed, and no result ended the run.
_OPENED = stream.message("msg_a", 1)[:-1]
_INTERRUPTED = "\n".join((stream.init(), *_OPENED))
# The main capture beside a line the JSON decoder refuses although it parses: the run parsers refuse the stream.
_REFUSED = f"{capture.MAIN_RUN_STDOUT}\n{request_cases.REFUSED_LINE}"
_TIMELINE = frozenset(("run_usage", "turns", "output"))
_UNFINISHED = (
    ("failed", MappingProxyType({"exit_code": 1, "timed_out": False})),
    ("timed out", MappingProxyType({"exit_code": -9, "timed_out": True})),
)


def _settled(request_usage: dict) -> tuple[tuple[object, ...], ...]:
    return tuple(request_cases.picked(sample, *_SETTLED) for sample in request_usage[_SAMPLES])


def _untimed(record: dict) -> dict:
    """A written record without the moment it was written."""
    return {name: field_value for name, field_value in record.items() if name != "ts"}


def _turn_outputs(record: dict) -> dict[int, int]:
    return {turn["turn"]: turn[_OUTPUT] for turn in record["turns"]}


def _linked_outputs(request_usage: dict) -> dict[int, int]:
    return {sample["trajectory_turn"]: sample[_OUTPUT] for sample in request_usage[_SAMPLES]}


class ClaudeRequestUsageRecordTest(support.RecordAgentExitTrajectorySupport):
    """One tracked Claude exit writes its requests beside the trajectory, and changes nothing else the record says."""

    def test_record_carries_the_captured_requests(self) -> None:
        # The captured subagent run: one sample per request in the common shape, each with its scope, its status, and
        # the report that settled it, its totals as checkpoints of their own scope, and no text of the run.
        request_usage = self._written_records(stdout=_STDOUT)[0][_REQUEST_USAGE]
        self.assertEqual(_settled(request_usage), _REQUESTS)
        for sample in request_usage[_SAMPLES]:
            self.assertLessEqual(set(sample), cases.SAMPLE_KEYS)
            self.assertLessEqual(set(sample["raw"]), _RAW_KEYS)
        self.assertEqual(request_usage[_COVERAGE][_STATUS], coverage.INCOMPLETE)
        scopes = tuple(checkpoint["scope"] for checkpoint in request_usage["checkpoints"])
        self.assertEqual(scopes, _CHECKPOINT_SCOPES)
        serialized = json.dumps(request_usage)
        for private in _PRIVATE:
            with self.subTest(private=private):
                self.assertNotIn(private, serialized)

    def test_record_keeps_everything_else(self) -> None:
        # The baseline record, the run usage and its costs, the turns, and the timeline are exactly what the run writes
        # with no request collected, and each sample links the turn holding its own settled output.
        collected = self._written_records(stdout=_STDOUT)
        with patch.object(usage_trajectory, "parse_agent_request_usage", return_value=None):
            uncollected = self._written_records(stdout=_STDOUT)
        record = _untimed(collected[0])
        request_usage = record.pop(_REQUEST_USAGE)
        self.assertEqual(record, _untimed(uncollected[0]))
        baseline = [_untimed(written) for written in collected[1]]
        self.assertEqual(baseline, [_untimed(written) for written in uncollected[1]])
        self.assertEqual(collected[1][0]["cost_usd"], capture.SUBAGENT_RUN_COST_USD)
        self.assertEqual(_linked_outputs(request_usage), _turn_outputs(record))

    def test_unfinished_runs_keep_their_requests(self) -> None:
        # What the process printed is its own whether or not it finished or returned a session id.
        for name, ending in _UNFINISHED:
            with self.subTest(name):
                record = self._written_records(stdout=_INTERRUPTED, backend=protocol.CLAUDE, session_id=None, **ending)
                self.assertNotIn("session_id", record[0])
                request_usage = record[0][_REQUEST_USAGE]
                self.assertEqual(len(request_usage[_SAMPLES]), 1)
                self.assertEqual(request_usage[_COVERAGE][_STATUS], coverage.INCOMPLETE)

    def test_refused_stream_links_no_turn(self) -> None:
        # The run parsers refuse the stream, so the record carries no turns and no timeline: its requests are kept,
        # every one of them, and none names a turn the record does not have.
        with self.assertLogs(analytics_sink.log, level="ERROR"):
            record = self._written_records(stdout=_REFUSED)[0]
        self.assertTrue(record["stream_refused"])
        self.assertFalse(_TIMELINE & set(record))
        samples = record[_REQUEST_USAGE][_SAMPLES]
        self.assertEqual(len(samples), len(capture.MAIN_RUN_MESSAGES))
        linked = [sample for sample in samples if "trajectory_turn" in sample]
        self.assertEqual(linked, [])
