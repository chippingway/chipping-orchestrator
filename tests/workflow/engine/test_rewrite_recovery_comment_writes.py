# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured transaction's abandonment over a pinned comment short of room, or written by another road meanwhile.

A run captured for the landed head the base advanced past again is abandoned
before its attempt retires in the same write, staged on the comment as it
then reads, so an approval another road wrote meanwhile is kept rather than
refusing it, and the tick's rebase goes on. An exact tree's carry an earlier
finish captured is proved again under a
configuration that moved, over a comment with no room to invalidate the
current evidence, or one another road wrote the carry's approval onto after
the recovery read it, refusing the write that invalidates the current
evidence: the route is held either way, but behind the last word, so the carry
is still abandoned durably -- its history entry takes less room than the
transaction it retires, and the approval it answers for goes with it -- and
once the configuration is back the head is routed with nothing carried or
run. A run captured for the landed head whose requirements move while it is
proved is abandoned even where another road writes an approval onto the
comment meanwhile: the abandonment is staged on the comment as it then reads,
so that approval is kept rather than refusing it, and putting the
requirements back routes nothing the run carried.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git.base_sync import replay_evidence
from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from orchestrator.workflow.engine.review_subjects import APPROVED_SUBJECT
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)
from tests.workflow.interleaving import _RacesPastTheStep

# A key nothing reads, standing in for whatever else fills the comment.
_FILLER = "room_filler"

_CONFIGURED = f"test -f feature.py && echo '{git_support.CHECKED}'"

_CLASSIFIED = "_made_for_another_publication"


def _fills_the_comment(case: support.VerificationRecoveryCase) -> None:
    """Fill `case`'s pinned comment to its limit, as another road's records would."""
    filled = case.gh.read_pinned_state(case.issue)
    filled.set(_FILLER, "")
    room = MAX_PINNED_BODY - len(pinned_state_body(filled.data))
    filled.set(_FILLER, "x" * room)
    case.gh.write_pinned_state(case.issue, filled)


def _makes_room(case: support.VerificationRecoveryCase) -> None:
    """Take the filler back off `case`'s pinned comment, as a human making room does."""
    emptied = case.gh.read_pinned_state(case.issue)
    emptied.data.pop(_FILLER)
    case.gh.write_pinned_state(case.issue, emptied)


def _approves_and_edits(case: support.VerificationRecoveryCase, approval, approved) -> None:
    """Record `approved` as `approval` on `case`'s comment as another road would, and edit the issue's requirements."""
    written = case.gh.read_pinned_state(case.issue)
    written.set(approval, approved)
    case.gh.write_pinned_state(case.issue, written)
    case.issue.body = "Also cover an approval written meanwhile."


def _approves_once(case: support.VerificationRecoveryCase, approved, done: list) -> None:
    """Record `approved` as the approval on `case`'s comment as another road would, the first time only."""
    if done:
        return
    done.append(approved)
    written = case.gh.read_pinned_state(case.issue)
    written.set(APPROVED_SUBJECT, approved)
    case.gh.write_pinned_state(case.issue, written)


def _approves_behind_the_classification(case: support.VerificationRecoveryCase, captured) -> None:
    """Have another road write `captured`'s approval once `case`'s next recovery has classified what it fetched."""
    approves = partial(_approves_once, case, captured.binding.target.subject, [])
    racing = _RacesPastTheStep(getattr(replay_evidence, _CLASSIFIED), approves)
    case.enterContext(patch.object(replay_evidence, _CLASSIFIED, side_effect=racing))


def _captures(case: support.VerificationRecoveryCase) -> tuple:
    """Land a reviewed rebase whose finish records its run and dies at the relabel; the head, and that run."""
    head = case.lands_a_reviewed_rebase()
    case.dies_routing(partial(case.finishes, head))
    return head, readings.pinned_records(case)[0]


class CommentWritesRecoveryTest(support.VerificationRecoveryCase, unittest.TestCase):
    """A captured transaction something moved under is abandoned whatever room the comment has or who wrote it."""

    def test_no_room_to_invalidate_still_abandons(self) -> None:
        # The configuration moves under the captured carry, which would
        # invalidate the current evidence, over a comment with no room for
        # that: the route is held, and the carry is abandoned behind it.
        # With the configuration back and room made, the head is routed
        # with nothing carried or run.
        head, captured = self._holds_a_moved_carry(lambda case, _captured: _fills_the_comment(case))

        self._assert_retired(captured)
        _makes_room(self)
        self.configures(_CONFIGURED)
        self.recovers()
        self._assert_retired(captured)
        self.assertEqual(self.runs(), 0)
        self.assert_recovered(head)

    def test_a_refused_invalidation_still_abandons(self) -> None:
        # The configuration moves under the captured carry, and another road
        # writes the approval the carry answers for once the recovery has
        # read the comment, so the write invalidating the current evidence is
        # refused. The carry is abandoned behind that refusal all the same,
        # its approval with it, and with the configuration back the head is
        # routed with nothing carried or run.
        head, captured = self._holds_a_moved_carry(_approves_behind_the_classification)

        self._assert_retired(captured)
        self.assertIsNone(readings.pinned(self).get(APPROVED_SUBJECT))
        self.configures(_CONFIGURED)
        self.recovers()
        self.assertEqual(self.runs(), 0)
        self.assert_recovered(head)

    def test_an_advanced_base_keeps_the_approval(self) -> None:
        # The base advances again past the landed head, and another road
        # writes an approval once the recovery has read the comment: the
        # captured run is still abandoned before the attempt retires -- in a
        # write staged on the comment as it then reads, so the approval is
        # kept rather than refusing it -- and the tick's rebase publishes the
        # next head with nothing run again.
        head, captured = _captures(self)
        support.advances_the_base_again(self)
        _approves_behind_the_classification(self, captured)

        self.recovers()

        self._assert_retired(captured)
        approved = readings.pinned(self).get(APPROVED_SUBJECT)
        said = (support.announced(self), self.pushes.call_count, self.runs())
        self.assertEqual(approved, captured.binding.target.subject)
        self.assertEqual(said, ([head, git_support.remote_head(self)], 1, 1))

    def test_another_roads_approval_is_kept(self) -> None:
        # Another road writes an approval while the recovery re-reads the
        # settled report the captured run is bound to, and the requirements
        # are edited at that moment: the run is abandoned unrun, and the
        # approval stands as that road wrote it. Put back, the requirements
        # route nothing the run carried.
        head, captured, body = self._recovers_beside_an_approval()
        subject = captured.binding.target.subject

        self._assert_retired(captured)
        approved = readings.pinned(self).get(APPROVED_SUBJECT)
        self.assertEqual((approved, self.runs()), (subject, 1))
        self.issue.body = body
        self.recovers()
        self._assert_retired(captured)
        self.assert_recovered(head)

    def _holds_a_moved_carry(self, beside) -> tuple:
        """A carry captured for a rebase onto the anchor's tree, recovered under a moved configuration.

        `beside` is handed the case and the carry before that recovery, which
        holds the route. The head, and the carry.
        """
        git_support.advances_the_base(self, net=False)
        head = self.rebases_by_hand()
        self.reviews(head)
        self.dies_routing(partial(self.finishes, head))
        captured = readings.pinned_records(self)[0]
        self.assertNotEqual(captured.binding.tested_sha, head)
        self.configures("echo another")
        beside(self, captured)
        self.recovers()
        self.assert_held(None)
        return head, captured

    def _recovers_beside_an_approval(self) -> tuple:
        """A captured run, recovered with an approval written and the requirements edited as its report is re-read.

        The head, the run, and the issue body before the edit.
        """
        head = self.lands_a_reviewed_rebase()
        self.dies_routing(partial(self.finishes, head))
        captured = readings.pinned_records(self)[0]
        body = self.issue.body
        reread = self.gh.reread_report_location
        approves = partial(_approves_and_edits, self, APPROVED_SUBJECT, captured.binding.target.subject)
        self.gh.reread_report_location = _RacesPastTheStep(reread, approves)
        self.recovers()
        self.gh.reread_report_location = reread
        return head, captured, body

    def _assert_retired(self, captured) -> None:
        """Nothing pending, and `captured` the latest record retired, as abandoned."""
        recorded = readings.pinned_records(self)
        self.assertEqual(
            (recorded[0], recorded[2][-1]),
            (None, (captured.receipt, readings.ABANDONED)),
        )


if __name__ == "__main__":
    unittest.main()
