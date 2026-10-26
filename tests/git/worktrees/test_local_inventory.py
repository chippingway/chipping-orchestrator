# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The read-only scan: which issues a host's own artifacts name, and which it refuses.

Which clone a repository is read from and what a failed read costs are driven
with the branch listing stubbed on its owner, because neither turns on what
the listing says. What a candidate is made of is driven against real clones,
real branches, and real checkouts instead: the shapes an issue can be in are
exactly what the arguments, the attribution, and the on-disk layout produce
together, so a stub of any of them would assert itself back.
"""

from __future__ import annotations

import logging
import unittest

from orchestrator.git.worktrees import paths
from tests.git.worktrees import artifact_test_support as _support, local_inventory_test_support as _inventory_support
from tests.git.worktrees.artifact_test_support import _ArtifactWorld
from tests.support.git import _run_git

CLONE_NAME = "target"
SECOND_CLONE_NAME = "other-target"
CLONE_LINK_NAME = "target-link"
LINKED_TARGET_NAME = "target-linked-worktree"
NO_CLONE_NAME = "never-cloned"

BOTH_SIDES_ISSUE_NUMBER = 4
CHECKOUT_ONLY_ISSUE_NUMBER = 15
LEGACY_ISSUE_NUMBER = 9
GADGET_ISSUE_NUMBER = 6
COLLIDING_ISSUE_NUMBER = 3

# One branch each for the two entries a clone-grouping case configures.
ONE_EACH_BRANCHES = (
    _support._namespaced_branch(_support.WIDGET_SLUG, BOTH_SIDES_ISSUE_NUMBER),
    _support._namespaced_branch(_support.GADGET_SLUG, GADGET_ISSUE_NUMBER),
)

# What the scan must walk past: another repository's namespaced branch, a name
# in the namespace that carries no issue number at all, and the flat name an
# earlier layout left, which no configured repository derives.
IGNORED_BRANCHES = (
    "orchestrator/stranger__repo/issue-5",
    "orchestrator/issue-abc",
    _support._legacy_branch(LEGACY_ISSUE_NUMBER),
)


class CloneGroupingTest(unittest.TestCase):
    """Which clone a repository's branches are read from, and how often."""

    def setUp(self) -> None:
        self.world = _ArtifactWorld()
        self.world.prepare(self)
        self.clone = self.world.clone(CLONE_NAME)
        self.widget = _support._spec(_support.WIDGET_SLUG, self.clone)

    def test_one_listing_serves_a_clone(self) -> None:
        # The specs sharing a clone share its ref store, so a second listing
        # would spend a git process to read the same refs back.
        gadget = _support._spec(_support.GADGET_SLUG, self.clone)

        with _inventory_support._listing(()) as listed:
            _inventory_support._scan(self.widget, gadget)
            listed.assert_called_once_with(self.clone)

    def test_one_clone_under_two_paths_is_one(self) -> None:
        # One clone reached by another path -- a symlink to it, or a linked
        # worktree of it configured as a target of its own -- is still one ref
        # store, so it is read once and every branch on it is put to both
        # entries together.
        link = self.world.path(CLONE_LINK_NAME)
        link.symlink_to(self.clone)
        linked = self.world.path(LINKED_TARGET_NAME)
        _run_git("worktree", "add", "-q", "--detach", str(linked), "HEAD", cwd=self.clone)

        for path in (link, linked):
            with self.subTest(path=path.name), _inventory_support._listing(ONE_EACH_BRANCHES) as listed:
                scanned = _inventory_support._scan(self.widget, _support._spec(_support.GADGET_SLUG, path))
                listed.assert_called_once()

                self.assertEqual(_inventory_support._found(scanned), (
                    (_support.GADGET_SLUG, GADGET_ISSUE_NUMBER),
                    (_support.WIDGET_SLUG, BOTH_SIDES_ISSUE_NUMBER),
                ))
                self.assertEqual(scanned.refused, ())


class LocalInventoryRefusalTest(unittest.TestCase):
    """What one read that could not be taken costs the rest of the answer."""

    def setUp(self) -> None:
        self.world = _ArtifactWorld()
        self.world.prepare(self)
        self.clone = self.world.clone(CLONE_NAME)
        self.widget = _support._spec(_support.WIDGET_SLUG, self.clone)

    def test_an_unread_clone_refuses_all_of_it(self) -> None:
        # The checkout is right there on disk and is still not reported: what
        # a caller does with an issue turns on whether a branch is under it,
        # and an unread ref store cannot say.
        gadget = _support._spec(_support.GADGET_SLUG, self.clone)
        self.world.checkout(self.widget, BOTH_SIDES_ISSUE_NUMBER)

        with _inventory_support._listing(None):
            scanned = _inventory_support._scan(self.widget, gadget)

        self.assertEqual(scanned.issues, ())
        self.assertEqual(scanned.refused, (_support.GADGET_SLUG, _support.WIDGET_SLUG))

    def test_an_unresolvable_clone_refuses_one(self) -> None:
        # The refusal has to come from the grouping too: resolution runs
        # before a single repository has been read, so a root that cannot be
        # resolved would otherwise end the scan for the healthy ones with it.
        gadget = _support._spec(_support.GADGET_SLUG, self.world.clone(SECOND_CLONE_NAME))
        self.world.checkout(gadget, GADGET_ISSUE_NUMBER)
        widget = _support._spec(_support.WIDGET_SLUG, _inventory_support._LoopingPath(self.clone))

        with self.assertLogs(_support.LIFECYCLE_LOGGER, logging.WARNING), _inventory_support._listing(()):
            scanned = _inventory_support._scan(widget, gadget)

        self.assertEqual(scanned.refused, (_support.WIDGET_SLUG,))
        self.assertEqual(_inventory_support._found(scanned), ((_support.GADGET_SLUG, GADGET_ISSUE_NUMBER),))

    def test_a_shared_checkout_directory_refuses(self) -> None:
        # The sanitizer naming each repository's checkout directory is lossy
        # too, so two entries it cannot tell apart are handed one directory --
        # and the `issue-<n>` in it belongs to whichever of them created it,
        # which the directory does not record. Both are refused, and the
        # repository with a directory of its own still answers.
        gadget = _support._spec(_support.GADGET_SLUG, self.world.clone(SECOND_CLONE_NAME))
        self.world.checkout(gadget, GADGET_ISSUE_NUMBER)
        colliding = tuple(_support._spec(slug, self.clone) for slug in _support.COLLIDING_SLUGS)
        self.world.checkout(colliding[0], BOTH_SIDES_ISSUE_NUMBER)

        with self.assertLogs(_support.LIFECYCLE_LOGGER, logging.WARNING), _inventory_support._listing(()):
            scanned = _inventory_support._scan(*colliding, gadget)

        self.assertEqual(scanned.refused, tuple(sorted(_support.COLLIDING_SLUGS)))
        self.assertEqual(_inventory_support._found(scanned), ((_support.GADGET_SLUG, GADGET_ISSUE_NUMBER),))

    def test_a_refused_spec_still_claims_a_branch(self) -> None:
        # Refusing a repository settles what the scan REPORTS, not who could
        # have published what is on the clone. The colliding pair is still on
        # this ref store, so the one branch name both derive belongs to
        # neither -- while the branch naming a repository outright is still
        # that repository's.
        healthy = _support._spec(_support.GADGET_SLUG, self.clone)
        colliding = tuple(_support._spec(slug, self.clone) for slug in _support.COLLIDING_SLUGS)
        branches = (
            _support._namespaced_branch(_support.COLLIDING_SLUGS[1], COLLIDING_ISSUE_NUMBER),
            _support._namespaced_branch(_support.GADGET_SLUG, GADGET_ISSUE_NUMBER),
        )

        with self.assertLogs(_support.LIFECYCLE_LOGGER, logging.WARNING), _inventory_support._listing(branches):
            scanned = _inventory_support._scan(*colliding, healthy)

        self.assertEqual(scanned.refused, tuple(sorted(_support.COLLIDING_SLUGS)))
        self.assertEqual(_inventory_support._found(scanned), ((_support.GADGET_SLUG, GADGET_ISSUE_NUMBER),))

    def test_an_unread_store_still_claims_everywhere(self) -> None:
        # A twin whose clone would not be read could share any ref store, so it
        # stays a claimant on this one: the branch both derive is nobody's, and
        # the checkout standing on it is withheld with it.
        first, twin = (
            _support._spec(_support.DIGEST_COLLIDING_SLUGS[0], self.clone),
            _support._spec(_support.DIGEST_COLLIDING_SLUGS[1], self.world.path(NO_CLONE_NAME)),
        )
        shared = _support._namespaced_branch(_support.DIGEST_COLLIDING_SLUGS[1], COLLIDING_ISSUE_NUMBER)
        self.world.checkout(first, COLLIDING_ISSUE_NUMBER)

        with self.assertLogs(_support.LIFECYCLE_LOGGER, logging.WARNING), _inventory_support._listing((shared,)):
            scanned = _inventory_support._scan(first, twin)

        self.assertEqual(scanned.issues, ())
        self.assertEqual(scanned.refused, (_support.DIGEST_COLLIDING_SLUGS[1],))

    def test_an_unread_root_refuses_one_repository(self) -> None:
        # The refusal is per repository: a host that cannot list one
        # repository's checkouts still answers for the rest.
        gadget = _support._spec(_support.GADGET_SLUG, self.world.clone(SECOND_CLONE_NAME))
        self.world.checkout(gadget, GADGET_ISSUE_NUMBER)
        _support._block_worktrees_root(self.widget)

        with self.assertLogs(_support.LIFECYCLE_LOGGER, logging.WARNING), _inventory_support._listing(()):
            scanned = _inventory_support._scan(self.widget, gadget)

        self.assertEqual(scanned.refused, (_support.WIDGET_SLUG,))
        self.assertEqual(_inventory_support._found(scanned), ((_support.GADGET_SLUG, GADGET_ISSUE_NUMBER),))


class FlatCheckoutInventoryTest(unittest.TestCase):
    """The checkout layout that had no per-repository parent, on a real host.

    `WORKTREES_DIR/issue-<n>` is no configured entry's derivation, so it is
    never any repository's artifact: not when its clone is a single entry's,
    and not when the tree stands on a branch the scan does report.
    """

    def setUp(self) -> None:
        self.world = _ArtifactWorld()
        self.world.prepare(self)
        self.clone = self.world.clone(CLONE_NAME)
        self.widget = _support._spec(_support.WIDGET_SLUG, self.clone)

    def test_a_flat_checkout_is_never_reported(self) -> None:
        # Its clone settles nothing either: a worktree of the one entry's own
        # clone, or of a clone two entries share, is still no candidate.
        flat = self.world.legacy_checkout(self.widget, LEGACY_ISSUE_NUMBER)
        for sibling in (
            _support._spec(_support.GADGET_SLUG, self.world.clone(SECOND_CLONE_NAME)),
            _support._spec(_support.GADGET_SLUG, self.clone),
        ):
            with self.subTest(sibling=sibling.target_root.name):
                scanned = _inventory_support._scan(self.widget, sibling)

                self.assertEqual(scanned.issues, ())
                self.assertEqual(scanned.refused, ())
        self.assertTrue(flat.exists())

    def test_its_current_branch_is_reported_alone(self) -> None:
        # The tree is standing on the issue's own current branch. The branch is
        # still the issue's, and it is reported with no checkout: the flat
        # directory is no candidate's, and what keeps the branch while a tree
        # stands on it is the checkout listing every branch deletion reads.
        branch = _support._namespaced_branch(_support.WIDGET_SLUG, LEGACY_ISSUE_NUMBER)
        self.world.branch(self.clone, branch)
        self.world.legacy_checkout(self.widget, LEGACY_ISSUE_NUMBER)

        scanned = _inventory_support._scan(self.widget)

        self.assertEqual(
            tuple((found.issue_number, found.worktrees, found.branches) for found in scanned.issues),
            ((LEGACY_ISSUE_NUMBER, (), (branch,)),),
        )


class LocalInventoryRealGitTest(unittest.TestCase):
    """The whole scan against real clones, branches, and checkouts."""

    def setUp(self) -> None:
        self.world = _ArtifactWorld()
        self.world.prepare(self)
        self.clone = self.world.clone(CLONE_NAME)
        self.widget = _support._spec(_support.WIDGET_SLUG, self.clone)

    def test_every_shape_on_one_clone_is_read(self) -> None:
        # The three shapes an issue reaches a scan in: a checkout with its
        # branch -- one entry, not two -- a branch whose checkout is gone, and
        # a checkout whose branch is.
        self._plant_widget_artifacts()

        scanned = _inventory_support._scan(self.widget)

        self.assertEqual(
            tuple(
                (found.issue_number, found.worktrees, found.branches)
                for found in scanned.issues
            ),
            (
                (
                    BOTH_SIDES_ISSUE_NUMBER,
                    (
                        paths._worktree_path(
                            self.widget, BOTH_SIDES_ISSUE_NUMBER,
                        ),
                    ),
                    (_support._namespaced_branch(_support.WIDGET_SLUG, BOTH_SIDES_ISSUE_NUMBER),),
                ),
                (
                    CHECKOUT_ONLY_ISSUE_NUMBER,
                    (
                        paths._worktree_path(
                            self.widget, CHECKOUT_ONLY_ISSUE_NUMBER,
                        ),
                    ),
                    (),
                ),
            ),
        )
        self.assertEqual(scanned.refused, ())

    def test_a_shared_clone_splits_by_branch(self) -> None:
        # A second entry on this clone: the namespaced branches keep saying who
        # published them, and the flat one stays nobody's.
        gadget = _support._spec(_support.GADGET_SLUG, self.clone)
        self._plant_widget_artifacts()
        self.world.branch(
            self.clone, _support._namespaced_branch(_support.GADGET_SLUG, GADGET_ISSUE_NUMBER),
        )

        scanned = _inventory_support._scan(self.widget, gadget)

        self.assertEqual(_inventory_support._found(scanned), (
            (_support.GADGET_SLUG, GADGET_ISSUE_NUMBER),
            (_support.WIDGET_SLUG, BOTH_SIDES_ISSUE_NUMBER),
            (_support.WIDGET_SLUG, CHECKOUT_ONLY_ISSUE_NUMBER),
        ))

    def test_several_clones_make_one_answer(self) -> None:
        gadget = _support._spec(_support.GADGET_SLUG, self.world.clone(SECOND_CLONE_NAME))
        self._plant_widget_artifacts()
        self.world.branch(
            gadget.target_root,
            _support._namespaced_branch(_support.GADGET_SLUG, GADGET_ISSUE_NUMBER),
        )

        scanned = _inventory_support._scan(self.widget, gadget)

        self.assertEqual(_inventory_support._found(scanned), (
            (_support.GADGET_SLUG, GADGET_ISSUE_NUMBER),
            (_support.WIDGET_SLUG, BOTH_SIDES_ISSUE_NUMBER),
            (_support.WIDGET_SLUG, CHECKOUT_ONLY_ISSUE_NUMBER),
        ))
        self.assertEqual(scanned.refused, ())

    def test_a_broken_ref_refuses_the_repository(self) -> None:
        # The whole cost of a listing that warns, end to end: the checkout is
        # on disk and its branch is the ref git skipped, so an answer built
        # from what the listing did print would report the issue as a checkout
        # whose branch is gone -- the shape a cleanup acts on.
        self.world.checkout(self.widget, BOTH_SIDES_ISSUE_NUMBER)
        _support._break_ref(
            self.clone, _support._namespaced_branch(_support.WIDGET_SLUG, BOTH_SIDES_ISSUE_NUMBER),
        )

        with self.assertLogs(_support.LIFECYCLE_LOGGER, logging.WARNING):
            scanned = _inventory_support._scan(self.widget)

        self.assertEqual(scanned.issues, ())
        self.assertEqual(scanned.refused, (_support.WIDGET_SLUG,))

    def _plant_widget_artifacts(self) -> None:
        """The widget's artifacts: one issue under its own branch, the
        branches no configured repository owns, and two checkouts -- one
        under a branch of its own, one with no branch left at all."""
        for branch in (
            _support._namespaced_branch(_support.WIDGET_SLUG, BOTH_SIDES_ISSUE_NUMBER),
            *IGNORED_BRANCHES,
        ):
            self.world.branch(self.clone, branch)
        self.world.checkout(self.widget, BOTH_SIDES_ISSUE_NUMBER)
        self.world.checkout(self.widget, CHECKOUT_ONLY_ISSUE_NUMBER)


if __name__ == "__main__":
    unittest.main()
