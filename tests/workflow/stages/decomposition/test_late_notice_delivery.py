# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The three answers a stranded park notice gets that are not a plain retry.

The retry itself is the module beside this one. What is here is the edges of
it: a park a fresh attempt re-takes, which is announced by that attempt rather
than ahead of it; a sentence too long to write down, which is said once and
honestly not retried; and the guard's own park, whose retry is the owed read
rather than the redelivery -- and which owes the thread nothing to take back
if the thread was never told in the first place.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from orchestrator.workflow.stages.decomposition.late_session import (
    MAX_RECORDED_BODY,
)
from tests.workflow.stages.decomposition import late_settlement_support as _support
from tests.workflow.stages.decomposition.late_content_support import (
    PARK_REVISION_UNANSWERED,
    RefusedComment,
    reply,
)
from tests.workflow.stages.decomposition.late_revision_support import (
    DEV_PIN,
    UNCHANGED,
    RevisionCase,
)
from tests.workflow.stages.decomposition.late_run_support import agent_reply
from tests.workflow.stages.decomposition.late_settlement_support import GuardedLateCase, HeldPlanPrCase
from tests.workflow.stages.decomposition.late_test_support import KEYS

DISPLACED_NOTICE = "a description this orchestrator did not write"

UNREADABLE_NOTICE = "could not be read from GitHub"

UNVOUCHED_NOTICE = "without vouching for it"

# A reply too long to quote into a park the pinned comment could also hold.
# The park is still posted; what it cannot be is written down for a retry.
TOO_LONG_TO_QUOTE = "q" * MAX_RECORDED_BODY

REFUSED_TO_RECORD = "does not fit the pinned comment"

ONE_REFUSAL = 1

SAID_ONCE = 1


class SupersededNoticeTest(HeldPlanPrCase, unittest.TestCase):
    """A park a fresh attempt re-takes is left to that attempt to announce.

    Not to the retry above it. The attempt runs on this very tick and either
    settles the wall or hits it again and says the reason it fails for NOW --
    so announcing the older sentence first would report a wall this tick is
    about to walk through, twice.
    """

    def setUp(self) -> None:
        super().setUp()
        self.plan_pr.body = _support.HUMAN_REWRITE
        with RefusedComment(self.github), self.assertRaises(RuntimeError):
            self._adjudicate(_support.SINGLE_RUN)

    def test_the_refusal_stands_with_nothing_said(self) -> None:
        pinned = self._pinned()

        self.assertEqual(pinned.get(KEYS.park_reason), _support.PARK_HOLD_FAILED)
        self.assertEqual(self.github.posted_comments, [])

    def test_the_re_taking_attempt_says_it_once(self) -> None:
        outcome, spawn = self._adjudicate(_support.SINGLE_RUN)

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        said = [body for _number, body in self.github.posted_comments]
        self.assertEqual(len(said), SAID_ONCE)
        self.assertIn(DISPLACED_NOTICE, said[0])


class UnrecordableNoticeTest(RevisionCase):
    """A sentence too long to write down is said once and not retried.

    The pinned comment is shared and bounded, and a park quoting a developer's
    whole reply can be big enough to matter. Refusing the record is the only
    safe answer: a notice that broke the write would take the park it explains
    down with it, which is a worse failure than the retry it costs. So it is
    refused whole, loudly, and the tick still says it.
    """

    def test_a_notice_too_long_is_refused_and_said(self) -> None:
        self._seed(**DEV_PIN)
        reply(self.issue)

        with self.assertLogs(_support.WORKFLOW_LOG, level=_support.ERROR) as logged:
            self._revise(reply=agent_reply(TOO_LONG_TO_QUOTE), seed=UNCHANGED)
            refusals = [
                line for line in logged.output if REFUSED_TO_RECORD in line
            ]

        self.assertEqual(len(refusals), ONE_REFUSAL)
        pinned = self._pinned()
        self.assertEqual(
            pinned.get(KEYS.park_reason), PARK_REVISION_UNANSWERED,
        )
        self.assertNotIn(KEYS.park_notice, pinned)
        self.assertIn(UNVOUCHED_NOTICE, "".join(self._bodies()))


class StrandedGuardNoticeTest(GuardedLateCase, unittest.TestCase):
    """The guard's own park, and the two ends of a notice it never said.

    Nothing supersedes "GitHub could not be asked" either, but the tick that
    re-says its sentence is the reconciliation of the owed read rather than
    the redelivery above it: that reconciliation returns before anything else
    on the tick runs, so the sentence rides out on whichever answer it gets.
    """

    def setUp(self) -> None:
        super().setUp()
        with (
            RefusedComment(self.github),
            _support.unreadable_owner(self.github),
            self.assertLogs(_support.WORKFLOW_LOG, level=_support.ERROR),
            self.assertRaises(RuntimeError),
        ):
            self._adjudicate(_support.SPLIT_RUN)

    def test_a_failing_read_says_the_stranded_one(self) -> None:
        with _support.unreadable_owner(self.github), self.assertLogs(_support.WORKFLOW_LOG, level=_support.ERROR):
            outcome, spawn = self._adjudicate()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        said = [body for _number, body in self.github.posted_comments]
        self.assertEqual(len(said), SAID_ONCE)
        self.assertIn(UNREADABLE_NOTICE, said[0])
        self.assertNotIn(KEYS.park_notice, self._pinned())

    def test_a_healed_read_takes_back_nothing(self) -> None:
        # The recovery follow-up retires an alarming last word. There was no
        # last word: this park told nobody anything, so a follow-up would be
        # the first thing this episode said -- a recovery message for a
        # failure the thread never heard about.
        outcome, spawn = self._adjudicate()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        self.assertEqual(self.github.posted_comments, [])
        pinned = self._pinned()
        self.assertFalse(pinned.get(KEYS.awaiting))
        self.assertNotIn(KEYS.park_notice, pinned)


if __name__ == "__main__":
    unittest.main()
