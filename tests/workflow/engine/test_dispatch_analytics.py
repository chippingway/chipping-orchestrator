# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Stage analytics records emitted by the dispatcher, label flips, and parks:
`_process_issue` writes one `stage_evaluation` record per handler call
(happy-path, a handler that parks, no-stage pickup, error path, backlog-skip
short-circuit, disabled-sink no-op); `set_workflow_label` writes one `stage_enter`
analytics record per non-None label transition; emitted `park_awaiting_human`
events fan out to the analytics recorder."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator.github.labels import BACKLOG_LABEL, PAUSED_LABEL
from orchestrator.observability.analytics import settings as analytics_settings
from orchestrator.workflow.engine import (
    guards as _guards,
    issue_processing as _issue_processing,
    pickup,
)
from orchestrator.workflow.stages.implementing import handler as implementing
from tests.support.fakes import FakeGitHubClient, FakeIssue, FakeLabel, make_issue
from tests.workflow.fixtures import (
    _TEST_SPEC,
    EVENT_PARK_AWAITING_HUMAN,
    EVENT_STAGE_ENTER,
    EVENT_STAGE_EVALUATION,
    LABEL_IMPLEMENTING,
    LABEL_VALIDATING,
    TEST_REPO_SLUG,
    _analytics_records,
)

# The tag each label reports itself as: what the analytics row records.
_DECOMPOSING_STAGE = "decomposing"
_IMPLEMENTING_STAGE = "implementing"
_VALIDATING_STAGE = "validating"

_ANALYTICS_FILENAME = "analytics.jsonl"
# The reviewer handler is patched by name: this module wants the validating
# handler owner only as a patch target, and naming it instead of importing it
# keeps the module under the import ceiling.
_VALIDATING_HANDLER = (
    "orchestrator.workflow.stages.validating.handler._handle_validating"
)
_IMPLEMENTING_HANDLER = (
    "orchestrator.workflow.stages.implementing.handler._handle_implementing"
)
_ANALYTICS_PATH_ATTR = "ANALYTICS_LOG_PATH"
_STAGE_KEY = "stage"
_EVENT_KEY = "event"
_ISSUE_KEY = "issue"
_REPO_KEY = "repo"
_TS_KEY = "ts"
_KEY_REASON = "reason"
_RESULT_KEY = "result"
_TIMEOUT_PR = 42
_HARD_SKIPPED_ISSUE = 8004
_SUCCESS_ISSUE = 8001
_UNLABELED_ISSUE = 8002
_ERROR_ISSUE = 8003
_DISABLED_SINK_ISSUE = 8005
_PARKING_ISSUE = 8006
_STAGE_ENTER_ISSUE = 8101
_LABEL_CLEAR_ISSUE = 8102
_PARK_ISSUE = 8201
_QUESTION_REASON = "agent_question"
_PARK_REASON = "agent_timeout"
_PARK_MESSAGE = "please advise"
_PARK_LOG = "park_analytics.jsonl"
_RECORD_PARK_TARGET = (
    "orchestrator.observability.analytics.recording.events"
    ".record_park_awaiting_human"
)


def _stage_evaluations(path: Path, issue_number: int) -> list[dict]:
    return [
        record for record in _analytics_records(path)
        if record.get(_EVENT_KEY) == EVENT_STAGE_EVALUATION
        and record.get(_ISSUE_KEY) == issue_number
    ]


def _process_hard_skipped_issue(skip_label: str) -> tuple[MagicMock, list[dict]]:
    with tempfile.TemporaryDirectory(prefix="analytics-skip-") as temp_dir:
        path = Path(temp_dir) / _ANALYTICS_FILENAME
        gh = FakeGitHubClient()
        issue = make_issue(_HARD_SKIPPED_ISSUE, label=LABEL_IMPLEMENTING)
        issue.labels.append(FakeLabel(skip_label))
        gh.add_issue(issue)
        handler_mock = MagicMock()
        with patch.object(analytics_settings, _ANALYTICS_PATH_ATTR, path), patch.object(
            implementing,
            "_handle_implementing",
            handler_mock,
        ):
            _issue_processing._process_issue(gh, _TEST_SPEC, issue)
        return handler_mock, _analytics_records(path)


def _process_error(gh: FakeGitHubClient, issue) -> RuntimeError:
    try:
        _issue_processing._process_issue(gh, _TEST_SPEC, issue)
    except RuntimeError as error:
        return error
    raise AssertionError("the stage handler did not propagate its error")


class StageEvaluationAnalyticsTest(unittest.TestCase):
    """`_process_issue` times every dispatch and appends a single
    `stage_evaluation` analytics record carrying repo / issue / stage /
    duration_s / result. The record fires on both happy-path and
    exception paths; an unhandled handler exception still propagates so
    the per-issue tick try/except in `workflow.engine.tick.tick` owns the isolation.
    Backlog-skips are NOT timed -- no handler runs.
    """

    def test_success_appends_evaluation_record(self) -> None:
        # End-to-end: a labeled issue runs through the dispatcher with
        # the matching handler mocked, and the wrapper writes one
        # `stage_evaluation` line carrying the current label + ok result.
        with tempfile.TemporaryDirectory(prefix="analytics-stageval-") as td:
            path = Path(td) / _ANALYTICS_FILENAME
            gh = FakeGitHubClient()
            issue = make_issue(_SUCCESS_ISSUE, label=LABEL_IMPLEMENTING)
            gh.add_issue(issue)
            with patch.object(analytics_settings, _ANALYTICS_PATH_ATTR, path), \
                 patch.object(implementing, "_handle_implementing"):
                _issue_processing._process_issue(gh, _TEST_SPEC, issue)
            record = _stage_evaluations(path, _SUCCESS_ISSUE)[0]
        self.assertEqual(record[_REPO_KEY], TEST_REPO_SLUG)
        self.assertEqual(record[_STAGE_KEY], _IMPLEMENTING_STAGE)
        self.assertEqual(record[_RESULT_KEY], "ok")
        self.assertIn("duration_s", record)
        self.assertGreaterEqual(record["duration_s"], 0)

    def test_a_parking_handler_still_evaluates_ok(self) -> None:
        # A park is the workflow waiting on a human, not the handler failing:
        # the evaluation says the handler returned without raising, and the
        # park record beside it is what says the issue did not progress.
        with tempfile.TemporaryDirectory(prefix="analytics-park-eval-") as park_dir:
            records = self._dispatch_parking_issue(
                Path(park_dir, _ANALYTICS_FILENAME),
            )
        self.assertEqual(
            [
                (record[_EVENT_KEY], record.get(_RESULT_KEY), record.get(_KEY_REASON))
                for record in records
            ],
            [
                (EVENT_PARK_AWAITING_HUMAN, None, _QUESTION_REASON),
                (EVENT_STAGE_EVALUATION, "ok", None),
            ],
        )

    def test_unlabeled_issue_records_no_stage(
        self,
    ) -> None:
        # The dispatcher routes a label=None issue to `_handle_pickup`;
        # the `stage_evaluation` record drops the optional `stage` field
        # (build_record's documented contract for None values) so the
        # absence of a workflow label is encoded as "no stage" rather
        # than a string sentinel that downstream aggregations would
        # have to special-case.
        with tempfile.TemporaryDirectory(prefix="analytics-pickup-") as td:
            path = Path(td) / _ANALYTICS_FILENAME
            gh = FakeGitHubClient()
            issue = make_issue(_UNLABELED_ISSUE)
            gh.add_issue(issue)
            with patch.object(analytics_settings, _ANALYTICS_PATH_ATTR, path), \
                 patch.object(pickup, "_handle_pickup"):
                _issue_processing._process_issue(gh, _TEST_SPEC, issue)
            record = _stage_evaluations(path, _UNLABELED_ISSUE)[0]
        self.assertNotIn(_STAGE_KEY, record)
        self.assertEqual(record[_RESULT_KEY], "ok")

    def test_error_is_recorded_and_propagated(
        self,
    ) -> None:
        # The handler raising must NOT suppress the exception: the
        # tick loop's per-issue isolation depends on the dispatcher
        # surfacing failures so they can be logged and the loop
        # continues with the next issue. The record must still land
        # with result=error and the duration captured up to the raise.
        with tempfile.TemporaryDirectory(prefix="analytics-err-") as td:
            path = Path(td) / _ANALYTICS_FILENAME
            gh = FakeGitHubClient()
            issue = make_issue(_ERROR_ISSUE, label=LABEL_VALIDATING)
            gh.add_issue(issue)
            with (
                patch.object(analytics_settings, _ANALYTICS_PATH_ATTR, path),
                patch(
                    _VALIDATING_HANDLER,
                    side_effect=RuntimeError("handler blew up"),
                ),
            ):
                self.assertEqual(
                    str(_process_error(gh, issue)),
                    "handler blew up",
                )
            record = _stage_evaluations(path, _ERROR_ISSUE)[0]
        self.assertEqual(record[_STAGE_KEY], _VALIDATING_STAGE)
        self.assertEqual(record[_RESULT_KEY], "error")
        self.assertIn("duration_s", record)

    def test_hard_skip_records_no_evaluation(self) -> None:
        # A hard-skip control label (`backlog` / `paused`) parks the issue
        # OUTSIDE the state machine before any handler runs; there is nothing
        # to time. The early return must short-circuit before the timing
        # wrapper writes a record so operators do not see a noisy run of
        # zero-duration evaluations for issues the orchestrator ignores.
        for skip_label in (BACKLOG_LABEL, PAUSED_LABEL):
            with self.subTest(label=skip_label):
                handler_mock, records = _process_hard_skipped_issue(skip_label)
                handler_mock.assert_not_called()
                self.assertEqual(records, [])

    def test_disabled_sink_writes_no_evaluation(self) -> None:
        # The off knob is documented as a silent no-op for the analytics
        # sink. `_process_issue` must respect it so an operator who set
        # ANALYTICS_LOG_PATH=off does not see a phantom file appear.
        with tempfile.TemporaryDirectory(prefix="analytics-off-") as td:
            sentinel = Path(td) / "must-not-be-created.jsonl"
            gh = FakeGitHubClient()
            issue = make_issue(_DISABLED_SINK_ISSUE, label=LABEL_IMPLEMENTING)
            gh.add_issue(issue)
            with patch.object(analytics_settings, _ANALYTICS_PATH_ATTR, None), \
                 patch.object(implementing, "_handle_implementing"):
                _issue_processing._process_issue(gh, _TEST_SPEC, issue)
            self.assertFalse(sentinel.exists())
            self.assertEqual(list(Path(td).iterdir()), [])

    def _dispatch_parking_issue(self, path: Path) -> list[dict]:
        client = FakeGitHubClient()
        parking_issue = make_issue(_PARKING_ISSUE, label=LABEL_IMPLEMENTING)
        client.add_issue(parking_issue)
        with patch.object(analytics_settings, _ANALYTICS_PATH_ATTR, path), patch(
            _IMPLEMENTING_HANDLER,
            side_effect=lambda *_args, **_kwargs: _guards._park_awaiting_human(
                client,
                parking_issue,
                MagicMock(),
                _PARK_MESSAGE,
                reason=_QUESTION_REASON,
            ),
        ):
            _issue_processing._process_issue(client, _TEST_SPEC, parking_issue)
        return _analytics_records(path)


class StageEnterAnalyticsRecordTest(unittest.TestCase):
    """`set_workflow_label` is the single chokepoint for stage transitions;
    every flip emits both the audit `stage_enter` event (to
    `EVENT_LOG_PATH`) and an analytics-compatible `stage_enter` record
    (to `ANALYTICS_LOG_PATH`). Workflow correctness still keys on pinned
    GitHub state; the analytics record is observability only.
    """

    def test_label_transition_writes_stage_enter(self) -> None:
        with tempfile.TemporaryDirectory(prefix="analytics-stage-enter-") as td:
            path = Path(td) / _ANALYTICS_FILENAME
            with patch.object(analytics_settings, _ANALYTICS_PATH_ATTR, path):
                gh = FakeGitHubClient()
                issue = make_issue(_STAGE_ENTER_ISSUE)
                gh.add_issue(issue)
                gh.set_workflow_label(issue, LABEL_IMPLEMENTING)
                gh.set_workflow_label(issue, LABEL_VALIDATING)
            records = _analytics_records(path)
        self.assertEqual(len(records), 2)
        self.assertEqual(
            [record[_STAGE_KEY] for record in records],
            [_IMPLEMENTING_STAGE, _VALIDATING_STAGE],
        )
        self.assertEqual(
            list(map(self._stage_enter_projection, records)),
            [
                (EVENT_STAGE_ENTER, _STAGE_ENTER_ISSUE, TEST_REPO_SLUG),
                (EVENT_STAGE_ENTER, _STAGE_ENTER_ISSUE, TEST_REPO_SLUG),
            ],
        )

    def test_label_clear_emits_no_record(self) -> None:
        # Mirrors the existing `_emit_stage_enter` no-op for None labels:
        # clearing a label is not a stage and must not produce a phantom
        # `stage_enter` analytics record.
        with tempfile.TemporaryDirectory(prefix="analytics-stage-none-") as td:
            path = Path(td) / _ANALYTICS_FILENAME
            with patch.object(analytics_settings, _ANALYTICS_PATH_ATTR, path):
                gh = FakeGitHubClient()
                issue = make_issue(_LABEL_CLEAR_ISSUE, label=LABEL_IMPLEMENTING)
                gh.add_issue(issue)
                gh.set_workflow_label(issue, None)
        self.assertEqual(_analytics_records(path), [])

    def _stage_enter_projection(self, record: dict) -> tuple:
        datetime.fromisoformat(record["ts"])
        return record[_EVENT_KEY], record[_ISSUE_KEY], record[_REPO_KEY]


def _capture_park_records(
    client: FakeGitHubClient,
    stage: str,
    reason: str,
    **correlation,
) -> tuple[dict, dict]:
    with tempfile.TemporaryDirectory(prefix="analytics-park-") as park_dir:
        log_file = Path(park_dir, _PARK_LOG)
        with patch.object(analytics_settings, _ANALYTICS_PATH_ATTR, log_file):
            park_issue = make_issue(_PARK_ISSUE, label=stage)
            client.add_issue(park_issue)
            _guards._park_awaiting_human(
                client,
                park_issue,
                MagicMock(),
                _PARK_MESSAGE,
                reason=reason,
                **correlation,
            )
        return client.recorded_events[0], _analytics_records(log_file)[0]


class ParkAwaitingHumanAnalyticsRecordTest(unittest.TestCase):
    """Every emitted `park_awaiting_human` event fans out to analytics."""

    def test_park_writes_analytics_record(self) -> None:
        with tempfile.TemporaryDirectory(prefix="analytics-park-") as park_dir:
            log_file = Path(park_dir, _PARK_LOG)
            with patch.object(analytics_settings, _ANALYTICS_PATH_ATTR, log_file):
                self._run_park(FakeGitHubClient())
            rec = _analytics_records(log_file)[0]
        self.assertEqual(rec[_EVENT_KEY], EVENT_PARK_AWAITING_HUMAN)
        self.assertEqual(rec[_REPO_KEY], TEST_REPO_SLUG)
        self.assertEqual(rec[_ISSUE_KEY], _PARK_ISSUE)
        self.assertEqual(rec[_STAGE_KEY], _IMPLEMENTING_STAGE)
        self.assertEqual(rec[_KEY_REASON], _PARK_REASON)

    def test_disabled_sink_writes_no_record(self) -> None:
        with tempfile.TemporaryDirectory(prefix="analytics-park-off-") as park_dir:
            sentinel = Path(park_dir, "must-not-exist.jsonl")
            with patch.object(analytics_settings, _ANALYTICS_PATH_ATTR, None):
                self._run_park(FakeGitHubClient())
            self.assertFalse(sentinel.exists())
            self.assertEqual(list(Path(park_dir).iterdir()), [])

    def test_park_failure_leaves_state_intact(self) -> None:
        client = FakeGitHubClient()
        state = MagicMock()
        with (
            patch(
                _RECORD_PARK_TARGET,
                side_effect=RuntimeError("disk full"),
            ),
            self.assertLogs("orchestrator.github", level="WARNING"),
        ):
            park_issue = self._run_park(client, state=state)
        self.assertEqual(len(park_issue.comments), 1)
        self.assertIn(_PARK_MESSAGE, park_issue.comments[0].body)
        state.set.assert_any_call("awaiting_human", True)
        self.assertEqual(client.workflow_label(park_issue), LABEL_IMPLEMENTING)

    def test_failed_runs_share_payload(self) -> None:
        event, record = _capture_park_records(
            FakeGitHubClient(),
            LABEL_VALIDATING,
            "reviewer_timeout",
            agent_role="reviewer",
            session_id="sess-timeout-1",
            review_round=1,
            retry_count=0,
            pr_number=_TIMEOUT_PR,
        )
        self._assert_shared_payload(
            event,
            record,
            {
                _EVENT_KEY: EVENT_PARK_AWAITING_HUMAN,
                _REPO_KEY: TEST_REPO_SLUG,
                _ISSUE_KEY: _PARK_ISSUE,
                _STAGE_KEY: _VALIDATING_STAGE,
                _KEY_REASON: "reviewer_timeout",
                "agent_role": "reviewer",
                "session_id": "sess-timeout-1",
                "review_round": 1,
                "retry_count": 0,
                "pr_number": _TIMEOUT_PR,
            },
        )
        event, record = _capture_park_records(
            FakeGitHubClient(),
            _DECOMPOSING_STAGE,
            "decomposer_silent",
            agent_role="decomposer",
            session_id="sess-fail-2",
            retry_count=2,
        )
        self._assert_shared_payload(
            event,
            record,
            {
                _EVENT_KEY: EVENT_PARK_AWAITING_HUMAN,
                _REPO_KEY: TEST_REPO_SLUG,
                _ISSUE_KEY: _PARK_ISSUE,
                _STAGE_KEY: _DECOMPOSING_STAGE,
                _KEY_REASON: "decomposer_silent",
                "agent_role": "decomposer",
                "session_id": "sess-fail-2",
                "retry_count": 2,
            },
        )

    def test_unsupported_field_rejected(self) -> None:
        client = FakeGitHubClient()
        state = MagicMock()
        with self.assertRaises(TypeError):
            self._run_park(
                client,
                state=state,
                reason="reviewer_timeout",
                agent_role="reviewer",
                unsupported_field="unexpected_payload",
            )
        self.assertEqual(len(client.posted_comments), 0)
        self.assertEqual(len(client.recorded_events), 0)
        state.set.assert_not_called()

    def _assert_shared_payload(
        self,
        audit_record: dict,
        analytics_record: dict,
        expected_fields: dict,
    ) -> None:
        for field_name, expected in expected_fields.items():
            self.assertEqual(audit_record.get(field_name), expected)
            self.assertEqual(analytics_record.get(field_name), expected)
        self.assertEqual(
            set(audit_record.keys()) - {_TS_KEY},
            set(analytics_record.keys()) - {_TS_KEY},
        )

    def _run_park(
        self,
        client: FakeGitHubClient,
        state: MagicMock | None = None,
        reason: str | None = _PARK_REASON,
        stage: str | None = LABEL_IMPLEMENTING,
        **correlation,
    ) -> FakeIssue:
        park_issue = make_issue(_PARK_ISSUE, label=stage)
        client.add_issue(park_issue)
        target_state = MagicMock() if state is None else state
        _guards._park_awaiting_human(
            client,
            park_issue,
            target_state,
            _PARK_MESSAGE,
            reason=reason,
            **correlation,
        )
        return park_issue


if __name__ == "__main__":
    unittest.main()
