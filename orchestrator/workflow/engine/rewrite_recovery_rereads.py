# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The comment a dormant recovery reads last behind its writes, laid over the tick's state where another road moved it.

The reset's record (`rewrite_recovery_parks.records_the_reset`) lets the reset go on over the comment it reads
afresh behind its own writes, and a landed hold's, park's, or clear's record answers over the one read behind it;
the tick's state is written behind them -- whole, by a recovery context that hands in no park of its own. A usage
total another road added to by then, a revision floor it raised, or a transaction it recorded would be put back by
that write. So `lays_what_moved` lays that reading over the state for every field another road moved since the
tick's own reading, each taken in as read (`rewrite_finish_rechecks.lays`), so a guarded write behind counts none of
it as the tick's own move either; a field the tick staged itself stays staged, for the write behind to merge or
refuse as the guarded commit does. A move of a field the caller holds the reading to, or a transaction another road
recorded pending under a receipt the attempt does not name, holds the caller. Behind a landed hold's or park's record
the reading is asked for movement first (`stands_behind`): movement under evidence the tick holds is proved again by
the caller's proof, the comment read again behind it, so it stands however soon it is put back; and a transaction the
record itself took in pending under such a receipt holds the caller all the same. Behind a landed clear, which took
the attempt guarding the evidence it retired with it, evidence that reading carries put back under a receipt the clear
retired is retired again over it, in a write of its own (`retires_again`); the clear's own write spent a revision past
each run it retired (`outranks_the_retired`), so a run written back after that, or past a retirement refused, stays
outranked for every reader with no attempt left to guard it.

Dormant, as those records are: no recovery context the workflow builds reaches it.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Collection, Mapping
from functools import partial
from typing import Any

from orchestrator.git.base_sync import attempts as _attempts, models as _base_sync_models
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    report_commits as _commits,
    rewrite_landing_records as _landing_records,
    rewrite_landing_retirement as _retirement,
    rewrite_recovery_readings as _readings,
    verification_record_state as _record_state,
    verification_records as _evidence_records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence
from orchestrator.workflow.engine.rewrite_finish_outranking import spends_past
from orchestrator.workflow.engine.rewrite_finish_rechecks import lays


def lays_what_moved(state: PinnedState, reading: PinnedState, held: Collection[str] = ()) -> bool:
    """Lay over `state` each field `reading` spells otherwise than the reading `state` was synced with; whether to hold.

    `reading` is the comment read afresh. A field `state` itself spells otherwise than that reading is the tick's own
    staging and is left as it is. True where any field laid is one of `held`, or where another road recorded a
    transaction pending there under a receipt the attempt `reading` carries does not name -- a successor the reset
    would otherwise go on under. A state nothing was read into has no reading to measure moves from, and lays nothing.
    """
    if state.synced is None:
        return False
    synced = json.loads(state.synced)
    moved = _moved(reading.data, synced) - _moved(state.data, synced)
    lays(state, reading, moved)
    if not moved.isdisjoint(held):
        return True
    if _evidence_records.PENDING_EVIDENCE not in moved or _landing_records.captured(reading) is not None:
        return False
    return _record_state.read_pending_evidence(reading) is not None


def stands_behind(
    context: _base_sync_models._AutoRebaseRecoveryContext,
    proves: Callable[[dict[str, ReportEvidence]], bool],
    reads: Callable[..., tuple],
    pending: str | None,
) -> bool:
    """Whether a record that landed may answer over the comment read afresh behind it, what moved there proved first.

    The comment is read through `reads` -- `verification_durable.durable_comment`, as the caller resolves it -- and
    asked what it records moving under each evidence the tick's state holds (`rewrite_landing_retirement.moved_under`).
    Movement under a receipt that state holds is handed to `proves`, the caller's proof, which retires or marks what
    moved, so that movement stands however soon it is put back; the comment is read again behind it, until a reading
    carries none. That reading is laid over the state (`lays_what_moved`). False where `proves` does not land, where a
    reading would not read, where an attempt member moved, and where the reading carries a transaction pending under
    a receipt the attempt does not name that the tick did not hold, as `pending` spells its pending record before the
    record -- however that record took it in.
    """
    moved: dict[str, ReportEvidence] = {}
    asks = partial(_retirement.moved_under, tick=context.state, into=moved)
    asked = _readings.asks_every_reading(context, asks)
    durable = reads(asked.gh, context.issue, context.state)[0]
    if durable is None:
        return False
    if moved.keys() & _retirement.receipts(context.state):
        return proves(moved) and stands_behind(context, proves, reads, pending)
    arrived = _commit_models.spelled(durable.data, _evidence_records.PENDING_EVIDENCE) != pending
    if lays_what_moved(context.state, durable, _attempts._ATTEMPT_KEYS):
        return False
    if not arrived or _landing_records.captured(durable) is not None:
        return True
    return _record_state.read_pending_evidence(durable) is None


def outranks_the_retired(state: PinnedState, read: PinnedState) -> None:
    """Stage on `state` a revision spent past each run `read` carries for the landed head that `state` no longer does.

    For a clear, whose write retires a run -- captured, or settled -- with the attempt that guarded it: the revision
    floor raised past that run in the very write (`rewrite_finish_outranking.spends_past`), so every reader reads it
    outranked however soon another road writes it back, and whatever later write of the clear's own is refused. `read`
    is the comment as the tick read it; a run `state` still carries is left as it is.
    """
    standing = {
        getattr(record, "receipt", None)
        for record in (_settlement.read_current_evidence(state), _record_state.read_pending_evidence(state))
    }
    for run in (_landing_records.captured(read), _landing_records.settled(read)):
        if run is not None and run.receipt not in standing:
            spends_past(state, run)


def retires_again(
    context: _base_sync_models._AutoRebaseRecoveryContext,
    reading: PinnedState | None,
    retired: frozenset[str],
    write: _commits.ReportWrite,
    reads: Callable[..., tuple],
) -> bool:
    """Retire again what a landed write retired that `reading` carries put back; whether none of it stands then.

    For a write that took the attempt guarding that evidence with it -- a clear -- so evidence another road put back
    right behind it under one of `retired`, the receipts it retired, stands guarded by nothing for the next proof to
    take up again. It is abandoned or invalidated again, staged on `reading` itself, and landed as `write` over it;
    where that does not land, the comment is read again through `reads` -- `verification_durable.durable_comment`, as
    the caller resolves it -- and asked once more. False where it still stands: a comment that would not read, writes
    that did not land, or no room for the history entry.
    """
    if reading is None:
        return False
    if _retires_over(context, reading, retired, write):
        return True
    reread = reads(context.gh, context.issue, reading)[0]
    return _retires_over(context, reread, retired, write)


def _retires_over(
    context: _base_sync_models._AutoRebaseRecoveryContext,
    reading: PinnedState | None,
    retired: frozenset[str],
    write: _commits.ReportWrite,
) -> bool:
    """Retire again, staged on `reading` and landed as `write` over it, what it carries under `retired`; whether none
    of it stands then."""
    if reading is None:
        return False
    retires = _retires_on(reading, retired)
    if retires is None:
        return True
    if not retires:
        return False
    landed = _commits.ReportCommit(context.gh, context.issue, reading).lands(reading, write)
    return landed.status is _commit_models.CommitStatus.COMMITTED


def _retires_on(staged: PinnedState, retired: frozenset[str]) -> bool | None:
    """Retire on `staged` the evidence standing there under one of `retired`; whether all of it was, None for none."""
    current = _settlement.read_current_evidence(staged)
    pending = _record_state.read_pending_evidence(staged)
    standing = [
        record for record in (current, pending)
        if record is not None and record.receipt in retired
    ]
    if not standing:
        return None
    invalidated = current not in standing or _settlement.retire_current_evidence(staged)
    abandoned = pending not in standing or _settlement.retire_pending_evidence(staged, pending)
    return invalidated and abandoned


def _moved(
    after: Mapping[str, Any], before: Mapping[str, Any],
) -> set[str]:
    """Every field `after` spells otherwise than `before`, one that either lacks included."""
    spelled = _commit_models.spelled
    return {
        field for field in after.keys() | before.keys()
        if spelled(after, field) != spelled(before, field)
    }
