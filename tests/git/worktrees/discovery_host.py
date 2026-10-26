# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Real published branches and sibling repositories for candidate discovery."""
from __future__ import annotations

import unittest
from pathlib import Path

from orchestrator.config import models as _config_models
from tests.git.worktrees import artifact_git as _artifact_git
from tests.git.worktrees.artifact_git import BASE_BRANCH
from tests.git.worktrees.artifact_test_support import GADGET_SLUG, WIDGET_SLUG, _namespaced_branch, _spec
from tests.git.worktrees.candidate_host_test_support import (
    CLONE_NAME,
    _CandidateWorld,
)
from tests.git.worktrees.eligibility_test_support import ISSUE_NUMBER

# The second bare repository and the second clone a multi-repository case
# builds, named apart from the world's own so both can stand at once.
SIBLING_REMOTE_DIR = "sibling.git"

SIBLING_CLONE_NAME = "sibling"


class _DiscoveryHostCase(unittest.TestCase):
    """One issue branch and the clones, remotes, and checkouts a discovery must attribute."""

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
        which no configured repository derives, so nothing attributes it.
        """
        return self.world.checkout_at(
            self.spec,
            _artifact_git._flat_checkout_path(ISSUE_NUMBER),
            branch or self.branch,
        )

    def sibling_on_this_clone(self) -> _config_models.RepoSpec:
        """A second configured repository over the very same clone.

        A public and a private remote across one checkout, which is the shape
        branch namespacing exists for: each entry's namespaced names still say
        which of them published them, and a flat one says nothing for either.
        """
        sibling = _spec(GADGET_SLUG, self.clone)
        self.world.serve_beside(sibling, SIBLING_REMOTE_DIR)
        return sibling

    def sibling_on_its_own_clone(self) -> _config_models.RepoSpec:
        """A second configured repository, on a clone and a remote of its own.

        What a multi-repo host normally looks like: the entries do not share a
        ref store, so a flat checkout here is a worktree of exactly one of
        their clones -- and still no entry's artifact.
        """
        sibling = _spec(GADGET_SLUG, self.world.clone(SIBLING_CLONE_NAME))
        self.world.serve_beside(sibling, SIBLING_REMOTE_DIR)
        return sibling
