# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkout an auto-rebase road is about to rewrite, proven the issue's own again.

The refresh proves the checkout before it routes anything
(`workflow/engine/base_refresh.py`), and every fetch, read, and write the road
makes comes after that proof. The steps that take whatever the tree holds --
the rebase that replays its branch onto the base, and the reset-and-park
tail's `reset --hard` with the `git clean -fd` behind it -- are asked again
here, last, with nothing written: a tree switched onto the flat branch,
another repository's, or a detached HEAD in the meantime keeps its branch,
its head, and its files, and the road rebases, resets, cleans, and parks
nothing more. The clean is asked separately, behind a reset that landed,
since the reset itself is a window a tree can be switched in, and so is a
failed rebase's abort, which switches the tree back onto the branch the
rebase was rewriting and discards what the index holds. The pre-PR rebase
owner may import nothing above the git layer, so it is handed that question
bound (`_asked_before`) rather than asking it itself.
"""
from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git.base_sync.state import log
from orchestrator.git.worktrees import evidence as _evidence
from orchestrator.git.worktrees.models import ProbeAnswer


def _still_its_checkout(
    spec: _config_models.RepoSpec, issue_number: int, worktree: Path, step: str,
) -> bool:
    """Whether `worktree` is still proven the issue's own ahead of `step`; said where it is not.

    Asked as a recovery asks it (`rebasing`), so the checkout an interrupted
    rebase of the issue's own branch leaves detached still answers, and the
    reset that puts it back on the anchor still runs.
    """
    identity = _evidence._checkout_identity(spec, issue_number, worktree, rebasing=True)
    if identity is ProbeAnswer.CONFIRMED:
        return True
    log.warning(
        "issue=#%d auto-rebase road: holding rather than %s, since %s is not proven this issue's own (%s); "
        "it is left for manual disposition with nothing more rebased, reset, cleaned, or parked",
        issue_number, step, worktree, identity,
    )
    return False


def _asked_before(
    spec: _config_models.RepoSpec, issue_number: int, worktree: Path, step: str,
) -> Callable[[], bool]:
    """`_still_its_checkout` bound to one checkout and one step, for an owner that asks it later."""
    return partial(_still_its_checkout, spec, issue_number, worktree, step)
