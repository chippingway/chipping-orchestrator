# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a question park reports beside its reason, and how often it says it.

Every case drives one tick with the audit sink OFF and the analytics sink ON --
the install an operator counting human waits actually runs -- and reads the
analytics line back, because that is the surface the correlation is for.

Three things these records have to keep saying: which road the tick reached its
park from, which conversation the park belongs to, and nothing at all about
what the agent wrote. A fourth is about how often they say it: a wait is
recorded when the issue enters one, never again while it stands.
"""

from __future__ import annotations

import contextlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import guards as _guards
from tests.support.fakes import FakeComment
from tests.workflow.fixtures import (
    BACKEND_CLAUDE,
    EVENT_PARK_AWAITING_HUMAN,
    KEY_AWAITING_HUMAN,
    STAGE_QUESTION,
    _agent,
    _analytics_records,
)
from tests.workflow.stages.question.question_conversation_test_support import (
    _QuestionWorkflowMixin,
)
from tests.workflow.stages.question.question_test_support import (
    PARK_QUESTION_ANSWER,
    QUESTION_SESSION,
    _seed_question,
)

_ANALYTICS_FILE = "analytics.jsonl"
_EVENT_PATH_ATTR = "EVENT_LOG_PATH"
_SINK_PREFIX = "question-park-correlation-"

_KEY_REASON = "reason"
_KEY_STAGE = "stage"
_KEY_ROUTE = "route"
_KEY_AGENT_ROLE = "agent_role"
_KEY_SESSION_ID = "session_id"
_KEY_PR_NUMBER = "pr_number"

# The vocabulary spelled independently of the owner, because these values go
# into two durable sinks: a rename is a change to what an operator's saved
# query matches, not a refactor.
_ROUTE_ROUND = "question_round"
_ROUTE_RESUME = "question_resume"
_QUESTION_ROLE = "question"

# The envelope every analytics record carries on top of its own extras.
_ENVELOPE = frozenset((
    "ts", "repo", "issue", "event", _KEY_STAGE, _KEY_REASON,
))

_FRESH_ISSUE_NUMBER = 640
_RESUMED_ISSUE_NUMBER = 641
_PR_BACKED_ISSUE_NUMBER = 642
_SESSIONLESS_ISSUE_NUMBER = 643
_PROSE_ISSUE_NUMBER = 644
_REPEAT_ISSUE_NUMBER = 645

_ANSWER_TEXT = "The ledger lives in `orchestrator/observability/`."
_STDERR_TEXT = "Traceback: the backend died halfway through the stream"
_HUMAN_REPLY = "and where is its schema written down?"
_RESUMED_ANSWER = "Beside the sink, in the same package."
_REPLY_ID = 46000
_PARKED_WATERMARK = 45000
_RECORDED_PR_NUMBER = 88


def _flattened(record: dict) -> str:
    """Everything the record actually wrote, as one string to search."""
    return " ".join(str(written) for written in record.values())


class _QuestionParkRecordCase(unittest.TestCase, _QuestionWorkflowMixin):
    """Drives question ticks against a live analytics sink."""

    @contextlib.contextmanager
    def _analytics_sink(self):
        """A sink the ticks inside write to, with the audit sink switched off.

        The audit sink being off is what shows the fan-out is not riding the
        JSONL trace: an operator who keeps the counts without the transcript
        still gets the park.
        """
        with tempfile.TemporaryDirectory(prefix=_SINK_PREFIX) as sink_dir:
            with patch.object(config, _EVENT_PATH_ATTR, None):
                yield Path(sink_dir, _ANALYTICS_FILE)
            self.assertLessEqual(
                {written.name for written in Path(sink_dir).iterdir()},
                {_ANALYTICS_FILE},
            )

    def _park_records(self, gh, issue, **run_options) -> list[dict]:
        with self._analytics_sink() as log_file:
            self._run_question(
                gh, issue, analytics_log_path=log_file, **run_options,
            )
            records = _analytics_records(
                log_file, event=EVENT_PARK_AWAITING_HUMAN,
            )
        return records

    def _only_park(self, gh, issue, **run_options) -> dict:
        records = self._park_records(gh, issue, **run_options)
        self.assertEqual(len(records), 1)
        return records[0]


class QuestionParkRoadTest(_QuestionParkRecordCase):
    """Which of the stage's two roads the park it published came off."""

    def test_a_first_round_records_the_opening_road(self) -> None:
        gh, issue = _seed_question(_FRESH_ISSUE_NUMBER)

        record = self._only_park(
            gh,
            issue,
            run_agent=_agent(
                session_id=QUESTION_SESSION, last_message=_ANSWER_TEXT,
            ),
            has_new_commits=False,
        )

        self.assertEqual(record[_KEY_STAGE], STAGE_QUESTION)
        self.assertEqual(record[_KEY_REASON], PARK_QUESTION_ANSWER)
        self.assertEqual(record[_KEY_ROUTE], _ROUTE_ROUND)
        self.assertEqual(record[_KEY_AGENT_ROLE], _QUESTION_ROLE)
        self.assertEqual(record[_KEY_SESSION_ID], QUESTION_SESSION)

    def test_a_reply_records_the_resume_road(self) -> None:
        # The label and the reason are the same ones the opening round leaves,
        # so the road is the only thing in the record that tells a
        # conversation being opened from one being answered.
        gh, issue = _seed_question(_RESUMED_ISSUE_NUMBER)
        issue.comments.append(FakeComment(id=_REPLY_ID, body=_HUMAN_REPLY))
        gh.seed_state(
            issue.number,
            awaiting_human=True,
            last_action_comment_id=_PARKED_WATERMARK,
            question_agent=BACKEND_CLAUDE,
            question_session_id=QUESTION_SESSION,
            park_reason=PARK_QUESTION_ANSWER,
        )

        record = self._only_park(
            gh,
            issue,
            run_agent=_agent(
                session_id=QUESTION_SESSION, last_message=_RESUMED_ANSWER,
            ),
            has_new_commits=False,
        )

        self.assertEqual(record[_KEY_ROUTE], _ROUTE_RESUME)
        self.assertEqual(record[_KEY_SESSION_ID], QUESTION_SESSION)


class QuestionParkOptionalContextTest(_QuestionParkRecordCase):
    """Context the issue holds is reported; context it does not is dropped."""

    def test_a_recorded_pull_request_rides_along(self) -> None:
        # An issue relabeled to `question` from a PR stage arrives carrying
        # one, and that number is what joins the park to the work it is about.
        gh, issue = _seed_question(_PR_BACKED_ISSUE_NUMBER)
        gh.seed_state(issue.number, pr_number=_RECORDED_PR_NUMBER)

        record = self._only_park(
            gh,
            issue,
            run_agent=_agent(
                session_id=QUESTION_SESSION, last_message=_ANSWER_TEXT,
            ),
            has_new_commits=False,
        )

        self.assertEqual(record[_KEY_PR_NUMBER], _RECORDED_PR_NUMBER)

    def test_context_the_issue_never_held_is_dropped(self) -> None:
        # A backend that handed no session id back, on an issue with no pull
        # request: both fields are absent rather than written as nulls an
        # aggregation would have to special-case.
        gh, issue = _seed_question(_SESSIONLESS_ISSUE_NUMBER)

        record = self._only_park(
            gh,
            issue,
            run_agent=_agent(session_id="", last_message=_ANSWER_TEXT),
            has_new_commits=False,
        )

        self.assertEqual(record[_KEY_ROUTE], _ROUTE_ROUND)
        self.assertNotIn(_KEY_SESSION_ID, record)
        self.assertNotIn(_KEY_PR_NUMBER, record)


class QuestionParkPayloadIsBoundedTest(_QuestionParkRecordCase):
    """No part of what the agent wrote reaches the record."""

    def test_declared_fields_and_no_prose(self) -> None:
        # Both halves of what a run says are seeded, since both are what an
        # operator would otherwise have to redact before reading a sink.
        gh, issue = _seed_question(_PROSE_ISSUE_NUMBER)

        record = self._only_park(
            gh,
            issue,
            run_agent=_agent(
                session_id=QUESTION_SESSION,
                last_message=_ANSWER_TEXT,
                stderr=_STDERR_TEXT,
            ),
            has_new_commits=False,
        )

        written = _flattened(record)
        for prose in (_ANSWER_TEXT, _STDERR_TEXT):
            self.assertNotIn(prose, written)
        self.assertEqual(
            set(record) - _ENVELOPE - _guards.ALLOWED_CORRELATION_FIELDS,
            set(),
        )


class QuestionWaitIsRecordedOnceTest(_QuestionParkRecordCase):
    """One record per entry into a wait, not per poll of one that stands."""

    def test_a_second_poll_adds_nothing(self) -> None:
        gh, issue = _seed_question(_REPEAT_ISSUE_NUMBER)

        with self._analytics_sink() as log_file:
            for _ in range(2):
                self._run_question(
                    gh,
                    issue,
                    analytics_log_path=log_file,
                    run_agent=_agent(
                        session_id=QUESTION_SESSION,
                        last_message=_ANSWER_TEXT,
                    ),
                    has_new_commits=False,
                )
            records = _analytics_records(
                log_file, event=EVENT_PARK_AWAITING_HUMAN,
            )

        # Still waiting after the second poll, and still on one record: a tick
        # that meets a wait it did not open records nothing.
        self.assertTrue(gh.pinned_data(issue.number)[KEY_AWAITING_HUMAN])
        self.assertEqual(len(records), 1)


if __name__ == "__main__":
    unittest.main()
