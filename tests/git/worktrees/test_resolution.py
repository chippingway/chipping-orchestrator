# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The live branch resolver: the one name an issue owns, or a refusal."""

from __future__ import annotations

import unittest

from orchestrator.git.worktrees import naming as _naming
from orchestrator.github import pinned_refusal as _pinned_refusal
from tests.git.worktrees.path_test_support import (
    ALICE_REPO_SLUG,
    BRANCH_KEY,
    LEGACY_BRANCH,
    NAMESPACED_BRANCH,
    PR_NUMBER,
    _branch,
    _migration_spec,
    _state,
)

PR_NUMBER_KEY = "pr_number"
ISSUE_NUMBER = 7

# Records that name no branch live work may use, each beside the pull request
# a refusal has to hold still. The recorded pull request with no branch is the
# one an earlier resolver read as the flat `orchestrator/issue-<n>`; the rest
# are pins an `orchestrator/` prefix, a flat name, or a stray value would once
# have been honored on, or replaced with the derived name.
_REFUSED_RECORDS = (
    ("a pull request with no branch beside it", {PR_NUMBER_KEY: PR_NUMBER}),
    ("the flat branch beside a pull request", {PR_NUMBER_KEY: PR_NUMBER, BRANCH_KEY: LEGACY_BRANCH}),
    ("the flat branch alone", {BRANCH_KEY: LEGACY_BRANCH}),
    ("another repository's branch", {BRANCH_KEY: _branch(ALICE_REPO_SLUG, ISSUE_NUMBER)}),
    ("another issue's branch", {BRANCH_KEY: NAMESPACED_BRANCH.replace("issue-7", "issue-8")}),
    ("a name extending the current one", {BRANCH_KEY: f"{NAMESPACED_BRANCH}-candidate"}),
    ("a branch outside the namespace", {BRANCH_KEY: "feature/foreign-branch"}),
    ("an empty pin", {BRANCH_KEY: ""}),
    ("a pin that is no string", {BRANCH_KEY: PR_NUMBER}),
    ("a pin that is a list", {BRANCH_KEY: [NAMESPACED_BRANCH]}),
)


class ResolveBranchNameTest(unittest.TestCase):
    """Fresh work and a pinned current branch get the issue's own name."""

    def test_fresh_work_takes_the_current_layout(self) -> None:
        # Nothing pinned and no pull request recorded is the one record a name
        # is derived for, and the name is the one artifact ownership owns, so a
        # reclamation never refuses what a publication just made.
        spec = _migration_spec()
        for fresh in ({}, {BRANCH_KEY: None}):
            with self.subTest(record=fresh):
                self.assertEqual(
                    _naming._resolve_branch_name(_state(fresh), spec, ISSUE_NUMBER),
                    NAMESPACED_BRANCH,
                )
        self.assertEqual(_naming._branch_name(spec, ISSUE_NUMBER), NAMESPACED_BRANCH)

    def test_a_pinned_current_branch_round_trips(self) -> None:
        spec = _migration_spec()
        for pinned in (
            {BRANCH_KEY: NAMESPACED_BRANCH},
            {BRANCH_KEY: NAMESPACED_BRANCH, PR_NUMBER_KEY: PR_NUMBER},
        ):
            with self.subTest(record=pinned):
                self.assertEqual(
                    _naming._resolve_branch_name(_state(pinned), spec, ISSUE_NUMBER),
                    NAMESPACED_BRANCH,
                )
                self.assertEqual(
                    _naming._trusted_branch(_state(pinned), spec, ISSUE_NUMBER),
                    NAMESPACED_BRANCH,
                )


class BranchRefusalTest(unittest.TestCase):
    """A record naming no branch live work may use is refused, never replaced.

    No flat name is inferred from a recorded pull request, no `orchestrator/`
    prefix stands in for the exact name, and no derived name is substituted
    for a pin: each would point a checkout, a launch, or a push at a branch the
    record never named. The refusal is the record refusal the dispatcher
    abandons a handler on, and it is said once on the lifecycle channel.
    """

    def test_every_untrustworthy_record_is_refused(self) -> None:
        self.assertTrue(issubclass(_naming.BranchRefused, _pinned_refusal.RecordRefused))
        spec = _migration_spec()
        for described, record in _REFUSED_RECORDS:
            state = _state(record)
            with self.subTest(record=described), self.assertLogs(_naming.log, level="WARNING") as logged:
                self.assertRaises(
                    _naming.BranchRefused,
                    _naming._resolve_branch_name, state, spec, ISSUE_NUMBER,
                )
                self.assertIn(repr(record.get(BRANCH_KEY)), logged.output[0])
            self.assertIsNone(_naming._trusted_branch(state, spec, ISSUE_NUMBER))
            self.assertEqual(state.data, record, described)

if __name__ == "__main__":
    unittest.main()
