# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A finished docs pass's completion, landed as a checkpoint, and nothing made behind one that did not land.

Every road that finishes a pass ends in one guarded write over the comment the
tick last confirmed: prepared before its notice, landed before its relabel.
What GitHub does with that write is not always an answer -- a comment nobody
could read, an edit refused, an edit that landed and whose answer was lost, a
comment a human edited while the notice was out, a comment with no room left --
and none of those is relabelled on. The tick that follows reads what landed: it
finishes the handoff from a receipt still standing, and runs the pass again
where none does.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.workflow.stages.documenting import (
    documenting_completion_test_support as completion,
    documenting_gate_test_support as gate,
    documenting_test_support as documenting,
)

MEASURED_CANDIDATE_SHA = gate.MEASURED_CANDIDATE_SHA
UNDER_THE_CEILING = gate.UNDER_THE_CEILING

# The roads that leave no receipt behind an unconfirmed write, as how the write
# went and whether the pass published a commit: a published pass whose write
# landed and lost its answer, and a clean no-change, which publishes nothing,
# whichever way its write went.
UNRECEIPTED = (
    (completion.LOST, True),
    (completion.REFUSED, False),
    (completion.LOST, False),
)

# A receipt a maintainer strips off the comment while the notice is out, and
# whether the tick reading what is left runs the pass again: the docs receipt
# the completion consumes, and the publication's, which it only reads.
STRIPPED = (
    (gate.KEY_SETTLED_DOCS_SHA, True),
    (gate.KEY_RECEIPT_SHA, False),
)


class UnresolvedCompletionTest(unittest.TestCase, gate._DocsGateFixtureMixin):
    """A write that went out, or was meant to, and whose landing nobody confirmed."""

    def test_an_unlanded_write_finishes_from_receipt(self) -> None:
        # Refused over a comment nobody could read, or sent and refused, which
        # comes back unconfirmed: either way the receipt the gate put down is
        # still what the comment says, so the tick that reads it finishes the
        # handoff without a second agent or push -- recording and walking past
        # the notice it posts, and leaving the publication's own receipt as
        # the gate wrote it.
        for how in (completion.UNREADABLE, completion.REFUSED):
            with self.subTest(how=how):
                github, issue = self._seeded(pickup_comment_id=documenting.PICKUP_COMMENT_ID)
                self._unresolved_tick(github, issue, how, publishes=True)
                self._assert_unstamped(github)
                self.assertEqual(self._pinned(github)[gate.KEY_SETTLED_DOCS_SHA], MEASURED_CANDIDATE_SHA)

                mocks = self._settled_tick(github, issue)

                mocks[documenting.RUN_AGENT].assert_not_called()
                mocks[documenting.PUSH_BRANCH].assert_not_called()
                self._assert_handed_off_once(github, gate.HANDOFF_NOTICE, notices=2)
                self._assert_walked_past_its_notice(github)

    def test_an_unreceipted_write_reruns_the_pass(self) -> None:
        # The tick that sent the write cannot tell one that landed from one
        # that never did, and relabels nothing. The next one reads what landed
        # -- a stamp where it landed, none where it did not, and no receipt
        # either way -- and runs the pass again rather than handing off on a
        # record no receipt vouches for; only that pass's confirmed write hands
        # the issue on.
        for how, publishes in UNRECEIPTED:
            with self.subTest(how=how, publishes=publishes):
                github, issue = self._seeded()
                self._unresolved_tick(github, issue, how, publishes)
                self._assert_unreceipted(github, stamped=how == completion.LOST)

                mocks = self._rerun(github, issue)

                mocks[documenting.RUN_AGENT].assert_called_once()
                self.assertEqual(github.label_history, [(self.issue_number, documenting.IN_REVIEW)])

    def _unresolved_tick(self, github, issue, how: str, publishes: bool) -> None:
        """One tick whose completion's edit is left unanswered `how`: its notice posted, and nothing relabelled.

        `publishes` is a pass that pushed a commit; otherwise a clean
        no-change, which publishes nothing.
        """
        with patch.object(github, gate.EDIT_PINNED_STATE, completion._FailsTheCompletion(github, how)):
            if publishes:
                self._fresh_tick(github, issue, added_lines=UNDER_THE_CEILING)
            else:
                self._rerun(github, issue)
        self.assertEqual(github.label_history, [])
        self.assertEqual(len(github.posted_pr_comments), 1)

    def _assert_unreceipted(self, github, stamped: bool) -> None:
        """No receipt left on the comment, and a docs verdict on it only where the write landed."""
        landed = self._pinned(github)
        self.assertIsNone(landed.get(gate.KEY_SETTLED_DOCS_SHA))
        verdict = landed.get(documenting.DOCS_VERDICT)
        self.assertEqual(verdict is not None, stamped)

    def _assert_walked_past_its_notice(self, github) -> None:
        """The last notice on the pull request recorded as this orchestrator's, with the PR watermark past it."""
        announced = github.get_pr(self.pr_number).issue_comments[-1]
        pinned = self._pinned(github)
        self.assertIn(announced.id, pinned[gate.ORCHESTRATOR_COMMENT_IDS])
        self.assertGreaterEqual(pinned[gate.PR_LAST_COMMENT_ID], announced.id)


class RefusedCompletionTest(unittest.TestCase, gate._DocsGateFixtureMixin):
    """A write the comment would not take as the tick last confirmed it."""

    def test_a_hand_edit_under_the_write_stands(self) -> None:
        # The write is decided on both receipts as the tick last confirmed
        # them, so a maintainer's edit of either while the notice is out
        # refuses it: nothing is relabelled, and the comment keeps the edit as
        # the human made it -- neither put back nor stamped over. The tick that
        # reads it decides over what is there: with no docs receipt it runs the
        # pass, and with one it finishes the handoff from it.
        for stripped, reruns in STRIPPED:
            with self.subTest(stripped=stripped):
                github, issue = self._seeded()
                with patch.object(
                    github, completion.PR_COMMENT,
                    completion._StripsWhilePosting(github, self.issue_number, stripped),
                ):
                    self._fresh_tick(github, issue, added_lines=UNDER_THE_CEILING)
                self.assertEqual(github.label_history, [])
                self._assert_unstamped(github)
                self.assertNotIn(stripped, self._pinned(github))

                mocks = self._rerun(github, issue)

                self.assertEqual(mocks[documenting.RUN_AGENT].call_count, int(reruns))
                self.assertEqual(github.label_history, [(self.issue_number, documenting.IN_REVIEW)])

    def test_a_full_comment_announces_nothing(self) -> None:
        # The completion is measured over the comment before its notice goes
        # out, with what posting that notice and walking past it write
        # reserved: a comment with no room left for it is told nothing and
        # handed on nowhere, and the receipt stays for the tick after a human
        # has made room, which announces the handoff once.
        github, issue = self._seeded(**{gate.KEY_SETTLED_DOCS_SHA: MEASURED_CANDIDATE_SHA})
        completion._leaves_no_room(github, self.issue_number)

        self._settled_tick(github, issue)

        self.assertEqual(github.posted_pr_comments, [])
        self.assertEqual(github.label_history, [])
        self._assert_unstamped(github)
        self.assertEqual(self._pinned(github)[gate.KEY_SETTLED_DOCS_SHA], MEASURED_CANDIDATE_SHA)

        completion._makes_room(github, self.issue_number)
        self._settled_tick(github, issue)

        self._assert_handed_off_once(github, gate.HANDOFF_NOTICE)


if __name__ == "__main__":
    unittest.main()
