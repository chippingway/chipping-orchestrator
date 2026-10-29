# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkout ownership and placement reads, stated for fixtures whose checkout no layout path holds.

Every road that works in, reuses, rebases, or publishes from an issue's
checkout asks `git/worktrees/evidence._checkout_identity` first: a worktree of
the clone, on the issue's current-layout branch, at its layout path under
`WORKTREES_DIR`. Where no checkout stands, the path is asked
`evidence._at_layout_path` before anything is created there. A fixture whose
checkout is the clone itself, a plain directory, a faked path, or a worktree
it resolves the issue's path to outside `WORKTREES_DIR` has nothing either
read could prove, so both answers are stated rather than read -- as the
issue's own, until a case states the checkout switched off the issue's branch
partway through a road (`stated_switch`).
"""
from __future__ import annotations

import contextlib
from unittest.mock import MagicMock, patch

from orchestrator.git.worktrees import evidence as _evidence, models as _worktree_models

_READS = ("_checkout_identity", "_at_layout_path")


def stated_ownership() -> contextlib.ExitStack:
    """A context in which both reads answer that the checkout and its path are the issue's own."""
    stack = contextlib.ExitStack()
    for read in _READS:
        stack.enter_context(patch.object(
            _evidence, read, MagicMock(return_value=_worktree_models.ProbeAnswer.CONFIRMED),
        ))
    return stack


def stated_identity(test_case) -> None:
    """Answer both reads as the issue's own until the case ends."""
    test_case.enterContext(stated_ownership())


def stated_switch() -> None:
    """Have the stated identity read refute the checkout from here on, as one switched off the issue's branch."""
    _evidence._checkout_identity.return_value = _worktree_models.ProbeAnswer.REFUTED
