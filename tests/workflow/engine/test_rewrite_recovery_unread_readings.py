# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run's recovery over a reading nobody could take: held for another proof, never hiding movement.

A checkout read on another head than the landed one is movement under the run
the evidence write captured, and abandons it. One whose head the proof could
not name -- read for the recovery's candidate, or again by the last word behind
the run's proof -- read nothing move: the recovery holds the route with the run
still recorded, and the next recovery, reading the checkout on the head, routes
that very run with its own transcript and tested and source provenance. A pull
request nobody could read stops the run's proof, but not the records beside it:
a review subject moved on the pinned comment -- before the recovery, or while
the pull request is asked -- still abandons the run, and putting the subject
back routes nothing it carried. Nothing runs, pushes, or announces again, and
no developer is launched.
"""
from __future__ import annotations

import hashlib
import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator.git.base_sync import rewrite_facts
from orchestrator.git.publication.probes import _BranchDivergence
from orchestrator.workflow.engine import report_publication_evidence
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence, ReportEvidenceVerdict
from orchestrator.workflow.engine.review_subjects import REVIEW_SUBJECT
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)

_CHECKOUT_READ = "_reads_the_checkout"

_PULL_REQUEST_READ = "subject_verdict"

# The pull request read answering as one nobody could take does.
_UNREAD_PULL_REQUEST = ReportEvidence(ReportEvidenceVerdict.HOLD, "the recorded pull request could not be read")

# A requirements revision no reviewer was handed, for a review subject moved on the comment.
_ELSEWHERE = hashlib.sha256(b"requirements nobody was handed").hexdigest()

# Which of a recovery's checkout readings proves no head, numbered in the order
# the recovery takes them: the one its candidate is read with, and the last
# word's, behind the captured run's proof.
_UNPROVED_READINGS = (("the candidate's", 1), ("the last word's", 2))


def _unproved_at(original, failing: int, calls: list, *args):
    """Answer `original`, except that reading number `failing` proves no head, as a failed head proof reads."""
    reading = original(*args)
    calls.append(reading)
    if len(calls) != failing:
        return reading
    return replace(reading, head="", tree="", base=_BranchDivergence())


def _moves_the_subject(case: support.VerificationRecoveryCase, recorded: dict) -> None:
    """Record `recorded` on `case`'s pinned comment as the review subject the latest reviewer was handed."""
    moved = case.gh.read_pinned_state(case.issue)
    moved.set(REVIEW_SUBJECT, recorded)
    case.gh.write_pinned_state(case.issue, moved)


def _unread(move, *_args) -> ReportEvidence:
    """A pull request read nobody could take, `move` made while it was asked."""
    move()
    return _UNREAD_PULL_REQUEST


class UnreadCheckoutRecoveryTest(support.VerificationRecoveryCase, unittest.TestCase):
    """A captured run is held over a checkout nobody could read, then routed as recorded with nothing run again."""

    def test_an_unread_checkout_holds_the_run(self) -> None:
        # Whichever reading fails, the route is held for the checkout that
        # could not be read, with the captured run still pending rather than
        # abandoned. Read on the head again, the run -- its transcript, and the
        # commit and source it was tested on -- is routed exactly as recorded.
        for reading, failing in _UNPROVED_READINGS:
            with self.subTest(reading=reading):
                head, captured = self._holds_over_an_unread_checkout(failing)

                self.recovers()

                self.assertEqual(
                    (readings.pinned_records(self), self.runs()),
                    ((captured, None, git_support.invalidated(self)), 1),
                )
                self.assert_recovered(head)

    def test_an_unread_pull_request_hides_no_move(self) -> None:
        # The pull request cannot be read for the captured run's proof, which
        # stops there, and the review subject the run answers for is moved on
        # the comment before the recovery or while the pull request is asked.
        # The records are read beside that reading all the same, so the run is
        # abandoned unrun; with the subject put back, the head is routed with
        # nothing run or recorded.
        for during in (False, True):
            with self.subTest(moved_while_asked=during):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                self.dies_routing(partial(self.finishes, head))
                captured = readings.pinned_records(self)[0]
                self._recovers_beside_a_moved_subject(during=during)

                self._assert_abandoned(captured)
                self.recovers()
                self._assert_abandoned(captured)
                self.assert_recovered(head)

    def _recovers_beside_a_moved_subject(self, *, during: bool) -> None:
        """Recover over a pull request nobody could read, the review subject moved before or `during` that read.

        The subject is put back once the recovery is done.
        """
        recorded = self.gh.read_pinned_state(self.issue).get(REVIEW_SUBJECT)
        moves = partial(_moves_the_subject, self, {**recorded, "requirements": _ELSEWHERE})
        if not during:
            moves()
        unread = partial(_unread, moves if during else lambda: None)
        with patch.object(report_publication_evidence, _PULL_REQUEST_READ, side_effect=unread):
            self.recovers()
        _moves_the_subject(self, recorded)

    def _assert_abandoned(self, captured) -> None:
        """Nothing pending or current, the settled evidence invalidated and `captured` abandoned, and no second run."""
        retired = (*git_support.invalidated(self), (captured.receipt, readings.ABANDONED))
        self.assertEqual(
            (readings.pinned_records(self), self.runs()),
            ((None, None, retired), 1),
        )

    def _holds_over_an_unread_checkout(self, failing: int) -> tuple:
        """A fresh case's captured run, recovered with checkout reading number `failing` proving no head.

        The head and the run, once that recovery held the route over the
        unread checkout with the run still pending.
        """
        self.setUp()
        head = self.lands_a_reviewed_rebase()
        self.dies_routing(partial(self.finishes, head))
        captured = readings.pinned_records(self)[0]
        unproved = partial(_unproved_at, getattr(rewrite_facts, _CHECKOUT_READ), failing, [])
        with (
            patch.object(rewrite_facts, _CHECKOUT_READ, side_effect=unproved),
            self.assertLogs("orchestrator.workflow", "WARNING") as logged,
        ):
            self.recovers()
            self.assertIn("could not be proved", str(logged.output))
        self.assert_held(captured)
        return head, captured


if __name__ == "__main__":
    unittest.main()
