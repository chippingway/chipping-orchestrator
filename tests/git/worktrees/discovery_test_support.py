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

from collections.abc import Sequence
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import discovery, probes
from orchestrator.git.worktrees.candidates import MaintenanceCandidate
from tests.git.worktrees import discovery_host as _discovery_host

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


class _DiscoveryTestCase(_discovery_host._DiscoveryHostCase):
    """One finished issue, with its artifacts on a real host and remote."""

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
