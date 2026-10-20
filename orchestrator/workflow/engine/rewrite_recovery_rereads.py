# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The comment a dormant recovery reads behind its writes, laid over the tick's state where another road moved it.

The reset's record (`rewrite_recovery_parks.records_the_reset`) and a landed hold's, park's, or clear's record answer
over the comment read afresh behind them, laid over the tick's state where another road moved it (`lays_what_moved`);
behind a hold or park, movement under any evidence it carries is proved again first (`stands_behind`); and a run a clear
or releasing park retires is outranked in that write (`outranks_the_retired`), retired again behind a clear where
written back (`retires_again`). Dormant, as those records are: no recovery context the workflow builds reaches it.
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

    A field `state` itself moved off that reading is the tick's own staging and is kept. True where a field laid is one
    of `held`, or a transaction another road recorded pending under a receipt the attempt does not name. A state nothing
    was read into lays nothing.
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
    before: PinnedState,
) -> bool:
    """Whether a record that landed may answer over the comment read afresh behind it, what moved there proved first.

    Read through `reads` (`verification_durable.durable_comment`, as the caller resolves it), the comment is asked what
    moves under the evidence it carries (`rewrite_landing_retirement.moved_under`), evidence under a receipt history
    records retired -- its own, the tick's, or `before`'s, the state ahead of the record, so a record that took the
    evidence back in erases none of it -- moved by that alone, handed to `proves` (a successor laid over the state first
    to be proved on its own binding, `reconciles`) and read again until none moves, then laid over the state
    (`lays_what_moved`). False where `proves` does not land, a reading would not read, an attempt member moved, or it
    carries a transaction pending under a receipt the attempt does not name that `before` did not.
    """
    moved: dict[str, ReportEvidence] = {}
    asks = partial(_retirement.moved_under, tick=context.state, into=moved)
    asked = _readings.asks_every_reading(context, asks)
    durable = reads(asked.gh, context.issue, context.state)[0]
    if durable is None:
        return False
    retired = {
        entry.receipt
        for state in (before, context.state, durable)
        for entry in _settlement.read_evidence_history(state) or ()
    }
    retired &= _retirement.receipts(durable) - moved.keys()
    moved.update(dict.fromkeys(retired, _readings.REVIVED))
    if moved.keys() - _retirement.receipts(context.state):
        moved = _retirement.reconciles(context, moved)
    if moved:
        return proves(moved) and stands_behind(context, proves, reads, before)
    if lays_what_moved(context.state, durable, _attempts._ATTEMPT_KEYS):
        return False
    return (
        _commit_models.spelled(durable.data, _evidence_records.PENDING_EVIDENCE)
        == _commit_models.spelled(before.data, _evidence_records.PENDING_EVIDENCE)
        or _landing_records.captured(durable) is not None
        or _record_state.read_pending_evidence(durable) is None
    )


def outranks_the_retired(state: PinnedState, read: PinnedState) -> None:
    """Stage on `state` a revision spent past each run `read` carries for the landed head that `state` no longer does.

    For a clear, or a releasing park, whose write retires a run with its attempt: the floor raised past it there
    (`rewrite_finish_outranking.spends_past`) keeps it outranked however it is written back. `read` is as the tick read.
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

    For a clear, which took the attempt guarding it: evidence under one of `retired` is retired again, staged on
    `reading` and landed as `write`, asked once more over a reading through `reads` where that does not land.
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
