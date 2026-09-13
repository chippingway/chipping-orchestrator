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

from orchestrator import config
from orchestrator.git import branch_transport as _branch_transport
from orchestrator.git.measurement import (
    commits as _measurement_commits,
    fingerprint as _fingerprint,
)
from orchestrator.git.measurement.models import FrozenCommit
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
from orchestrator.workflow.state import WorkflowLabel
from tests.support.authorization import _authorize
from tests.support.fakes import (
    FakeGitHubClient,
    FakeLabel,
    FakePR,
    FakePRRef,
    make_issue,
)
from tests.support.replay_repository import (
    TOPIC_BRANCH,
    ReplayRepositoryMixin,
    divergence_from_the_publication,
)
from tests.workflow.observation_support import ObservedCloseCase

ISSUE_NUMBER = 9
PR_NUMBER = 77
STAGE = WorkflowLabel.RESOLVING_CONFLICT

LABEL_DECOMPOSING = "workflow:decomposing"

# The topic commit adds three lines, so a ceiling of two is what an oversized
# candidate was adjudicated against -- and what a change nobody ruled on has
# to be held to again.
PAST_THE_CEILING = 2

MAX_ADDED_LINES = "MAX_ADDED_LINES"
FREEZE_BASE = "_freeze_base_commit"
PUSH_BRANCH = "_push_branch"


class _RealReplayCase(ObservedCloseCase, ReplayRepositoryMixin):
    """One adjudicated commit, really replayed, really fingerprinted."""

    def setUp(self) -> None:
        super().setUp()
        # The transfer re-reads the issue before granting anything, and a
        # close another case latched process-wide is a refusal this one never
        # asked for.
        self._fresh_process()
        self.replay = self.build_replay()

    def _adjudicated(self, candidate: str):
        """The gate for an issue whose exemption names the replayed commit.

        The pinned comment is exactly what a settled `single` verdict leaves,
        with the digest taken over the objects rather than chosen: the pair
        the adjudication was measured between, and the real contribution
        between them.
        """
        github = FakeGitHubClient()
        issue = make_issue(ISSUE_NUMBER)
        issue.labels.append(FakeLabel(str(STAGE)))
        github.add_issue(issue)
        github.add_pr(FakePR(
            number=PR_NUMBER,
            head_branch=TOPIC_BRANCH,
            head=FakePRRef(sha=self.replay.accepted),
        ))
        github.seed_state(ISSUE_NUMBER, pr_number=PR_NUMBER)
        state = github.read_pinned_state(issue)
        contributes = self._contributes(
            self.replay.accepted_base, self.replay.accepted,
        )
        _exemption.record_exemption(state, self.replay.accepted)
        _exemption.record_semantic_identity(
            state,
            base_sha=self.replay.accepted_base,
            candidate_sha=self.replay.accepted,
            fingerprint=contributes,
        )
        _authorize(
            state, self.replay.accepted, self.replay.accepted_base, contributes,
        )
        github.write_pinned_state(issue, state)
        return _late_records._gate(
            github, self.replay.spec, issue, state, self.replay.worktree,
        )

    def _contributes(self, base: str, candidate: str) -> str:
        """What one pair really contributes, over the objects this host holds."""
        fingerprinted = _fingerprint._fingerprint_contribution(
            self.replay.worktree, base, candidate,
        )
        self.assertTrue(fingerprinted.is_fingerprinted)
        return fingerprinted.digest

    def _context(self, gate) -> _conflict_models._ConflictContext:
        """The tick this stage's own owners are handed."""
        return _conflict_models._ConflictContext(
            gate.gh, gate.spec, gate.issue, gate.state,
        )

    def _evidence(self, gate, candidate: str):
        """What the replay hands the gate, over the fork points git answers."""
        return _evidence._rewritten(
            self._context(gate),
            self.replay.worktree,
            _evidence._replayed(
                self.replay.spec, self.replay.worktree, self.replay.accepted,
            ),
            candidate,
            PR_NUMBER,
        )

    def _entered(self, gate, candidate: str) -> _late_records._Entered:
        return _late_records._Entered(
            head=self.replay.accepted,
            reconciling=True,
            candidate=candidate,
            rewrite=self._evidence(gate, candidate),
        )


class ReplayedTransferRealGitTest(_RealReplayCase, unittest.TestCase):
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

    def _gate_for(self, gate, candidate: str):
        """The subject the permit is asked over, with the entry it froze."""
        return _replace(
            gate,
            reconciling=True,
            candidate=candidate,
            entry=_late_records._PublicationEntry(
                stage=STAGE,
                pr_number=PR_NUMBER,
                published_sha=self.replay.accepted,
            ),
            rewrite=self._evidence(gate, candidate),
        )


class DivergentRecoveryRealGitTest(_RealReplayCase, unittest.TestCase):
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
            PR_NUMBER,
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
            gate.gh.get_pr(PR_NUMBER),
            _conflict_models._WorktreeSync(
                worktree=self.replay.worktree,
                branch=TOPIC_BRANCH,
                ahead=ahead,
                behind=behind,
                fetched_tip=self.replay.accepted,
            ),
        )


class AuthoredChangeRealGitTest(_RealReplayCase, unittest.TestCase):
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
            (ISSUE_NUMBER, LABEL_DECOMPOSING), gate.gh.label_history,
        )

    def test_an_equivalent_replay_still_publishes(self) -> None:
        # The other half of the same run, and what says the refusal above is
        # about the byte rather than about the ceiling: the identical setup
        # over the replayed commit goes out under the same low ceiling.
        gate = self._adjudicated(self.replay.replayed)

        published = self._publishes(gate, self.replay.replayed)

        self.assertTrue(published.landed)
        self.assertNotIn(
            (ISSUE_NUMBER, LABEL_DECOMPOSING), gate.gh.label_history,
        )
        self.assertEqual(
            gate.gh.pinned_data(ISSUE_NUMBER)[_exemption.LATE_EXEMPT_SHA],
            self.replay.replayed,
        )

    def _publishes(self, gate, candidate: str):
        """One gated publication of this candidate, under a ceiling it is past.

        Every reading but two is the real one. The base freeze goes to the
        remote, which this fixture has no token to reach, and the push is the
        network hop itself.
        """
        self.enterContext(patch.object(
            _measurement_commits, FREEZE_BASE,
            MagicMock(return_value=FrozenCommit(sha=self.replay.replayed_base)),
        ))
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
