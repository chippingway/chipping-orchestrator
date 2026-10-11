# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether a landed head still stands on the base tip its replay was made onto, read by identity on real git.

A pull request branch one base advance behind, rebased by the auto-rebase's own
hardened rebase, and the base moved every way it can move afterwards: advanced
past the head, moved on the remote alone, rewound under the head, or left
unread on either side. A reading nobody could take never hides movement the
other reading took, and an attempt that recorded no tip proves nothing.
"""
from __future__ import annotations

import shutil
import unittest
from unittest.mock import MagicMock, patch

from orchestrator.git import branch_transport
from orchestrator.git.base_sync import rewrite_facts
from orchestrator.git.base_sync.rewrite_handoffs import _BaseStanding
from tests.git.base_sync.rewrite_git_support import BASE_BRANCH, ORIGIN, RewriteRepository, rewrite_repository

# The clone's remote-tracking base ref, which the worktree shares.
_BASE_REF = f"refs/remotes/{ORIGIN}/{BASE_BRANCH}"

_UPDATE_REF = "update-ref"


def _advances(repository: RewriteRepository) -> None:
    """Land a commit on the base and fetch it: the base advanced past the replay."""
    repository.advance_base()


def _rewinds(repository: RewriteRepository) -> None:
    """Rewind the local base ref under the replay, which the head is then ahead of rather than behind."""
    repository.git(_UPDATE_REF, _BASE_REF, f"{_BASE_REF}~1", cwd=repository.clone)


def _forgets(repository: RewriteRepository) -> None:
    """Delete the local base ref, so nobody can count the head against it."""
    repository.git(_UPDATE_REF, "-d", _BASE_REF, cwd=repository.clone)


def _moves_the_remote(repository: RewriteRepository) -> None:
    """Move the remote's base to a commit nothing here fetched."""
    based = f"refs/heads/{BASE_BRANCH}"
    tip = repository.head_of(based, repository.remote)
    tree = f"{tip}^{{tree}}"
    moved = repository.git("commit-tree", tree, "-p", tip, "-m", "elsewhere", cwd=repository.remote)
    repository.git(_UPDATE_REF, based, moved, cwd=repository.remote)


def _silences_the_remote(repository: RewriteRepository) -> None:
    """Take the remote away, so nobody can read where its base is."""
    shutil.move(repository.remote, repository.root / "gone.git")


# What happens to the base after the rebase, and where the head is read as
# standing against the tip its replay was made onto.
_BASE_SINCE_REPLAYED = (
    ((), _BaseStanding.STANDING),
    ((_advances,), _BaseStanding.MOVED),
    ((_moves_the_remote,), _BaseStanding.MOVED),
    ((_rewinds,), _BaseStanding.DROPPED),
    ((_forgets,), _BaseStanding.UNREAD),
    ((_silences_the_remote,), _BaseStanding.UNREAD),
    ((_forgets, _moves_the_remote), _BaseStanding.MOVED),
    ((_rewinds, _silences_the_remote), _BaseStanding.DROPPED),
)


class BaseStandingTest(unittest.TestCase):
    """The base a landed head is counted against has to BE the tip the rebase used, and the remote's base too."""

    def test_the_base_is_held_to_the_replayed_tip(self) -> None:
        for moves, standing in _BASE_SINCE_REPLAYED:
            with self.subTest(moves=[move.__name__ for move in moves]):
                repository = rewrite_repository(self)
                candidate = repository.prepared()
                for move in moves:
                    move(repository)

                self.assertEqual(_standing(repository, candidate, candidate.checkout.base.tip), standing)

    def test_no_recorded_tip_proves_nothing(self) -> None:
        # A legacy attempt names no tip, and nothing is read for it.
        repository = rewrite_repository(self)
        candidate = repository.prepared()
        reads = MagicMock()

        with patch.object(branch_transport, "_remote_branch_read", reads):
            standing = _standing(repository, candidate, "")

        self.assertEqual((standing, reads.call_count), (_BaseStanding.UNPROVEN, 0))



def _standing(repository: RewriteRepository, candidate, onto: str) -> _BaseStanding:
    """Where `candidate`'s head stands against `onto` in `repository`'s worktree."""
    return rewrite_facts._standing_on_the_remote_base(repository.spec, repository.worktree, candidate, onto)


if __name__ == "__main__":
    unittest.main()
