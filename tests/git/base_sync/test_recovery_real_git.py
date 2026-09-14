# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Crash recovery against a real repository left mid-rebase."""

from __future__ import annotations

import unittest

from orchestrator.git.base_sync import refresh, refresh_selection
from tests.git.base_sync import recovery_git_support as fixtures
from tests.git.base_sync.recovery_git_support import RecoveryGitFixtureMixin

PARK_FAILED = "auto_base_rebase_failed"

# A commit id no object in this repository answers to.
MISSING_COMMIT = "dead" * 10


class RecoveryRealGitTest(RecoveryGitFixtureMixin, unittest.TestCase):
    """The comparison the routing runs on is the one git itself computed."""

    def test_unpushed_rebase_is_leased_onto_remote(self) -> None:
        # A replay is behind its own publication -- git counts the commit the
        # remote still carries as one this branch no longer has -- so the
        # counts alone would read the canonical pre-push recovery as an
        # out-of-band update and park it.
        self.assertGreater(self.divergence_from_remote()[1], 0)

        recovered = self.recover()

        # The pair of heads the attempt recorded is what sees past that: the
        # remote is still on the anchor and the checkout is the replay this
        # attempt wrote down, so the interrupted push is reissued.
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
        self._assert_announcement_parks(self.recovered)

    def test_a_mark_naming_another_head_is_reset_too(self) -> None:
        # A checkpoint something took apart says the route got that far and
        # nothing more; read as an absence it costs the same second notice.
        self._assert_announcement_parks(self.anchor)

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

    def test_an_unreadable_checkout_is_parked(self) -> None:
        # The branch names a commit this store does not hold, so the refresh
        # cannot count the lag against base -- and stopping there would leave
        # the anchor for a recovery no tick reaches, under a dispatcher that
        # holds the handler back while it stands. The checkout the attempt
        # left cannot be compared against anything, so it is put back on the
        # anchor and a human is asked.
        branch_ref = self.work / ".git" / "refs" / "heads" / fixtures.BRANCH
        branch_ref.write_text(f"{MISSING_COMMIT}\n")

        refresh._sync_worktree_with_base(
            self.gh, self.spec, self.work, fixtures.ISSUE,
        )

        self.assertEqual(self.push.leases, [])
        self._assert_parked(fixtures.PARK_PUSH_FAILED)
        self.assertFalse(refresh_selection._recovery_holds_dispatch(
            self.issue, fixtures.LABEL,
            self.gh.read_pinned_state(self.issue), self.work,
        ))

    def _assert_announcement_parks(self, announced: str) -> None:
        self.announce_a_finish(announced)

        recovered = self.recover()

        self.assertTrue(recovered)
        self.assertEqual(self.push.leases, [])
        self.assertEqual(self._remote_head(), self.anchor)
        self._assert_parked(fixtures.PARK_PUSH_FAILED)

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


if __name__ == "__main__":
    unittest.main()
