# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A real replay of the branch, for the crash recovery to finish.

The repository ``recovery_git_support`` builds, with the interrupted rebase a
real `git rebase` onto an advanced base -- the shape the divergence counts read
as an out-of-band update -- and the moves a case makes to leave the branch and
the pinned record the way a crash, a rollback, or a hand edit leaves them, and
`recover` hands the recovery the attempt record read off the comment.
"""
from __future__ import annotations

from orchestrator.git.base_sync import (
    attempt_records as _attempt_records,
    recovery,
)
from tests.git.base_sync import recovery_git_support as fixtures

KEY_PENDING_REWRITE_SHA = "pending_auto_base_rebase_rewrite_sha"

KEY_PENDING_REWRITE_PR = "pending_auto_base_rebase_rewrite_pr"

KEY_PENDING_REWRITE_STAGE = "pending_auto_base_rebase_rewrite_stage"

KEY_PENDING_ANNOUNCED_SHA = "pending_auto_base_rebase_announced_sha"

# The record as one group, because the window a case seeds by dropping it is
# the one where the attempt reached none of it.
_REWRITE_RECORD_KEYS = (
    KEY_PENDING_REWRITE_SHA,
    KEY_PENDING_REWRITE_PR,
    KEY_PENDING_REWRITE_STAGE,
)

# The path a commit nothing in this attempt made writes, so a case reads a
# branch somebody else left by name rather than by counting.
UNRELATED_FILE = "unrelated.py"


class VouchedReplayGitFixtureMixin(fixtures.RecoveryGitFixtureMixin):
    """A real replay of the branch, recovered on the record the attempt left.

    `recover` hands the recovery the attempt record read off the comment, the
    way the eligibility gate does.
    """

    replays = True

    def recover(self, label: str = fixtures.LABEL) -> bool:
        """Run the recovery over the issue as it now reads."""
        state = self.gh.read_pinned_state(self.issue)
        return recovery._recover_pending_auto_base_rebase(
            self.gh,
            self.spec,
            self.issue,
            state,
            self.work,
            pr_number=fixtures.PR_NUMBER,
            label=label,
            pending_pre_rebase_sha=self.anchor,
            pending_rewrite=_attempt_records._pending_rewrite(state),
        )

    def strand_an_unrelated_head(self, *, forget_record: bool = True) -> str:
        """Leave the branch on a divergent commit this attempt never made.

        A worktree rebuilt from elsewhere, an operator's reset, a branch
        pointed at somebody else's work: from the outside every one of them
        looks exactly like a replay -- clean tree, remote still on the anchor,
        histories diverged -- and the anchor lease they would be pushed under
        is satisfied. Only the record of what the attempt produced tells them
        apart, so this leaves the branch here and `forget_record` says
        whether it goes too -- kept, the record disowns the checkout by
        naming another commit; dropped, nothing on the comment says anything
        about it at all.
        """
        fixtures.run_git(
            fixtures.CHECKOUT, "--detach", f"{self.anchor}^", cwd=self.work,
        )
        stranded = fixtures.commit(
            self.work, UNRELATED_FILE, "unrelated\n", "feat: somebody else",
        )
        fixtures.run_git(
            fixtures.CHECKOUT, "-B", fixtures.BRANCH, stranded, cwd=self.work,
        )
        if forget_record:
            self.forget_the_rewrite_record()
        return stranded

    def roll_back_to_the_anchor(self) -> None:
        """Put the branch back where the attempt found it, records intact.

        What a reset that landed and whose park write did not leaves, and what
        an operator's own `git reset --hard` leaves: HEAD exactly on the
        anchor, with the record of the replay and the permission granted for
        it still standing on the comment.
        """
        fixtures.run_git("reset", "--hard", self.anchor, cwd=self.work)

    def roll_the_remote_back(self) -> None:
        """Put the pull request's branch back on the anchor, out of band.

        Forced, because the replay a finish published is not an ancestor of
        the commit it replaced. The tracking ref is rewound with it, so the
        recovery's own fetch is what finds the rollback.
        """
        fixtures.run_git(
            fixtures.PUSH, "--force", fixtures.REMOTE_NAME,
            f"{self.anchor}:{fixtures.BRANCH_REF}",
            cwd=self.work,
        )
        self._rewind_tracking_ref()

    def announce_a_finish(self, announced: str) -> None:
        """Leave the checkpoint a finish writes past its notice and event.

        Written between the two and the relabel, so a comment carrying one
        says the push had landed and the pull request had already been told.
        """
        state = self.gh.read_pinned_state(self.issue)
        state.set(KEY_PENDING_ANNOUNCED_SHA, announced)
        self.gh.write_pinned_state(self.issue, state)

    def forget_the_rewrite_record(self, *, head_only: bool = False) -> None:
        """Drop a replay's head alone, or the whole record of its attempt.

        Keeping the terms seeds the crash between git returning and its head
        being recorded. Dropping all members seeds an anchor-only comment.
        """
        keys = (KEY_PENDING_REWRITE_SHA,) if head_only else _REWRITE_RECORD_KEYS
        state = self.gh.read_pinned_state(self.issue)
        for key in keys:
            state.set(key, None)
        self.gh.write_pinned_state(self.issue, state)


    def divergence_from_remote(self) -> tuple[int, int]:
        """Ahead and behind as git counts this branch against the tracking ref.

        Read before the recovery runs, since the tracking ref still names the
        commit the crash left the remote on. What a case uses it for is to say
        out loud that a replayed branch is behind its own publication -- the
        fact the SHA comparison exists to see past.
        """
        counted = fixtures.run_git(
            "rev-list", "--left-right", "--count",
            f"refs/remotes/{fixtures.REMOTE_NAME}/{fixtures.BRANCH}"
            f"...{fixtures.HEAD_REF}",
            cwd=self.work,
        ).split()
        return int(counted[1]), int(counted[0])
