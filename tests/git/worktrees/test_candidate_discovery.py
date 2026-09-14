# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one issue's artifacts read as on a host and on the remote beside it.

The local scan already answers for what a host holds; what is pinned down here
is the half it cannot answer -- a branch this clone no longer has a ref for --
and the reading that says which layout an issue was published under.

Driven against real clones, real branches, real checkouts, and real bare
remotes, because every part of the question is something git answers: the
namespace listing, the ref store the local half is read from, the exact names
attribution re-derives and compares, and the git directory that says which
clone a checkout carrying no name at all is a worktree of. The multi-repository
cases are built both ways round for that last one -- two entries on one clone,
where the flat checkout is nobody's, and two entries on their own clones, where
each is answered for.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.git import ref_discovery
from orchestrator.git.worktrees import discovery, probes
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
from tests.git.worktrees.discovery_test_support import LIFECYCLE_LOGGER, _CloneOfAllBut, _DiscoveryTestCase
from tests.git.worktrees.eligibility_test_support import ISSUE_NUMBER

OTHER_ISSUE_NUMBER = 315
WARNING = "WARNING"
# The one name every layout this module builds shares.
LEGACY_BRANCH = _legacy_branch(ISSUE_NUMBER)


class CandidateLayoutTest(_DiscoveryTestCase):
    """Every shape one issue's artifacts can be found in reads as one candidate."""

    def test_a_checkout_and_branch_read_as_current(self) -> None:
        self.published()
        self.checkout()

        found = self.only_candidate()

        self.assertEqual(found.layout, CandidateLayout.CURRENT)
        self.assertEqual(found.artifacts.branches, (self.branch,))
        self.assertEqual(len(found.artifacts.worktrees), 1)

    def test_the_flat_name_reads_as_the_legacy_layout(self) -> None:
        legacy = LEGACY_BRANCH
        self.published(legacy)

        found = self.only_candidate()

        self.assertEqual(found.layout, CandidateLayout.LEGACY)
        self.assertEqual(found.artifacts.branches, (legacy,))

    def test_both_names_read_as_one_mixed_candidate(self) -> None:
        # A migration leaves an issue carrying both, and no single derivation
        # produces that pair -- so it is one issue with two names rather than
        # two candidates.
        legacy = LEGACY_BRANCH
        self.published()
        self.published(legacy)

        found = self.only_candidate()

        self.assertEqual(found.layout, CandidateLayout.MIXED)
        self.assertEqual(found.artifacts.branches, (self.branch, legacy))

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

    def test_a_local_and_a_remote_name_read_mixed(self) -> None:
        # The two halves are merged into one candidate in the order a teardown
        # takes them, whichever host each name was found on.
        legacy = LEGACY_BRANCH
        self.published()
        self.published(legacy)
        _branch_at(self.clone, legacy, None)

        found = self.only_candidate()

        self.assertEqual(found.layout, CandidateLayout.MIXED)
        self.assertEqual(found.artifacts.branches, (self.branch, legacy))


class LegacyCheckoutTest(_DiscoveryTestCase):
    """The checkout layout that had no per-repository parent is found too.

    A host that has been running since before the slug went into the path is
    still holding `WORKTREES_DIR/issue-<n>` directories. Nothing writes there
    now, so the only thing that will ever take one down is a teardown that can
    see it -- and one that cleared the branches while leaving the tree would
    take the last artifact any later discovery could have found it by.
    """

    def test_a_flat_checkout_is_the_whole_candidate(self) -> None:
        # The shape a host that was mid-issue at the migration is left in, once
        # its branch has gone: the flat directory is the only thing here naming
        # the issue, and it still makes a candidate.
        legacy = LEGACY_BRANCH
        self.published(legacy)
        worktree = self.legacy_checkout(legacy)

        found = self.only_candidate()

        self.assertEqual(found.layout, CandidateLayout.LEGACY)
        self.assertEqual(found.artifacts.worktrees, (worktree,))
        self.assertEqual(found.artifacts.branches, (legacy,))

    def test_both_checkout_layouts_read_as_one(self) -> None:
        # What the migration really left: the flat checkout the issue started
        # in and the per-repository one the next tick made, current-first and
        # under one candidate rather than two.
        legacy = LEGACY_BRANCH
        _branch_at(self.clone, legacy, self.published())
        current = self.checkout()
        flat = self.legacy_checkout(legacy)

        found = self.only_candidate()

        self.assertEqual(found.layout, CandidateLayout.MIXED)
        self.assertEqual(found.artifacts.worktrees, (current, flat))


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
    """A flat checkout is attributed by the clone it is a worktree of.

    Its name says nothing -- every configured entry derived
    `WORKTREES_DIR/issue-<n>` identically -- but the directory itself is a
    worktree of exactly one repository, and on a host whose entries keep their
    own clones that settles it. Refusing here instead would leave the checkout
    where it is with nothing left to find it by once its branches have gone.
    """

    def setUp(self) -> None:
        super().setUp()
        self.specs = (self.spec, self.sibling_on_its_own_clone())

    def test_a_flat_checkout_belongs_to_its_own_clone(self) -> None:
        legacy = LEGACY_BRANCH
        self.published(legacy)
        worktree = self.legacy_checkout(legacy)

        found = self.only_candidate(self.specs)

        self.assertEqual(found.artifacts.spec.slug, WIDGET_SLUG)
        self.assertEqual(found.artifacts.worktrees, (worktree,))
        self.assertEqual(found.layout, CandidateLayout.LEGACY)


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
        legacy = LEGACY_BRANCH

        with self.assertLogs(LIFECYCLE_LOGGER, level=WARNING):
            self.published(legacy)
            found = self.discovered(self.specs)

        self.assertEqual(found, ())

    def test_a_shared_flat_name_out_there_is_too(self) -> None:
        legacy = LEGACY_BRANCH
        self.published(legacy)
        _branch_at(self.clone, legacy, None)

        self.assertEqual(self.discovered(self.specs), ())

    def test_each_repository_answers_for_its_own(self) -> None:
        self.published()
        _branch_at(self.clone, self.branch, None)

        found = self.only_candidate(self.specs)

        self.assertEqual(found.artifacts.spec.slug, WIDGET_SLUG)
        self.assertEqual(found.layout, CandidateLayout.REMOTE_ONLY)

    def test_a_shared_flat_checkout_withholds_it_all(self) -> None:
        # The path counterpart of the flat branch rule, and it is wider: the
        # flat checkout sits under a directory every entry shares, so a second
        # configured repository is enough to make it unattributable. What it
        # takes with it is the whole issue -- the branch that tree is standing
        # on included, on this host and on the remote.
        self.published()
        self.legacy_checkout()

        with self.assertLogs(LIFECYCLE_LOGGER, level=WARNING):
            found = self.discovered(self.specs)

        self.assertEqual(found, ())

    def test_a_sibling_s_name_here_is_not_ours(self) -> None:
        # A branch spelled for the other entry that turned up on this remote is
        # evidence about neither: this repository never published it, and the
        # other one never published it HERE.
        sibling_branch = _namespaced_branch(GADGET_SLUG, ISSUE_NUMBER)
        self.published(sibling_branch)
        _branch_at(self.clone, sibling_branch, None)

        found = self.discovered((self.spec,))

        self.assertEqual(found, ())


class UnreadableCloneTest(_DiscoveryTestCase):
    """An entry whose own clone will not answer still claims a flat checkout.

    The identity read is what makes a flat checkout attributable at all, so a
    configured repository it could not be taken for is one nothing ruled out.
    Dropping such an entry from the claimants is how a checkout on a shared
    clone reads as uniquely owned -- the sibling that would have made it
    ambiguous simply did not answer.
    """

    def test_an_unreadable_sibling_still_claims_it(self) -> None:
        sibling = self.sibling_on_this_clone()
        self.landed()
        self.legacy_checkout()

        with (
            patch.object(
                probes,
                "_checkout_clone",
                side_effect=_CloneOfAllBut(sibling),
            ),
            self.assertLogs(LIFECYCLE_LOGGER, level=WARNING),
        ):
            found = self.discovered((self.spec, sibling))

        self.assertEqual(found, ())

    def test_a_lone_unread_entry_still_claims_it(self) -> None:
        # One configured repository, and nothing established that the tree is
        # its worktree: an attribution here would be a guess about the one
        # artifact whose name says nothing at all.
        self.landed()
        self.legacy_checkout()

        with (
            patch.object(
                probes,
                "_checkout_clone",
                side_effect=_CloneOfAllBut(self.spec),
            ),
            self.assertLogs(LIFECYCLE_LOGGER, level=WARNING),
        ):
            found = self.discovered()

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
