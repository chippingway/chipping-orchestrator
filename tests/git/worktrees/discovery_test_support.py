# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The host and remote a candidate discovery is read off, both of them real.

The world is the artifact classification's own -- a clone, the bare repository
its authenticated transport is pointed at, and the checkouts under a redirected
worktrees root -- because every part of the question is something git answers:
the namespace listing, the ref store the local half comes from, the exact names
the attribution re-derives and compares, and the git directory that says which
clone a checkout carrying no name at all is a worktree of. A double of any of
them would hand the fixture's own answer back.

Nothing here reaches GitHub. What the discovery decides is where an issue's
artifacts are and who they belong to, which is settled entirely between the
host and the remotes it publishes to.
"""

from __future__ import annotations

import unittest
from collections.abc import Sequence
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import discovery, paths, probes
from orchestrator.git.worktrees.candidates import MaintenanceCandidate
from tests.git.worktrees.artifact_test_support import (
    BASE_BRANCH,
    GADGET_SLUG,
    WIDGET_SLUG,
    _namespaced_branch,
    _spec,
)
from tests.git.worktrees.candidate_host_test_support import (
    CLONE_NAME,
    _CandidateWorld,
)
from tests.git.worktrees.eligibility_test_support import ISSUE_NUMBER

# The second bare repository and the second clone a multi-repository case
# builds, named apart from the world's own so both can stand at once.
SIBLING_REMOTE_DIR = "sibling.git"

SIBLING_CLONE_NAME = "sibling"

LIFECYCLE_LOGGER = "orchestrator.worktree_lifecycle"


class _CloneOfAllBut:
    """The identity read, refusing to answer for one configured repository.

    What a clone that would not open looks like to the attribution: every other
    path still resolves, so the answer differs from the real one in exactly the
    entry whose own reading failed. The real read is captured at construction
    rather than looked up per call, since the patch it is installed under would
    otherwise send it back to itself.
    """

    def __init__(self, unreadable: _config_models.RepoSpec) -> None:
        self._unreadable = unreadable
        self._real = probes._checkout_clone

    def __call__(self, root: Path) -> Path | None:
        if root == self._unreadable.target_root:
            return None
        return self._real(root)


class _DiscoveryTestCase(unittest.TestCase):
    """One finished issue, with its artifacts on a real host and remote."""

    def setUp(self) -> None:
        self.world = _CandidateWorld()
        self.world.prepare(self)
        self.clone = self.world.clone(CLONE_NAME)
        self.spec = _spec(WIDGET_SLUG, self.clone)
        self.world.serve(self.spec)
        self.branch = _namespaced_branch(WIDGET_SLUG, ISSUE_NUMBER)

    def published(self, branch: str | None = None) -> str:
        """Put one commit on a branch and push it, as a run's own round does."""
        branch = branch or self.branch
        return self.world.publish(
            self.clone, branch, self.world.commit_on(self.clone, branch),
        )

    def landed(self, branch: str | None = None) -> str:
        """Publish that branch and move the remote's base onto it.

        The ordinary shape of a merged pull request, which is what a candidate
        the classification behind this would clear looks like on the host.
        """
        branch = branch or self.branch
        tip = self.published(branch)
        self.world.publish(self.clone, BASE_BRANCH, branch)
        return tip

    def checkout(self, branch: str | None = None) -> Path:
        """Add this issue's worktree, on the branch its creator leaves it on."""
        return self.world.attached_checkout(
            self.spec, ISSUE_NUMBER, branch or self.branch,
        )

    def legacy_checkout(self, branch: str | None = None) -> Path:
        """Add the checkout where this orchestrator put one before namespacing.

        Directly under `WORKTREES_DIR`, with no per-repository parent, which is
        the layout every entry shared until the slug went into the path -- and
        which a host that has been running since then is still holding.
        """
        return self.world.checkout_at(
            self.spec,
            paths._legacy_worktree_path(ISSUE_NUMBER),
            branch or self.branch,
        )

    def sibling_on_this_clone(self) -> _config_models.RepoSpec:
        """A second configured repository over the very same clone.

        A public and a private remote across one checkout, which is the shape
        branch namespacing exists for -- and the one shape in which an artifact
        carrying no slug cannot be charged to either of them.
        """
        sibling = _spec(GADGET_SLUG, self.clone)
        self.world.serve_beside(sibling, SIBLING_REMOTE_DIR)
        return sibling

    def sibling_on_its_own_clone(self) -> _config_models.RepoSpec:
        """A second configured repository, on a clone and a remote of its own.

        What a multi-repo host normally looks like: the entries do not share a
        ref store, so nothing about one of them makes the other's artifacts
        ambiguous -- which is the whole difference between this and a shared
        `target_root`.
        """
        sibling = _spec(GADGET_SLUG, self.world.clone(SIBLING_CLONE_NAME))
        self.world.serve_beside(sibling, SIBLING_REMOTE_DIR)
        return sibling

    def discovered(
        self, specs: Sequence[_config_models.RepoSpec] | None = None,
    ) -> tuple[MaintenanceCandidate, ...]:
        """Every candidate the discovery finds on this host and its remote."""
        return discovery._maintenance_candidates(
            specs or (self.spec,),
        ).candidates

    def only_candidate(self, specs=None) -> MaintenanceCandidate:
        """The single candidate this host and its remote hold between them."""
        found = self.discovered(specs)
        self.assertEqual(len(found), 1, f"expected one candidate, got {found}")
        return found[0]
