# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The three parks that lose their sentence outright when a comment fails.

A park is durable before it is spoken, which is the order everything else in
this mode depends on -- and it leaves one gap. The flag lands, the comment is
refused, and every later tick reads an `awaiting_human` it cannot tell from
one whose comment landed: it takes the human as told and says nothing.

For the parks a fresh attempt supersedes that costs one tick and no more. For
these three it is unbounded. A categorized question, an edit nobody has
explained, and a checkout the developer left dirty ARE what the issue is
waiting on: no attempt re-takes them, so their own sentence is the only thing
that would ever say what the human has to do, and losing it leaves the issue
parked in silence for as long as nobody thinks to look.

Each is driven the same way -- one tick whose park lands and whose comment
does not, then the next tick, which has no agent to spend and must say the
sentence anyway.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.late_split import keys as _late_keys
from orchestrator.workflow.stages.decomposition.late_notice import PARK_NOTICE
from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from tests.workflow.stages.decomposition.late_content_replies import reply
from tests.workflow.stages.decomposition.late_content_support import (
    EDITED_TITLE,
    PARK_CONTENT_DRIFT,
    PARK_QUESTION,
    PARK_REVISION_DIRTY,
    LateContentCase,
    RefusedComment,
)
from tests.workflow.stages.decomposition.late_revision_support import (
    DEV_PIN,
    DIRTY_NOTICE,
    DIRTY_TREE,
    RevisionCase,
)
from tests.workflow.stages.decomposition.late_run_support import (
    WorktreeSeed,
    adjudicate,
)
from tests.workflow.stages.decomposition.late_test_support import (
    KEYS,
    QUESTION_ASKED,
    QUESTION_REPLY,
)

# The phrase that tells each park's own sentence from everything else the
# thread carries. Asserted on rather than the whole notice, because what these
# tests are about is whether it was said at all.
DRIFT_NOTICE = "the requirements changed after"

REASON = "reason"


class RefusedQuestionNoticeTest(LateContentCase):
    """A categorized question the thread never saw.

    The whole failure in one issue: the outcome is recorded, the park is
    durable, and the comment is not. Nothing supersedes a question, so every
    tick after this one reads the flag, calls the human asked, and reuses the
    record without saying a word.
    """

    def setUp(self) -> None:
        self._seed()
        with RefusedComment(self.github), self.assertRaises(RuntimeError):
            self._run(QUESTION_REPLY)

    def test_the_park_stands_with_nothing_said(self) -> None:
        pinned = self._pinned()

        self.assertTrue(pinned.get(KEYS.awaiting))
        self.assertEqual(pinned.get(KEYS.park_reason), PARK_QUESTION)
        self.assertEqual(self._bodies(), [])
        self.assertEqual(
            pinned.get(KEYS.park_notice, {}).get(REASON), PARK_QUESTION,
        )

    def test_the_next_tick_asks_the_question(self) -> None:
        outcome, spawn = adjudicate(self.github, self.issue)

        # No second agent: what failed was the comment, and the answer it was
        # announcing is already recorded against this exact candidate.
        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        self.assertIn(QUESTION_ASKED, "".join(self._bodies()))
        self.assertNotIn(KEYS.park_notice, self._pinned())

    def test_the_question_is_asked_once(self) -> None:
        adjudicate(self.github, self.issue)
        asked = len(self.github.posted_comments)

        adjudicate(self.github, self.issue)

        self.assertEqual(len(self.github.posted_comments), asked)


class RefusedDriftNoticeTest(LateContentCase):
    """An edit nobody explained, on an issue nobody was told was waiting."""

    def setUp(self) -> None:
        self._seed()
        self.issue.title = EDITED_TITLE
        with RefusedComment(self.github), self.assertRaises(RuntimeError):
            adjudicate(self.github, self.issue)

    def test_the_hold_stands_with_nothing_said(self) -> None:
        pinned = self._pinned()

        self.assertEqual(pinned.get(KEYS.park_reason), PARK_CONTENT_DRIFT)
        self.assertEqual(self._bodies(), [])

    def test_the_next_tick_says_what_moved(self) -> None:
        # The drift branch consumes nothing and returns as soon as its own
        # park is standing, so nothing below the top of the tick would ever
        # reach the sentence again.
        outcome, spawn = adjudicate(self.github, self.issue)

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertIn(DRIFT_NOTICE, "".join(self._bodies()))
        self.assertNotIn(KEYS.park_notice, self._pinned())


class RefusedRevisionNoticeTest(RevisionCase):
    """A checkout the developer left changed, and a human never told to."""

    def setUp(self) -> None:
        self._seed(**DEV_PIN)
        reply(self.issue)
        with RefusedComment(self.github, DIRTY_NOTICE), self.assertRaises(RuntimeError):
            self._revise(seed=WorktreeSeed(dirty=DIRTY_TREE))

    def test_the_revision_park_says_nothing(self) -> None:
        pinned = self._pinned()

        self.assertEqual(pinned.get(KEYS.park_reason), PARK_REVISION_DIRTY)
        self.assertNotIn(DIRTY_NOTICE, "".join(self._bodies()))
        self.assertEqual(
            pinned.get(KEYS.park_notice, {}).get(REASON), PARK_REVISION_DIRTY,
        )

    def test_the_next_tick_says_what_to_clean(self) -> None:
        # A stalled revision waits for a human's reply, and a human with no
        # notice has nothing to reply to: without the retry the issue sits
        # `awaiting_human` indefinitely, with no agent respawned and nothing
        # on the thread naming the worktree that has to be cleaned.
        outcome, spawn = adjudicate(self.github, self.issue)

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertIn(DIRTY_NOTICE, "".join(self._bodies()))
        self.assertNotIn(KEYS.park_notice, self._pinned())


class NoticeKeyTest(unittest.TestCase):
    """The obligation outlives the generation the park was taken under."""

    def test_it_is_not_one_of_the_generation_keys(self) -> None:
        # Cleared with the generation, a park that survived a settlement or a
        # cancellation would keep its flag and lose its sentence -- which is
        # the exact state this field exists to make impossible.
        self.assertNotIn(PARK_NOTICE, _late_keys.LATE_STATE_KEYS)
        self.assertEqual(PARK_NOTICE, KEYS.park_notice)


if __name__ == "__main__":
    unittest.main()
