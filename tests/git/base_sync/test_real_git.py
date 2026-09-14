# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.late_split import exemption_reading as _exemption_reading
from orchestrator.workflow.stages.implementing import (
    candidate_recovery as _candidate_recovery,
    checkout_recovery as _checkout_recovery,
    disposition as _disposition,
)
from tests.git.base_sync.real_git_test_support import (
    _RefreshBaseRealGitFixture,
)

EXTRA_FILENAME = "extra.txt"
FEATURE_SUBJECT = "feat: add feature"
SCRATCH_FILENAME = "scratch.py"
# The issue the fixture builds its worktree for.
FIXTURE_ISSUE = 7
MOVED_CHECKOUT_PARK = "late_candidate_moved"
TIMEOUT_PARK = "agent_timeout"
STUCK = "stuck"
BASE_REF = "origin/main"
# The seam past the recovery's own proofs: what it does with a commit it
# accepted, stubbed so this fixture's branch is not pushed to its own remote.
PUBLISH_SEAM = "_publish_committed_work"
WORKTREES_DIR_ATTR = "WORKTREES_DIR"
WORKTREES_DIR_NAME = "worktrees"


class RefreshPrePrRealGitTest(_RefreshBaseRealGitFixture, unittest.TestCase):
    def test_clean_advance_rebases_worktree(self) -> None:
        self._advance_base(conflicting=False)
        head_before = self._wt_head()
        self._refresh()
        head_after = self._wt_head()
        self.assertNotEqual(head_before, head_after)
        # The base file landed in the worktree's tree.
        self.assertTrue((self._wt / EXTRA_FILENAME).exists())
        self.assertEqual(
            self._git("log", "-1", "--format=%s", cwd=self._wt).strip(),
            FEATURE_SUBJECT,
        )
        self.assertTrue(self._is_clean())

    def test_no_op_when_already_up_to_date(self) -> None:
        head_before = self._wt_head()
        self._refresh()
        self.assertEqual(head_before, self._wt_head())
        self.assertTrue(self._is_clean())

    def test_conflict_aborts_leaving_worktree_clean(self) -> None:
        self._advance_base(conflicting=True)
        head_before = self._wt_head()
        self._refresh()
        # HEAD did NOT move (rebase aborted) and worktree is clean again --
        # the conflict surfaces later via the resolving_conflict stage.
        self.assertEqual(head_before, self._wt_head())
        self.assertTrue(self._is_clean())

    def test_dirty_worktree_skips_without_changes(self) -> None:
        self._advance_base(conflicting=False)
        # Plant an uncommitted edit in the worktree -- mirrors a mid-flight
        # agent edit. The base rebase must NOT run.
        (self._wt / SCRATCH_FILENAME).write_text("scratch\n")
        head_before = self._wt_head()
        self._refresh()
        self.assertEqual(head_before, self._wt_head())
        # Untracked file still present, nothing else was added.
        self.assertTrue((self._wt / SCRATCH_FILENAME).exists())
        self.assertFalse((self._wt / EXTRA_FILENAME).exists())


class RefreshLateHandoffRealGitTest(
    _RefreshBaseRealGitFixture, unittest.TestCase,
):
    """The two late records the refresh runs ahead of, over a real advance.

    Both name a commit that a LATER tick has to find in the checkout, and the
    refresh is the first thing that touches a worktree each tick. A rebase in
    between rewrites the branch the record is evidence about, and neither
    reader substitutes what it finds instead: the gate measures the rewrite as
    a fresh candidate, and the park that was waiting for a restored checkout
    goes on waiting for a commit that is no longer reachable from the branch.
    """

    def test_an_accepted_commit_survives_an_advance(self) -> None:
        # The window a `single` verdict opens: the generation is retired with
        # the decision, so the exemption is the only thing left saying this
        # branch carries work a human already adjudicated, and it has to be
        # true of the checkout the NEXT tick publishes from.
        accepted = self._wt_head()
        self._gh.seed_state(FIXTURE_ISSUE, late_exempt_sha=accepted)
        self._advance_base(conflicting=False)

        self._refresh()

        self.assertEqual(accepted, self._wt_head())
        self.assertFalse((self._wt / EXTRA_FILENAME).exists())
        self.assertTrue(
            _exemption_reading.is_exempt(self._pinned(), self._wt_head()),
            "the next tick's gate would measure this candidate again",
        )

    def test_a_stale_exemption_does_not_freeze(self) -> None:
        # The other half, and the reason the freeze reads the checkout rather
        # than the record: an exemption is never cleared, so freezing on its
        # presence would take every issue that ever earned a verdict out of
        # the base refresh for good. The developer committed after the verdict,
        # what publishes is that new work, and the gate measures it as the
        # fresh candidate it is -- with or without this rebase.
        stale = self._git("rev-parse", "HEAD~1", cwd=self._wt).strip()
        self._gh.seed_state(FIXTURE_ISSUE, late_exempt_sha=stale)
        self._advance_base(conflicting=False)
        head_before = self._wt_head()

        self._refresh()

        self.assertNotEqual(head_before, self._wt_head())
        self.assertTrue((self._wt / EXTRA_FILENAME).exists())
        self.assertFalse(_exemption_reading.is_exempt(self._pinned(), self._wt_head()))

    def test_a_restored_checkout_survives_an_advance(self) -> None:
        # The park whose remedy is an operator's `git checkout` rather than a
        # reply. They put the worktree back on the approved commit between two
        # ticks, and the refresh is what the next tick reaches first: rebased
        # here, the head is off that commit again and the recovery that would
        # have published it never fires.
        approved = self._wt_head()
        self._gh.seed_state(
            FIXTURE_ISSUE,
            awaiting_human=True,
            park_reason=MOVED_CHECKOUT_PARK,
            late_approved_sha=approved,
        )
        self._advance_base(conflicting=False)

        self._refresh()

        self.assertEqual(approved, self._wt_head())
        self.assertEqual(
            _checkout_recovery._restored_checkout(
                self._gh.get_issue(FIXTURE_ISSUE), self._pinned(), self._wt,
            ),
            approved,
            "the next tick's recovery would leave the park where it is",
        )

    def _pinned(self):
        """This issue's pinned state, as the next tick would read it."""
        return self._gh.read_pinned_state(self._gh.get_issue(FIXTURE_ISSUE))


class RefreshTimeoutParkRealGitTest(
    _RefreshBaseRealGitFixture, unittest.TestCase,
):
    """The timeout park over a real base advance, and what recovers it.

    The one park here whose watermark names a commit that does not exist yet:
    `pre_implement_sha` is the tip the killed run STARTED at, and everything
    the recovery does with it is a comparison against what the checkout has
    become since. On the commonest shape of the park -- a run killed before it
    committed anything -- the branch carries nothing of its own, so a base
    that advances fast-forwards the checkout straight onto the new tip and the
    comparison reports a difference no developer wrote.
    """

    def setUp(self) -> None:
        super().setUp()
        # A spawn's checkout: standing at base, carrying nothing of its own,
        # which is what a run killed before its first commit leaves behind.
        self._git("reset", "--hard", BASE_REF, cwd=self._wt)
        self._pre_sha = self._wt_head()
        self._gh.seed_state(
            FIXTURE_ISSUE,
            awaiting_human=True,
            park_reason=TIMEOUT_PARK,
            pre_implement_sha=self._pre_sha,
            dev_agent="codex",
            dev_session_id="sess-x",
        )

    def test_a_base_advance_leaves_the_park_intact(self) -> None:
        # The whole tick, in the order it runs: the refresh reaches the
        # worktree first, and the recovery reads what it left. Frozen, the
        # head is still the watermark, so the recovery says what is true --
        # the timeout produced no commit -- and leaves the park for a human.
        self._advance_base(conflicting=False)

        self._refresh()

        self.assertEqual(self._pre_sha, self._wt_head())
        self.assertFalse((self._wt / EXTRA_FILENAME).exists())
        self.assertEqual(self._recover(), STUCK)
        self._assert_nothing_published()

    def test_a_fast_forwarded_head_is_not_a_commit(self) -> None:
        # The freeze is this orchestrator's refresh and nothing else, so the
        # rebase still happens where an operator, another process, or a park
        # taken before the freeze existed performs it. The head has moved and
        # the base is what it moved to; published on the difference alone,
        # this issue gets a branch and a pull request with no diff in them.
        self._advance_base(conflicting=False)
        self._git("rebase", BASE_REF, cwd=self._wt)
        self.assertNotEqual(self._pre_sha, self._wt_head())

        self.assertEqual(self._recover(), STUCK)
        self._assert_nothing_published()

    def test_a_late_commit_still_recovers(self) -> None:
        # And the proof is not a wall: the shape the recovery exists for --
        # a descendant the timeout cleanup raced finishing a commit after the
        # park was written -- still passes both readings, base advance or no.
        # Read at the seam rather than through the publication behind it,
        # which would push this fixture's branch to its own remote.
        self._advance_base(conflicting=False)
        (self._wt / SCRATCH_FILENAME).write_text("late work\n")
        self._git("add", ".", cwd=self._wt)
        self._git(
            "commit", "-m", "feat: late landing", cwd=self._wt,
            env_extra=self._author_env,
        )

        with patch.object(_candidate_recovery, PUBLISH_SEAM) as published:
            self.assertEqual(self._recover(), "pushed")
            published.assert_called_once()

    def _recover(self) -> str:
        """One next-tick recovery attempt, against the real checkout.

        The worktree root is patched for the same reason `_refresh` patches
        it: the recovery resolves the checkout from `WORKTREES_DIR`, and
        without it every attempt here would answer "stuck" for the one reason
        the test is not about -- a directory that is not there.
        """
        with patch.object(
            config, WORKTREES_DIR_ATTR, self._tmpdir / WORKTREES_DIR_NAME,
        ):
            return _disposition._try_recover_implementing_timeout_park(
                self._gh, self._spec,
                self._gh.get_issue(FIXTURE_ISSUE), self._pinned(),
            )

    def _assert_nothing_published(self) -> None:
        """No branch, no pull request, and the park still on the issue."""
        self.assertEqual(self._gh.opened_prs, [])
        self.assertEqual(self._gh.posted_comments, [])
        pinned = self._pinned()
        self.assertTrue(pinned.get("awaiting_human"))
        self.assertEqual(pinned.get("park_reason"), TIMEOUT_PARK)

    def _pinned(self):
        return self._gh.read_pinned_state(self._gh.get_issue(FIXTURE_ISSUE))


if __name__ == "__main__":
    unittest.main()
