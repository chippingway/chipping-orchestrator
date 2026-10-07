# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An interrupted rebase's recovery, entered where the workflow's base-rewrite coordinator enters it.

The coordinator hands the recovery decision the refresh's own inputs and the
anchor the dead tick pinned (`workflow/engine/rewrite_recovery.py`), and the
decision reads the attempt's record of its replay off the comment itself. A
real repository left mid-rebase is resumed the same way, so what a case reads
back is what that decision and every road behind it left.
"""
from __future__ import annotations

from orchestrator.git.base_sync import models as _models
from orchestrator.workflow.engine import rewrite_recovery as _rewrite_recovery

# The pull request every fixture here pins its issue to, and the field the
# anchor an attempt pins before git runs is read back from.
_PR_NUMBER = 42
_ANCHOR_KEY = "pending_auto_base_rebase_push_sha"


def resumed(fixture, label: str) -> _models._AutoRebaseDecision:
    """The decision taken over `fixture`'s issue as it now reads, labelled `label`.

    The anchor is read off the pinned comment as the coordinator reads it, so
    a tick after a finish or a rollback that retired the attempt finds nothing
    to recover. The replay is already on the advanced base, so nothing is
    behind it, and no human reply brought it back.
    """
    state = fixture.gh.read_pinned_state(fixture.issue)
    return _rewrite_recovery.decides(
        _models._AutoRebaseContext(
            gh=fixture.gh,
            spec=fixture.spec,
            issue=fixture.issue,
            state=state,
            worktree=fixture.work,
            pr_number=_PR_NUMBER,
            behind=0,
            label=label,
            pending_pre_rebase_sha=state.get(_ANCHOR_KEY),
        ),
        None,
    )
