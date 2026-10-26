# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which repository a local branch is charged to, and which are charged to nobody."""

from __future__ import annotations

import logging
import unittest
from pathlib import Path

from orchestrator.git.worktrees import attribution
from tests.git.worktrees.artifact_test_support import (
    COLLIDING_SLUGS,
    GADGET_SLUG,
    LIFECYCLE_LOGGER,
    STRANGER_SLUG,
    WIDGET_SLUG,
    _legacy_branch,
    _namespaced_branch,
    _spec,
)

SHARED_CLONE = Path("/tmp/orchestrator-attribution-clone")

BRANCH_ISSUE_NUMBER = 4
LEGACY_ISSUE_NUMBER = 9
BOTH_LAYOUTS_ISSUE_NUMBER = 7
COLLIDING_ISSUE_NUMBER = 3

# Names that live in the orchestrator-owned namespace and belong to none of the
# configured repositories: another repository's segment, a segment no entry
# produces, issue numbers written in forms nothing here writes, a tail buried
# one component too deep, one component too shallow, and a branch that names no
# issue at all.
UNOWNED_BRANCHES = (
    _namespaced_branch(STRANGER_SLUG, 3),
    "orchestrator/acme__gizmo/issue-3",
    "orchestrator/issue-007",
    "orchestrator/issue-0",
    "orchestrator/issue-+3",
    "orchestrator/issue-abc",
    "orchestrator/acme__widget/deep/issue-3",
    "orchestrator/acme__widget/issue-3/tail",
    "orchestrator/issue-3-fixup",
    "orchestrator/main",
)


class CurrentLayoutTest(unittest.TestCase):
    """A namespaced branch is charged to the repository that publishes it.

    The case a shared clone exists for: both repositories' branches sit in one
    ref store, and each name says which of them wrote it.
    """

    def test_each_repository_gets_its_own(self) -> None:
        widget = _spec(WIDGET_SLUG, SHARED_CLONE)
        gadget = _spec(GADGET_SLUG, SHARED_CLONE)
        widget_branch = _namespaced_branch(WIDGET_SLUG, BRANCH_ISSUE_NUMBER)
        gadget_branch = _namespaced_branch(GADGET_SLUG, BRANCH_ISSUE_NUMBER)

        owned = attribution._attributed_issues(
            (widget_branch, gadget_branch), (widget, gadget),
        )

        self.assertEqual(owned, {
            widget: {BRANCH_ISSUE_NUMBER: (widget_branch,)},
            gadget: {BRANCH_ISSUE_NUMBER: (gadget_branch,)},
        })

    def test_a_repository_with_none_is_absent(self) -> None:
        # An empty entry and a missing one read differently to a caller
        # walking the answer, so a repository nothing was found for is simply
        # not in it.
        widget = _spec(WIDGET_SLUG, SHARED_CLONE)
        gadget = _spec(GADGET_SLUG, SHARED_CLONE)

        owned = attribution._attributed_issues(
            (_namespaced_branch(WIDGET_SLUG, BRANCH_ISSUE_NUMBER),),
            (widget, gadget),
        )

        self.assertEqual(tuple(owned), (widget,))


class FlatLayoutTest(unittest.TestCase):
    """The flat pre-namespacing branch carries no slug, so nobody owns it.

    Not even a repository alone on its clone: being the only claimant is no
    ownership evidence, and a branch attributed that way is one a teardown
    would go on to delete.
    """

    def test_no_repository_owns_it(self) -> None:
        widget = _spec(WIDGET_SLUG, SHARED_CLONE)
        gadget = _spec(GADGET_SLUG, SHARED_CLONE)
        legacy = _legacy_branch(LEGACY_ISSUE_NUMBER)
        for specs in ((widget,), (widget, gadget)):
            with self.subTest(claimants=len(specs)):
                self.assertEqual(
                    attribution._attributed_issues((legacy,), specs), {},
                )

    def test_a_mixed_layout_keeps_the_current_name(self) -> None:
        # An issue migrated mid-flight has a branch under each layout. The
        # namespaced one is the issue's; the flat one beside it stays nobody's.
        widget = _spec(WIDGET_SLUG, SHARED_CLONE)
        namespaced = _namespaced_branch(WIDGET_SLUG, BOTH_LAYOUTS_ISSUE_NUMBER)
        legacy = _legacy_branch(BOTH_LAYOUTS_ISSUE_NUMBER)

        owned = attribution._attributed_issues((legacy, namespaced), (widget,))

        self.assertEqual(
            owned, {widget: {BOTH_LAYOUTS_ISSUE_NUMBER: (namespaced,)}},
        )


class UnattributableBranchTest(unittest.TestCase):
    """Everything else in the namespace is left where it was found."""

    def test_names_nothing_publishes_are_left(self) -> None:
        widget = _spec(WIDGET_SLUG, SHARED_CLONE)
        for branch in UNOWNED_BRANCHES:
            with self.subTest(branch=branch):
                self.assertEqual(
                    attribution._attributed_issues((branch,), (widget,)), {},
                )

    def test_two_repositories_deriving_one(self) -> None:
        # Two `REPOS` entries whose slugs differ only in a character the ref
        # sanitizer rewrites publish under one branch name, and nothing in that
        # name says which of them wrote it. Both claimants are named.
        specs = tuple(_spec(slug, SHARED_CLONE) for slug in COLLIDING_SLUGS)

        with self.assertLogs(LIFECYCLE_LOGGER, logging.WARNING) as logs:
            owned = attribution._attributed_issues(
                (_namespaced_branch(COLLIDING_SLUGS[1], COLLIDING_ISSUE_NUMBER),),
                specs,
            )
            refusal = logs.output[0]

        self.assertEqual(owned, {})
        for slug in COLLIDING_SLUGS:
            self.assertIn(slug, refusal)


if __name__ == "__main__":
    unittest.main()
