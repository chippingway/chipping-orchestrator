# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkout a recovered plan publication pushes from, over real repositories.

A publication the last tick began and never finished is picked up from its
marker, reading the plan out of the tree at the issue's path and pushing it.
A branch of the right name proves nothing about that tree: an unrelated clone
standing there on the issue's branch name is no worktree of this clone, so
the recovery refuses before the artifact is read or published -- no push, no
pull request, no record of a plan. The issue's own checkout is proven again
last before the push and before the pull request is opened, since the remote
reads, the push itself, and the pull request's own lookup come after the
first proof: one switched onto the flat branch in any of those windows pushes
nothing, or opens nothing over what it pushed, and leaves the marker for the
recovery that finds it restored. So does one switched while GitHub is asked
which pull request already carries the plan: nothing is adopted, edited, or
recorded over it.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import DEFAULT, MagicMock, patch

from orchestrator.git import branch_transport, push_questions
from orchestrator.git.publication import titles
from orchestrator.git.worktrees import naming, paths
from orchestrator.workflow.stages.discussion import handler
from tests.support.fakes import FakeGitHubClient, FakePR, FakePRRef, make_issue
from tests.workflow.stages.discussion.discussion_real_git_test_support import (
    _commit_file,
    _git,
    _held_outside,
    _real_git_spec,
    _seed_upstream_clone,
)

ISSUE = 9
PLAN = "plans/issue-9.md"
PLAN_PR = 51
_PUBLISHING = "discussion_publishing_sha"

# The requests a plan pull request's lookup and open are switched during: the
# lookup with none open, the lookup of one open to be reused, the reused one's
# body edit, and the title of the one to open -- with the edits each leaves.
_LOOKUP_WINDOWS = (
    (None, "find_open_pr", False, 0),
    (None, "find_open_pr", True, 0),
    (None, "edit_pr_body", True, 1),
    (titles, "_first_commit_subject", False, 0),
)

# The requests adopting a pull request that already carries the plan is
# switched during: the search by commit, and the body edit -- with the edits each
# leaves.
_ADOPTION_WINDOWS = (("find_pr_for_commit", 0), ("edit_pr_body", 1))


def _replaced_by_a_clone(spec, root: Path, branch: str) -> str:
    """Seed the round's checkout, then put an unrelated clone at its path on `branch`; the round's base."""
    checkout = paths._worktree_path(spec, ISSUE)
    checkout.parent.mkdir(parents=True)
    base = _seed_upstream_clone(spec, root / "upstream", checkout, branch)
    _git(spec.target_root, "worktree", "remove", str(checkout))
    _git(root, "clone", "-q", str(root / "upstream"), str(checkout))
    _git(checkout, "checkout", "-q", "-b", branch)
    return base


def _switching(switch, through):
    """`through`, with `switch` called ahead of it."""

    def wrapper(*args, **kwargs):
        switch()
        return through(*args, **kwargs)
    return wrapper


def _preparing(switch, sent: list):
    """A push transport that `switch`es the checkout while it prepares, asking the caller's question last; its sends."""

    def wrapper(*_args, **_kwargs):
        switch()
        push_questions._asks()
        sent.append(True)
        return True
    return wrapper


def _opened_plan_pr(github: FakeGitHubClient, branch: str) -> None:
    """Leave a plan pull request open on `branch`, its body a human's, for the publication to reuse."""
    open_pr = FakePR(number=PLAN_PR, head_branch=branch, body="A human's description")
    github.add_pr(open_pr)
    github.existing_open_pr[branch] = open_pr


def _in_flight(github: FakeGitHubClient, branch: str, base: str, plan_sha: str) -> None:
    """Seed the record of a round over `base` whose publication of `plan_sha` began and never finished."""
    github.seed_state(
        ISSUE, branch=branch, discussion_agent="claude",
        discussion_session_id="discussion-session",
        discussion_base_sha=base, discussion_round_sha=base,
        discussion_round_branch=branch, **{_PUBLISHING: plan_sha},
    )


class ForeignPublicationCheckoutTest(unittest.TestCase):
    """An in-flight publication whose checkout was replaced by an unrelated clone."""

    def setUp(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="orch-plan-publication-")))
        _held_outside(self, root)
        self.spec = _real_git_spec(root)
        self.issue = make_issue(ISSUE, label="discussion")
        branch = naming._branch_name(self.spec, ISSUE)
        base = _replaced_by_a_clone(self.spec, root, branch)
        self.gh = FakeGitHubClient()
        self.gh.add_issue(self.issue)
        checkout = paths._worktree_path(self.spec, ISSUE)
        _in_flight(self.gh, branch, base, _commit_file(checkout, PLAN, "# Plan\n"))

    def test_an_unrelated_clone_publishes_nothing(self) -> None:
        recorded = self.gh.pinned_data(ISSUE)
        push = MagicMock(return_value=True)

        with (
            patch.object(branch_transport, "_remote_branch_tip", return_value=""),
            patch.object(branch_transport, "_push_branch", push),
        ):
            self.assertRaises(naming.BranchRefused, handler._handle_discussion, self.gh, self.spec, self.issue)

        push.assert_not_called()
        self.assertEqual(self.gh.opened_prs, [])
        self.assertEqual(self.gh.pinned_data(ISSUE), recorded)


class SwitchedPublicationCheckoutTest(unittest.TestCase):
    """An in-flight publication over the issue's own checkout, switched onto the flat branch as it runs."""

    def setUp(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="orch-plan-switch-")))
        _held_outside(self, root)
        self.spec = _real_git_spec(root)
        self.issue = make_issue(ISSUE, label="discussion")
        branch = naming._branch_name(self.spec, ISSUE)
        self.checkout = paths._worktree_path(self.spec, ISSUE)
        self.checkout.parent.mkdir(parents=True)
        base = _seed_upstream_clone(self.spec, root / "upstream", self.checkout, branch)
        self.gh = FakeGitHubClient()
        self.gh.add_issue(self.issue)
        _in_flight(self.gh, branch, base, _commit_file(self.checkout, PLAN, "# Plan\n"))
        self._has_switched = False
        self.push = MagicMock(return_value=True)
        self.tip = MagicMock(return_value="")
        self.enterContext(patch.object(branch_transport, "_push_branch", self.push))
        self.enterContext(patch.object(branch_transport, "_remote_branch_tip", self.tip))

    def test_the_issue_s_own_checkout_is_published(self) -> None:
        handler._handle_discussion(self.gh, self.spec, self.issue)

        self.assertEqual(self.push.call_count, 1)
        self.assertEqual(len(self.gh.opened_prs), 1)

    def test_a_switch_mid_tip_read_pushes_nothing(self) -> None:
        # Switched while the remote tip is read, or while the push transport
        # prepares in the worktree behind the last proof -- the push's own
        # question refusing it there before anything is sent: nothing is
        # opened, and the marker waits for the restored checkout.
        for transported in (False, True):
            with self.subTest(transported=transported):
                self.setUp()
                sent = []
                if transported:
                    self.push.side_effect = _preparing(self._switched, sent)
                else:
                    self.tip.side_effect = self._switched

                self.assertRaises(naming.BranchRefused, handler._handle_discussion, self.gh, self.spec, self.issue)

                self.assertEqual((self.push.call_count, sent), (int(transported), []))
                self.assertEqual(self.gh.opened_prs, [])
                self.assertIsNotNone(self.gh.pinned_data(ISSUE).get(_PUBLISHING))

    def test_a_switch_mid_push_opens_nothing(self) -> None:
        self.push.side_effect = self._switched

        self.assertRaises(naming.BranchRefused, handler._handle_discussion, self.gh, self.spec, self.issue)

        self.assertEqual(self.push.call_count, 1)
        self.assertEqual(self.gh.opened_prs, [])
        self.assertIsNotNone(self.gh.pinned_data(ISSUE).get(_PUBLISHING))

    def test_a_switch_mid_lookup_opens_nothing(self) -> None:
        # Switched while the plan pull request is looked up -- none open, or
        # one open to be reused -- while a reused one's body is edited, or
        # while the title of the one to open is read off the branch's history:
        # the push stands, nothing is opened, nothing is recorded, and the
        # marker waits for the restored checkout.
        for owner, read, reused, edits in _LOOKUP_WINDOWS:
            with self.subTest(read=read, reused=reused):
                self.setUp()
                if reused:
                    _opened_plan_pr(self.gh, naming._branch_name(self.spec, ISSUE))
                owner = owner or self.gh
                found = _switching(self._switched, getattr(owner, read))
                with patch.object(owner, read, side_effect=found):
                    self.assertRaises(naming.BranchRefused, handler._handle_discussion, self.gh, self.spec, self.issue)

                self.assertEqual(self.push.call_count, 1)
                self.assertEqual(self.gh.opened_prs, [])
                self.assertEqual(len(self.gh.edited_pr_bodies), edits)
                self.assertIsNotNone(self.gh.pinned_data(ISSUE).get(_PUBLISHING))

    def test_a_switch_mid_pr_search_adopts_nothing(self) -> None:
        # A pull request the humans merged already carries the plan, so the
        # publication only adopts it -- naming its session in the body and
        # recording it. The tree is switched while GitHub is asked which pull
        # request carries the commit, or while the body is edited, and the
        # adoption refuses with the marker and the record as they were.
        for read, edits in _ADOPTION_WINDOWS:
            with self.subTest(read=read):
                self.setUp()
                recorded = self.gh.pinned_data(ISSUE)
                self.gh.add_pr(FakePR(
                    number=PLAN_PR, head_branch=naming._branch_name(self.spec, ISSUE),
                    head=FakePRRef(sha=recorded[_PUBLISHING]), body="A human's description",
                    merged=True, state="closed",
                ))
                found = _switching(self._switched, getattr(self.gh, read))
                with patch.object(self.gh, read, side_effect=found):
                    self.assertRaises(naming.BranchRefused, handler._handle_discussion, self.gh, self.spec, self.issue)

                self.push.assert_not_called()
                self.assertEqual(len(self.gh.edited_pr_bodies), edits)
                self.assertEqual(self.gh.pinned_data(ISSUE), recorded)

    def _switched(self, *_args, **_kwargs):
        """Switch the checkout onto the flat branch the first time; the stood-in call's own answer."""
        if not self._has_switched:
            _git(self.checkout, "checkout", "-q", "-b", f"orchestrator/issue-{ISSUE}")
            self._has_switched = True
        return DEFAULT


if __name__ == "__main__":
    unittest.main()
