# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Crashes at the reset, commit, push, and receipt boundaries of a squash."""
from __future__ import annotations

from unittest import mock

from orchestrator.git.publication import rewrite as _rewrite
from tests.git.publication.squash_gate_support import (
    SQUASH_PR_NUMBER,
)

# The client call every durable record of a tick goes through, which is what a
# case standing in for a dead process replaces.
PINNED_WRITE = "write_pinned_state"

SOFT_RESET = ("reset", "--soft")

# The keywords a gated push is named and pinned by.
REVISION = "revision"


class _Interrupted(RuntimeError):
    """The process dying at the seam a case is about."""


class _CrashesAfterTheCommit:
    """A squash that collapses the branch and never reaches the gate.

    The narrowest boundary the rewrite has, and the one nothing durable
    survives: the record of the collapse is on the comment, the branch is one
    commit, and no approval, no permission, and no receipt names it.
    """

    def __init__(self) -> None:
        # Bound before the seam is replaced, so making the commit does not
        # re-enter the double standing in for it.
        self._commits = _rewrite._create_squash_commit

    def __call__(self, worktree, message):
        self._commits(worktree, message)
        raise _Interrupted("died after the squash commit")


class _CrashesBeforeTheCommit:
    """A branch rewound onto its base and never committed again.

    The seam between the two halves of the rewrite, and the one that leaves
    neither: HEAD is the base, every collapsed change is staged in the index,
    and the record still says a squash is outstanding.
    """

    def __call__(self, worktree, message):
        raise _Interrupted("died between the reset and the commit")


class _CrashesBeforeTheReset:
    """A squash whose record is durable and whose rewrite never ran.

    Hung on the hardened git call rather than on a call count, because the
    soft reset is the first destructive step and every other hardened call the
    run makes is one this crash has to leave alone.
    """

    def __init__(self) -> None:
        self._runs = _rewrite.commands._git_hardened

    def __call__(self, *argv, **options):
        if argv[:2] == SOFT_RESET:
            raise _Interrupted("died before the reset")
        return self._runs(*argv, **options)


class _CrashesAfterThePush:
    """A push that lands on the pull request and a receipt that never does.

    The far side of the window, and the one no local note can tell from the
    near side: the remote carries the rewrite and the comment does not say so.
    """

    def __init__(self, fixture, gate) -> None:
        self.landed = False
        self._fixture = fixture
        self._gate = gate
        self._writes = gate.gh.write_pinned_state

    def pushes(self, *_argv, **options) -> bool:
        """Move the pull request onto the commit this push was named for."""
        self._gate.gh.get_pr(SQUASH_PR_NUMBER).head.sha = (
            options.get(REVISION) or self._fixture._head_sha()
        )
        self.landed = True
        return True

    def writes(self, issue, state):
        """Take every write up to the receipt the landed push earns."""
        if self.landed:
            raise _Interrupted("died before the receipt")
        return self._writes(issue, state)

    def held(self):
        """Refuse the receipt this run's push earns, for its duration."""
        return mock.patch.object(self._gate.gh, PINNED_WRITE, self.writes)


def _dies_before_the_push(*_argv, **_options):
    """A process that ends between the gate's approval and the request."""
    raise _Interrupted("died before the push")
