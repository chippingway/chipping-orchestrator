# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run whose abandonment did not land keeps the recovery that owes it.

A finish recorded its run for the landed head and died at its relabel, and the
remote was rolled back onto the anchor before the next recovery. That snapshot
is movement under the run, and the road it chooses resets and clears the
attempt -- so the run is abandoned first. Where that abandonment does not land
-- the pinned comment would not read again, or another road moved a record
under the write -- the recovery takes no road at all: nothing is reset,
cleared, or parked, and the attempt's anchor keeps the dispatcher's
reconciliation off the run, so putting the heads back settles nothing. The
next recovery abandons the run and goes on down the road it chose. Nothing
runs, pushes, or announces again, and no developer is launched.
"""
from __future__ import annotations

import hashlib
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.workflow.engine import verification_durable, verification_transaction
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence, ReportEvidenceVerdict
from orchestrator.workflow.engine.review_subjects import REVIEW_SUBJECT
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)
from tests.workflow.interleaving import _RacesPastTheStep

_DURABLE_READ = "durable_comment"

# The comment read again for the abandonment answering as one nobody could read.
_UNREAD = (None, ReportEvidence(ReportEvidenceVerdict.HOLD, "the pinned comment could not be read again"))

# A requirements revision no reviewer was handed, for a review subject another road moves.
_ELSEWHERE = hashlib.sha256(b"requirements another road recorded").hexdigest()


def _moves_the_subject(case: support.VerificationRecoveryCase) -> None:
    """Move the review subject on `case`'s pinned comment, as another road's write would."""
    moved = case.gh.read_pinned_state(case.issue)
    moved.set(REVIEW_SUBJECT, {**moved.get(REVIEW_SUBJECT), "requirements": _ELSEWHERE})
    case.gh.write_pinned_state(case.issue, moved)


def _unreadable(*_called, **_options):
    """The comment read again for an abandonment, answering as one nobody could read."""
    return _UNREAD


def _puts_the_remote_on(case: support.VerificationRecoveryCase, head: str) -> None:
    """Point `case`'s remote branch at `head`."""
    case._git("update-ref", f"refs/heads/{git_support.BRANCH}", head, cwd=case._remote)


def _reconciles(case: support.VerificationRecoveryCase) -> None:
    """Run the dispatcher's reconciliation of `case`'s recorded evidence, over the comment as it stands."""
    verification_transaction._reconciles_pending_evidence(
        case.gh, case._spec, case.issue, git_support.REVIEWING, case.gh.read_pinned_state(case.issue),
    )


# How the abandonment's write fails: the comment nobody could read again, or a
# record another road moved between that reading and the write.
_UNLANDED = (
    ("the comment would not read again", lambda _case, _original: _unreadable),
    (
        "another road moved a record under the write",
        lambda case, original: _RacesPastTheStep(original, partial(_moves_the_subject, case)),
    ),
)


class UnlandedAbandonmentTest(support.VerificationRecoveryCase, unittest.TestCase):
    """A recovery holds, with its attempt standing, until the abandonment it owes lands."""

    def test_an_unlanded_abandonment_holds(self) -> None:
        # The abandonment fails, so nothing is reset, cleared, or parked and
        # the reconciliation leaves the run to the standing attempt, even
        # with the heads put back. Rolled back again, the next recovery
        # abandons the run and takes the road the rollback chose.
        for failure, failing in _UNLANDED:
            with self.subTest(failure=failure):
                head, captured = self._holds_an_unlanded_abandonment(failing)
                _puts_the_remote_on(self, head)
                _reconciles(self)
                self.assertEqual(readings.pinned_records(self)[:2], (captured, None))
                _puts_the_remote_on(self, self.anchor)

                self.recovers()

                self._assert_abandoned(head, captured)

    def _holds_an_unlanded_abandonment(self, failing) -> tuple:
        """A fresh case's captured run, its remote rolled back and its abandonment failing as `failing` makes it.

        The recovery holds with the checkout where it was, the attempt
        standing, and the run recorded. The head, and the run.
        """
        self.setUp()
        head = self.lands_a_reviewed_rebase()
        self.dies_routing(partial(self.finishes, head))
        captured = readings.pinned_records(self)[0]
        _puts_the_remote_on(self, self.anchor)
        unlanded = failing(self, verification_durable.durable_comment)
        with patch.object(verification_durable, _DURABLE_READ, side_effect=unlanded):
            self.recovers()
        self.assertEqual(self._wt_head(), head)
        self.assert_held(captured)
        return head, captured

    def _assert_abandoned(self, head: str, captured) -> None:
        """`captured` abandoned and the attempt cleared, `head` announced once, and nothing pushed, launched, or run."""
        recorded = readings.pinned_records(self)
        attempt = readings.pinned(self)[readings.KEY_PENDING_PUSH]
        self.assertEqual(
            (recorded[0], recorded[2][-1], attempt),
            (None, (captured.receipt, readings.ABANDONED), None),
        )
        said = (support.announced(self), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(said, ([head], 0, 0))
        self.assertEqual(self.runs(), 1)

if __name__ == "__main__":
    unittest.main()
