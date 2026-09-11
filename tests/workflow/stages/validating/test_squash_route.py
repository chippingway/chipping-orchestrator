# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where the recorded-collapse route sits in a validating tick, and why.

A squash this issue began and did not finish is answered before anything else
on the tick runs an agent. Asked only from the approval road it would be asked
on no tick whose reviewer times out, crashes, or votes CHANGES_REQUESTED: an
already-landed collapse would never get its notice, its watermarks, or its
relabel, a record nothing can read would reach `fixing` without the park it
owes, and a body edit would resume the dev on a branch standing on a commit
nobody accounted for.

The park is the other half of owning the tick, and the two kinds are answered
differently. This recovery's own park is retried every tick and mentions
nobody twice -- what its notice asks for is proved by the recovery getting
further, not by a reply. A park the size gate worded is held instead, since
the gate says its own piece on every reading it cannot take, and the reply to
one is spent on the recovery rather than on the dev, who would otherwise be
resumed on the very branch the record is about.
"""
from __future__ import annotations

import unittest

from tests.workflow.stages.validating import squash_approval_support as _support
from tests.workflow.stages.validating.squash_approval_support import (
    _CollapseWorldMixin,
    _RefusesTheCollapse,
    _SquashApprovalFixtureMixin,
)

# The stage a reviewer's CHANGES_REQUESTED would send this issue to, which a
# record nothing can account for may not reach without its park.
LABEL_FIXING = "workflow:fixing"

HANDED_ON = (_support.APPROVAL_ISSUE, _support.LABEL_DOCUMENTING)


class PendingCollapseRouteTest(
    unittest.TestCase,
    _SquashApprovalFixtureMixin,
    _CollapseWorldMixin,
):
    """No road on the tick may reach an agent while a collapse is recorded."""

    def test_a_landed_collapse_is_finished_first(self) -> None:
        github, issue = self._approved_issue()
        self._records_a_collapse(github)

        mocks = self._lands_a_collapse(github, issue)

        mocks[_support.RUN_AGENT].assert_not_called()
        mocks[_support.SQUASH_SEAM].assert_called_once()
        self.assertIn(HANDED_ON, github.label_history)
        self.assertNotIn(_support.COLLAPSE_KEY, github.pinned_data(_support.APPROVAL_ISSUE))

    def test_an_unaccountable_record_parks_first(self) -> None:
        github, issue = self._approved_issue()
        self._records_a_collapse(github)

        mocks = self._run_squash_approval(github, issue, _RefusesTheCollapse())

        mocks[_support.RUN_AGENT].assert_not_called()
        self.assertTrue(github.pinned_data(_support.APPROVAL_ISSUE)[_support.AWAITING_HUMAN])
        self.assertNotIn((_support.APPROVAL_ISSUE, LABEL_FIXING), github.label_history)
        self.assertNotIn(HANDED_ON, github.label_history)

    def test_nothing_recorded_still_reviews(self) -> None:
        # The route costs one lookup on the pinned comment: an issue with no
        # collapse on it reaches the reviewer exactly as it always did.
        github, issue = self._approved_issue()

        mocks = self._lands_a_collapse(github, issue)

        mocks[_support.RUN_AGENT].assert_called_once()

    def test_a_drifted_body_waits_for_the_collapse(self) -> None:
        # Ahead of the drift route as well as of the reviewer: resumed on an
        # edited body, the dev is pointed at a branch standing on a commit
        # nothing has accounted for -- and past the refusal that would take,
        # an ordinary tick never reaches the recovery again.
        github, issue = self._approved_issue()
        self._records_a_collapse(github)
        self._edits_the_body(github)

        mocks = self._lands_a_collapse(github, issue)

        mocks[_support.RUN_AGENT].assert_not_called()
        mocks[_support.SQUASH_SEAM].assert_called_once()
        self.assertIn(HANDED_ON, github.label_history)

    def test_a_gate_park_is_left_alone(self) -> None:
        # The size gate posts a fresh notice for every reading it cannot take,
        # so a tick that ran the recovery back into it would mention a human
        # every poll. Held instead, until they answer.
        github, issue = self._approved_issue()
        self._records_a_collapse(github)
        self._parks(github)

        mocks = self._run_squash_approval(github, issue, _RefusesTheCollapse())

        mocks[_support.RUN_AGENT].assert_not_called()
        mocks[_support.SQUASH_SEAM].assert_not_called()
        self.assertEqual(github.posted_comments, [])
        self.assertTrue(github.pinned_data(_support.APPROVAL_ISSUE)[_support.AWAITING_HUMAN])

    def test_its_own_park_is_retried_quietly(self) -> None:
        # What that notice asks for -- a branch reconciled, a comment repaired
        # -- is proved by the recovery getting further rather than by a reply,
        # so it runs again every tick and mentions nobody a second time.
        github, issue = self._approved_issue()
        self._records_a_collapse(github)
        self._parks(github, _support.PARK_SQUASH_FAILED)

        mocks = self._run_squash_approval(github, issue, _RefusesTheCollapse())

        mocks[_support.RUN_AGENT].assert_not_called()
        mocks[_support.SQUASH_SEAM].assert_called_once()
        self.assertEqual(github.posted_comments, [])

    def test_a_human_reply_retries_the_collapse(self) -> None:
        # And the reply is the answer that park asked for -- a branch
        # reconciled, a comment repaired -- so it is spent on the recovery.
        github, issue = self._approved_issue()
        self._records_a_collapse(github)
        self._parks(github)
        self._human_replies(issue)

        mocks = self._lands_a_collapse(github, issue)

        mocks[_support.RUN_AGENT].assert_not_called()
        mocks[_support.SQUASH_SEAM].assert_called_once()
        self.assertFalse(github.pinned_data(_support.APPROVAL_ISSUE)[_support.AWAITING_HUMAN])
        self.assertIn(HANDED_ON, github.label_history)


if __name__ == "__main__":
    unittest.main()
