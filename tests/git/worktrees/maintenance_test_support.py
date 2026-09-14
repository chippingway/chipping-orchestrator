# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The finished issue a maintenance pass runs over, on a real host and remote.

The world is the artifact classification's own -- a clone, the bare repository
its authenticated transport is pointed at, and the checkouts under a redirected
worktrees root -- because a pass is only worth testing against the things it
actually mutates: `worktree remove` refusing a tree it has been written in, a
leased delete the remote turns down, a ref store that will not let go of a
branch that has moved. A double of any of them would hand the fixture's own
answer back.

What is doubled is the issue and its pull requests, through the in-memory
client, since the ending a candidate needs is a fact about GitHub rather than
about the host.

The quiet period is real too, which is why every case that expects a pass to
act back-dates the checkout first: a tree created moments ago is one this pass
is designed to leave alone, and a fixture that patched the constant away would
stop testing the guard that says so.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import (
    probes,
)
from tests.git.worktrees import (
    maintenance_assertions as _maintenance_assertions,
    maintenance_host as _maintenance_host,
)

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


def _refused_delete(*_args, **_options) -> bool:
    """A teardown step the host or the remote turned down."""
    return False


class _MaintenanceTestCase(_maintenance_assertions._MaintenanceAssertions, _maintenance_host._MaintenanceHostCase):
    """One finished issue, with its artifacts on a real host and remote."""

    def settled_checkout(self, branch: str | None = None) -> Path:
        """The same checkout, left alone long enough for the pass to act."""
        worktree = self.checkout(branch)
        _maintenance_host._settle(worktree)
        return worktree
