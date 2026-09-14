# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A conflict-stage replay decided over a real repository and real bytes.

The claim this seam rests on is one about content: a rebase that replayed an
adjudicated commit onto a base that moved carries the SAME contribution, and
anything that moved a covered byte carries a different one. Neither half can
be settled by a case that seeds the digests, because a seeded digest answers
what the case said rather than what the objects hold.

So both readings here are the real ones -- git's own fork points at each end,
git's own rebase between them, and the canonical fingerprint taken over the
actual trees and blobs. Only the two the fixture has no token for are stood
in: the remote-side base freeze, and the authenticated push.

The pair of outcomes is the whole point. The replay earns the permit and
publishes without a reading, so the change a human ruled on is not ruled on
twice. The same replay with ONE byte written into it earns nothing, is
measured like any other candidate, and past the ceiling goes back to the
adjudication -- which is what any change nobody has seen is owed.
"""
from __future__ import annotations

import unittest
from dataclasses import replace as _replace
from unittest.mock import MagicMock, patch

from orchestrator.config import settings as config
from orchestrator.git import branch_transport as _branch_transport
from orchestrator.workflow.late_split import (
    exemption as _exemption,
    rewrites as _rewrites,
)
from orchestrator.workflow.stages.conflicts import (
    divergence as _divergence,
    evidence as _evidence,
    models as _conflict_models,
)
from orchestrator.workflow.stages.implementing import (
    late_push as _late_push,
    late_records as _late_records,
    late_transfer as _transfer,
)
from tests.support.replay_repository import (
    TOPIC_BRANCH,
    divergence_from_the_publication,
)
from tests.workflow.stages.conflicts import real_replay_case as _real_replay

LABEL_DECOMPOSING = "workflow:decomposing"

# The topic commit adds three lines, so a ceiling of two is what an oversized
# candidate was adjudicated against -- and what a change nobody ruled on has
# to be held to again.
PAST_THE_CEILING = 2

MAX_ADDED_LINES = "MAX_ADDED_LINES"
PUSH_BRANCH = "_push_branch"


class ReplayedTransferRealGitTest(_real_replay._RealReplayCase, unittest.TestCase):
    """A replay whose contribution the objects say is the accepted one."""

    def test_the_two_ends_fingerprint_alike(self) -> None:
        # What the permit turns on, read straight off the repository: a base
        # that moved changes which commit the diff is taken from and nothing
        # about the diff itself.
        accepted = self._contributes(
            self.replay.accepted_base, self.replay.accepted,
        )
        replayed = self._contributes(
            self.replay.replayed_base, self.replay.replayed,
        )

        self.assertEqual(accepted, replayed)
        self.assertNotEqual(self.replay.accepted, self.replay.replayed)

    def test_an_equivalent_replay_earns_the_permit(self) -> None:
        gate = self._adjudicated(self.replay.replayed)

        carried = _transfer._carried_over(
            self._gate_for(gate, self.replay.replayed), self.replay.replayed,
        )

        self.assertEqual(carried, _transfer._CARRIED_OVER)

    def test_the_permit_records_what_git_answered(self) -> None:
        # The grant is durable before any push, and what it records is what a
        # later reader re-derives the equality from -- both ends, over the two
        # fork points git really answered.
        gate = self._adjudicated(self.replay.replayed)
        _transfer._carried_over(
            self._gate_for(gate, self.replay.replayed), self.replay.replayed,
        )

        authorized = _rewrites.read_rewrite_authorization(gate.state)
        self.assertEqual(authorized.rewrite.from_sha, self.replay.accepted)
        self.assertEqual(
            authorized.rewrite.from_base_sha, self.replay.accepted_base,
        )
        self.assertEqual(authorized.rewrite.to_sha, self.replay.replayed)
        self.assertEqual(
            authorized.rewrite.to_base_sha, self.replay.replayed_base,
        )

    def test_a_base_no_remote_has_earns_nothing(self) -> None:
        # The forgery the base proof is here for, decided over real objects.
        # Both ends fingerprint alike -- the forged base carries the bulk, so
        # the replay is read as adding exactly what was adjudicated -- and the
        # commit it produced carries that bulk and the adjudicated change
        # together. Held to the branch the remote really answers for, the
        # permit refuses and the ordinary cumulative gate measures it.
        forged = self.replays_onto_a_forged_base(self.replay)
        gate = self._adjudicated(forged.replayed)
        self.assertEqual(
            self._contributes(forged.replayed_base, forged.replayed),
            self._contributes(self.replay.accepted_base, self.replay.accepted),
        )

        carried = _transfer._carried_over(
            self._gate_for(gate, forged.replayed), forged.replayed,
        )

        self.assertEqual(carried, "")
        self.assertIsNone(_rewrites.read_rewrite_authorization(gate.state))
        self.assertEqual(
            gate.gh.pinned_data(_real_replay.ISSUE_NUMBER)[_exemption.LATE_EXEMPT_SHA],
            self.replay.accepted,
        )

    def _gate_for(self, gate, candidate: str):
        """The subject the permit is asked over, with the entry it froze."""
        return _replace(
            gate,
            reconciling=True,
            candidate=candidate,
            entry=_late_records._PublicationEntry(
                stage=_real_replay.STAGE,
                pr_number=_real_replay.PR_NUMBER,
                published_sha=self.replay.accepted,
            ),
            rewrite=self._evidence(gate, candidate),
        )


class DivergentRecoveryRealGitTest(_real_replay._RealReplayCase, unittest.TestCase):
    """The shape a real replay leaves, and what lets a recovery past it.

    A rebase moves the branch off the head it replayed, so the publication
    stops being an ancestor: the checkout comes back ahead of the pull request
    AND behind it. That is the same reading a stale branch carrying somebody
    else's commit gives, and this stage parks it -- so without the record a
    tick that rebased and died before its push could never be finished.
    """

    def test_a_replay_really_diverges(self) -> None:
        # Measured off the objects, because the whole guard turns on it: an
        # ahead-only reading would be a commit made ON TOP of what the remote
        # has, which is not what a rebase leaves.
        ahead, behind = divergence_from_the_publication(self.replay)

        self.assertGreater(ahead, 0)
        self.assertGreater(behind, 0)

    def test_the_record_leases_the_pre_rebase_head(self) -> None:
        # The exception this stage needs: the record names the head the pull
        # request is standing on and the commit the checkout is on, so the
        # commits the force-push drops are the ones the replay superseded --
        # and the lease is that same pre-rebase head.
        gate = self._adjudicated(self.replay.replayed)
        self._records_the_replay(gate)

        decision = self._diverged(gate)

        self.assertFalse(decision.parked)
        self.assertEqual(decision.publish_lease, self.replay.accepted)

    def test_a_branch_no_record_explains_stays_parked(self) -> None:
        # The default this guard was written for, and what says the exception
        # above is the record's doing rather than the shape being waved
        # through: the same diverged checkout with nothing accounting for it
        # is refused.
        gate = self._adjudicated(self.replay.replayed)

        decision = self._diverged(gate)

        self.assertTrue(decision.parked)

    def _records_the_replay(self, gate) -> None:
        """What the rebase wrote about itself before it ran, and then again."""
        _evidence._records_the_replay(
            self._context(gate),
            _evidence._Replayed(
                head=self.replay.accepted, base_sha=self.replay.accepted_base,
            ),
            _real_replay.PR_NUMBER,
        )
        _evidence._records_the_replayed_commit(
            self._context(gate),
            _evidence._Replayed(
                head=self.replay.accepted, base_sha=self.replay.accepted_base,
            ),
            self.replay.replayed,
        )

    def _diverged(self, gate):
        """What the guard decides over the real divergence this replay left."""
        ahead, behind = divergence_from_the_publication(self.replay)
        return _divergence._guard_diverged_worktree(
            self._context(gate),
            gate.gh.get_pr(_real_replay.PR_NUMBER),
            _conflict_models._WorktreeSync(
                worktree=self.replay.worktree,
                branch=TOPIC_BRANCH,
                ahead=ahead,
                behind=behind,
                fetched_tip=self.replay.accepted,
            ),
        )


class AuthoredChangeRealGitTest(_real_replay._RealReplayCase, unittest.TestCase):
    """The same replay with one byte written into it, decided the same way."""

    def test_one_byte_moves_the_contribution(self) -> None:
        amended = self.writes_one_byte(self.replay)

        accepted = self._contributes(
            self.replay.accepted_base, self.replay.accepted,
        )
        authored = self._contributes(self.replay.replayed_base, amended)

        self.assertNotEqual(accepted, authored)

    def test_one_byte_takes_the_cumulative_gate(self) -> None:
        # The permit is a claim about the CONTRIBUTION, so a commit carrying
        # one byte nobody ruled on is refused however plainly a rebase put it
        # there -- and falls through to the reading every other candidate for
        # a published pull request gets.
        amended = self.writes_one_byte(self.replay)
        gate = self._adjudicated(amended)

        published = self._publishes(gate, amended)

        self.assertTrue(published.held)
        self.assertFalse(_rewrites.carries_rewrite_authorization(gate.state))
        self.assertIn(
            (_real_replay.ISSUE_NUMBER, LABEL_DECOMPOSING), gate.gh.label_history,
        )

    def test_an_equivalent_replay_still_publishes(self) -> None:
        # The other half of the same run, and what says the refusal above is
        # about the byte rather than about the ceiling: the identical setup
        # over the replayed commit goes out under the same low ceiling.
        gate = self._adjudicated(self.replay.replayed)

        published = self._publishes(gate, self.replay.replayed)

        self.assertTrue(published.landed)
        self.assertNotIn(
            (_real_replay.ISSUE_NUMBER, LABEL_DECOMPOSING), gate.gh.label_history,
        )
        self.assertEqual(
            gate.gh.pinned_data(_real_replay.ISSUE_NUMBER)[_exemption.LATE_EXEMPT_SHA],
            self.replay.replayed,
        )

    def _publishes(self, gate, candidate: str):
        """One gated publication of this candidate, under a ceiling it is past.

        Every reading but two is the real one. The base freeze the case seeds
        goes to the remote, and the push is the network hop itself.
        """
        self.enterContext(patch.object(
            _branch_transport, PUSH_BRANCH, MagicMock(return_value=True),
        ))
        self.enterContext(patch.object(
            config, MAX_ADDED_LINES, PAST_THE_CEILING,
        ))
        return _late_push._publishes(
            gate, TOPIC_BRANCH, self._entered(gate, candidate),
        )


if __name__ == "__main__":
    unittest.main()
