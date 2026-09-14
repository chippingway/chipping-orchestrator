# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Slug sanitization plus worktree path and branch derivation."""

from __future__ import annotations

import unittest
from pathlib import Path

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import naming as _naming, paths
from tests.git.worktrees.path_test_support import (
    ALICE_REPO_SLUG,
    BASE_BRANCH,
    BOB_REPO_SLUG,
    PR_NUMBER,
    SHARED_BRANCH_ISSUE_NUMBER,
    _migration_spec,
    _spec,
)

SHARED_CLONE_ROOT = Path("/tmp/shared-clone")

# One issue number per digit count a real repository reaches, so the round trip
# is not asserted on a single-digit case alone.
ROUND_TRIP_ISSUE_NUMBERS = (1, 42, 1484)

# The two digit runs a name can carry that no issue number does: one digit past
# the width a name is read as an issue at, and enough digits that converting
# them is what raises rather than what answers.
OVER_WIDTH_DIGIT_COUNT = 19
UNCONVERTIBLE_DIGIT_COUNT = 5000
OVER_WIDTH_DIGITS = "9" * OVER_WIDTH_DIGIT_COUNT
UNCONVERTIBLE_DIGITS = "9" * UNCONVERTIBLE_DIGIT_COUNT


class WorktreePathSlugNamespaceTest(unittest.TestCase):
    """Two repos with the same issue number must produce distinct worktree
    paths, otherwise simultaneous orchestration of both would have them
    fighting over the same `WORKTREES_DIR/issue-N` checkout. The slug
    sanitizer also has to produce a single filesystem-safe segment
    (no `/`, no leading `.`) since it becomes a directory name.
    """

    def test_distinct_slugs_same_number_never_collide(self) -> None:
        spec_a = _spec(ALICE_REPO_SLUG)
        spec_b = _spec(BOB_REPO_SLUG)
        path_a = paths._worktree_path(spec_a, 7)
        path_b = paths._worktree_path(spec_b, 7)

        self.assertNotEqual(path_a, path_b)
        # Both must live under WORKTREES_DIR with the issue-N leaf.
        self.assertEqual(path_a.name, "issue-7")
        self.assertEqual(path_b.name, "issue-7")
        self.assertEqual(path_a.parent.parent, config.WORKTREES_DIR)
        self.assertEqual(path_b.parent.parent, config.WORKTREES_DIR)


class SanitizeSlugTest(unittest.TestCase):
    def test_sanitize_slug_replaces_owner_separator(self) -> None:
        self.assertEqual(_naming._sanitize_slug("owner/name"), "owner__name")

    def test_sanitize_slug_is_a_single_segment(self) -> None:
        # A directory name with `/` would split into nested directories,
        # defeating the point of namespacing.
        for raw in (
            "owner/name",
            "deep/owner/name",
            "name-only",
            "weird name with spaces",
        ):
            cleaned = _naming._sanitize_slug(raw)
            self.assertNotIn("/", cleaned, f"slug={raw!r} -> {cleaned!r}")

    def test_sanitize_slug_no_leading_dot(self) -> None:
        # Hidden directories (.foo) hide the worktree from a casual
        # operator inspection; escape leading dots.
        self.assertFalse(_naming._sanitize_slug(".dotfile/repo").startswith("."))
        self.assertFalse(_naming._sanitize_slug("./repo").startswith("."))

    def test_sanitize_slug_strips_unsafe_chars(self) -> None:
        cleaned = _naming._sanitize_slug("owner@#$/name with spaces")
        # No path separator, no shell-special chars; only [A-Za-z0-9_.-]
        for ch in cleaned:
            self.assertTrue(
                ch.isalnum() or ch in "_.-",
                f"unexpected char {ch!r} in {cleaned!r}",
            )

    def test_sanitize_slug_empty_input_falls_back(self) -> None:
        # Empty would collapse `WORKTREES_DIR/<slug>/issue-N` into
        # `WORKTREES_DIR/issue-N`, reintroducing the cross-repo collision.
        self.assertNotEqual(_naming._sanitize_slug(""), "")
        self.assertNotEqual(_naming._sanitize_slug(""), ".")

    def test_default_repo_spec_path_format(self) -> None:
        # Anchor the documented `<owner>__<name>/issue-N` layout.
        path = paths._worktree_path(_migration_spec(), 9)
        self.assertEqual(
            path,
            config.WORKTREES_DIR / "chippingway__orchestrator" / "issue-9",
        )


class BranchNameSlugNamespaceTest(unittest.TestCase):
    """Two RepoSpecs that share the same `target_root` (a single local
    clone with multiple remotes) would otherwise collide on
    `orchestrator/issue-N` because git refuses to check the same branch
    out in two worktrees of one repo. `_branch_name` includes the
    sanitized slug so each spec lives on its own branch.
    """

    def test_same_number_distinct_slugs_make_branches(self) -> None:
        spec_a = _config_models.RepoSpec(
            slug="geserdugarov/lance-open-source",
            target_root=SHARED_CLONE_ROOT,
            base_branch=BASE_BRANCH,
        )
        spec_b = _config_models.RepoSpec(
            slug="geserdugarov/lance-private",
            target_root=SHARED_CLONE_ROOT,
            base_branch=BASE_BRANCH,
        )

        self.assertNotEqual(
            _naming._branch_name(spec_a, SHARED_BRANCH_ISSUE_NUMBER),
            _naming._branch_name(spec_b, SHARED_BRANCH_ISSUE_NUMBER),
        )

    def test_branch_name_format(self) -> None:
        self.assertEqual(
            _naming._branch_name(_migration_spec(), 9),
            "orchestrator/chippingway__orchestrator/issue-9",
        )

    def test_branch_name_keeps_orchestrator_prefix(self) -> None:
        # `_cleanup_terminal_branch` relies on the `orchestrator/` prefix
        # to constrain what branches it is willing to delete.
        for repo_slug in (ALICE_REPO_SLUG, BOB_REPO_SLUG, "weird name/x"):
            self.assertTrue(
                _naming._branch_name(
                    _spec(repo_slug), PR_NUMBER,
                ).startswith("orchestrator/"),
                repo_slug,
            )


class IssueSegmentNumberTest(unittest.TestCase):
    """The `issue-<n>` tail read back off a name that already exists.

    A reader of a worktree directory or a local branch has only the name to go
    on, so what this refuses is what keeps a name nothing here published from
    arriving at a caller as a claim on an issue.
    """

    def test_it_reads_back_what_the_derivations_write(self) -> None:
        # The pair that must not drift: every name built for an issue ends in
        # the tail this reads, so the round trip is the contract.
        for issue_number in ROUND_TRIP_ISSUE_NUMBERS:
            with self.subTest(issue_number=issue_number):
                built = paths._worktree_path(_migration_spec(), issue_number)
                self.assertEqual(
                    paths._issue_segment_number(built.name), issue_number,
                )
                branch = _naming._branch_name(_migration_spec(), issue_number)
                self.assertEqual(
                    paths._issue_segment_number(branch.rsplit("/", 1)[-1]),
                    issue_number,
                )

    def test_a_spelling_nothing_writes_is_no_issue(self) -> None:
        # `int()` answers 7 for the first three of these, which would turn
        # three names this orchestrator never wrote into a claim on issue #7 --
        # and it does not answer the last two at all: a run of digits past its
        # conversion ceiling raises, which is how a name in a ref store nobody
        # controls would end a read instead of being passed over by it.
        for segment in (
            "issue-007",
            "issue-+7",
            "issue- 7",
            "issue-0",
            "issue-",
            "issue-7-fixup",
            "issue-7/tail",
            "decompose-7",
            "ISSUE-7",
            "",
            f"issue-{OVER_WIDTH_DIGITS}",
            f"issue-{UNCONVERTIBLE_DIGITS}",
        ):
            with self.subTest(segment=segment):
                self.assertIsNone(paths._issue_segment_number(segment))


if __name__ == "__main__":
    unittest.main()
