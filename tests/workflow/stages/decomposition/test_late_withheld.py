# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Guidance a park's response boundary held back, and what finally reads it.

A park's notice moves the reply floor past every comment written before it
went out, so words a human wrote while the issue was being parked are no
answer to that park. They are not answered either: no agent has read them.
These cases pin what keeps them from being folded into a baseline on the way
past. Whatever ends the park they sat under hands them to the developer,
whose consumption lands only once the run has read them -- never to an
adjudication consumed for ahead of spawn gates that can stop it -- and a
control answered with no agent behind it spends only its own reply.
"""
from __future__ import annotations

from typing import Self
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeIssue
from tests.workflow.fixtures import _iso_hours_ago
from tests.workflow.stages.decomposition import late_content_support as _support
from tests.workflow.stages.decomposition.late_content_replies import (
    PARK_NOTICE_ID,
    authorization,
    human_comment,
    reply,
)
from tests.workflow.stages.decomposition.late_requirements_support import KEY_USER_CONTENT_HASH, requirements
from tests.workflow.stages.decomposition.late_revision_support import (
    DEV_PIN,
    DEV_SESSION,
    PausedDuringRun,
    RevisionCase,
)
from tests.workflow.stages.decomposition.late_test_support import KEYS

WITHHELD = "and keep the importer's retry flag working while you are at it"

LATER = "also leave the CLI flags alone"

# Background past what a prompt's thread excerpt holds, so the next agent to
# read the withheld comment through an excerpt of the thread's tail would lose
# the instruction at its head.
BACKGROUND_WORDS = 700

BACKGROUND = "background " * BACKGROUND_WORDS

LONG_WITHHELD = f"{WITHHELD}\n\n{BACKGROUND}"

# The phrase the drift park's own notice is recognized by.
DRIFT_NOTICE = "the requirements changed"

# A comment the thread already carried when a park now standing fired: past
# the late watermark, and below the id that park's notice took.
BEFORE_THE_NOTICE = PARK_NOTICE_ID // 2

MAX_RETRIES = "MAX_RETRIES_PER_DAY"

# A spawn budget the issue has spent to its last slot, so an adjudication
# the answer reopened would be refused at its spawn gate.
SPENT = 2


class _WrittenDuringTheNotice:
    """A human posting while the drift park's notice is on its way out.

    Their comment lands after the reading that took the park and before the
    notice, so the notice's id -- the floor a reply has to clear -- is above
    it.
    """

    def __init__(self, github: FakeGitHubClient, issue: FakeIssue) -> None:
        self._github = github
        self._issue = issue
        self._taken = github.comment
        self.written = None

    def __call__(self, issue: FakeIssue, body: str) -> FakeComment:
        if DRIFT_NOTICE in body and self.written is None:
            self.written = reply(self._issue, WITHHELD)
        return self._taken(issue, body)

    def __enter__(self) -> Self:
        self._github.comment = self
        return self

    def __exit__(self, *unused_error) -> bool:
        self._github.comment = self._taken
        return False


def _reverted(issue: FakeIssue) -> None:
    """The human taking the edit back."""
    issue.title = _support.ISSUE_TITLE


def _certified(issue: FakeIssue) -> None:
    """The human vouching for the frozen commit once they have read the notice."""
    reply(issue, _support.BARE_CONTINUE)


class DriftParkWithheldTest(RevisionCase):
    """Words written under a drift park's notice reach the developer."""

    def test_ending_the_park_hands_it_over(self) -> None:
        # Neither answer is the comment's own, and neither is a reason to
        # spend it. A revert over a recorded verdict would otherwise reuse the
        # verdict with no agent reading it, and a certificate would spend it
        # on an adjudication its spawn gates could still stop.
        for shape, answer in (("a revert", _reverted), ("a certificate", _certified)):
            with self.subTest(answer=shape):
                self._parked_over_a_comment()
                answer(self.issue)

                outcome, spawn = self._revise()

                self.assertEqual(outcome.disposition, _LateDisposition.REVISED)
                self._assert_handed_over(spawn)

    def test_a_revision_quotes_it_beside_the_reply(self) -> None:
        # A reply after the notice buys the run; the comment under it still
        # goes in, ahead of the reply, since the run folds both.
        self._parked_over_a_comment()
        reply(self.issue, LATER)

        _outcome, spawn = self._revise()

        prompt = spawn.call_args.args[1]
        self.assertLess(prompt.index(WITHHELD), prompt.index(LATER))

    def test_with_no_park_it_runs_the_developer(self) -> None:
        # The park that held it back has been retired, so nothing is left for
        # it to answer: it is an instruction nobody has read.
        self._seed(**DEV_PIN, **{_support.KEY_LAST_ACTION_COMMENT_ID: PARK_NOTICE_ID})
        self.issue.comments.append(human_comment(BEFORE_THE_NOTICE, WITHHELD))

        outcome, spawn = self._revise()

        self.assertEqual(outcome.disposition, _LateDisposition.REVISED)
        self.assertIn(WITHHELD, spawn.call_args.args[1])

    def _parked_over_a_comment(self) -> None:
        """Park on an edit while a trusted comment lands under its notice."""
        self._seed(**DEV_PIN, **_support.RECORDED_SINGLE)
        self.issue.title = _support.EDITED_TITLE
        with _WrittenDuringTheNotice(self.github, self.issue) as during:
            parked, _spawn = self._run()
            self.withheld = during.written
        self.assertEqual(parked.disposition, _LateDisposition.PARKED)
        self.assertEqual(self._pinned()[KEYS.park_reason], _support.PARK_CONTENT_DRIFT)
        self.assertLess(
            self.withheld.id, self._pinned()[_support.KEY_LAST_ACTION_COMMENT_ID],
        )

    def _assert_handed_over(self, spawn) -> None:
        """The locked developer read the comment, and only then was it spent."""
        spawn.assert_called_once()
        self.assertEqual(spawn.call_args.kwargs["resume_session_id"], DEV_SESSION)
        self.assertIn(WITHHELD, spawn.call_args.args[1])
        pinned = self._pinned()
        self.assertGreaterEqual(pinned[_support.KEY_COMMENT_WATERMARK], self.withheld.id)
        self.assertEqual(pinned[KEY_USER_CONTENT_HASH], requirements(self.issue))


class QuestionParkWithheldTest(RevisionCase):
    """Words written under a question's notice outlast a rerun that cannot start."""

    def test_a_control_answer_folds_none_of_it(self) -> None:
        # A refused continue runs no agent, so it spends its own reply and
        # nothing else: no baseline vouches for the comment it left unread.
        self._asked_over_a_comment()
        nudge = reply(self.issue, _support.BARE_CONTINUE)

        refused, held = self._run()

        self.assertEqual(refused.disposition, _LateDisposition.PARKED)
        held.assert_not_called()
        pinned = self._pinned()
        self.assertGreaterEqual(pinned[_support.KEY_LAST_ACTION_COMMENT_ID], nudge.id)
        self.assertNotIn(_support.KEY_COMMENT_WATERMARK, pinned)
        self.assertNotIn(KEY_USER_CONTENT_HASH, pinned)

    def test_an_answer_hands_it_to_the_developer(self) -> None:
        # The budget is spent, so the adjudication an answer would reopen is
        # refused at its gate. The developer is resumed instead -- a resume is
        # no fresh spawn -- with the comment quoted ahead of the answer.
        self._asked_over_a_comment(spent=True)
        answer = reply(self.issue, LATER)

        outcome, spawn = self._revise()

        self.assertEqual(outcome.disposition, _LateDisposition.REVISED)
        spawn.assert_called_once()
        self.assertEqual(spawn.call_args.kwargs["resume_session_id"], DEV_SESSION)
        prompt = spawn.call_args.args[1]
        self.assertLess(prompt.index(WITHHELD), prompt.index(LATER))
        pinned = self._pinned()
        self.assertEqual(pinned[_support.KEY_COMMENT_WATERMARK], answer.id)
        self.assertEqual(pinned[KEY_USER_CONTENT_HASH], requirements(self.issue))

    def test_a_declined_run_leaves_it_unread(self) -> None:
        # A run the operator paused read nothing, so nothing is spent: the
        # comment, the answer, and the question the issue is parked on all
        # stand exactly as they did.
        self._asked_over_a_comment(spent=True)
        reply(self.issue, LATER)

        outcome, _spawn = self._revise(reply=PausedDuringRun(self))

        self.assertEqual(outcome.disposition, _LateDisposition.DEFERRED)
        pinned = self._pinned()
        self.assertEqual(pinned[KEYS.park_reason], _support.PARK_QUESTION)
        self.assertNotIn(_support.KEY_COMMENT_WATERMARK, pinned)
        self.assertNotIn(KEY_USER_CONTENT_HASH, pinned)

    def _asked_over_a_comment(self, *, spent: bool = False) -> None:
        """A question park with a trusted comment under its notice.

        `spent` leaves the issue's spawn budget with nothing in it, so any
        adjudication this tick reached would be refused at its gate.
        """
        budget = {}
        if spent:
            capped = patch.object(config, MAX_RETRIES, SPENT)
            capped.start()
            self.addCleanup(capped.stop)
            budget = {KEYS.retry_count: SPENT, KEYS.retry_window: _iso_hours_ago(1)}
        self._seed(**_support.ASKED_STATE, **DEV_PIN, **budget)
        self.issue.comments.append(human_comment(BEFORE_THE_NOTICE, WITHHELD))


class EndedParkWithheldTest(RevisionCase):
    """An answer that ends a park over withheld words publishes nothing past them."""

    def test_the_developer_is_handed_them_whole(self) -> None:
        # Authorizing a `single` would hand the issue to publication, and a
        # continue on a stalled revision re-reads the checkout with no agent --
        # either way the next agent to see the words would read them through a
        # bounded excerpt, if at all. The developer is resumed with them quoted
        # whole instead, and nothing publishes.
        for shape, parked, answer in (
            ("an authorization", _support.SINGLE_PARKED, authorization()),
            ("a stalled revision's continue", _support.REVISION_PARKED, _support.BARE_CONTINUE),
        ):
            with self.subTest(answer=shape):
                self._seed(**parked, **DEV_PIN)
                self.issue.comments.append(human_comment(BEFORE_THE_NOTICE, LONG_WITHHELD))
                reply(self.issue, answer)

                outcome, spawn = self._revise()

                self.assertEqual(outcome.disposition, _LateDisposition.REVISED)
                self.assertEqual(spawn.call_args.kwargs["resume_session_id"], DEV_SESSION)
                self.assertIn(LONG_WITHHELD, spawn.call_args.args[1])
                self.assertNotIn(KEYS.exempt_sha, self._pinned())
