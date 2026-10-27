# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Unpushed-commit probes driven against a real temp-backed clone."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from orchestrator.git.worktrees import recovery
from tests.git.worktrees.recovery_test_support import (
    GIT_BRANCH,
    GIT_REV_PARSE,
    GIT_UPDATE_REF,
    REAL_GIT_SLUG,
    GitBranchFixture,
    _flat_branch,
    _seed_branch_fixture,
    _temp_root,
)
from tests.support.git import (
    _run_git,
    _seed_target_root,
    _spec_for,
)
from tests.workflow.stages.question.question_test_support import _issue_branch

MISSING_BRANCH_ISSUE_NUMBER = 700
AHEAD_BRANCH_ISSUE_NUMBER = 702
FLAT_BRANCH_ISSUE_NUMBER = 704
DUAL_BRANCH_ISSUE_NUMBER = 705


class BranchHasUnpushedCommitsRealGitTest(unittest.TestCase):
    """Direct coverage for `_branch_has_unpushed_commits`. The stage-
    handler tests mock this helper on this owner so they do not
    exercise the real `git rev-list` plumbing; this class drives the
    helper against a real temp-backed clone so a regression in the
    rev-list args, the lock acquisition, or the branch-existence
    pre-check surfaces here.
    """

    def test_returns_false_when_branch_does_not_exist(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bhpc-noBranch-") as td:
            target, _ = _seed_target_root(Path(td))
            spec = _spec_for(target)
            self.assertFalse(
                recovery._branch_has_unpushed_commits(
                    spec,
                    MISSING_BRANCH_ISSUE_NUMBER,
                ),
            )

    def test_returns_false_when_branch_at_base(self) -> None:
        # `orchestrator/orch__realgit/issue-N` exists at exactly origin/main: a
        # fresh-from-base branch has no commits to inspect.
        with tempfile.TemporaryDirectory(prefix="bhpc-atBase-") as td:
            issue_number = 701
            target, base_sha = _seed_target_root(Path(td))
            _run_git(
                GIT_BRANCH,
                _issue_branch(issue_number, slug=REAL_GIT_SLUG),
                base_sha,
                cwd=target,
            )
            spec = _spec_for(target)
            self.assertFalse(
                recovery._branch_has_unpushed_commits(spec, issue_number),
            )

    def test_true_when_branch_ahead_of_base(
        self,
    ) -> None:
        # `orchestrator/orch__realgit/issue-N` has at least one commit beyond
        # origin/main. This is the read-only-violation we are
        # trying to detect.
        with tempfile.TemporaryDirectory(prefix="bhpc-ahead-") as td:
            fixture = _seed_branch_fixture(
                Path(td),
                AHEAD_BRANCH_ISSUE_NUMBER,
                _issue_branch(AHEAD_BRANCH_ISSUE_NUMBER, slug=REAL_GIT_SLUG),
            )
            # Add a commit on the issue branch. Update the ref
            # directly via `commit-tree` so we don't touch the
            # parent clone's checkout state.
            fixture.commit("agent commit")
            self.assertTrue(
                recovery._branch_has_unpushed_commits(
                    fixture.spec,
                    fixture.issue_number,
                ),
            )

    def test_false_when_remote_base_missing(self) -> None:
        # If `refs/remotes/origin/main` has been pruned (a
        # mis-configured local clone, a fetch failure earlier in
        # the tick), `git rev-list` exits non-zero. The helper
        # conservatively returns None -- the caller's later steps
        # surface any persistent problem.
        with tempfile.TemporaryDirectory(prefix="bhpc-noBase-") as td:
            issue_number = 703
            target, base_sha = _seed_target_root(Path(td))
            _run_git(
                GIT_BRANCH,
                _issue_branch(issue_number, slug=REAL_GIT_SLUG),
                base_sha,
                cwd=target,
            )
            _run_git(
                GIT_UPDATE_REF,
                "-d",
                "refs/remotes/origin/main",
                cwd=target,
            )
            spec = _spec_for(target)
            self.assertIsNone(
                recovery._branch_has_unpushed_commits(spec, issue_number),
            )

    def test_a_flat_branch_is_no_candidate(self) -> None:
        # The flat `orchestrator/issue-N` ref carries commits and the issue's
        # own branch does not, which is what an earlier layout's question or
        # dev run leaves behind. That ref is no artifact of this issue: nothing
        # here names it as work to recover or publish, and the creators refuse
        # a checkout standing on it, so its commits stay where they are for an
        # operator. With the current branch carrying commits beside it, the
        # current branch is the one answered for.
        with _temp_root("bhpc-flat-") as temp_root:
            flat = _seed_branch_fixture(
                temp_root,
                FLAT_BRANCH_ISSUE_NUMBER,
                _flat_branch(FLAT_BRANCH_ISSUE_NUMBER),
            )
            flat.commit("stale question commit")
            self.assertIsNone(
                recovery._branch_has_unpushed_commits(
                    flat.spec, flat.issue_number,
                ),
            )
            current = GitBranchFixture(
                target=flat.target,
                base_sha=flat.base_sha,
                issue_number=flat.issue_number,
                branch=_issue_branch(flat.issue_number, slug=REAL_GIT_SLUG),
            )
            current.commit(f"c on {current.branch}")
            self.assertEqual(
                recovery._branch_has_unpushed_commits(
                    current.spec, current.issue_number,
                ),
                current.branch,
            )


class BranchTipShaRealGitTest(unittest.TestCase):
    """Direct coverage for `_branch_tip_sha`, the probe the discussion
    stage's round anchor is compared against. The stage tests mock it on
    this owner, so the real `rev-parse` args, the lock acquisition, and
    the missing-ref answer are only exercised here.
    """

    def test_returns_empty_when_branch_does_not_exist(self) -> None:
        with _temp_root("tip-noBranch-") as temp_root:
            target, _ = _seed_target_root(temp_root)
            self.assertEqual(
                recovery._branch_tip_sha(
                    _spec_for(target),
                    _issue_branch(MISSING_BRANCH_ISSUE_NUMBER, slug=REAL_GIT_SLUG),
                ),
                "",
            )

    def test_returns_the_named_branch_tip(self) -> None:
        with _temp_root("tip-named-") as temp_root:
            fixture = _seed_branch_fixture(
                temp_root,
                AHEAD_BRANCH_ISSUE_NUMBER,
                _issue_branch(AHEAD_BRANCH_ISSUE_NUMBER, slug=REAL_GIT_SLUG),
            )
            fixture.commit("agent commit")
            tip = _run_git(
                GIT_REV_PARSE, fixture.branch, cwd=fixture.target,
            ).stdout.strip()
            self.assertEqual(
                recovery._branch_tip_sha(fixture.spec, fixture.branch),
                tip,
            )
            self.assertNotEqual(tip, fixture.base_sha)

    def test_the_named_branch_answers_for_itself(self) -> None:
        # The issue's branch sits at base while another ref beside it carries
        # a commit. A probe that walked candidates would answer with whichever
        # it found first; the tip answered for is the branch the caller names,
        # which is the one its recorded anchor belongs to.
        with _temp_root("tip-named-pair-") as temp_root:
            namespaced = _issue_branch(
                DUAL_BRANCH_ISSUE_NUMBER, slug=REAL_GIT_SLUG,
            )
            anchored = _seed_branch_fixture(
                temp_root,
                DUAL_BRANCH_ISSUE_NUMBER,
                _flat_branch(DUAL_BRANCH_ISSUE_NUMBER),
            )
            _run_git(GIT_BRANCH, namespaced, anchored.base_sha, cwd=anchored.target)
            anchored.commit("discussion agent commit")

            self.assertEqual(
                recovery._branch_tip_sha(anchored.spec, namespaced),
                anchored.base_sha,
            )
            self.assertNotEqual(
                recovery._branch_tip_sha(anchored.spec, anchored.branch),
                anchored.base_sha,
            )


if __name__ == "__main__":
    unittest.main()
