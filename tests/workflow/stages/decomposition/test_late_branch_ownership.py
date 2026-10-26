# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a split's superseded-branch reclamation may take: the issue's own only.

The ledger names the branch, and the reclamation proves it the issue's before
spending a delete on it. These cases hold the two refusals a name alone cannot
settle: a branch another configured repository derives identically, driven
through the real umbrella handler, and a checkout at the issue's path that
stands on another branch or is reached through a symlink, driven against a
real clone.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.late_split.obligations import LateResourceState
from orchestrator.workflow.stages.decomposition import late_branch_reclamation as _late_branch_reclamation
from tests.support.foreign_checkouts import LINKED_CHECKOUT, LINKED_PARENT, LOOSE_CONTENT, foreign_checkout
from tests.workflow.fixtures import _TEST_SPEC, _PatchedWorkflowMixin
from tests.workflow.stages.decomposition import late_cleanup_support as _support

# A configured slug the sanitizer cannot tell from the test repository's own:
# both derive one branch segment and one checkout directory.
_COLLIDING_SLUG = "chippingway__chipping-orchestrator"

_ISSUE_NUMBER = 41

# The current-layout name the real clone's spec (`orch/realgit`) publishes the
# issue under, written out rather than derived.
_OWN_BRANCH = f"orchestrator/orch__realgit/issue-{_ISSUE_NUMBER}"


class CollidingRepositoryTest(_PatchedWorkflowMixin, unittest.TestCase):
    """A branch two configured repositories derive alike is neither's to delete."""

    def test_the_branch_is_kept_and_owed(self) -> None:
        # The ledger names this issue's exact branch, but another configured
        # entry derives it too, so it could be that entry's issue of the same
        # number: nothing is deleted, and the umbrella does not close over it.
        seeded = _support.split_umbrella(LateResourceState.PENDING)
        colliding = replace(_TEST_SPEC, slug=_COLLIDING_SLUG)

        with (
            patch.object(config, "_REPO_SPECS", [_TEST_SPEC, colliding]),
            self.assertLogs(_support.WORKFLOW_LOG, level="ERROR"),
        ):
            _support.walk_owner(self, seeded)

        self.assertEqual(seeded.github.deleted_remote_branches, [])
        self.assertFalse(seeded.parent.closed)
        self.assertEqual(
            _support.resource_states(seeded.github),
            {_support.SUPERSEDED_BRANCH: _support.STATE_FAILED},
        )


class ForeignCheckoutTest(unittest.TestCase):
    """The local half keeps a tree the issue's path reaches that is not its own."""

    def test_a_tree_not_the_issue_s_own_stays(self) -> None:
        # A checkout at the issue's path on the flat branch, and a flat
        # checkout on the issue's own branch that the path reaches through a
        # symlink, each with uncommitted work in it. The teardown of the
        # issue's own branch removes nothing there, and the obligation stays
        # owed rather than settled over a tree left standing.
        for link in ("", LINKED_CHECKOUT, LINKED_PARENT):
            with (
                self.subTest(link=link),
                foreign_checkout(_ISSUE_NUMBER, link) as foreign,
                self.assertLogs("orchestrator", level="WARNING"),
            ):
                gone = _late_branch_reclamation._local_gone(foreign.spec, _ISSUE_NUMBER, _OWN_BRANCH)

                self.assertFalse(gone)
                self.assertEqual(foreign.loose.read_text(), LOOSE_CONTENT)
                self.assertTrue(foreign.branch_present())


if __name__ == "__main__":
    unittest.main()
