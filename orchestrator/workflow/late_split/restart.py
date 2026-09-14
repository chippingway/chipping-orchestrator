# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The two-phase restart marker, and the identities it is allowed to name.

A restart after a completed cancellation is a transaction over the same pinned
comment: the new cycle is persisted first, the notice and the label follow,
and only a reconciled pair retires the marker. This owner is both halves of
that, kept apart from the round trip beside it because what it decides is an
identity, not a field: which cycle a restart intends, and whether the one a
crashed tick left behind may still be believed.

`LateRestartTarget` is the whole of what a restart may apply, and it lives
here because applying one is what this owner does. The two members are the
workflow labels themselves, so a target read back out of a pinned comment is
either one of them or nothing at all.

Believed is the operative word, and it takes the whole marker rather than one
field of it. A marker is this domain's own only when all four agree: the
pending flag is set, the target is one of the two states a restart may put an
issue back into, the predecessor is exactly the cycle the record is on, and
the pending cycle is exactly the next one after it. Anything else is a damaged
field rather than a restart in flight -- a cycle 500 predecessor under cycle 2
is ancestry nothing wrote, and a pending cycle of 99 is a number an audit
record has no line for. Both halves re-mint from the current cycle instead,
which is the same answer a first entry gets, so a corrupted marker costs one
notice rather than a fabricated lineage. What a *caller* asks for is checked
before any of that: a target no restart may apply is refused whether or not a
marker is already standing, because the argument is a bug either way.

Retiring is the one operation here that refuses rather than re-deriving. The
fresh cycle keeps no ledger -- a restarted issue owns nothing on the remote
yet -- so retiring while an obligation is still pending, retained, failed, or
of a shape this binary could not read would delete the only record that the
remote is owed anything. Restart is reachable only from a cancellation whose
cleanup completed, so a generation that cannot show that is one whose restart
has not come due; `obligations_settled` is the same question a caller can ask
before getting the refusal.
"""
from __future__ import annotations

import dataclasses
from enum import StrEnum
from typing import Any

from orchestrator.workflow.late_split import formats as _formats, identity as _identity
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.late_split.obligations import LateResourceState
from orchestrator.workflow.state import WorkflowLabel


class LateRestartTarget(StrEnum):
    """The two states a restart may put an issue back into.

    The current `DECOMPOSE` setting chooses between them; nothing else is a
    restart, so nothing else is recordable or applicable as one.
    """

    DECOMPOSING = WorkflowLabel.DECOMPOSING
    IMPLEMENTING = WorkflowLabel.IMPLEMENTING


def restart_target(given: Any) -> LateRestartTarget | None:
    """Return the label a restart may apply, or None for anything else."""
    try:
        return LateRestartTarget(given)
    except (TypeError, ValueError):
        return None


def obligations_settled(generation: LateGeneration) -> bool:
    """Whether every external obligation this generation recorded is discharged.

    A ledger this binary could not fully read counts as unsettled, because
    what it could not type it also cannot see the state of. The consumer
    ledger is not asked about: it is what retains a snapshot rather than an
    obligation of its own, and a snapshot still being retained is a resource
    entry that has not reconciled.
    """
    if generation.obligations.is_opaque:
        return False
    return all(
        entry.resource_state is LateResourceState.RECONCILED
        for entry in generation.obligations.resources
    )


def begin_restart(
    generation: LateGeneration,
    *,
    target: str,
) -> LateGeneration:
    """Return the record that stands while a restart is half-applied.

    The target is checked first and always: a caller asking for one of the two
    a restart may apply is the whole contract, and a marker already standing
    does not excuse the argument -- writing an unchecked one would put a label
    nobody chose into the pinned comment for a later tick to obey.

    Then create-or-keep: a marker this domain could have written already IS
    this restart, so re-entering after a crash resumes it rather than minting
    a second one and posting a second notice. One that could not be is
    re-minted from the current cycle.
    """
    wanted = restart_target(target)
    if wanted is None:
        raise _formats.InvalidLateValue(
            f"restart_target is not recordable ({type(target).__name__})",
        )
    if _is_believable(generation):
        return generation
    return dataclasses.replace(
        generation,
        restart_pending=True,
        restart_target=str(wanted),
        restart_cycle_id=_identity.next_identity(generation.cycle_id),
        restart_predecessor=generation.cycle_id,
    )


def retire_restart(generation: LateGeneration) -> LateGeneration:
    """Return the fresh cycle a fully reconciled restart leaves behind.

    Only the identities that keep the new cycle joinable to the old one
    survive -- the cycle it is, the issue and root it belongs to, and the
    cycle it succeeds. The generation counter, the frozen SHAs, the
    measurement, the hold, both ledgers, and the cancellation are
    gone, and the lineage depth is back to the root's 0 rather than unknown,
    because a restarted issue is a fresh attempt with room to split -- not a
    cancelled one wearing a new number, and not one whose depth nothing could
    read.

    Raises `InvalidLateValue` while any obligation is still owed. The ledgers
    do not survive the projection, so retiring over one that has not settled
    would discharge it by forgetting it: a retained snapshot, a failed branch
    deletion, and an entry of a shape this binary could not read would each
    leave the remote holding something no later tick could reclaim.

    Which cycle it becomes is the marker's only while the whole marker is
    believable. A pending identity that does not follow the current cycle, or
    a predecessor that is not the cycle it is being retired from, would hand
    the fresh attempt a number an audit record never issued and an ancestry
    nothing wrote, so both are re-derived from the cycle in hand instead.
    """
    if not obligations_settled(generation):
        raise _formats.InvalidLateValue(
            "restart cannot retire while an external obligation is owed",
        )
    if _is_believable(generation):
        minted = generation.restart_cycle_id
        predecessor = generation.restart_predecessor
    else:
        minted = _identity.next_identity(generation.cycle_id)
        predecessor = generation.cycle_id
    return LateGeneration(
        cycle_id=minted,
        root_issue=generation.root_issue,
        current_issue=generation.current_issue,
        lineage_depth=0,
        restart_predecessor=predecessor or None,
    )


def _is_believable(generation: LateGeneration) -> bool:
    """Whether the whole pending marker is one this domain could have written."""
    if not generation.restart_pending:
        return False
    if restart_target(generation.restart_target) is None:
        return False
    if not _formats.whole_number(generation.restart_predecessor):
        return False
    if generation.restart_predecessor != generation.cycle_id:
        return False
    return generation.restart_cycle_id == _identity.next_identity(
        generation.cycle_id,
    )
