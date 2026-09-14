# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Crash recovery against a real repository left mid-rebase.

Both routes, each over the shape it is built for: the running one over a
commit on top of the anchor, and the dormant vouched-replay one over a real
replay of the branch -- which it classifies on the record the attempt left,
since the divergence counts read that replay as an out-of-band update.
"""

from __future__ import annotations

import unittest

from orchestrator.workflow.stages.implementing import (
    late_approval_reading as _late_approval_reading,
    late_approval_state as _late_approval_state,
)
from tests.git.base_sync import recovery_git_support as fixtures
from tests.git.base_sync.recovery_git_support import RecoveryGitFixtureMixin
from tests.git.base_sync.vouched_replay_git_support import (
    VouchedReplayGitFixtureMixin,
)

PARK_FAILED = "auto_base_rebase_failed"

# A commit id no object in this repository answers to.
MISSING_COMMIT = "dead" * 10


class _InterruptedRebaseCases:
    """The four interruptions every recovery route answers the same way."""

    def test_unpushed_rebase_is_leased_onto_remote(self) -> None:
        recovered = self.recover()

        # The remote is still on the anchor, so the recovery reissues the push
        # the crash interrupted rather than rebasing again.
        self.assertTrue(recovered)
        self.assertEqual(self.push.leases, [self.anchor])
        self.assertEqual(self._remote_head(), self.recovered)
        self.assertEqual(fixtures.head_sha(self.work), self.recovered)
        self._assert_routed_to_validating("crash_recovery_pushed")

    def test_landed_push_is_finalized_once(self) -> None:
        self.publish_recovered_head()

        recovered = self.recover()

        # Only the recovery's own fetch can tell that the interrupted push
        # already landed -- the stale tracking ref still names the anchor.
        self.assertTrue(recovered)
        self.assertEqual(self.push.leases, [])
        self.assertEqual(self._remote_head(), self.recovered)
        self._assert_routed_to_validating("crash_recovery_relabel_only")

    def test_out_of_band_update_restores_anchor(self) -> None:
        pushed_elsewhere = self.advance_remote_out_of_band()

        recovered = self.recover()

        # Ahead *and* behind: the reissued force-push would drop someone
        # else's commit, so HEAD goes back to the last-known remote head.
        self.assertTrue(recovered)
        self.assertEqual(self.push.leases, [])
        self.assertEqual(self._remote_head(), pushed_elsewhere)
        self._assert_parked(fixtures.PARK_PUSH_FAILED)

    def test_dirty_worktree_is_reset_and_cleaned(self) -> None:
        (self.work / fixtures.FEATURE_FILE).write_text("half-resolved\n")
        (self.work / fixtures.SCRATCH_FILE).write_text("scratch\n")

        recovered = self.recover()

        # A rebase that left edits behind never had a publishable head, so
        # the worktree is restored and the leftovers are discarded.
        self.assertTrue(recovered)
        self.assertEqual(self.push.leases, [])
        self.assertEqual(self._remote_head(), self.anchor)
        self.assertFalse((self.work / fixtures.SCRATCH_FILE).exists())
        self.assertTrue(self.is_clean())
        self._assert_parked(fixtures.PARK_DIRTY)

    def _remote_head(self) -> str:
        return fixtures.head_sha(self.remote, fixtures.BRANCH_REF)

    def _assert_routed_to_validating(self, method: str) -> None:
        self.assertIn(
            (fixtures.ISSUE, fixtures.VALIDATING), self.gh.label_history,
        )
        published = self.gh.pinned_data(fixtures.ISSUE)
        self.assertIsNone(published.get(fixtures.KEY_PENDING_PUSH_SHA))
        self.assertEqual(
            [
                event.get(fixtures.METHOD_FIELD)
                for event in self.rebase_events()
            ],
            [method],
        )

    def _assert_parked(self, reason: str) -> None:
        # The reset put HEAD back on the anchor, so the anchor is dropped and
        # a later tick re-enters through the normal rebase flow instead.
        self.assertEqual(fixtures.head_sha(self.work), self.anchor)
        published = self.gh.pinned_data(fixtures.ISSUE)
        self.assertTrue(published.get(fixtures.KEY_AWAITING_HUMAN))
        self.assertEqual(published.get(fixtures.KEY_PARK_REASON), reason)
        self.assertIsNone(published.get(fixtures.KEY_PENDING_PUSH_SHA))
        self.assertEqual(self.gh.label_history, [])
        self.assertEqual(self.rebase_events(), [])


class RecoveryRealGitTest(
    _InterruptedRebaseCases, RecoveryGitFixtureMixin, unittest.TestCase,
):
    """The comparison the running route runs on is the one git computed."""


class VouchedReplayRealGitTest(
    _InterruptedRebaseCases, VouchedReplayGitFixtureMixin, unittest.TestCase,
):
    """The dormant route, over the replay a real `git rebase` leaves."""

    def test_unpushed_rebase_is_leased_onto_remote(self) -> None:
        # A replay is behind its own publication -- git counts the commit the
        # remote still carries as one this branch no longer has -- so the
        # counts alone would read the canonical pre-push recovery as an
        # out-of-band update and park it. The pair of heads the attempt
        # recorded is what sees past that.
        self.assertGreater(self.divergence_from_remote()[1], 0)

        super().test_unpushed_rebase_is_leased_onto_remote()

    def test_a_head_the_record_disowns_is_reset(self) -> None:
        stranded = self.strand_an_unrelated_head(forget_record=False)

        recovered = self.recover()

        # A rebuilt worktree, an operator's reset, and a branch pointed at
        # other work all leave this shape and all satisfy the anchor lease.
        # The record naming some other commit is what refuses it.
        self.assertTrue(recovered)
        self.assertEqual(self.push.leases, [])
        self.assertEqual(self._remote_head(), self.anchor)
        self.assertNotEqual(stranded, self.anchor)
        self._assert_parked(PARK_FAILED)

    def test_an_unrecorded_replay_uses_the_counts(self) -> None:
        self.strand_an_unrelated_head()

        recovered = self.recover()

        # A comment carrying no record of a replay is the one state the
        # ahead/behind counts still answer for, and a branch with commits the
        # remote does not have parks rather than force-pushing over them.
        self.assertTrue(recovered)
        self.assertEqual(self.push.leases, [])
        self._assert_parked(fixtures.PARK_PUSH_FAILED)

    def test_a_replay_a_finish_announced_is_reset(self) -> None:
        # The mark is written past a finish's notice and audit event, so it
        # stands only where a push had landed. The remote being back on the
        # anchor is that publication rolled back -- reissuing the push would
        # overwrite it and announce the same rebase a second time.
        _assert_announcement_parks(self, self.recovered)

    def test_a_mark_naming_another_head_is_reset_too(self) -> None:
        # A checkpoint something took apart says the route got that far and
        # nothing more; read as an absence it costs the same second notice.
        _assert_announcement_parks(self, self.anchor)

    def test_its_own_relabel_then_a_rollback_resets(self) -> None:
        # The finish pushed, announced, and relabelled to `validating` before
        # the write that clears the attempt, and the remote was rolled back
        # while the process was down. The relabel is this route's own last
        # step rather than a stage somebody moved the issue to, so what is
        # left is the announced publication the remote has lost.
        self.publish_recovered_head()
        self.announce_a_finish(self.recovered)
        self.roll_the_remote_back()

        recovered = self.recover(label=fixtures.VALIDATING)

        self.assertTrue(recovered)
        self.assertEqual(self.push.leases, [])
        self.assertEqual(self._remote_head(), self.anchor)
        self._assert_parked(fixtures.PARK_PUSH_FAILED)

    def test_a_debt_this_attempt_did_not_leave_parks(self) -> None:
        # Leased to this very anchor, so the refresh's freeze sets it aside as
        # this attempt's own work -- but it names a commit nothing here made.
        # Pushed past, the replay goes out and the gate's write replaces the
        # only record of a push somebody else is owed.
        state = self.gh.read_pinned_state(self.issue)
        _late_approval_state._approve(
            state, MISSING_COMMIT, self.anchor,
            _late_approval_reading.LateApprovalBasis.UNMEASURED,
        )
        self.gh.write_pinned_state(self.issue, state)

        recovered = self.recover()

        self.assertTrue(recovered)
        self.assertEqual(self.push.leases, [])
        self._assert_parked(PARK_FAILED)


def _assert_announcement_parks(case, announced: str) -> None:
    case.announce_a_finish(announced)

    recovered = case.recover()

    case.assertTrue(recovered)
    case.assertEqual(case.push.leases, [])
    case.assertEqual(case._remote_head(), case.anchor)
    case._assert_parked(fixtures.PARK_PUSH_FAILED)


if __name__ == "__main__":
    unittest.main()
