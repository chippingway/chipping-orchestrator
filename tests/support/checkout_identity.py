# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkout ownership read, stated for fixtures whose checkout no layout path holds.

Every road that works in, reuses, rebases, or publishes from an issue's
checkout asks `git/worktrees/evidence._checkout_identity` first: a worktree of
the clone, on the issue's current-layout branch, at its layout path under
`WORKTREES_DIR`. A fixture whose checkout is the clone itself, a plain
directory, a faked path, or a worktree it resolves the issue's path to outside
`WORKTREES_DIR` has nothing that read could prove, so the answer is stated
rather than read -- for the whole case, as the issue's own.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from orchestrator.git.worktrees import evidence as _evidence, models as _worktree_models


def stated_identity(test_case) -> None:
    """Answer the checkout's ownership read as the issue's own until the case ends."""
    stated = patch.object(
        _evidence, "_checkout_identity",
        MagicMock(return_value=_worktree_models.ProbeAnswer.CONFIRMED),
    )
    stated.start()
    test_case.addCleanup(stated.stop)
