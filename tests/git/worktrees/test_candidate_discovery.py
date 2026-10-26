# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one issue's artifacts read as on a host and on the remote beside it.

The local scan already answers for what a host holds; what is pinned down here
is the half it cannot answer -- a branch this clone no longer has a ref for --
and the reading that says whether anything of the issue is left locally.

Driven against real clones, real branches, real checkouts, and real bare
remotes, because every part of the question is something git answers: the
namespace listing, the ref store the local half is read from, and the exact
names attribution re-derives and compares. The flat names and checkouts an
earlier layout left are planted beside the current ones on both kinds of host
-- two entries on one clone, and two entries on their own clones -- and are
nobody's candidate on either.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.git import ref_discovery
from orchestrator.git.worktrees import discovery
from orchestrator.git.worktrees.candidates import CandidateLayout
from tests.git.worktrees.artifact_test_support import (
    GADGET_SLUG,
    WIDGET_SLUG,
    _legacy_branch,
    _namespaced_branch,
    _spec,
)
from tests.git.worktrees.candidate_refs import _branch_at
from tests.git.worktrees.discovery_host import SIBLING_REMOTE_DIR
from tests.git.worktrees.discovery_test_support import LIFECYCLE_LOGGER, _DiscoveryTestCase
from tests.git.worktrees.eligibility_test_support import ISSUE_NUMBER

OTHER_ISSUE_NUMBER = 315
WARNING = "WARNING"
# The one name every layout this module builds shares.
LEGACY_BRANCH = _legacy_branch(ISSUE_NUMBER)


class CandidateLayoutTest(_DiscoveryTestCase):
    """Every shape one issue's current artifacts can be found in reads as one candidate."""

    def test_a_checkout_and_branch_read_as_current(self) -> None:
        self.published()
        self.checkout()

        found = self.only_candidate()

        self.assertEqual(found.layout, CandidateLayout.CURRENT)
        self.assertEqual(found.artifacts.branches, (self.branch,))
        self.assertEqual(len(found.artifacts.worktrees), 1)

    def test_a_flat_name_is_no_candidate(self) -> None:
        # Published and held locally, or left only on the remote: no
        # configured repository derives the name, so nothing is found for it.
        self.published(LEGACY_BRANCH)
        for local in (True, False):
            if not local:
                _branch_at(self.clone, LEGACY_BRANCH, None)
            with self.subTest(local=local):
                self.assertEqual(self.discovered(), ())

    def test_a_mixed_layout_keeps_the_current_name(self) -> None:
        # A migration leaves an issue carrying both names, locally or only on
        # the remote. The candidate is the current one alone; the flat name
        # beside it is no artifact of the issue's.
        self.published()
        self.published(LEGACY_BRANCH)
        for local in (True, False):
            if not local:
                _branch_at(self.clone, LEGACY_BRANCH, None)
            with self.subTest(local=local):
                found = self.only_candidate()

                self.assertEqual(found.layout, CandidateLayout.CURRENT)
                self.assertEqual(found.artifacts.branches, (self.branch,))

    def test_a_branch_only_out_there_reads_remote(self) -> None:
        # The whole reason this discovery is wider than the scan: the clone was
        # rebuilt, or the ref deleted by hand, and the work is still published.
        self.published()
        _branch_at(self.clone, self.branch, None)

        found = self.only_candidate()

        self.assertEqual(found.layout, CandidateLayout.REMOTE_ONLY)
        self.assertEqual(found.artifacts.branches, (self.branch,))
        self.assertEqual(found.artifacts.worktrees, ())

    def test_a_checkout_with_no_branch_is_current(self) -> None:
        # Nothing is remote-only while this host still has something to look
        # at, whatever is left of the branch that named it.
        self.published()
        worktree = self.checkout()
        _branch_at(self.clone, self.branch, None)
        self.world.unpublish(self.clone, self.branch)

        found = self.only_candidate()

        self.assertEqual(found.layout, CandidateLayout.CURRENT)
        self.assertEqual(found.artifacts.branches, ())
        self.assertEqual(found.artifacts.worktrees, (worktree,))


class FlatCheckoutTest(_DiscoveryTestCase):
    """The checkout layout that had no per-repository parent is nobody's.

    A host that has been running since before the slug went into the path can
    still hold `WORKTREES_DIR/issue-<n>` directories. No configured entry
    derives that path, so it never becomes a candidate and is left on disk for
    manual disposition.
    """

    def test_a_flat_checkout_is_no_candidate(self) -> None:
        self.published(LEGACY_BRANCH)
        flat = self.legacy_checkout(LEGACY_BRANCH)

        self.assertEqual(self.discovered(), ())
        self.assertTrue(flat.exists())

    def test_mixed_checkouts_keep_the_current_one(self) -> None:
        # The flat checkout the issue started in beside the per-repository one
        # the next tick made: the candidate is the current checkout and branch.
        _branch_at(self.clone, LEGACY_BRANCH, self.published())
        current = self.checkout()
        self.legacy_checkout(LEGACY_BRANCH)

        found = self.only_candidate()

        self.assertEqual(found.layout, CandidateLayout.CURRENT)
        self.assertEqual(found.artifacts.worktrees, (current,))
        self.assertEqual(found.artifacts.branches, (self.branch,))


class CandidateOrderTest(_DiscoveryTestCase):
    """Two discoveries of one unchanged world are the same answer."""

    def test_candidates_are_ordered_by_issue(self) -> None:
        self.published()
        self.published(_namespaced_branch(WIDGET_SLUG, OTHER_ISSUE_NUMBER))
        _branch_at(
            self.clone, _namespaced_branch(WIDGET_SLUG, OTHER_ISSUE_NUMBER),
            None,
        )

        found = self.discovered()

        self.assertEqual(
            tuple(
                candidate.artifacts.issue_number for candidate in found
            ),
            (ISSUE_NUMBER, OTHER_ISSUE_NUMBER),
        )


class DistinctCloneDiscoveryTest(_DiscoveryTestCase):
    """A flat checkout is nobody's even where its clone is one entry's alone.

    The directory is a worktree of exactly one configured repository's clone,
    and that settles nothing: being the only possible owner is no ownership
    evidence, so the checkout is left for manual disposition.
    """

    def setUp(self) -> None:
        super().setUp()
        self.specs = (self.spec, self.sibling_on_its_own_clone())

    def test_a_flat_checkout_there_is_nobody_s(self) -> None:
        self.published(LEGACY_BRANCH)
        self.legacy_checkout(LEGACY_BRANCH)

        self.assertEqual(self.discovered(self.specs), ())


class SharedCloneDiscoveryTest(_DiscoveryTestCase):
    """A name two repositories could own is charged to neither of them.

    The remote says which repository a branch was pushed to, and that is not
    the question: the local ref of that name is what a teardown goes on to
    delete, and on a shared clone nothing says which entry created it.
    """

    def setUp(self) -> None:
        super().setUp()
        self.sibling = _spec(GADGET_SLUG, self.clone)
        self.world.serve_beside(self.sibling, SIBLING_REMOTE_DIR)
        self.specs = (self.spec, self.sibling)

    def test_a_shared_flat_name_is_nobody_s(self) -> None:
        # Here or only out there, the flat name is no entry's derivation.
        self.published(LEGACY_BRANCH)
        for local in (True, False):
            if not local:
                _branch_at(self.clone, LEGACY_BRANCH, None)
            with self.subTest(local=local):
                self.assertEqual(self.discovered(self.specs), ())

    def test_each_repository_answers_for_its_own(self) -> None:
        self.published()
        _branch_at(self.clone, self.branch, None)

        found = self.only_candidate(self.specs)

        self.assertEqual(found.artifacts.spec.slug, WIDGET_SLUG)
        self.assertEqual(found.layout, CandidateLayout.REMOTE_ONLY)

    def test_a_shared_flat_checkout_is_not_reported(self) -> None:
        # A flat checkout standing on this issue's current branch: the branch is
        # still the issue's candidate, and the tree is no part of it. What
        # keeps that branch while the tree stands on it is the teardown's own
        # checkout listing, not the scan.
        self.published()
        self.legacy_checkout()

        found = self.only_candidate(self.specs)

        self.assertEqual(found.artifacts.branches, (self.branch,))
        self.assertEqual(found.artifacts.worktrees, ())

    def test_a_sibling_s_name_here_is_not_ours(self) -> None:
        # A branch spelled for the other entry that turned up on this remote is
        # evidence about neither: this repository never published it, and the
        # other one never published it HERE.
        sibling_branch = _namespaced_branch(GADGET_SLUG, ISSUE_NUMBER)
        self.published(sibling_branch)
        _branch_at(self.clone, sibling_branch, None)

        found = self.discovered((self.spec,))

        self.assertEqual(found, ())


class UnreachableRemoteTest(_DiscoveryTestCase):
    """A repository whose remote will not answer is left out entirely."""

    def test_an_unreachable_remote_refuses_it_all(self) -> None:
        # Every question asked after this one goes to the same remote, so
        # reporting the local half alone would hand out a picture of a host
        # that nothing could act on.
        self.published()
        self.checkout()
        self.world.unreachable(self.spec)

        with self.assertLogs(LIFECYCLE_LOGGER, level=WARNING):
            scanned = discovery._maintenance_candidates((self.spec,))

        self.assertEqual(scanned.candidates, ())
        self.assertEqual(scanned.refused, (WIDGET_SLUG,))

    def test_a_transport_that_raises_only_refuses(self) -> None:
        # The transport answers None for what it recognizes and raises for what
        # is underneath it; an exception out of one repository's listing would
        # otherwise take every other repository in the discovery with it.
        self.published()

        with (
            patch.object(
                ref_discovery,
                "_remote_ref_names",
                side_effect=OSError("git could not be spawned"),
            ),
            self.assertLogs(LIFECYCLE_LOGGER, level=WARNING),
        ):
            scanned = discovery._maintenance_candidates((self.spec,))

        self.assertEqual(scanned.candidates, ())
        self.assertEqual(scanned.refused, (WIDGET_SLUG,))

    def test_an_empty_remote_is_not_a_refusal(self) -> None:
        # The empty listing is an answer: this repository has published
        # nothing that is still out there, and what the host holds is reported
        # exactly as it stands.
        self.world.commit_on(self.clone, self.branch)
        worktree = self.checkout()

        scanned = discovery._maintenance_candidates((self.spec,))

        self.assertEqual(scanned.refused, ())
        self.assertEqual(len(scanned.candidates), 1)
        self.assertEqual(
            scanned.candidates[0].artifacts.worktrees, (worktree,),
        )
        self.assertEqual(
            scanned.candidates[0].artifacts.branches, (self.branch,),
        )


if __name__ == "__main__":
    unittest.main()
