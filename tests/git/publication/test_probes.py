# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The divergence reading the publication path proves a branch against."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.git import commands
from orchestrator.git.publication import probes
from tests.git.publication.publication_helpers import (
    HARDENED_HELPER,
    WORKTREE,
    _GitRecorder,
    _spec,
)

BRANCH = "orchestrator/issue-5"

REV_PARSE = "rev-parse"

# The tip the fetched ref resolves to, and the commit something moves it to
# while the reading is being taken.
TIP = "1ec04e5e" * 5
MOVED_TIP = "cafe1234" * 5

# The local commit a caller about to publish freezes and counts, and the
# argument that keeps a revision from being read as a path.
FROZEN = "5eed1ced" * 5
PATH_SEPARATOR = "--"

# Every reading that did not happen, which is what no caller may act on.
UNREADABLE = probes._BranchDivergence()


class _ResolvesThenCounts:
    """A git double answering the two commands one divergence reading makes.

    The ref resolve first, then the comparison, so a case can say what each
    one answered. `tips` may name MORE than one: a ref something moves while
    the reading is being taken answers the next resolve differently, which is
    what a second one would have got.
    """

    def __init__(self, *tips: str, counts: str = "0\t0\n") -> None:
        self.calls: list[tuple] = []
        self._tips = list(tips)
        self._counts = counts

    def __call__(self, *args, cwd):
        self.calls.append((args, cwd))
        if args[0] != REV_PARSE:
            return _git_answer(self._counts)
        answered = self._tips[0]
        if len(self._tips) > 1:
            self._tips.pop(0)
        return _git_answer(answered)

    @property
    def resolves(self) -> int:
        """How many times the ref was asked what it points at."""
        asked = [args for args, _cwd in self.calls if args[0] == REV_PARSE]
        return len(asked)


def _git_answer(stdout: str, *, returncode: int = 0):
    """One completed git invocation, as the probe reads it."""
    return MagicMock(returncode=returncode, stdout=stdout, stderr="")


class _RefusesTheComparison(_ResolvesThenCounts):
    """A ref that resolves and a comparison git will not take."""

    def __call__(self, *args, cwd):
        self.calls.append((args, cwd))
        if args[0] == REV_PARSE:
            return _git_answer(TIP)
        return _git_answer("", returncode=1)


class BranchDivergenceTest(unittest.TestCase):
    """One reading: the ref resolved once, then HEAD counted against it.

    The two commands are one fact, and the commit is why. The counts are a
    claim about the tip they were taken against, and the push that claim
    licenses is pinned to that same commit -- so a ref something moves in
    between must not leave the branch proved against one head and the push
    pinned to another.
    """

    def test_the_comparison_names_the_resolved_commit(self) -> None:
        # Not the ref. Named the ref, a fetch racing this reading would have
        # the counts taken against a tip the caller never reports -- and the
        # push it licenses would be leased to a head nothing compared.
        git = _ResolvesThenCounts(TIP, counts="2\t3\n")

        divergence = self._divergence(git)

        self.assertEqual(divergence.tip, TIP)
        # `<tip>...HEAD` puts the tip-only count on the left, so the left
        # field is `behind` and the right field is `ahead`.
        self.assertEqual((divergence.ahead, divergence.behind), (3, 2))
        self.assertTrue(divergence.readable)
        counted, _cwd = git.calls[1]
        self.assertIn(f"{TIP}...HEAD", counted)
        self.assertNotIn(f"refs/remotes/private/{BRANCH}...HEAD", counted)

    def test_a_ref_that_moves_is_resolved_once(self) -> None:
        # The race this reading closes: the ref is at H0 when the comparison
        # is taken and at H1 a moment later. Asked twice -- once to compare
        # against and once to name -- the counts would be about H0 while the
        # head reported, and therefore the lease the push is pinned to, is
        # H1: where the pull request has moved to H1 too, that lease is
        # satisfied and the force-push lands on top of it.
        git = _ResolvesThenCounts(TIP, MOVED_TIP, counts="0\t1\n")

        divergence = self._divergence(git)

        self.assertEqual(git.resolves, 1)
        self.assertEqual(divergence.tip, TIP)
        counted, _cwd = git.calls[1]
        self.assertIn(f"{TIP}...HEAD", counted)

    def test_an_in_sync_branch_is_readable(self) -> None:
        # What says every refusal above is about the reading rather than
        # about zero counts: in sync is zero and zero AND readable.
        divergence = self._divergence(_ResolvesThenCounts(TIP))

        self.assertTrue(divergence.readable)
        self.assertEqual((divergence.ahead, divergence.behind), (0, 0))

    def test_a_reading_that_did_not_happen_refuses(self) -> None:
        # Every way one of the two commands can fail to answer, and none of
        # them is `(0, 0)`: read as an in-sync branch, a stale checkout is
        # rebased, spawned over, and force-pushed on evidence nobody took.
        refused = (
            _GitRecorder("", returncode=1, stderr="fatal: bad revision"),
            _GitRecorder("\n"),
            _RefusesTheComparison(TIP),
            *(
                _ResolvesThenCounts(TIP, counts=counts)
                for counts in ("", "4\n", "one\ttwo\n", "1\t2\t3\n")
            ),
        )
        for git in refused:
            with self.subTest(git=type(git).__name__):
                self.assertEqual(self._divergence(git), UNREADABLE)

    def _divergence(self, git):
        with patch.object(commands, HARDENED_HELPER, git):
            return probes._branch_divergence(
                _spec(remote_name="private"), WORKTREE, BRANCH,
            )


class FrozenRevisionDivergenceTest(unittest.TestCase):
    """The local end named as a commit, for a caller about to publish.

    `HEAD` is a symbol every command re-resolves, so a count taken against it
    is a claim about whatever the checkout pointed at when `rev-list` ran --
    and a caller that names a commit afterwards can be naming another. A
    publication has to be about ONE commit at both ends, so it freezes the
    local id and counts that.
    """

    def test_a_named_revision_is_what_the_count_walks(self) -> None:
        # The whole contract, and the reason it is asserted on the command
        # rather than on the counts: a revision the range did not carry reads
        # back identically, and reverting to symbolic `HEAD` would restore
        # the race in silence.
        git = _ResolvesThenCounts(TIP, counts="0\t1\n")

        divergence = self._divergence(git, FROZEN)

        self.assertEqual((divergence.tip, divergence.ahead), (TIP, 1))
        counted, _cwd = git.calls[1]
        self.assertIn(f"{TIP}...{FROZEN}", counted)
        self.assertNotIn(f"{TIP}...HEAD", counted)
        # The revision is stopped from being read as a path, so a branch or a
        # commit that looks like one cannot turn the count into a file walk.
        self.assertEqual(counted[-1], PATH_SEPARATOR)

    def test_no_revision_counts_the_checkout_head(self) -> None:
        # The default every caller that only asks how stale a checkout is
        # keeps, so freezing is opt-in rather than a rewrite of them all.
        git = _ResolvesThenCounts(TIP)

        self._divergence(git, None)

        counted, _cwd = git.calls[1]
        self.assertIn(f"{TIP}...HEAD", counted)

    def _divergence(self, git, revision):
        named = () if revision is None else (revision,)
        with patch.object(commands, HARDENED_HELPER, git):
            return probes._branch_divergence(
                _spec(remote_name="private"), WORKTREE, BRANCH, *named,
            )


if __name__ == "__main__":
    unittest.main()
