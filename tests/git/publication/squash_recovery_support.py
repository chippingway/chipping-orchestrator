# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The crash boundaries one squash-on-approval can be interrupted at.

A squash is a run of effects: the record of what it is about to do, the local
rewrite, the gate's own approval, the leased push, and the receipt that
accounts for it. A process can die between any two of them, and each helper
here stops one run at exactly one seam and leaves the world in the state that
crash really leaves -- the pinned comment as far as the write before it, the
branch as far as the reset and the commit, and the pull request as far as the
push.

`_next_tick` is the other half. A crash ends a process, so what comes back
reads the pinned comment afresh rather than carrying whatever the dead tick
had staged -- which is exactly the difference between a record that was made
durable and one that was only about to be.
"""
from __future__ import annotations

from unittest import mock

from orchestrator.git.publication import models as _models, rewrite as _rewrite
from orchestrator.workflow.late_split import collapses as _collapses
from orchestrator.workflow.stages.implementing import (
    late_records as _late_records,
)
from tests.git.publication import (
    squash_crash_doubles as _squash_crashes,
    squash_git_support as squash_support,
    squash_race_doubles as _squash_races,
)
from tests.git.publication.squash_gate_support import (
    PublicationSeed,
    _squash_gate,
)

# The git verbs and flags these fixtures spell more than a handful of times.
CHECKOUT = "checkout"

COMMIT = "commit"

STAGE_ALL = "add"

RESET = "reset"

HARD = "--hard"

MESSAGE_FLAG = "-m"

# The fixtures' base branch, and the ref it is read through -- which is also
# what a hand reset throws a branch back onto.
BASE_BRANCH = "main"

REMOTE_BASE_REF = "origin/main"

# What the fixture's topic branch adds over the base: one line per commit,
# three commits, collapsed by the squash into one.
APPROVED_COMMITS = 3

# The same three commits with the middle one written with no message at all.
# A subject list built from these carries two entries and the branch is still
# three commits long.
BLANK_SUBJECT_HISTORY = ("fix: the first", "", "chore: the third")

UNDER_THE_CEILING = APPROVED_COMMITS + 1

# What the branch carries once a squash has collapsed it.
COLLAPSED_COMMITS = 1

MAX_ADDED_LINES = "MAX_ADDED_LINES"

# The switch that decides whether a NEW collapse is made, which is not the
# same question as whether a recorded one is finished.
SQUASH_ON_APPROVAL = "SQUASH_ON_APPROVAL"

# The switch that keeps a squash out of the size gate entirely, which is also
# what keeps the entry from proving the tree for itself.
DECOMPOSE = "DECOMPOSE"

# The seam a squash makes its commit through, which is the boundary between a
# branch nobody rewrote and one collapsed but never published.
SQUASH_COMMIT_HELPER = "_create_squash_commit"

# The hardened git call the reset runs through, and the reset itself: the
# boundary between the record of a rewrite and the rewrite.
HARDENED_GIT_HELPER = "_git_hardened"

# The record one collapse leaves, read back by a case that has to say whether
# a crash left it standing.
KEY_COLLAPSE_HEAD = _collapses.LATE_COLLAPSE_HEAD

KEY_COLLAPSE_BASE_SHA = _collapses.LATE_COLLAPSE_BASE_SHA

KEY_COLLAPSE_COUNT = _collapses.LATE_COLLAPSE_COUNT

# The receipt a landed gated push leaves, and the debt the gate records for a
# commit it approved ahead of that push.
KEY_RECEIPT_SHA = "implementing_published_sha"

KEY_APPROVED_SHA = "late_approved_sha"

LEASE = "force_with_lease"

# The three places a failed squash can leave the branch, as the outcome names
# them. A case about the notice a human gets asserts on this rather than on
# the sentence, since the sentence is the stage's to word and the reading is
# the squash owner's to take.
BRANCH_INTACT = _models.BRANCH_INTACT

BRANCH_COLLAPSED = _models.BRANCH_COLLAPSED

BRANCH_BURIED = _models.BRANCH_BURIED

BRANCH_UNKNOWN = _models.BRANCH_UNKNOWN

# A head somebody else pushed onto the pull request while this host was down.
MOVED_HEAD = "cafe1234" * 5

# A whole object id no repository in these fixtures holds, which is what a
# hand-edited or foreign record's head reads back as.
ABSENT_HEAD = "0123abcd" * 5


class _SquashTickMixin:
    """One squash run per tick, over a gate a case keeps across them."""

    def _gate_subject(self):
        """The gate this issue's squashes run under, kept across ticks."""
        return _squash_gate(self, PublicationSeed())

    def _next_tick(self, gate):
        """The gate a fresh process builds over the same issue and checkout.

        The pinned comment is re-read, so anything the dead tick had only
        staged is gone and anything it made durable is what the recovery has
        to work from.
        """
        return _late_records._gate(
            gate.gh,
            gate.spec,
            gate.issue,
            gate.gh.read_pinned_state(gate.issue),
            self.work,
        )

    def _squashes(self, squashed, **run_options):
        """One squash under a case's own gate, at a ceiling it passes."""
        return self._squash(
            publication=PublicationSeed(gate=squashed),
            **{MAX_ADDED_LINES: UNDER_THE_CEILING},
            **run_options,
        )

    def _publishes(self, gate):
        """A push that lands and moves the pull request onto what it sent."""
        return _squash_races._LandsOnTheRemote(self, gate)

    def _pinned(self, gate) -> dict:
        """The pinned comment as the client durably holds it."""
        return dict(gate.gh.pinned_data(gate.issue.number))

    def _assert_branch_carries(self, commits: int) -> None:
        """How many commits the topic branch stands on over its base."""
        self.assertEqual(len(self._commits_on_branch()), commits)

    def _rebuilds_with_a_blank_subject(self) -> None:
        """Rebuild the topic branch with one commit written with no message.

        Real and ordinary -- `git commit --allow-empty-message` makes one --
        and the shape a count taken from the SUBJECTS is short by, since a
        commit with no subject contributes none.
        """
        squash_support.run_git(
            RESET, HARD, REMOTE_BASE_REF, cwd=self.work,
        )
        for index, subject in enumerate(BLANK_SUBJECT_HISTORY, start=1):
            (self.work / f"b{index}.txt").write_text(f"{index}\n")
            squash_support.run_git(STAGE_ALL, ".", cwd=self.work)
            squash_support.run_git(
                COMMIT, "--allow-empty-message", MESSAGE_FLAG, subject,
                cwd=self.work, env_extra=squash_support.author_env(),
            )


class _SquashHistoryMixin:
    """The shapes this branch's own history can take between two ticks."""

    def _discards_the_branch(self) -> None:
        """Throw the branch back onto its base, the way a hand reset does."""
        squash_support.run_git(
            RESET, HARD, REMOTE_BASE_REF, cwd=self.work,
        )


class _SquashCrashMixin:
    """What can happen to a branch between the tick that squashed it and the
    next one: the seams a squash-on-approval can be stopped part way through
    at, and the base moving under whatever it left behind.
    """

    def _advances_the_base(self) -> None:
        """Put a commit on the base branch and fetch it, for real.

        What every ordinary week does to a long-lived branch, and what the
        pre-tick refresh answers by rebasing. A collapse in flight is exactly
        what may not be rebased under.
        """
        squash_support.run_git(CHECKOUT, BASE_BRANCH, cwd=self.work)
        (self.work / "base-moved.txt").write_text("the base advanced\n")
        squash_support.run_git(STAGE_ALL, ".", cwd=self.work)
        squash_support.run_git(
            COMMIT, MESSAGE_FLAG, "chore: advance the base",
            cwd=self.work, env_extra=squash_support.author_env(),
        )
        squash_support.run_git("push", "origin", BASE_BRANCH, cwd=self.work)
        squash_support.run_git(CHECKOUT, self.branch, cwd=self.work)
        squash_support.run_git("fetch", "origin", cwd=self.work)

    def _crashes_after_the_commit(self, gate) -> None:
        """Collapse the branch, then die before anything is measured."""
        with mock.patch.object(
            _rewrite, SQUASH_COMMIT_HELPER, _squash_crashes._CrashesAfterTheCommit(),
        ), self.assertRaises(_squash_crashes._Interrupted):
            self._squashes(gate)

    def _crashes_before_the_commit(self, gate) -> None:
        """Rewind the branch onto its base and die before committing it."""
        with mock.patch.object(
            _rewrite, SQUASH_COMMIT_HELPER, _squash_crashes._CrashesBeforeTheCommit(),
        ), self.assertRaises(_squash_crashes._Interrupted):
            self._squashes(gate)

    def _crashes_before_the_reset(self, gate) -> None:
        """Record the collapse, then die before the branch is rewritten."""
        with mock.patch.object(
            _rewrite.commands, HARDENED_GIT_HELPER, _squash_crashes._CrashesBeforeTheReset(),
        ), self.assertRaises(_squash_crashes._Interrupted):
            self._squashes(gate)

    def _crashes_before_the_push(self, gate) -> None:
        """Measure and approve the collapse, then die before it goes out."""
        with self.assertRaises(_squash_crashes._Interrupted):
            self._squashes(gate, push_result=_squash_crashes._dies_before_the_push)

    def _crashes_after_the_push(self, gate) -> None:
        """Land the push, then die before the receipt that accounts for it."""
        crash = _squash_crashes._CrashesAfterThePush(self, gate)
        with crash.held(), self.assertRaises(_squash_crashes._Interrupted):
            self._squashes(gate, push_result=crash.pushes)


class _SquashForgeryMixin:
    """What a hand, or another history, can put in front of the recovery.

    Neither of these is a state this workflow produces. They are the shapes a
    record's own claims read as true over -- the same tree on another base,
    and a base the branch was never built on -- which is what makes them the
    cases a proof has to be more than a comparison to refuse.
    """

    def _forges_over_the_base(self) -> str:
        """Re-parent this branch's tree onto the base it did not collapse.

        The sharpest thing a tree-only proof would let through: the same tree
        as the recorded head, on a base that has since advanced. Published, it
        takes whatever that base added straight back off the pull request --
        under an exemption a human granted a different change.
        """
        carried = squash_support.run_git(
            "rev-parse", "--verify", "HEAD^{tree}", cwd=self.work,
        ).strip()
        self._advances_the_base()
        forged = squash_support.run_git(
            "commit-tree", carried, "-p", REMOTE_BASE_REF,
            MESSAGE_FLAG, "forged: the same tree over a newer base",
            cwd=self.work, env_extra=squash_support.author_env(),
        ).strip()
        squash_support.run_git(RESET, HARD, forged, cwd=self.work)
        return forged

    def _unrelated_history(self) -> str:
        """A commit on a history this branch was never built on."""
        squash_support.run_git(
            CHECKOUT, "--orphan", "unrelated", cwd=self.work,
        )
        squash_support.run_git("rm", "-rf", "--cached", ".", cwd=self.work)
        (self.work / "unrelated.txt").write_text("elsewhere\n")
        squash_support.run_git(STAGE_ALL, "unrelated.txt", cwd=self.work)
        squash_support.run_git(
            COMMIT, MESSAGE_FLAG, "chore: an unrelated root",
            cwd=self.work, env_extra=squash_support.author_env(),
        )
        orphan = squash_support.run_git(
            "rev-parse", "HEAD", cwd=self.work,
        ).strip()
        squash_support.run_git(CHECKOUT, "-f", self.branch, cwd=self.work)
        squash_support.run_git(
            "branch", "-D", "unrelated", cwd=self.work,
        )
        return orphan


class _SquashWorldMixin(_SquashHistoryMixin, _SquashForgeryMixin):
    """Everything a case can put in front of a tick: the shapes this branch's
    own history takes, and the ones only a hand or another history produces.
    """


class SquashRecoveryMixin(
    _SquashTickMixin, _SquashCrashMixin, _SquashWorldMixin,
):
    """Compose the per-tick squash runs and the crashes that interrupt one."""
