# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run whose route the retirement refuses for a record moved behind the last word, abandoned there.

A finish recorded its run for the landed head and died at its relabel, and the
recovery proves that run again and takes the last word behind every request it
made -- and then another road moves the review subject the run is bound
through, before the write that retires the attempt lands. That write is
decided on every record the evidence is bound through, so it refuses the
route; the last word is asked once more behind the refusal, reads the subject
moved, and abandons the run. So putting the subject back before the next tick
routes nothing the run carried. Nothing runs, pushes, or announces again, and
no developer is launched.
"""
from __future__ import annotations

import hashlib
import unittest
from functools import partial

from orchestrator.workflow.engine.review_subjects import REVIEW_SUBJECT
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)
from tests.workflow.interleaving import _RacesPastTheStep

# A requirements revision no reviewer was handed, for a review subject another road records.
_ELSEWHERE = hashlib.sha256(b"requirements recorded behind the last word").hexdigest()


def _records_the_subject(case: support.VerificationRecoveryCase, recorded: dict) -> None:
    """Record `recorded` as the review subject on `case`'s pinned comment, as another road's write would."""
    moved = case.gh.read_pinned_state(case.issue)
    moved.set(REVIEW_SUBJECT, recorded)
    case.gh.write_pinned_state(case.issue, moved)


class RetirementMoveRecoveryTest(support.VerificationRecoveryCase, unittest.TestCase):
    """A run whose retirement a moved record refuses is abandoned, and no restoration revives it."""

    def test_a_review_moved_at_retirement_abandons(self) -> None:
        # The review subject moves as the recovery relabels, between the
        # write retiring the attempt being prepared and landing: the write is
        # refused and the attempt stands, but the run is abandoned behind the
        # refusal. With the subject put back, the next recovery routes the
        # head with nothing run or recorded.
        head = self.lands_a_reviewed_rebase()
        self.dies_routing(partial(self.finishes, head))
        captured = readings.pinned_records(self)[0]
        recorded = self.gh.read_pinned_state(self.issue).get(REVIEW_SUBJECT)
        relabel = self.gh.set_workflow_label
        moves = partial(_records_the_subject, self, {**recorded, "requirements": _ELSEWHERE})
        self.gh.set_workflow_label = _RacesPastTheStep(relabel, moves)

        self.recovers()

        self.gh.set_workflow_label = relabel
        self._assert_abandoned(captured)
        self.assertEqual(readings.pinned(self)[readings.KEY_PENDING_PUSH], self.anchor)
        _records_the_subject(self, recorded)
        self.recovers()
        self._assert_abandoned(captured)
        self.assert_recovered(head)

    def _assert_abandoned(self, captured) -> None:
        """Nothing pending or current, the settled evidence invalidated and `captured` abandoned, and no second run."""
        retired = (*git_support.invalidated(self), (captured.receipt, readings.ABANDONED))
        self.assertEqual(
            (readings.pinned_records(self), self.runs()),
            ((None, None, retired), 1),
        )


if __name__ == "__main__":
    unittest.main()
