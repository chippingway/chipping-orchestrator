# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkout the shared publication seam pushes from and hands on, over a real clone.

The seam proves the checkout the issue's own on entry, but the gate's reading
of the pull request comes after that proof, and a tree switched onto the flat
branch at the measured commit passes every reading of the commit and the
tree. So the push takes the proof again and refuses with nothing pushed; and
a tree switched while the push itself runs, or while the receipt's write runs
behind it, gets no handoff -- the push and its receipt stand, nothing is
parked, and the claim it owes is recorded for the tick that finds the
checkout restored. A push nobody could name its commit for is held to the
same proof, since whose checkout it is needs no commit to compare against.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.git import branch_transport, push_questions, ref_transport
from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.git.worktrees import naming
from orchestrator.workflow.stages.implementing import late_publication_state, late_push
from orchestrator.workflow.stages.implementing.late_gate_models import _Entered, _Gate
from orchestrator.workflow.stages.implementing.late_publication import _PublishedCandidate
from tests.git.worktrees.real_git_test_support import _AmendedPlanRepo, _run_git
from tests.support.fakes import FakeGitHubClient, FakePR, FakePRRef, make_issue

ISSUE = 300
PR_NUMBER = 42
_FLAT_BRANCH = f"orchestrator/issue-{ISSUE}"
_RECEIPT = "implementing_published_sha"
_INTENT = "late_approved_sha"

# The windows past the push a tree is switched in: the push itself, the write
# that carries its receipt, and the post-push head read onto a branch carrying
# a commit of its own -- which that read parks as a moved checkout before
# whose checkout it is can be asked again.
_PUSH_WINDOW = "the push"
_RECEIPT_WINDOW = "the receipt's write"
_HEAD_READ_WINDOW = "the post-push head read"

# Each of those windows beside the park it leaves: none, save the head read's.
_PAST_THE_PUSH = ((_PUSH_WINDOW, None), (_RECEIPT_WINDOW, None), (_HEAD_READ_WINDOW, "late_candidate_moved"))

# Who commits on a switched checkout, named so no ambient git identity is needed.
_OPERATOR = ("-c", "user.name=Operator", "-c", "user.email=operator@example.invalid")

# An object id no repository here has, which no proof of a candidate can name.
_MISSING = "0000000000000000000000000000000000000000"


def _switch(worktree, *, commits: bool = False) -> None:
    """Switch `worktree` onto the flat branch at the commit it stands on -- an operator's commit on top -- once."""
    if not _run_git("branch", "--list", _FLAT_BRANCH, cwd=worktree).strip():
        _run_git("checkout", "-q", "-b", _FLAT_BRANCH, cwd=worktree)
        if commits:
            _run_git(*_OPERATOR, "commit", "-q", "--allow-empty", "-m", "operator work", cwd=worktree)


def _switching(worktree, through, *, behind: str = ""):
    """`through`, with `worktree` switched onto the flat branch ahead of it, or behind a write recording `behind`."""

    def wrapper(*args, **kwargs):
        if not behind:
            _switch(worktree)
        answer = through(*args, **kwargs)
        written = args[1].get(behind) if behind else None
        if written:
            _switch(worktree)
        return answer
    return wrapper


def _switching_past_the_push(case, through, *, commits: bool = False):
    """`through`, with `case`'s checkout switched onto the flat branch the first time it runs behind the push."""

    def wrapper(*args, **kwargs):
        if case.push.called:
            _switch(case.repo.worktree, commits=commits)
        return through(*args, **kwargs)
    return wrapper


def _preparing(worktree):
    """A push transport preparing in `worktree`, switched onto the flat branch meanwhile, asking the question last."""

    def wrapper(*_args, **_kwargs):
        _switch(worktree)
        push_questions._asks()
        return True
    return wrapper


def _switched_during(case, window: str):
    """A context in which `case`'s checkout is switched onto the flat branch during `window`."""
    worktree = case.repo.worktree
    if window == _PUSH_WINDOW:
        return patch.object(case.push, "side_effect", _switching(worktree, MagicMock(return_value=True)))
    if window == _HEAD_READ_WINDOW:
        read = _switching_past_the_push(case, _measurement_commits._prove_candidate_commit, commits=True)
        return patch.object(_measurement_commits, "_prove_candidate_commit", side_effect=read)
    written = _switching(worktree, case.gh.write_pinned_state, behind=_RECEIPT)
    return patch.object(case.gh, "write_pinned_state", side_effect=written)


class PublicationCheckoutTest(unittest.TestCase):
    """One gated push of the planted commit onto the pull request the remote already carries."""

    def setUp(self) -> None:
        self.repo = _AmendedPlanRepo()
        self.branch = naming._branch_name(self.repo.spec, ISSUE)
        self.repo.plant(self, ISSUE, self.branch)
        self.gh = FakeGitHubClient()
        self.issue = make_issue(ISSUE, label="workflow:fixing")
        self.gh.add_issue(self.issue)
        amended = FakePRRef(sha=self.repo.amended)
        self.gh.add_pr(FakePR(number=PR_NUMBER, head_branch=self.branch, head=amended))
        self.gh.seed_state(ISSUE, branch=self.branch, pr_number=PR_NUMBER)
        self.push = MagicMock(return_value=True)
        self.enterContext(patch.object(config, "DECOMPOSE", False))
        self.enterContext(patch.object(branch_transport, "_push_branch", self.push))

    def test_the_issue_s_own_checkout_is_published(self) -> None:
        published = self._published()

        self.assertEqual((self.push.call_count, published.landed), (1, True))

    def test_a_switch_mid_read_pushes_nothing(self) -> None:
        # Switched while the gate reads the pull request, or while the push
        # transport prepares in the worktree behind the seam's last proof: the
        # push's own question refuses before anything is sent, and nothing of
        # a landing is recorded.
        for transported in (False, True):
            with self.subTest(transported=transported):
                self.setUp()
                worktree = self.repo.worktree
                read = self.gh.get_pr if transported else _switching(worktree, self.gh.get_pr)
                self.push.side_effect = _preparing(self.repo.worktree) if transported else None
                with patch.object(self.gh, "get_pr", side_effect=read):
                    self.assertRaises(naming.BranchRefused, self._published)

                self.assertEqual(self.push.call_count, int(transported))
                self.assertIsNone(self.gh.pinned_data(ISSUE).get(_RECEIPT))

    def test_a_switch_past_the_push_hands_nothing_on(self) -> None:
        # Switched while the push runs, or while the write carrying its receipt
        # does -- behind every proof ahead of that write -- the push and its
        # receipt stand, and the claim they owe the checkout is recorded in
        # place of the handoff, with nothing parked or posted. Switched during
        # the post-push head read onto a branch carrying its own commit, the
        # handoff is held the same way, but that read has already seen a
        # moved head and parked before ownership is asked again.
        for window, parked_as in _PAST_THE_PUSH:
            with self.subTest(window=window):
                self.setUp()
                with _switched_during(self, window):
                    published = self._published()

                pinned = self.gh.pinned_data(ISSUE)
                self.assertEqual(self.push.call_count, 1)
                self.assertEqual((published.landed, published.held), (False, True))
                self.assertEqual(pinned.get(_RECEIPT), self.repo.published)
                self.assertEqual(pinned.get(_INTENT), self.repo.published)
                self.assertEqual(pinned.get("park_reason"), parked_as)
                self.assertEqual(len(self.gh.posted_comments), int(parked_as is not None))

    def test_an_unnamed_push_hands_nothing_on(self) -> None:
        # The gate could not name the candidate, so the push goes out as the
        # checkout stands and no claim can be recorded about it -- but a tree
        # switched while it ran still holds the handoff.
        unread = _measurement_commits._prove_candidate_commit(self.repo.worktree, _MISSING)

        with _switched_during(self, _PUSH_WINDOW), patch.object(
            _measurement_commits, "_prove_candidate_commit", return_value=unread,
        ):
            published = self._published(candidate="")

        answered = (published.landed, published.held)
        self.assertEqual((self.push.call_count, answered), (1, (False, True)))
        self.assertIsNone(self.push.call_args.kwargs["revision"])

    def test_a_settled_retry_switched_mid_read_holds(self) -> None:
        # The receipt already names the candidate and the pull request stands
        # on it, so the push is the leased no-op a retry makes and nothing is
        # left to settle -- and the tree is switched while the head is read
        # behind that push. Whose checkout it is gets asked again behind those
        # readings, so the handoff holds with its claim beside the receipt.
        landed = self.repo.published
        self.gh.get_pr(PR_NUMBER).head.sha = landed
        state = self.gh.read_pinned_state(self.issue)
        late_publication_state._record_publication(state, landed, "", PR_NUMBER)
        self.gh.write_pinned_state(self.issue, state)
        read = _switching_past_the_push(self, _measurement_commits._prove_candidate_commit)

        with patch.object(_measurement_commits, "_prove_candidate_commit", side_effect=read):
            published = self._published(head=landed)

        pinned = self.gh.pinned_data(ISSUE)
        self.assertEqual(self.push.call_count, 1)
        self.assertEqual((published.landed, published.held), (False, True))
        self.assertEqual(pinned.get(_RECEIPT), landed)
        self.assertEqual(pinned.get(_INTENT), landed)
        self.assertIsNone(pinned.get("park_reason"))

    def _published(self, candidate: str | None = None, head: str | None = None) -> late_push._PushedCandidate:
        """The seam's answer for the planted commit, or `candidate`, entered over the head the pull request is on."""
        repo = self.repo
        state = self.gh.read_pinned_state(self.issue)
        gate = _Gate(self.gh, repo.spec, self.issue, state, repo.worktree)
        named = repo.published if candidate is None else candidate
        entered = _Entered(candidate=named, head=head or repo.amended)
        return late_push._publishes(gate, self.branch, entered)


class UnpinnedPushCheckoutTest(unittest.TestCase):
    """A gated push the gate froze no head for, which reads the remote for its own lease.

    The read is the seam's own, ahead of a last proof of the checkout, rather
    than the transport's inside the push: a tree switched while it runs is
    refused with nothing sent, and the push otherwise carries the tip the
    remote answered as its explicit lease.
    """

    def setUp(self) -> None:
        self.repo = _AmendedPlanRepo()
        self.branch = naming._branch_name(self.repo.spec, ISSUE)
        self.repo.plant(self, ISSUE, self.branch)
        github = FakeGitHubClient()
        issue = make_issue(ISSUE, label="workflow:fixing")
        github.add_issue(issue)
        github.seed_state(ISSUE, branch=self.branch, pr_number=PR_NUMBER)
        state = github.read_pinned_state(issue)
        self.gate = _Gate(github, self.repo.spec, issue, state, self.repo.worktree)
        self.switches = False
        self.push = MagicMock(return_value=True)
        self.enterContext(patch.object(branch_transport, "_push_branch", self.push))
        self.enterContext(patch.object(branch_transport, "_remote_branch_read", side_effect=self._read_remote))

    def test_the_remote_s_tip_is_the_lease(self) -> None:
        self.assertTrue(self._pushed())

        self.assertEqual(self.push.call_args.kwargs["force_with_lease"], self.repo.amended)

    def test_a_switch_mid_read_pushes_nothing(self) -> None:
        self.switches = True

        self.assertRaises(naming.BranchRefused, self._pushed)

        self.push.assert_not_called()

    def _pushed(self) -> bool:
        """The seam's push of the planted commit, with no head frozen to lease it against."""
        unpinned = _PublishedCandidate(held=False, revision=self.repo.published)
        return late_push._pushed(self.gate, self.branch, unpinned)

    def _read_remote(self, *_args):
        """The remote's answer for the branch, the checkout switched onto the flat branch while it is read."""
        if self.switches:
            _switch(self.repo.worktree)
        return ref_transport._RefRead(sha=self.repo.amended)


if __name__ == "__main__":
    unittest.main()
