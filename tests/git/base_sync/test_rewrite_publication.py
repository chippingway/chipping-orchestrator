# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Preparing, publishing, and observing a base-rewrite candidate on real git."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.git import branch_transport, ref_transport
from orchestrator.git.base_sync import rewrite_transport
from orchestrator.git.base_sync.rewrite_handoffs import (
    _LandedRewrite,
    _PushOutcome,
    _RewriteCandidate,
    _RewriteRefusal,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.git.base_sync.rewrite_git_support import (
    BASE_BRANCH,
    FEATURE_FILE,
    ORIGIN,
    PR_BRANCH,
    PR_NUMBER,
    RewriteRepository,
    pull_request_head,
    rewrite_repository,
)

PUSH_BRANCH = "_push_branch"

HEAD = "HEAD"

_BASE_REF = f"refs/remotes/{ORIGIN}/{BASE_BRANCH}"

# Which of the fixture's checkouts a change is made in.
_WORKTREE = "worktree"

_CLONE = "clone"

# The push before any case replaces it, so a double can still reach the remote.
_REAL_PUSH = branch_transport._push_branch

# What happens to the checkout between the reading and the push, and the
# refusal each earns: work landing on top, an edit beside it, an index entry
# git was told to stop comparing, a head that names no commit, and a base ref
# rewound off the tip the replay sits over.
_SINCE_PREPARED = (
    (_WORKTREE, ("commit", "--allow-empty", "-m", "later"), _RewriteRefusal.MOVED_CHECKOUT),
    (_WORKTREE, ("rm", "--cached", FEATURE_FILE), _RewriteRefusal.DIRTY_TREE),
    (_WORKTREE, ("update-index", "--skip-worktree", FEATURE_FILE), _RewriteRefusal.UNREADABLE_TREE),
    (_WORKTREE, ("symbolic-ref", HEAD, "refs/heads/unborn"), _RewriteRefusal.UNREADABLE_HEAD),
    (_CLONE, ("update-ref", _BASE_REF, f"{_BASE_REF}~1"), _RewriteRefusal.MOVED_BASE),
)


def _publishes(
    repository: RewriteRepository, candidate: _RewriteCandidate,
) -> _LandedRewrite:
    """Publish `candidate` from the repository's worktree."""
    return rewrite_transport._publishes_the_candidate(
        repository.spec, repository.worktree, candidate,
    )


def _lands_and_loses_the_answer(*args, **kwargs) -> bool:
    """The real push, whose answer never makes it back."""
    _REAL_PUSH(*args, **kwargs)
    return False


class _PreparedRewrite(unittest.TestCase):
    """A rebased pull request branch, and the candidate read off it."""

    def setUp(self) -> None:
        self.repository = rewrite_repository(self)
        self.candidate = self.repository.prepared()

    def _publishes(self) -> _LandedRewrite:
        return _publishes(self.repository, self.candidate)


class PreparedCandidateTest(_PreparedRewrite):
    """A clean rebase is read whole, off the checkout and the remote."""

    def test_a_clean_rebase_hands_over_every_reading(self) -> None:
        repository = self.repository
        candidate = self.candidate
        worktree = repository.worktree
        base = candidate.checkout.base

        self.assertIsNone(candidate.refusal)
        self.assertEqual(candidate.original_head, repository.anchor)
        self.assertEqual(candidate.rewritten_head, repository.head_of(HEAD, worktree))
        self.assertEqual(
            candidate.original_tree,
            repository.head_of(f"{repository.anchor}^{{tree}}", worktree),
        )
        self.assertEqual(candidate.checkout.tree, repository.head_of("HEAD^{tree}", worktree))
        self.assertTrue(candidate.checkout.status.is_clean)
        # The replay sits on the base the remote carries, one commit ahead.
        self.assertEqual(
            (base.tip, base.ahead, base.behind),
            (repository.head_of(f"refs/heads/{BASE_BRANCH}", repository.remote), 1, 0),
        )
        self.assertEqual(candidate.remote.sha, repository.anchor)
        self.assertEqual(
            (candidate.branch, candidate.attempt.pr_number, candidate.attempt.stage),
            (PR_BRANCH, PR_NUMBER, WorkflowLabel.VALIDATING),
        )


class PublicationTest(_PreparedRewrite):
    """The push names the candidate and is leased to the head it replaced."""

    def test_the_candidate_goes_out_under_its_lease(self) -> None:
        push = MagicMock(wraps=_REAL_PUSH)

        with patch.object(branch_transport, PUSH_BRANCH, push):
            landed = self._publishes()

        self.assertEqual((landed.outcome, landed.landed), (_PushOutcome.ACCEPTED, True))
        self.assertEqual(pull_request_head(self.repository), self.candidate.rewritten_head)
        # The exact publication: one push, naming the commit that was read and
        # leased to the head the pull request stood on before the rewrite.
        self.assertEqual(push.call_count, 1)
        self.assertEqual(
            push.call_args.kwargs,
            {
                "force_with_lease": self.repository.anchor,
                "revision": self.candidate.rewritten_head,
            },
        )

    def test_a_landed_candidate_is_never_resent(self) -> None:
        # The push landed and its tick never came back. The frozen candidate
        # handed in again still says the remote is on the anchor, and a fresh
        # one says what the remote really holds; neither sends anything.
        self._publishes()
        push = MagicMock()

        with patch.object(branch_transport, PUSH_BRANCH, push):
            observed = rewrite_transport._observes_the_landing(
                self.repository.spec, self.repository.worktree, self.candidate,
            )
            reused = self._publishes()
            fresh = _publishes(self.repository, self.repository.prepared())

        self.assertEqual((observed.outcome, observed.landed), (_PushOutcome.OBSERVED, True))
        for again in (reused, fresh):
            with self.subTest(prepared=again.candidate.remote.sha):
                self.assertEqual(
                    (again.outcome, again.refusal, again.landed),
                    (_PushOutcome.REFUSED, _RewriteRefusal.PUBLISHED, True),
                )
        push.assert_not_called()

    def test_a_remote_moved_since_sends_nothing(self) -> None:
        foreign = self.repository.pushes_a_foreign_commit()

        landed = self._publishes()

        self.assertEqual(
            (landed.outcome, landed.refusal, landed.remote.sha),
            (_PushOutcome.REFUSED, _RewriteRefusal.MOVED_REMOTE, foreign),
        )
        self.assertEqual(pull_request_head(self.repository), foreign)

    def test_a_push_racing_the_lease_is_rejected(self) -> None:
        # The remote moves after the last reading and before git runs, which
        # is the window only the lease covers.
        with patch.object(branch_transport, PUSH_BRANCH, self._races_the_lease):
            landed = self._publishes()

        foreign = pull_request_head(self.repository)
        self.assertNotIn(foreign, {self.repository.anchor, self.candidate.rewritten_head})
        self.assertEqual(
            (landed.outcome, landed.landed, landed.remote.sha),
            (_PushOutcome.REJECTED, False, foreign),
        )

    def test_an_advanced_base_still_publishes(self) -> None:
        # A base moves forward on its own; the replay is still onto history it
        # carries, and the next refresh is what catches up with the new tip.
        self.repository.advance_base()

        landed = self._publishes()

        self.assertEqual(landed.outcome, _PushOutcome.ACCEPTED)
        self.assertEqual(pull_request_head(self.repository), self.candidate.rewritten_head)

    def _races_the_lease(self, *args, **kwargs) -> bool:
        """Move the remote branch, then make the real push."""
        self.repository.pushes_a_foreign_commit()
        return _REAL_PUSH(*args, **kwargs)


class UncertainResponseTest(_PreparedRewrite):
    """A push git answered with a failure is classified by reading the remote."""

    def test_a_lost_answer_reads_as_landed(self) -> None:
        with patch.object(branch_transport, PUSH_BRANCH, _lands_and_loses_the_answer):
            landed = self._publishes()

        self.assertEqual((landed.outcome, landed.landed), (_PushOutcome.UNCERTAIN, True))
        self.assertEqual(pull_request_head(self.repository), self.candidate.rewritten_head)

    def test_an_unreadable_remote_stays_uncertain(self) -> None:
        # The remote answers the reading ahead of the push, and nothing after it.
        unreadable = ref_transport._RefRead(detail="fatal: unable to access")
        reads = MagicMock(side_effect=[self.candidate.remote, unreadable])

        with patch.object(
            branch_transport, PUSH_BRANCH, MagicMock(return_value=False),
        ), patch.object(branch_transport, "_remote_branch_read", reads):
            landed = self._publishes()

        self.assertEqual(
            (landed.outcome, landed.landed, landed.remote),
            (_PushOutcome.UNCERTAIN, False, unreadable),
        )


class ChangedSincePreparedTest(unittest.TestCase):
    """A checkout that changed between the reading and the push sends nothing."""

    def test_a_changed_checkout_sends_nothing(self) -> None:
        for place, argv, refusal in _SINCE_PREPARED:
            with self.subTest(change=argv[0]):
                repository, landed = self._changed_then_published(place, argv)
                self.assertEqual(
                    (landed.outcome, landed.refusal), (_PushOutcome.REFUSED, refusal),
                )
                self.assertEqual(pull_request_head(repository), repository.anchor)

    def _changed_then_published(
        self, place: str, argv: tuple[str, ...],
    ) -> tuple[RewriteRepository, _LandedRewrite]:
        repository = rewrite_repository(self)
        candidate = repository.prepared()
        repository.git(*argv, cwd=getattr(repository, place))
        return repository, _publishes(repository, candidate)


if __name__ == "__main__":
    unittest.main()
