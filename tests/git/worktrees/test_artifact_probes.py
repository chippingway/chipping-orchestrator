# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The two local reads under the artifact scan, and what a failed one answers.

The branch listing is ``branch_probes``' and the checkout enumeration is
``probes``', and both are driven against real clones and real directories:
these are the only two places the scan touches the host, so a regression in
the `for-each-ref` arguments, in the ref-name stripping, or in which failures
count as "read nothing" surfaces here rather than in a caller's mock.
"""

from __future__ import annotations

import logging
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.worktrees import branch_probes, probes
from tests.git.worktrees import artifact_test_support as _support
from tests.git.worktrees.artifact_test_support import _ArtifactWorld

CLONE_NAME = "target"
NAMESPACED_ISSUE_NUMBER = 4
LEGACY_ISSUE_NUMBER = 9
CHECKOUT_ISSUE_NUMBER = 12
SYMLINKED_ISSUE_NUMBER = 42
UNRELATED_BRANCH = "feature/not-ours"
NOT_A_CHECKOUT = "not a checkout\n"
FOREIGN_DIRECTORY = "somebody-elses-tree"

# Names under the worktrees root that are not a checkout this orchestrator
# made for an issue: the decomposer's scratch directory, a padded number no
# derivation writes, and one directory per shape a near miss can take.
NON_CHECKOUT_DIRECTORIES = (
    "decompose-12",
    "issue-007",
    "issue-",
    "issue-abc",
    "issue-12-old",
)


class OrchestratorBranchListingTest(unittest.TestCase):
    """What one clone's orchestrator namespace holds, and what unread means."""

    def setUp(self) -> None:
        self.world = _ArtifactWorld()
        self.world.prepare(self)

    def test_lists_the_namespace_by_branch_name(self) -> None:
        root = self.world.clone(CLONE_NAME)
        namespaced = _support._namespaced_branch(_support.WIDGET_SLUG, NAMESPACED_ISSUE_NUMBER)
        legacy = _support._legacy_branch(LEGACY_ISSUE_NUMBER)
        for branch in (namespaced, legacy, UNRELATED_BRANCH):
            self.world.branch(root, branch)

        listed = branch_probes._local_orchestrator_branches(root)

        # Branch names as the derivations spell them, and nothing from
        # outside the namespace.
        self.assertEqual(sorted(listed), sorted((namespaced, legacy)))

    def test_a_tag_does_not_rename_its_branch(self) -> None:
        # Why the `refs/heads/` prefix is stripped here instead of asked for
        # as `%(refname:short)`: git's short form is the shortest unambiguous
        # one, so a tag of the same name would push the branch out to
        # `heads/orchestrator/...` -- a name no derivation produces, which
        # would read as a stranger's branch and drop the issue.
        root = self.world.clone(CLONE_NAME)
        namespaced = _support._namespaced_branch(_support.WIDGET_SLUG, NAMESPACED_ISSUE_NUMBER)
        self.world.branch(root, namespaced)
        self.world.tag(root, namespaced)

        self.assertEqual(
            branch_probes._local_orchestrator_branches(root), (namespaced,),
        )

    def test_a_clone_with_none_answers_empty(self) -> None:
        root = self.world.clone(CLONE_NAME)
        self.world.branch(root, UNRELATED_BRANCH)

        self.assertEqual(branch_probes._local_orchestrator_branches(root), ())

    def test_an_unreadable_store_answers_none(self) -> None:
        # A directory that is not a repository: git runs and refuses. The
        # empty tuple above is a clone that answered; this is one that did
        # not, and a caller must be able to tell them apart.
        plain = self.world.path("not-a-repo")
        plain.mkdir()

        with self.assertLogs(_support.LIFECYCLE_LOGGER, logging.WARNING):
            self.assertIsNone(branch_probes._local_orchestrator_branches(plain))

    def test_a_warned_listing_answers_none(self) -> None:
        # git skips a ref it cannot parse, warns about it, and exits zero all
        # the same. The branches it did print are a subset nothing marks as
        # one, so the listing is taken as unread rather than as what survived.
        root = self.world.clone(CLONE_NAME)
        self.world.branch(root, _support._legacy_branch(LEGACY_ISSUE_NUMBER))
        _support._break_ref(
            root, _support._namespaced_branch(_support.WIDGET_SLUG, NAMESPACED_ISSUE_NUMBER),
        )

        with self.assertLogs(_support.LIFECYCLE_LOGGER, logging.WARNING):
            self.assertIsNone(branch_probes._local_orchestrator_branches(root))

    def test_an_unspawnable_read_answers_none(self) -> None:
        # The clone's path does not exist, so the read never runs at all --
        # the failure git itself never gets to report.
        with self.assertLogs(_support.LIFECYCLE_LOGGER, logging.WARNING):
            self.assertIsNone(
                branch_probes._local_orchestrator_branches(self.world.path("gone")),
            )


class _UnstattablePath(Path):
    """A worktrees tree that lists its entries and will not let them be read.

    The shape a directory takes when it is readable without being searchable,
    reached through the path type rather than through a file mode so the test
    reads the same under any umask and for any user running it -- root
    included, which a mode-based one would sail straight past.
    """

    def stat(self, *, follow_symlinks: bool = True) -> os.stat_result:
        raise PermissionError(f"stat denied for {self}")

    def lstat(self) -> os.stat_result:
        raise PermissionError(f"stat denied for {self}")


class WorktreeCheckoutNumbersTest(unittest.TestCase):
    """Which issues this host still holds a checkout for, exactly."""

    def setUp(self) -> None:
        self.world = _ArtifactWorld()
        self.world.prepare(self)
        self.spec = _support._spec(_support.WIDGET_SLUG, self.world.clone(CLONE_NAME))

    def test_no_worktrees_root_holds_nothing(self) -> None:
        # Nothing has ever been checked out for this repository. An
        # established absence, not a failed read.
        self.assertEqual(
            probes._worktree_issue_numbers(self.spec), frozenset(),
        )

    def test_only_an_exact_checkout_counts(self) -> None:
        self.world.checkout(self.spec, CHECKOUT_ISSUE_NUMBER)
        root = _support._worktrees_root(self.spec)
        for name in NON_CHECKOUT_DIRECTORIES:
            (root / name).mkdir()
        # A file named exactly like a checkout is not one either.
        (root / f"issue-{LEGACY_ISSUE_NUMBER}").write_text(NOT_A_CHECKOUT)

        self.assertEqual(
            probes._worktree_issue_numbers(self.spec),
            frozenset((CHECKOUT_ISSUE_NUMBER,)),
        )

    def test_a_symlinked_checkout_is_not_one(self) -> None:
        # `is_dir` follows a symlink, so an `issue-<n>` pointing anywhere
        # answers exactly as a checkout does. What a caller acts on is the
        # path, and this one leads out of the tree the creators write in.
        self.world.checkout(self.spec, CHECKOUT_ISSUE_NUMBER)
        foreign = self.world.path(FOREIGN_DIRECTORY)
        foreign.mkdir()
        checkout_name = f"issue-{SYMLINKED_ISSUE_NUMBER}"
        (_support._worktrees_root(self.spec) / checkout_name).symlink_to(foreign)

        self.assertEqual(
            probes._worktree_issue_numbers(self.spec),
            frozenset((CHECKOUT_ISSUE_NUMBER,)),
        )

    def test_an_unlistable_root_answers_none(self) -> None:
        _support._block_worktrees_root(self.spec)

        with self.assertLogs(_support.LIFECYCLE_LOGGER, logging.WARNING):
            self.assertIsNone(probes._worktree_issue_numbers(self.spec))

    def test_an_unreadable_entry_answers_none(self) -> None:
        # The listing succeeded and the entries under it did not. Half a
        # directory is not a reading of what the repository holds, so it is
        # refused on the same terms as a root that never listed at all.
        self.world.checkout(self.spec, CHECKOUT_ISSUE_NUMBER)
        unstattable = _UnstattablePath(self.world.worktrees)

        with (
            patch.object(config, "WORKTREES_DIR", unstattable),
            self.assertLogs(_support.LIFECYCLE_LOGGER, logging.WARNING),
        ):
            self.assertIsNone(probes._worktree_issue_numbers(self.spec))


if __name__ == "__main__":
    unittest.main()
