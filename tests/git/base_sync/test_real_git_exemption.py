# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The refresh-time rebase of an adjudicated commit, against a real repository.

The exemption names one commit and only it, and the per-tick refresh takes the
branch off that commit as soon as the base moves: past the handoff a pushed
branch is kept in step with base by the PR-aware sync, which force-pushes a
replay nothing exempts. Measured afresh that replay is oversized again -- the
same lines, over an equivalent base -- and a pull request already open over the
work goes back into adjudication.

Every reading here is the real one: a real remote, a real base advance, a real
rebase, and the canonical fingerprint taken over the actual objects on both
sides of the replay. Only the authenticated push is stood in for, and only the
remote-side base freeze, which these fixtures have no token to reach.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.git import branch_transport
from orchestrator.git.base_sync import pre_pr
from orchestrator.workflow.late_split import (
    exemption_reading as _exemption_reading,
    rewrite_reading as _rewrite_reading,
    rewrite_values as _rewrite_values,
)
from tests.git.base_sync.exemption_git_support import (
    BASE_EDIT,
    FORGED_FILE,
    SHARED_FILE,
    AdjudicatedRebaseRealGitFixture,
    _RepointsTheBaseRef,
    _shared_body,
    events_of,
    forged_base,
)
from tests.git.base_sync.real_git_test_support import _LocalBranchPusher
from tests.workflow.fixtures import (
    LABEL_DECOMPOSING,
    LABEL_VALIDATING,
)

ISSUE = 7

EVENT_MEASUREMENT = "late_measurement"
EVENT_TRANSFER = "late_transfer"

# The park a rolled-back auto rebase leaves, which is what says the refusal
# reached the refresh's own failure path rather than the gate's.
KEY_AWAITING_HUMAN = "awaiting_human"
KEY_PARK_REASON = "park_reason"
PARK_PUSH_FAILED = "auto_base_rebase_push_failed"


class _AdjudicatedRebaseCase(AdjudicatedRebaseRealGitFixture):
    """One base advance published over a branch a human already ruled on."""

    def _refresh_with_push(self, push, forging: str = "") -> None:
        """Run one refresh, optionally with the base ref forged mid-tick."""
        rebase = _RepointsTheBaseRef(self, forging) if forging else None
        with patch.object(branch_transport, "_push_branch", side_effect=push):
            if rebase is None:
                self._refresh()
                return
            with patch.object(
                pre_pr, "_rebase_base_into_worktree", side_effect=rebase,
            ):
                self._refresh()

    def _rebase_over(self) -> str:
        """Advance the base off a path the branch has, and publish the replay.

        Answers with the head the replay replaced, which is both the commit
        the adjudication accepted and the head the force-push is leased
        against.
        """
        self._advance_base(conflicting=False)
        accepted = self._wt_head()
        self._refresh_with_push(_LocalBranchPusher())
        return accepted


class EquivalentRebaseRealGitTest(_AdjudicatedRebaseCase, unittest.TestCase):
    """The replay that contributes exactly what the adjudication accepted."""

    def setUp(self) -> None:
        super().setUp()
        self._adjudicate()
        self.accepted = self._rebase_over()

    def test_the_exemption_moves_onto_the_replay(self) -> None:
        # The push landed, so the commit the verdict now names is one the pull
        # request really carries -- which is the whole of what makes the move
        # safe and why it rides the receipt rather than the grant.
        replayed = self._wt_head()

        self.assertNotEqual(replayed, self.accepted)
        durable = self._gh.read_pinned_state(self._gh._issues[ISSUE])
        self.assertTrue(_exemption_reading.is_exempt(durable, replayed))
        identity = _exemption_reading.read_semantic_identity(durable)
        self.assertEqual(identity.candidate_sha, replayed)
        self.assertEqual(identity.base_sha, self._merge_base())

    def test_the_authorization_names_the_rebase(self) -> None:
        authorized = _rewrite_reading.read_rewrite_authorization(
            self._gh.read_pinned_state(self._gh._issues[ISSUE]),
        )

        self.assertEqual(
            authorized.rewrite.kind, _rewrite_values.LateRewriteKind.AUTO_CLEAN_REBASE,
        )
        self.assertEqual(authorized.rewrite.from_sha, self.accepted)
        self.assertEqual(authorized.rewrite.to_sha, self._wt_head())
        # The pre-rebase anchor is the head the force-push was leased against,
        # and it is a fact of its own beside the commit that was replaced.
        self.assertEqual(authorized.rewrite.lease, self.accepted)
        self.assertEqual(
            authorized.phase, _rewrite_values.LateRewritePhase.PUBLISHED,
        )

    def test_nothing_is_measured_or_adjudicated(self) -> None:
        # No late generation, no decomposer run, and no adjudication comment
        # pair: the replay publishes on the verdict a human already gave.
        self.assertEqual(events_of(self, EVENT_MEASUREMENT), [])
        self.assertNotIn((ISSUE, LABEL_DECOMPOSING), self._gh.label_history)
        self.assertEqual(len(events_of(self, EVENT_TRANSFER)), 1)


class MeasuredRebaseRealGitTest(_AdjudicatedRebaseCase, unittest.TestCase):
    """The replays that earn no transfer and get the reading they always did."""

    def test_a_changed_contribution_is_measured(self) -> None:
        # The base advanced under a file the branch also edits. The replay is
        # clean and the prospective contribution is a different one -- the
        # pre-image a reviewer would be handed is another blob -- so the
        # ordinary cumulative gate measures it exactly as it always has.
        self._commits_on_the_shared_file()
        self._adjudicate()
        accepted = self._wt_head()
        self._commit_to_base(SHARED_FILE, _shared_body(first=BASE_EDIT))

        self._refresh_with_push(_LocalBranchPusher())

        self.assertNotEqual(self._wt_head(), accepted)
        self._assert_verdict_put(accepted)
        self.assertEqual(len(events_of(self, EVENT_MEASUREMENT)), 1)
        self.assertIn((ISSUE, LABEL_VALIDATING), self._gh.label_history)

    def test_a_forged_base_ref_is_measured(self) -> None:
        # `refs/remotes/origin/main` lives in a store the agent writes to, and
        # a worktree sharing it can repoint the ref after this tick's fetch.
        # Replayed onto a base carrying work the remote does not have, the
        # branch fingerprints as the little sitting on top of it while the
        # pull request against the real base carries that work and this change
        # together -- so the base is frozen from the remote and the forgery is
        # a different contribution the cumulative gate measures.
        self._adjudicate()
        accepted = self._wt_head()
        self._advance_base(conflicting=False)

        self._refresh_with_push(
            _LocalBranchPusher(), forging=forged_base(self),
        )

        self.assertTrue((self._wt / FORGED_FILE).exists())
        self._assert_verdict_put(accepted)
        self.assertEqual(len(events_of(self, EVENT_MEASUREMENT)), 1)

    def test_a_refused_push_leaves_the_verdict_put(self) -> None:
        # The rollback puts the branch back onto the commit the exemption
        # never left, and the refresh parks for the operator exactly as it
        # does for any other rejected lease.
        self._adjudicate()
        accepted = self._wt_head()
        self._advance_base(conflicting=False)

        self._refresh_with_push(MagicMock(return_value=False))

        self.assertEqual(self._wt_head(), accepted)
        self._assert_verdict_put(accepted)
        pinned = self._gh.pinned_data(ISSUE)
        self.assertTrue(pinned[KEY_AWAITING_HUMAN])
        self.assertEqual(pinned[KEY_PARK_REASON], PARK_PUSH_FAILED)

    def _assert_verdict_put(self, accepted: str) -> None:
        """The exemption is on the commit a human ruled on, and alone."""
        durable = self._gh.read_pinned_state(self._gh._issues[ISSUE])
        self.assertTrue(_exemption_reading.is_exempt(durable, accepted))
        self.assertFalse(_rewrite_reading.carries_rewrite_authorization(durable))
        self.assertEqual(events_of(self, EVENT_TRANSFER), [])


if __name__ == "__main__":
    unittest.main()
