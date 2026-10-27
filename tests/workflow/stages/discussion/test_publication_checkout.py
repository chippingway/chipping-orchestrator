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
reads and the push itself come after the first proof: one switched onto the
flat branch in either window pushes nothing, or opens nothing over what it
pushed, and leaves the marker for the recovery that finds it restored.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import DEFAULT, MagicMock, patch

from orchestrator import config
from orchestrator.git import branch_transport
from orchestrator.git.worktrees import naming, paths
from orchestrator.observability.analytics import settings
from orchestrator.workflow.stages.discussion import handler
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.stages.discussion.discussion_real_git_test_support import (
    _commit_file,
    _git,
    _real_git_spec,
    _seed_upstream_clone,
)

ISSUE = 9
PLAN = "plans/issue-9.md"
_PUBLISHING = "discussion_publishing_sha"


def _held_outside(case, root: Path) -> None:
    """Point the worktrees root and the event logs under `root` for the case."""
    case.enterContext(patch.object(config, "WORKTREES_DIR", root / "worktrees"))
    case.enterContext(patch.object(settings, "ANALYTICS_LOG_PATH", root / "analytics.jsonl"))
    case.enterContext(patch.object(settings, "TRAJECTORY_LOG_PATH", root / "trajectory.jsonl"))


def _replaced_by_a_clone(spec, root: Path, branch: str) -> str:
    """Seed the round's checkout, then put an unrelated clone at its path on `branch`; the round's base."""
    checkout = paths._worktree_path(spec, ISSUE)
    checkout.parent.mkdir(parents=True)
    base = _seed_upstream_clone(spec, root / "upstream", checkout, branch)
    _git(spec.target_root, "worktree", "remove", str(checkout))
    _git(root, "clone", "-q", str(root / "upstream"), str(checkout))
    _git(checkout, "checkout", "-q", "-b", branch)
    return base


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
        self.tip.side_effect = self._switched

        self.assertRaises(naming.BranchRefused, handler._handle_discussion, self.gh, self.spec, self.issue)

        self.push.assert_not_called()
        self.assertEqual(self.gh.opened_prs, [])
        self.assertIsNotNone(self.gh.pinned_data(ISSUE).get(_PUBLISHING))

    def test_a_switch_mid_push_opens_nothing(self) -> None:
        self.push.side_effect = self._switched

        self.assertRaises(naming.BranchRefused, handler._handle_discussion, self.gh, self.spec, self.issue)

        self.assertEqual(self.push.call_count, 1)
        self.assertEqual(self.gh.opened_prs, [])
        self.assertIsNotNone(self.gh.pinned_data(ISSUE).get(_PUBLISHING))

    def _switched(self, *_args, **_kwargs):
        """Switch the checkout onto the flat branch the first time; the stood-in call's own answer."""
        if not self._has_switched:
            _git(self.checkout, "checkout", "-q", "-b", f"orchestrator/issue-{ISSUE}")
            self._has_switched = True
        return DEFAULT


if __name__ == "__main__":
    unittest.main()
