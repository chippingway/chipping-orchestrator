# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one reading says of an issue's manifest correction, and what its one launch is held to.

`read` classifies the attempt a reading carries (`correction_records`), asking
nothing beyond the reading itself. Only ELIGIBLE grants anything, and only to a
pending attempt that is the record's own -- its source charged on this very
comment, in the cycle the comment is on -- whose context still stands, whose
launch the ledgers rule out a start of, and whose comment still has room for
its launch and its widest resolution. Everything else grants nothing:

- STARTED: the ledgers show its launch's start, or cannot rule one out
  (`started`). The launch is owed exactly once at the rejected run's charge
  (`run_charge_state.OwedLaunch`), and the circuit records that count
  (`run_ledger_values.AGENT_RUN_OWED_STARTED`) in the very write that starts
  its charge; the run count, the reservation's phase, the usage meter, and the
  usage receipts have to rule a start out as well, so a record a hand edit
  dropped grants nothing. It is never launched again: an ambiguous start is the caller's to
  answer, never a retry.
- STALE: a reading proves the context it was armed under moved -- a recorded
  requirements baseline other than the revision its source was handed, or a
  decomposer pin naming another command or session, or retired. Asked ahead
  of the start, since a moved context is what ends even a started attempt.
- UNPROVED: neither proves it moved and something it is held to cannot be read
  -- a baseline that is no digest, a pin the record's own reader of that member
  refuses -- which is no evidence of drift and no license either.
- CROWDED: the comment has no room for the charge, start, and receipt its
  launch leaves beside its widest resolution (`correction_room.launches`).
- EXHAUSTED and RETIRED: resolved; DAMAGED: a claim nothing can read, or a
  cycle identity nothing can; DISPLACED: a source charged on another record or
  in another cycle; ABSENT: nothing armed.

`owed_launch` is the seam the run circuit cooperates through: the one launch an
eligible attempt buys, owed at its source's charge, with `stands` asking every
reading the circuit charges or starts from (`run_circuit._owed_stands`) whether
that very attempt still reads ELIGIBLE there. No second charging system: the
reservation, its honoring across a crash, the start, and the lifetime ceiling
are the circuit's own. Nothing here writes, and nothing invokes it yet.
"""
from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable
from enum import StrEnum
from functools import partial
from types import MappingProxyType

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    drift as _engine_drift,
    invocations as _invocations,
    run_ledger_values as _run_ledger_values,
    usage_receipts as _usage_receipts,
)
from orchestrator.workflow.engine.run_charge_state import OwedLaunch
from orchestrator.workflow.stages.decomposition import (
    correction_records as _records,
    correction_room as _room,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

# The fields a pending attempt's context is read off: the requirements
# baseline and the two decomposer pins.
CONTEXT = (_engine_drift._USER_CONTENT_HASH, _state._DECOMPOSER_AGENT, _state._DECOMPOSER_SESSION_ID)

# The ledger fields its launch's start is read off.
LEDGER = (
    _run_ledger_values.AGENT_RUNS_USED,
    _run_ledger_values._METERED_RUNS,
    _run_ledger_values.AGENT_RUN_OWED_STARTED,
    _run_ledger_values.AGENT_RUN_RESERVATION,
    _usage_receipts.RECEIPTS,
)


class Standing(StrEnum):
    """What one reading says of the attempt it carries."""

    ABSENT = "absent"
    ELIGIBLE = "eligible"
    STARTED = "started"
    STALE = "stale"
    UNPROVED = "unproved"
    CROWDED = "crowded"
    EXHAUSTED = "exhausted"
    RETIRED = "retired"
    DAMAGED = "damaged"
    DISPLACED = "displaced"


# The resolved stages, read as what they are whatever the reading beside them.
_RESOLVED = MappingProxyType({
    _records.CorrectionStage.EXHAUSTED: Standing.EXHAUSTED,
    _records.CorrectionStage.RETIRED: Standing.RETIRED,
})


@dataclasses.dataclass(frozen=True)
class CorrectionReading:
    """One reading's standing, and the attempt it carries where one reads."""

    standing: Standing
    attempt: _records.CorrectionAttempt | None = None

    @property
    def grants(self) -> bool:
        """Whether this reading grants the attempt its one launch."""
        return self.standing is Standing.ELIGIBLE

    @classmethod
    def pending(cls, reading: PinnedState, attempt: _records.CorrectionAttempt) -> CorrectionReading:
        """What `reading` says of `attempt`, a pending attempt bound to it."""
        context = moved(reading, attempt.source)
        if context is Standing.STALE:
            return cls(context, attempt)
        if started(reading, attempt.owed_at):
            return cls(Standing.STARTED, attempt)
        if context is not None:
            return cls(context, attempt)
        roomy = _room.launches(reading.state_data, attempt)
        return cls(Standing.ELIGIBLE if roomy else Standing.CROWDED, attempt)


def read(reading: PinnedState, issue_number: int) -> CorrectionReading:
    """What `reading`, `issue_number`'s pinned comment, says of the correction attempt it carries."""
    if not _records.carries(reading):
        return CorrectionReading(Standing.ABSENT)
    attempt = _records.read(reading)
    if attempt is None or _invocations.cycle_of(reading) is None:
        return CorrectionReading(Standing.DAMAGED)
    if not attempt.source.binds(reading, issue_number):
        return CorrectionReading(Standing.DISPLACED, attempt)
    resolved = _RESOLVED.get(attempt.stage)
    return CorrectionReading.pending(reading, attempt) if resolved is None else CorrectionReading(resolved, attempt)


def started(reading: PinnedState, owed_at: int) -> bool:
    """Whether `reading`'s ledgers show, or cannot rule out, the start of a launch owed at `owed_at`.

    The circuit records that count in the very write that starts the launch's
    charge, so a start recorded at it, or at a later count, or spelled as no
    count, may be it. Its absence is not taken on its own word, since a hand
    edit can drop it: the run count has to rule a start out as well. A count
    still at the source's charge saw no launch charged since; one past it rules
    a start out only where the one charge since stands `reserved`, unstarted --
    the charge the circuit honors across a crash for the launch it was taken
    for, which is kept for it rather than paid again
    (`correction_room.reserved_since`) -- and a count further
    on, or a phase reading `started`, none, or one this build does not write,
    may be the launch's own. A count read below the source's charge rules
    nothing out, since the count only ever rises, and neither does a usage
    receipt of a process charged after the source, or a receipt ledger
    nobody can read. Nor does a usage meter past the source's charge, whatever
    phase the reservation reads: the meter counts processes that returned, each
    one charged first, so a count past the source's is a process charged after
    it that ran -- evidence a reservation set back to `reserved` cannot answer.
    The count is read strictly
    (`run_ledger_values._runs_used_strictly`): the run ledger's own charge
    count, which has to read as one, beside the usage meter, absent or
    readable, since the meter alone is only a floor of what was spent, so a
    charge count nobody can read rules nothing out either.
    """
    recorded = _run_ledger_values._owed_started(reading)
    if reading.carries(_run_ledger_values.AGENT_RUN_OWED_STARTED) and (recorded is None or recorded >= owed_at):
        return True
    receipts = _usage_receipts.read(reading)
    if receipts is None or receipts.latest > owed_at:
        return True
    metered = _run_ledger_values._counted(reading.get(_run_ledger_values._METERED_RUNS))
    if metered is not None and metered > owed_at:
        return True
    used = _run_ledger_values._runs_used_strictly(reading)
    return used != owed_at and not _room.reserved_since(reading, owed_at)


def moved(reading: PinnedState, source: _records.CorrectionSource) -> Standing | None:
    """STALE where `reading` proves `source`'s context moved, UNPROVED where nothing proves either, else None.

    What counts as that proof is the source's own reading of the baseline and
    the pins (`correction_records.CorrectionSource.stands_on`).
    """
    stands = source.stands_on(reading)
    if stands is None:
        return Standing.UNPROVED
    return None if stands else Standing.STALE


def owed_launch(
    issue_number: int,
    attempt: _records.CorrectionAttempt,
    resolves: Callable[[], bool] | None = None,
) -> OwedLaunch:
    """The one launch `attempt` buys on `issue_number`, owed at its source's charge and held to the attempt.

    `stands` asks every reading the circuit charges or starts it from whether
    that very attempt still reads ELIGIBLE there, so a resolution, a context
    moved, a start recorded, or a comment pinned in its place since refuses
    it with nothing written; `resolves` is the caller's own question of what
    stands beyond the comment -- a hold, the owner, the requirements read
    again -- asked right behind the charge.
    """
    return OwedLaunch(at=attempt.owed_at, resolves=resolves, stands=partial(_stands, issue_number, attempt))


def _stands(issue_number: int, attempt: _records.CorrectionAttempt, reading: PinnedState) -> bool:
    """Whether `attempt` still reads ELIGIBLE on `reading`, said locally where it does not."""
    standing = read(reading, issue_number)
    if standing == CorrectionReading(Standing.ELIGIBLE, attempt):
        return True
    log.warning(
        "issue=#%d its manifest correction reads %s on the comment its launch is charged from; launching nothing",
        issue_number, standing.standing.value,
    )
    return False
