# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One late event reaching both sinks, and neither sink reaching the workflow."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.late_split import events as _events, records as _records, telemetry as _telemetry
from orchestrator.workflow.late_split.models import LateVerdict
from tests.support.fakes import FakeGitHubClient
from tests.workflow.late_split import generation_test_support as _support

_STAGE = "decomposing"
_STAGE_KEY = "stage"
_EVENT_KEY = "event"
_EMIT_EVENT = "emit_event"
_LATE_VERDICT = "late_verdict"
_WORKFLOW_CHANNEL = "orchestrator.workflow"
_ERROR = "ERROR"
_ANALYTICS_APPEND = _support.ANALYTICS_APPEND

_VERDICT_EVENT = _events.LateEvent(
    family=_events.LateEventFamily.VERDICT,
    verdict=LateVerdict.SINGLE,
)
_LATE_FAILURE = "late_failure"
# One reading the size gate could not take, as the seam that refused it hands
# it over: the step it stopped at, and the line that step wrote for itself.
_REFUSED_READING = _events.measurement_failure_event(
    _support.MEASUREMENT_STEP, _support.FAILURE_DETAIL,
)
# An agent's rationale, naming a path, offered as the state an issue was in.
_PROSE = "rationale: inspect /srv/private/key before splitting"
# A stage the caller names -> the tag both sinks record. Each state answers to
# its bare stage tag and its exact canonical label, the unprefixed labels
# among them, and records the tag the stage-enter events carry.
_KNOWN_STAGES = (
    ("decomposing", _STAGE),
    ("workflow:decomposing", _STAGE),
    ("resolving_conflict", "resolving_conflict"),
    ("workflow:resolving_conflict", "resolving_conflict"),
    ("in_review", "in_review"),
    ("rejected", "rejected"),
)
# Names that are no workflow state: prose, a prefixed name outside the
# vocabulary, the controls in either spelling, a near miss on a canonical
# label, and a value that is not a name at all.
_UNKNOWN_STAGES = (
    _PROSE,
    "workflow:python:pip",
    "backlog",
    "workflow:community_contribution",
    "community_contribution",
    "Workflow:Decomposing",
    7,
)


def _emit_verdict(gh) -> dict:
    """Emit one late verdict for the shared generation."""
    return _telemetry.emit_late_event(
        gh, _VERDICT_EVENT, _support.measured_generation(), stage=_STAGE,
    )


def _emit(gh, appended: list) -> dict:
    """Emit one late verdict, collecting what the analytics sink was handed."""
    with patch(_ANALYTICS_APPEND, appended.append):
        return _emit_verdict(gh)


def _sink_records(gh, appended: list) -> dict:
    """The last record each of the two sinks was handed, by sink."""
    return {"audit": gh.recorded_events[-1], "analytics": appended[-1]}


class DualEmissionTest(unittest.TestCase):
    """Both sinks receive the same event, under the same correlation."""

    def test_each_sink_records_family_and_stage(self) -> None:
        gh = FakeGitHubClient()
        appended: list = []
        _emit(gh, appended)
        for sink, record in _sink_records(gh, appended).items():
            with self.subTest(sink=sink):
                self.assertEqual(record[_EVENT_KEY], _LATE_VERDICT)
                self.assertEqual(record[_STAGE_KEY], _STAGE)
                self.assertEqual(record["repo"], _support.REPO)
                self.assertEqual(record["issue"], _support.CURRENT_ISSUE)

    def test_the_two_records_correlate(self) -> None:
        # The audit copy has to answer offline what the database answers, so
        # the two are joinable without reading the pinned comment back.
        gh = FakeGitHubClient()
        appended: list = []
        _emit(gh, appended)
        self.assertEqual(
            _records.correlation_key(gh.recorded_events[-1]),
            _records.correlation_key(appended[-1]),
        )

    def test_neither_record_exceeds_the_contract(self) -> None:
        gh = FakeGitHubClient()
        appended: list = []
        _emit(gh, appended)
        allowed = {"ts", "repo", "issue", _EVENT_KEY, _STAGE_KEY}
        allowed.update(_records.LATE_PAYLOAD_FIELDS)
        for sink, record in _sink_records(gh, appended).items():
            with self.subTest(sink=sink):
                self.assertLessEqual(set(record), allowed)

    def test_both_sinks_carry_the_refused_step(self) -> None:
        # The point of writing twice: an operator with only the JSONL audit
        # copy has to be able to tell a base a fetch cannot bring from a diff
        # nothing can pin, which is what the database answers.
        gh = FakeGitHubClient()
        appended: list = []
        with patch(_ANALYTICS_APPEND, appended.append):
            _telemetry.emit_late_event(
                gh, _REFUSED_READING, _support.measured_generation(),
                stage=_STAGE,
            )
        for sink, record in _sink_records(gh, appended).items():
            with self.subTest(sink=sink):
                self.assertEqual(record[_EVENT_KEY], _LATE_FAILURE)
                self.assertEqual(record["failure"], "measurement_failed")
                self.assertEqual(
                    record["measurement_failure"],
                    str(_support.MEASUREMENT_STEP),
                )
                self.assertEqual(record["detail"], _support.FAILURE_DETAIL)

    def test_the_returned_payload_is_what_landed(self) -> None:
        gh = FakeGitHubClient()
        appended: list = []
        payload = _emit(gh, appended)
        self.assertEqual(
            payload,
            _records.build_late_payload(
                _VERDICT_EVENT, _support.measured_generation(),
            ),
        )
        self.assertLessEqual(payload.items(), appended[-1].items())


class StageTest(unittest.TestCase):
    """The stage a record carries is a workflow state and nothing else."""

    def test_a_known_stage_records_its_bare_tag(self) -> None:
        for named, tag in _KNOWN_STAGES:
            with self.subTest(stage=named):
                gh = FakeGitHubClient()
                appended: list = []
                with patch(_ANALYTICS_APPEND, appended.append):
                    _telemetry.emit_late_event(
                        gh,
                        _VERDICT_EVENT,
                        _support.measured_generation(),
                        stage=named,
                    )
                self.assertEqual(appended[-1][_STAGE_KEY], tag)
                self.assertEqual(gh.recorded_events[-1][_STAGE_KEY], tag)

    def test_a_stage_that_is_not_a_state_is_refused(self) -> None:
        # The envelope's own field is the last one an emitter supplies, and
        # the sinks would carry anything: prose naming a path, offered as the
        # state an issue was in, or a label that is no state.
        for named in _UNKNOWN_STAGES:
            with self.subTest(stage=named):
                gh = FakeGitHubClient()
                appended: list = []
                with patch(_ANALYTICS_APPEND, appended.append), self.assertLogs(_WORKFLOW_CHANNEL, level=_ERROR):
                    payload = _telemetry.emit_late_event(
                        gh,
                        _VERDICT_EVENT,
                        _support.measured_generation(),
                        stage=named,
                    )
                self.assertEqual(payload, {})
                self.assertEqual(gh.recorded_events, [])
                self.assertEqual(appended, [])


class FailingSinkTest(unittest.TestCase):
    """A sink that refuses costs the record and nothing else."""

    def test_a_failed_audit_still_records_metrics(self) -> None:
        gh = FakeGitHubClient()
        appended: list = []
        with patch.object(gh, _EMIT_EVENT, side_effect=OSError), self.assertLogs(_WORKFLOW_CHANNEL, level=_ERROR):
            _emit(gh, appended)
        self.assertEqual(appended[-1][_EVENT_KEY], _LATE_VERDICT)

    def test_a_failed_analytics_still_audits(self) -> None:
        gh = FakeGitHubClient()
        with patch(_ANALYTICS_APPEND, side_effect=RuntimeError), self.assertLogs(_WORKFLOW_CHANNEL, level=_ERROR):
            _emit_verdict(gh)
        self.assertEqual(gh.recorded_events[-1][_EVENT_KEY], _LATE_VERDICT)

    def test_both_sinks_failing_does_not_raise(self) -> None:
        # Workflow disposition is reconciled from pinned state, never from
        # what a sink accepted, so the emission cannot raise into a tick.
        gh = FakeGitHubClient()
        with (
            patch.object(gh, _EMIT_EVENT, side_effect=OSError),
            patch(_ANALYTICS_APPEND, side_effect=OSError),
            self.assertLogs(_WORKFLOW_CHANNEL, level=_ERROR),
        ):
            payload = _emit_verdict(gh)
        self.assertEqual(payload["verdict"], "single")


if __name__ == "__main__":
    unittest.main()
