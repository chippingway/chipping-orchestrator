# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The `request_usage` field of a trajectory record: what it keeps, what it is charged, and what it never costs."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.observability.analytics import sink as analytics_sink
from orchestrator.observability.usage import protocol, request_coverage as coverage, trajectory as usage_trajectory
from tests.observability.analytics.analytics_jsonl_helpers import read_records
from tests.observability.analytics.trajectories import (
    request_usage_cases as cases,
    trajectories_test_support as support,
)
from tests.observability.usage import usage_agy_stream_capture as capture
from tests.support import agy_stream as stream

_REQUEST_USAGE = "request_usage"
_COVERAGE = "coverage"
_SAMPLES = "samples"
_STATUS = "status"
_COLLECTOR = "parse_agent_request_usage"
_FRESH_STDOUT = "\n".join(capture.FRESH_RUN)
_GUIDE_STDOUT = "\n".join(capture.GUIDE_RUN)
_FRESH_INPUT = 6827
_FRESH_ANSWER = "apple\n"
_GUIDE_CONVERSATION = "c3b66b04-872b-4fbe-a3a4-058a026ef20a"
_GUIDE_IDS = (f"{_GUIDE_CONVERSATION}:3", f"{_GUIDE_CONVERSATION}:4")
_PRIVATE = (cases.SECRET, cases.SPOKEN, cases.TOOL_TEXT, cases.TOOL_OUTPUT)
_INTERRUPTED = "\n".join((
    stream.init_event(),
    stream.step(1, usage=dict(cases.USAGE)),
    stream.step(2, state="ACTIVE"),
))
_FAILED = coverage.RequestUsage.failed().summary(0, 0)
# The keys a sample may carry: identities, positions, attribution, status, and counters with their evidence.
_SAMPLE_KEYS = frozenset((
    "id", "id_kind", "conversation_id", "session_id", "turn_id", "message_id", "step_index",
    "parent_conversation_id", "parent_step_index", "subagent_type", "position", "branch_order", "source_kind",
    "source_timestamp", "source_duration_s", "model", "model_source", "context_capacity", "source_version", "scope",
    "status", "settlement", "raw", "context_input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
    "cache_write_lifetimes", "reasoning_tokens", "total_tokens", "source_total_tokens", "overlap", "evidence",
))
_RAW_KEYS = frozenset(("input_tokens", "output_tokens", "thinking_tokens", "cache_read_tokens", "total_tokens"))


class RequestUsageRecordTest(support.RecordAgentExitTrajectorySupport):
    """One tracked exit writes the field beside the trajectory, and only where the trajectory sink is on."""

    def test_antigravity_record_carries_requests(self) -> None:
        record, baseline = self._written(stdout=_GUIDE_STDOUT, fallback_model=capture.MODEL)
        request_usage = record[_REQUEST_USAGE]
        ids = tuple(sample["id"] for sample in request_usage[_SAMPLES])
        self.assertEqual(ids, _GUIDE_IDS)
        self.assertEqual(request_usage[_COVERAGE][_STATUS], coverage.COMPLETE)
        self.assertEqual(len(request_usage["checkpoints"]), 1)
        # The timeline and the baseline record are what they always were.
        self.assertEqual(record[support.STEPS_KEY][0]["kind"], "assistant_message")
        self.assertNotIn(_REQUEST_USAGE, baseline[0])

    def test_request_usage_carries_no_text_or_secret(self) -> None:
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": cases.SECRET}):
            record, _ = self._written(stdout=cases.private_stdout(), prompt=cases.SPOKEN)
        request_usage = record[_REQUEST_USAGE]
        serialized = json.dumps(request_usage)
        for private in _PRIVATE:
            with self.subTest(private=private):
                self.assertNotIn(private, serialized)
        sample = request_usage[_SAMPLES][0]
        self.assertLessEqual(set(sample), _SAMPLE_KEYS)
        self.assertLessEqual(set(sample["raw"]), _RAW_KEYS)

    def test_failed_run_keeps_its_requests(self) -> None:
        record, _ = self._written(stdout=_INTERRUPTED, session_id=None, exit_code=1)
        request_usage = record[_REQUEST_USAGE]
        self.assertNotIn("session_id", record)
        self.assertEqual(len(request_usage[_SAMPLES]), 1)
        self.assertEqual(request_usage[_COVERAGE][_STATUS], coverage.INCOMPLETE)

    def test_runs_without_a_collector_carry_none(self) -> None:
        for backend in (support.CLAUDE, support.CODEX):
            with self.subTest(backend):
                record, _ = self._written(stdout=_FRESH_STDOUT, backend=backend)
                self.assertNotIn(_REQUEST_USAGE, record)

    def test_disabled_sink_runs_no_collector(self) -> None:
        with tempfile.TemporaryDirectory() as td, patch.object(usage_trajectory, _COLLECTOR) as collector:
            analytics_path = Path(td) / support.ANALYTICS_FILENAME
            self._emit(stdout=_FRESH_STDOUT, backend=protocol.AGY, analytics_path=analytics_path)
            self.assertEqual(len(read_records(analytics_path)), 1)
            collector.assert_not_called()

    def test_collector_failure_keeps_everything_else(self) -> None:
        failing = patch.object(usage_trajectory, _COLLECTOR, side_effect=RuntimeError("collector boom"))
        with failing, self.assertLogs(analytics_sink.log, level="ERROR"):
            record, baseline = self._written(stdout=_FRESH_STDOUT)
        # The trajectory and the baseline record are written whole; the field says only that collection failed.
        self.assertEqual(record[support.OUTPUT_KEY], _FRESH_ANSWER)
        self.assertEqual(record[_REQUEST_USAGE], {_COVERAGE: _FAILED})
        self.assertEqual(baseline[0][support.INPUT_TOKENS_KEY], _FRESH_INPUT)

    def _written(self, **options) -> tuple[dict, list[dict]]:
        options.setdefault("backend", protocol.AGY)
        with tempfile.TemporaryDirectory() as td:
            traj_path = Path(td) / support.TRAJECTORY_FILENAME
            analytics_path = Path(td) / support.ANALYTICS_FILENAME
            self._emit(traj_path=traj_path, analytics_path=analytics_path, **options)
            return read_records(traj_path)[0], read_records(analytics_path)


class RequestRetentionTest(unittest.TestCase):
    """The field's markers and samples are drawn after turns and item accounting, before steps, as prefixes."""

    def test_every_budget_keeps_a_prefix(self) -> None:
        trajectory = cases.every_array_trajectory()
        entries = cases.charged_entries(trajectory)
        whole = len(entries)
        for cut in range(1, whole + 1):
            with self.subTest(cut=cut):
                record = cases.built(trajectory, entries, cut)
                self.assertEqual(cases.kept_counts(record), cases.drawn_counts(entries, cut))
                self.assertIs(bool(record.get("truncated")), cut < whole)

    def test_coverage_is_kept_when_no_sample_fits(self) -> None:
        record = cases.built(cases.every_array_trajectory(), [], 0)
        request_usage = record[_REQUEST_USAGE]
        summary = request_usage[_COVERAGE]
        self.assertNotIn(_SAMPLES, request_usage)
        self.assertEqual(summary[_STATUS], coverage.STORAGE_TRUNCATED)
        self.assertEqual(summary["reasons"], {coverage.STORAGE_BUDGET: 3})
        self.assertEqual(summary["observed_samples"], 2)
        self.assertEqual(summary["retained_samples"], 0)
