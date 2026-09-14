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
    _seed_branch_fixture,
    _temp_root,
)
from tests.support.git import (
    _run_git,
    _seed_target_root,
    _spec_for,
)
from tests.workflow.stages.question.question_test_support import (
    _issue_branch,
    _legacy_branch,
)

MISSING_BRANCH_ISSUE_NUMBER = 700
AHEAD_BRANCH_ISSUE_NUMBER = 702
LEGACY_BRANCH_ISSUE_NUMBER = 704
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

    def test_detects_legacy_issue_branch_commits(
        self,
    ) -> None:
        # Regression: a pre-slug-namespacing `question_commits` park
        # holds the question agent's commits on the legacy
        # `orchestrator/issue-N` ref. The pinned state never recorded
        # `branch` (question stage is read-only and never pushed), so
        # the resolver falls back to the slug-namespaced form -- but
        # that branch does not exist locally. Probing ONLY the
        # namespaced form would return None, the `_handle_implementing`
        # relabel guard would clear the park, `_ensure_worktree` would
        # reuse the on-disk worktree (still checked out on the legacy
        # branch), and the recovered-worktree shortcut would push the
        # question-agent commits as a fresh dev PR. The helper must
        # also probe the legacy ref and name it in the return value
        # so the operator hint targets the right branch.
        with tempfile.TemporaryDirectory(prefix="bhpc-legacy-") as td:
            fixture = _seed_branch_fixture(
                Path(td),
                LEGACY_BRANCH_ISSUE_NUMBER,
                _legacy_branch(LEGACY_BRANCH_ISSUE_NUMBER),
            )
            fixture.commit("stale question commit")
            # Slug-namespaced form does NOT exist; only the legacy
            # form does. Helper must still return the offending
            # branch name (the legacy ref) so the relabel guard fires.
            self.assertEqual(
                recovery._branch_has_unpushed_commits(
                    fixture.spec,
                    fixture.issue_number,
                ),
                fixture.branch,
            )

    def test_namespaced_branch_wins(self) -> None:
        # Both refs carry commits (a host-restart edge case where the
        # operator force-recreated the namespaced branch without
        # reaping the legacy one). The helper must report the
        # namespaced form first -- that is the branch the rest of the
        # tick will operate on, so it is the one the operator should
        # reset.
        with tempfile.TemporaryDirectory(prefix="bhpc-both-") as td:
            namespaced = _issue_branch(
                DUAL_BRANCH_ISSUE_NUMBER,
                slug=REAL_GIT_SLUG,
            )
            primary = _seed_branch_fixture(
                Path(td),
                DUAL_BRANCH_ISSUE_NUMBER,
                namespaced,
            )
            legacy = GitBranchFixture(
                target=primary.target,
                base_sha=primary.base_sha,
                issue_number=primary.issue_number,
                branch=_legacy_branch(primary.issue_number),
            )
            primary.commit(f"c on {primary.branch}")
            legacy.commit(f"c on {legacy.branch}")
            self.assertEqual(
                recovery._branch_has_unpushed_commits(
                    primary.spec,
                    primary.issue_number,
                ),
                namespaced,
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

    def test_a_legacy_branch_answers_for_itself(self) -> None:
        # Regression: an issue pinned to the legacy `orchestrator/issue-N`
        # ref opens its discussion round there while the slug-namespaced ref
        # exists beside it at base. A probe that walked candidates would
        # answer with the namespaced tip -- unchanged since the round opened
        # -- and the commit sitting on the legacy branch would go unreported,
        # to be adopted by the next round as its own baseline. The tip
        # answered for is the branch the caller names.
        with _temp_root("tip-legacy-") as temp_root:
            namespaced = _issue_branch(
                DUAL_BRANCH_ISSUE_NUMBER, slug=REAL_GIT_SLUG,
            )
            anchored = _seed_branch_fixture(
                temp_root,
                DUAL_BRANCH_ISSUE_NUMBER,
                _legacy_branch(DUAL_BRANCH_ISSUE_NUMBER),
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
