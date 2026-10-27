# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkout an auto-rebase road is about to reset, proven the issue's own again.

The refresh proves the checkout before it routes anything
(`workflow/engine/base_refresh.py`), and every fetch, read, and write the road
makes comes after that proof. The reset-and-park tail is the one step that
takes whatever the tree holds -- `reset --hard` and the `git clean -fd` behind
it -- so it is asked again here, last, with nothing written: a tree switched
onto the flat branch, another repository's, or a detached HEAD in the meantime
keeps its head and its files, and the road resets, cleans, and parks nothing.
"""
from __future__ import annotations

from orchestrator.git.base_sync.models import _AutoRebaseContext, _AutoRebaseRecoveryContext
from orchestrator.git.base_sync.state import log
from orchestrator.git.worktrees import evidence as _evidence
from orchestrator.git.worktrees.models import ProbeAnswer


def _still_its_checkout(context: _AutoRebaseContext | _AutoRebaseRecoveryContext) -> bool:
    """Whether the checkout `context` names is still proven the issue's own; said where it is not.

    Asked as a recovery asks it (`rebasing`), so the checkout an interrupted
    rebase of the issue's own branch leaves detached still answers, and the
    reset that puts it back on the anchor still runs.
    """
    identity = _evidence._checkout_identity(
        context.spec, context.issue.number, context.worktree, rebasing=True,
    )
    if identity is ProbeAnswer.CONFIRMED:
        return True
    log.warning(
        "issue=#%d auto-rebase road: holding rather than resetting the checkout, since %s is not proven this "
        "issue's own (%s); it is left for manual disposition with nothing reset, cleaned, or parked",
        context.issue.number, context.worktree, identity,
    )
    return False
