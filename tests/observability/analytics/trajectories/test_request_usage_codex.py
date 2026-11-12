# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A Codex run's `request_usage` as a trajectory record stores it, read off its native session log at exit."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from orchestrator.observability.analytics import sink as analytics_sink
from orchestrator.observability.analytics.trajectories import codex_sessions
from orchestrator.observability.analytics.trajectories.codex_launch import LaunchObservation
from orchestrator.observability.usage import protocol, request_coverage as coverage, trajectory as usage_trajectory
from tests.observability.analytics.analytics_jsonl_helpers import read_records
from tests.observability.analytics.trajectories import (
    codex_session_support as sessions,
    trajectories_test_support as support,
)
from tests.observability.usage import usage_codex_native_capture as capture

_REQUEST_USAGE = "request_usage"
_COVERAGE = "coverage"
_SAMPLES = "samples"
_REASONS = "reasons"
_COLLECTOR = "parse_agent_request_usage"
_LOOKUP = "discovered_log"
_UNPRICED_MODEL = "unpriced-model"
_PRIVATE = (capture.TEXT_CANARY, capture.CREDENTIAL_CANARY, capture.WORKSPACE)
_NEWER_DAY = ("2026", "11", "13")
_OTHER_LOG = f"rollout-2026-11-13T09-00-00-{sessions.OTHER_SESSION}.jsonl"
_FRESH_INPUT = 37000
_FAILED = coverage.RequestUsage.failed().summary(0, 0)
_UNTIMED = frozenset(("ts", _REQUEST_USAGE))
# The ways a run ends before its turn does, each with its exit code and whether it timed out.
_UNFINISHED = (
    ("interrupted", -15, False),
    ("timed out", -1, True),
    ("failed", 1, False),
)


def _positions(record: dict) -> list[int]:
    samples = record[_REQUEST_USAGE].get(_SAMPLES, ())
    return [sample["position"] for sample in samples]


def _reasons(record: dict) -> dict[str, int]:
    return record[_REQUEST_USAGE][_COVERAGE][_REASONS]


def _without_requests(record: dict) -> dict:
    """A written record without its request usage or the moment it was written."""
    return {name: field_value for name, field_value in record.items() if name not in _UNTIMED}


class _CodexRecordTest(support.RecordAgentExitTrajectorySupport):
    """A Codex exit written against a `CODEX_HOME` of the test's own, its launch observed there."""

    def setUp(self) -> None:
        self.home = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def _exit(self, invocation: capture.Invocation, **options) -> dict:
        """The exit options of `invocation`, its launch observed against this test's home."""
        options.setdefault("session_id", capture.SESSION_ID)
        resumed = capture.SESSION_ID if invocation.resumed else None
        return {
            "stdout": invocation.stdout,
            "backend": protocol.CODEX,
            "resume_session_id": resumed,
            "launch_observation": LaunchObservation(self.home, invocation.launched_at),
            **options,
        }

    def _codex_record(self, invocation: capture.Invocation, **options) -> tuple[dict, list[dict]]:
        return self._written_records(**self._exit(invocation, **options))


class CodexRequestUsageRecordTest(_CodexRecordTest):
    """One tracked Codex exit writes its own requests beside the trajectory, and changes nothing else it says."""

    def test_the_record_carries_its_requests(self) -> None:
        # Collected or not, the run's usage, its timeline, and its item accounting are what they would be; collecting
        # request sizes never prices a run its accounting leaves unpriced.
        sessions.write_log(self.home, capture.log_text(capture.FRESH.end))
        record, baseline = self._codex_record(capture.FRESH, fallback_model=_UNPRICED_MODEL)
        with patch.object(usage_trajectory, _COLLECTOR, return_value=None):
            uncollected, _ = self._codex_record(capture.FRESH, fallback_model=_UNPRICED_MODEL)
        request_usage = record[_REQUEST_USAGE]
        self.assertEqual(_positions(record), [13, 18, 22])
        self.assertEqual(request_usage[_COVERAGE]["status"], coverage.COMPLETE)
        self.assertEqual(len(request_usage["checkpoints"]), 3)
        self.assertEqual(_without_requests(record), _without_requests(uncollected))
        self.assertIsNone(record["run_usage"]["cost_usd"])
        self.assertNotIn(_REQUEST_USAGE, baseline[0])

    def test_a_resume_reads_only_its_own(self) -> None:
        # The resumed session's log is under the date it began, a newer date holding another session's.
        sessions.write_log(self.home, "", day=_NEWER_DAY, name=_OTHER_LOG)
        sessions.write_log(self.home, capture.log_text(capture.SWITCHED.end))
        record, _ = self._codex_record(capture.SWITCHED)
        self.assertEqual(_positions(record), [40, 52])
        self.assertEqual(len(record[_REQUEST_USAGE]["markers"]), 2)

    def test_unfinished_runs_keep_their_requests(self) -> None:
        sessions.write_log(self.home, capture.log_text(capture.INTERRUPTED.end))
        for name, exit_code, timed_out in _UNFINISHED:
            with self.subTest(name):
                record, _ = self._codex_record(capture.INTERRUPTED, exit_code=exit_code, timed_out=timed_out)
                self.assertEqual(_positions(record), [69])
                self.assertEqual(_reasons(record), {coverage.NO_TERMINAL_RESULT: 1})

    def test_no_text_or_credential(self) -> None:
        sessions.write_log(self.home, capture.log_text())
        record, _ = self._codex_record(capture.LAST)
        serialized = json.dumps(record[_REQUEST_USAGE])
        self.assertEqual(_positions(record), [78])
        for private in _PRIVATE:
            with self.subTest(private=private):
                self.assertNotIn(private, serialized)


class CodexRequestUsageFailureTest(_CodexRecordTest):
    """A log the exit cannot read costs the record nothing but the field's samples, and the sink off reads none."""

    def test_no_log_and_no_session(self) -> None:
        # A log the lookup cannot find, and a run that returned no session -- which is looked up nowhere -- each
        # leave the trajectory and the baseline record whole, the field saying why it holds nothing.
        record, baseline = self._codex_record(capture.FRESH)
        with patch.object(codex_sessions, _LOOKUP) as lookup:
            unnamed, _ = self._codex_record(capture.FRESH, session_id=None)
            lookup.assert_not_called()
        self.assertEqual(_reasons(record), {coverage.NATIVE_LOG_MISSING: 1})
        self.assertEqual(_reasons(unnamed), {coverage.NO_SESSION_IDENTITY: 1})
        self.assertEqual(record[support.OUTPUT_KEY], "Done.")
        self.assertEqual(len(baseline), 1)

    def test_a_failing_lookup_keeps_everything_else(self) -> None:
        failing = patch.object(codex_sessions, _LOOKUP, side_effect=RuntimeError("lookup boom"))
        with failing, self.assertLogs(analytics_sink.log, level="ERROR"):
            record, baseline = self._codex_record(capture.FRESH)
        self.assertEqual(record[_REQUEST_USAGE], {_COVERAGE: _FAILED})
        self.assertEqual(record[support.OUTPUT_KEY], "Done.")
        self.assertEqual(baseline[0]["input_tokens"], _FRESH_INPUT)

    def test_a_disabled_sink_reads_nothing(self) -> None:
        sessions.write_log(self.home, capture.log_text(capture.FRESH.end))
        analytics_path = self.home / support.ANALYTICS_FILENAME
        with patch.object(codex_sessions, _LOOKUP) as lookup:
            self._emit(**self._exit(capture.FRESH), analytics_path=analytics_path)
            lookup.assert_not_called()
        self.assertEqual(len(read_records(analytics_path)), 1)
