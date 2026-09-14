# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Ask the publication permit over the recovery's frozen entry.

The replay recovery asks before publishing and repeats the same
permit-only restriction inside the gate. Workflow owners are loaded only
inside that call, preserving the Git layer's import boundary.
"""
from __future__ import annotations

from dataclasses import replace as _replace

from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
)
from orchestrator.git.base_sync.state import log


def _permits_the_publication(
    context: _AutoRebaseRecoveryContext, local_head: str, rewrite=None,
) -> bool:
    """Whether the permit still licenses this recovery to publish.

    Asked BEFORE the gated publication rather than through it, and that is
    the whole of what makes this road safe. The gate's answer to a permit
    that declines is the ordinary cumulative reading, which is right for a
    rebase deciding whether to publish and wrong on a recovery twice over: a
    count under the ceiling reports a publication landed with the verdict
    still on the commit a human ruled on, and a count over it routes an
    adjudicated change into a second adjudication with a pull request already
    open over the work. There is nothing on this road to decide -- the push
    the interrupted tick never made is already leased -- so the only question
    is whether the permission may be spent, and a refusal is a refusal. The
    gate is told the same thing on the way in, so a permit that stops holding
    between this ask and its own is refused there rather than measured.

    Asked over the evidence this recovery holds: the record the grant left,
    where there is one, and otherwise the rewrite re-derived for a grant the
    crash came before -- which is what `late_transfer` reads when a caller
    hands in no rewrite of its own. Every term is re-derived there: the
    publication this call freezes, the one the issue records, the checkout,
    the lease as an object this host holds, the issue read afresh, and both
    contributions fingerprinted from the objects themselves. A grant
    re-writes nothing, since the payload it would stage is the one already on
    the comment.

    The entry is frozen here for the same reason the permit needs one at all:
    it is the pull request read this tick, before any effect, and the terms
    the record claims are checked against it rather than against themselves.
    """
    # Lazy for the reason every upward reach in this package is: the permit
    # and the entry it is asked over sit in the workflow layer above it.
    from orchestrator.workflow.stages.implementing import (
        late_overflow as _overflow,
        late_records as _records,
        late_transfer as _transfer,
    )
    from orchestrator.workflow.stages.implementing.late_gate_models import _Entered
    gate = _records._gate(
        context.gh, context.spec, context.issue, context.state,
        context.worktree,
    )
    entered = _Entered(
        head=context.pending_pre_rebase_sha or "",
        reconciling=True,
        candidate=local_head,
    )
    entry = _overflow._frozen_entry(gate, entered)
    if not entry.is_frozen:
        log.warning(
            "issue=#%d auto-rebase recovery cannot enter the publication its "
            "interrupted rewrite was made against (%s); the transfer it owes "
            "is left standing",
            context.issue.number, entry.refusal,
        )
        return False
    gate = _replace(
        gate, entry=entry, candidate=local_head, reconciling=True,
        rewrite=rewrite,
    )
    return bool(_transfer._carried_over(gate, local_head))
