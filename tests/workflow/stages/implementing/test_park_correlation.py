# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the parks that emit their own human-wait record report beside it.

The question park and the two checkout refusals bypass the shared funnel, so
nothing the funnel's own tests prove covers them. Each case here drives the
implementing handler with the audit sink OFF and the analytics sink ON -- the
install an operator counting human waits actually runs -- and reads the
analytics line back, because that is the surface the correlation is for.

Three things the records must keep saying: the reason is the branch that ran,
the payload is bounded to declared identifiers, and a wait is recorded once,
when the issue enters it.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.agents.models import ToolLifecycle
from orchestrator.workflow.engine import guards as _guards
from orchestrator.workflow.stages.implementing import park_correlation as _park_correlation
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import (
    EVENT_PARK_AWAITING_HUMAN,
    LABEL_IMPLEMENTING,
    PROVIDER_OVERLOAD_MESSAGE,
    SESSION_LIMIT_MESSAGE,
    STAGE_IMPLEMENTING,
    _agent,
    _analytics_records,
    _PatchedWorkflowMixin,
)
from tests.workflow.report_values import _reported

_EVENT_PATH_ATTR = "EVENT_LOG_PATH"
_ANALYTICS_FILE = "analytics.jsonl"

_KEY_REASON = "reason"
_KEY_ROUTE = "route"
_KEY_STAGE = "stage"
_KEY_EXIT_CODE = "exit_code"
_KEY_PR_NUMBER = "pr_number"
_KEY_DIRTY_FILES = "dirty_files"
_KEY_PARK_REASON = "park_reason"
_AGENT_ROLE = "agent_role"
_SESSION_ID = "session_id"
_TIMED_OUT = "timed_out"

_DEVELOPER = "developer"
_QUESTION_ISSUE = 610
_DEV_SESSION = "sess-park-1"
_QUESTION_TEXT = "Which database should I use for the ledger?"
_STDERR_TEXT = "Traceback: the backend died halfway through the stream"
# The envelope every analytics record carries on top of its own extras.
_ENVELOPE = frozenset(("ts", "repo", "issue", "event", _KEY_STAGE, _KEY_REASON))
_DIRTY_PATHS = ("ledger.py", "ledger_test.py")
_PINNED_PR_NUMBER = 77
_PINNED_RETRY_COUNT = 2
_PINNED_CONFLICT_ROUND = 3
_PARK_EXECUTION_FAILED = "agent_execution_failed"


def _flattened(record: dict) -> str:
    """Everything the record actually wrote, as one string to search."""
    return " ".join(str(written) for written in record.values())


class _ParkRecordCase(unittest.TestCase, _PatchedWorkflowMixin):
    """Drives one implementing tick against a live analytics sink."""

    def _park_records(self, **run_options) -> tuple[list[dict], FakeGitHubClient]:
        """Records one tick wrote, and the client it left its state on."""
        github = FakeGitHubClient()
        issue = make_issue(_QUESTION_ISSUE, label=LABEL_IMPLEMENTING)
        github.add_issue(issue)
        with tempfile.TemporaryDirectory(prefix="park-correlation-") as sink_dir:
            log_file = Path(sink_dir, _ANALYTICS_FILE)
            # The audit sink is off and the analytics sink is on: the install
            # an operator who wants the counts without the JSONL trace runs,
            # and the one that shows the fan-out is not riding the audit log.
            with patch.object(config, _EVENT_PATH_ATTR, None):
                self._run_implementing(
                    github, issue, analytics_log_path=log_file, **run_options,
                )
            self.assertEqual(
                [written.name for written in Path(sink_dir).iterdir()],
                [_ANALYTICS_FILE],
            )
            records = _analytics_records(log_file, event=EVENT_PARK_AWAITING_HUMAN)
        return records, github

    def _only_park(self, **run_options) -> tuple[dict, dict]:
        records, github = self._park_records(**run_options)
        self.assertEqual(len(records), 1)
        return records[0], github.pinned_data(_QUESTION_ISSUE)

    def _assert_park_reason(
        self, record: dict, pinned: dict, reason: str, exit_code: int = 1,
    ) -> None:
        self.assertEqual(record[_KEY_REASON], reason)
        self.assertEqual(record[_KEY_EXIT_CODE], exit_code)
        self.assertEqual(pinned.get(_KEY_PARK_REASON), reason)


class DeveloperQuestionParkRecordTest(_ParkRecordCase):
    """A run that answered without committing is recorded as a question."""

    def test_question_park_records_reason_and_route(self) -> None:
        record, _pinned = self._only_park(
            run_agent=_agent(session_id=_DEV_SESSION, last_message=_QUESTION_TEXT),
            has_new_commits=False,
        )
        self.assertEqual(record[_KEY_STAGE], STAGE_IMPLEMENTING)
        self.assertEqual(record[_KEY_REASON], "agent_question")
        self.assertEqual(record[_KEY_ROUTE], _guards._ROUTE_DEV_RUN)
        self.assertEqual(record[_AGENT_ROLE], _DEVELOPER)
        self.assertEqual(record[_SESSION_ID], _DEV_SESSION)
        self.assertEqual(record[_KEY_EXIT_CODE], 0)
        # No pull request exists yet, so the field is dropped rather than
        # written as a null an aggregation would have to special-case.
        self.assertNotIn(_KEY_PR_NUMBER, record)

    def test_question_park_leaves_park_reason_null(self) -> None:
        # The event names the classification; the durable field stays null
        # because null is what tells a later tick this park is waiting on a
        # human's actual guidance rather than on a retry.
        record, pinned = self._only_park(
            run_agent=_agent(session_id=_DEV_SESSION, last_message=_QUESTION_TEXT),
            has_new_commits=False,
        )
        self.assertEqual(record[_KEY_REASON], "agent_question")
        self.assertIsNone(pinned.get(_KEY_PARK_REASON))

    def test_park_payload_carries_no_agent_prose(self) -> None:
        record, _ = self._only_park(
            run_agent=_agent(
                session_id=_DEV_SESSION,
                last_message=_QUESTION_TEXT,
                stderr=_STDERR_TEXT,
            ),
            has_new_commits=False,
        )
        written = _flattened(record)
        for prose in (_QUESTION_TEXT, _STDERR_TEXT):
            self.assertNotIn(prose, written)
        self.assertEqual(
            set(record) - _ENVELOPE - _guards.ALLOWED_CORRELATION_FIELDS,
            set(),
        )


class FailedRunParkRecordTest(_ParkRecordCase):
    """Silent, quota, and provider failures keep their own typed reasons."""

    def test_silent_run_records_its_exit_status(self) -> None:
        record, pinned = self._only_park(
            run_agent=_agent(session_id=_DEV_SESSION, last_message="", exit_code=1),
            has_new_commits=False,
        )
        self.assertEqual(record[_KEY_REASON], "agent_silent")
        self.assertEqual(record[_KEY_EXIT_CODE], 1)
        self.assertEqual(pinned.get(_KEY_PARK_REASON), "agent_silent")

    def test_backend_failures_report_by_name(self) -> None:
        # Both arrive as the non-empty final message a real question arrives
        # on. The event names which failure it was; the durable reason stays
        # the retryable one `/orchestrator continue` keys off.
        for last_message, exit_code, reason in (
            (SESSION_LIMIT_MESSAGE, 0, "agent_session_limit"),
            (PROVIDER_OVERLOAD_MESSAGE, 1, "agent_provider_unavailable"),
        ):
            with self.subTest(reason=reason):
                record, pinned = self._only_park(
                    run_agent=_agent(
                        session_id=_DEV_SESSION,
                        last_message=last_message,
                        exit_code=exit_code,
                    ),
                    has_new_commits=False,
                )
                self.assertEqual(record[_KEY_REASON], reason)
                self.assertEqual(record[_KEY_EXIT_CODE], exit_code)
                self.assertEqual(record[_KEY_ROUTE], _guards._ROUTE_DEV_RUN)
                self.assertEqual(pinned.get(_KEY_PARK_REASON), "agent_silent")

    def test_unfinished_command_records_failure(self) -> None:
        step = ToolLifecycle(step_index=1, tool_name="run_command", state="ACTIVE")
        record, pinned = self._only_park(
            run_agent=_agent(
                session_id=_DEV_SESSION,
                last_message="",
                exit_code=1,
                interrupted=True,
                unfinished_steps=(step,),
            ),
            has_new_commits=False,
        )
        self._assert_park_reason(record, pinned, _PARK_EXECUTION_FAILED)
        self.assertEqual(record[_KEY_ROUTE], _guards._ROUTE_DEV_RUN)

    def test_unfinished_command_precedes_question(self) -> None:
        # Even if the agent returned clarification text, structured unfinished
        # command steps take precedence over message-based question branches.
        step = ToolLifecycle(step_index=1, tool_name="run_command", state="ACTIVE")
        record, pinned = self._only_park(
            run_agent=_agent(
                session_id=_DEV_SESSION,
                last_message="Should I proceed with running the remaining tests?",
                exit_code=1,
                interrupted=True,
                unfinished_steps=(step,),
            ),
            has_new_commits=False,
        )
        self._assert_park_reason(record, pinned, _PARK_EXECUTION_FAILED)


class CheckoutRefusalRecordTest(_ParkRecordCase):
    """The publication seam's two refusals report which half of it failed."""

    def test_dirty_tree_counts_the_paths_it_refused(self) -> None:
        record, _ = self._only_park(
            run_agent=_agent(session_id=_DEV_SESSION, last_message="committed"),
            has_new_commits=[False, True],
            dirty_files=_DIRTY_PATHS,
            push_branch=True,
        )
        self.assertEqual(record[_KEY_REASON], "dirty_worktree")
        self.assertEqual(record[_KEY_DIRTY_FILES], len(_DIRTY_PATHS))
        self.assertEqual(record[_KEY_ROUTE], _guards._ROUTE_CANDIDATE_PUBLICATION)
        self.assertEqual(record[_AGENT_ROLE], _DEVELOPER)
        # A run that finished on its own is recorded as such, so a refusal a
        # killed run earned can be told from this one.
        self.assertFalse(record[_TIMED_OUT])
        written = _flattened(record)
        for path in _DIRTY_PATHS:
            self.assertNotIn(path, written)

    def test_unreadable_tree_reports_no_count(self) -> None:
        # A reading that never happened establishes nothing about the tree, so
        # a count of zero here would report it as one proved to be carrying
        # nothing.
        record, _ = self._only_park(
            run_agent=_agent(session_id=_DEV_SESSION, last_message="committed"),
            has_new_commits=[False, True],
            dirty_files=(),
            tree_readable=False,
            push_branch=True,
        )
        self.assertEqual(record[_KEY_REASON], "unreadable_worktree")
        self.assertNotIn(_KEY_DIRTY_FILES, record)
        self.assertEqual(record[_KEY_ROUTE], _guards._ROUTE_CANDIDATE_PUBLICATION)


class HumanWaitIsRecordedOnceTest(_ParkRecordCase):
    """One record per transition into a wait, and none for work that landed."""

    def test_successful_publication_records_no_wait(self) -> None:
        records, github = self._park_records(
            run_agent=_agent(session_id=_DEV_SESSION, last_message=_reported()),
            has_new_commits=[False, True],
            dirty_files=(),
            push_branch=True,
        )
        # The tick really finished its work -- the pull request is open and
        # the issue is not waiting -- so the empty sink is the absence of a
        # human wait rather than the absence of a tick.
        self.assertEqual(len(github.opened_prs), 1)
        self.assertFalse(github.pinned_data(_QUESTION_ISSUE).get("awaiting_human"))
        self.assertEqual(records, [])

    def test_second_tick_on_a_wait_adds_nothing(self) -> None:
        github = FakeGitHubClient()
        issue = make_issue(_QUESTION_ISSUE, label=LABEL_IMPLEMENTING)
        github.add_issue(issue)
        with tempfile.TemporaryDirectory(prefix="park-correlation-repeat-") as sink_dir:
            log_file = Path(sink_dir, _ANALYTICS_FILE)
            with patch.object(config, _EVENT_PATH_ATTR, None):
                self._tick_twice(github, issue, log_file)
            records = _analytics_records(log_file, event=EVENT_PARK_AWAITING_HUMAN)
        # Still waiting after the second poll, and still on one record: a tick
        # that meets a wait it did not open records nothing.
        self.assertTrue(github.pinned_data(_QUESTION_ISSUE).get("awaiting_human"))
        self.assertEqual(len(records), 1)

    def _tick_twice(self, github, issue, log_file: Path) -> None:
        """Park the issue, then poll it again with nothing new on the thread."""
        self._one_tick(github, issue, log_file)
        self._one_tick(github, issue, log_file)

    def _one_tick(self, github, issue, log_file: Path) -> None:
        self._run_implementing(
            github,
            issue,
            analytics_log_path=log_file,
            run_agent=_agent(session_id=_DEV_SESSION, last_message=_QUESTION_TEXT),
            has_new_commits=False,
        )


class CorrelatedFieldsTest(unittest.TestCase):
    """The payload builder reads the identifiers pinned state already holds."""

    def test_pinned_identity_rides_along(self) -> None:
        state = MagicMock()
        state.get.side_effect = lambda key, *rest: {
            "retry_count": _PINNED_RETRY_COUNT,
            "pr_number": str(_PINNED_PR_NUMBER),
        }.get(key)
        fields = _park_correlation._correlated_fields(
            state,
            _guards._ParkedRun(
                _agent(session_id=_DEV_SESSION, last_message=_QUESTION_TEXT),
                _guards._ROUTE_CONFLICT_RESUME,
                conflict_round=_PINNED_CONFLICT_ROUND,
            ),
        )
        self.assertEqual(fields[_KEY_PR_NUMBER], _PINNED_PR_NUMBER)
        self.assertEqual(fields["retry_count"], _PINNED_RETRY_COUNT)
        self.assertEqual(fields["conflict_round"], _PINNED_CONFLICT_ROUND)
        self.assertEqual(fields[_KEY_ROUTE], _guards._ROUTE_CONFLICT_RESUME)

    def test_undeclared_field_is_refused(self) -> None:
        with self.assertRaises(TypeError):
            _park_correlation._correlated_fields(
                MagicMock(),
                _guards._ParkedRun(_agent(last_message=""), _guards._ROUTE_DEV_RUN),
                last_message=_QUESTION_TEXT,
            )


if __name__ == "__main__":
    unittest.main()
