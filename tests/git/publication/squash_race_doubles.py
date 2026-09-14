# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Concurrent checkout and publication changes during squash recovery."""
from __future__ import annotations

from unittest import mock

from tests.git.publication import squash_crash_doubles as _squash_crashes, squash_git_support as squash_support
from tests.git.publication.squash_gate_support import (
    SQUASH_PR_NUMBER,
)

# What something else writes into the worktree while the collapse is being
# recorded, which a `--soft` reset and the commit behind it would carry.
RACED_FILE = "raced.txt"


class _RacesTheRecord:
    """A worktree something writes to while the collapse is being recorded.

    The one window every other reading in the squash is taken outside of: the
    entry proved the tree and the head, and the record that follows is a
    REQUEST, so the worktree is writable for the whole of it. What arrives
    there is committed by the reset and the commit behind it, since a squash
    takes the index rather than the plan.
    """

    def __init__(self, fixture, gate, *, commits: bool = False) -> None:
        self._fixture = fixture
        self._commits = commits
        self._writes = gate.gh.write_pinned_state
        self._gate = gate

    def __call__(self, issue, state):
        written = self._writes(issue, state)
        (self._fixture.work / RACED_FILE).write_text("staged mid-write\n")
        squash_support.run_git("add", ".", cwd=self._fixture.work)
        if self._commits:
            squash_support.run_git(
                "commit", "-m", "stray: not the plan",
                cwd=self._fixture.work,
                env_extra=squash_support.author_env(),
            )
        return written

    def held(self):
        """Write to the worktree on every durable write of one run."""
        return mock.patch.object(self._gate.gh, _squash_crashes.PINNED_WRITE, self)


class _CommitsWhileThePullRequestIsRead:
    """A commit that lands while the publication is being read.

    The other window a request opens, and the one the road with no push at all
    is left holding: the entry's pull-request read is a request like any
    other, so the worktree is writable for the whole of it. What arrives there
    is a commit no reviewer approved, on a checkout this road reports as
    standing on the head it planned over.
    """

    def __init__(self, fixture, gate) -> None:
        self.read = False
        self._fixture = fixture
        self._gate = gate
        self._reads = gate.gh.get_pr

    def __call__(self, number):
        # Once, and before the answer: a case is about the window, not about
        # every reading a tick happens to take through the same seam.
        if not self.read:
            self.read = True
            self._fixture._commits_over(2)
        return self._reads(number)

    def held(self):
        """Commit over the worktree on this run's first publication read."""
        return mock.patch.object(self._gate.gh, "get_pr", self)


class _LandsOnTheRemote:
    """A push that succeeds and moves the pull request onto what it sent."""

    def __init__(self, fixture, gate) -> None:
        self._fixture = fixture
        self._gate = gate

    def __call__(self, *_argv, **options) -> bool:
        self._gate.gh.get_pr(SQUASH_PR_NUMBER).head.sha = (
            options.get(_squash_crashes.REVISION) or self._fixture._head_sha()
        )
        return True
