# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one manifest correction an initial decomposition may be allowed, as its pinned record spells it.

One pinned field, `decomposer_correction` (`state._DECOMPOSER_CORRECTION`),
holds at most one attempt: the allowance a rejected decomposer answer earns to
be asked, once, for a complete corrected manifest. It is tied to what that
allowance is about and to nothing else -- the process invocation whose answer
was rejected (`source`, the six members `engine/invocations.minted` gave it),
the requirements revision that run was handed (`requirements`, one digest),
the saved decomposer command and session a correction resumes (`command`,
`session`), and the validation error the answer was rejected with
(`diagnostic`, the one line the correction prompt quotes) -- so no request
fingerprint, session id alone, log, analytics row, or in-memory counter is what
a later tick recovers it by, and a launch a restart, a refused start, or a
granted run limit left owed is still asked with the exact error.

Three stages, every member spelled on every record of its stage:

- `pending`: the allowance stands. Whether its one launch has started is not
  spelled here. That launch is owed exactly once, at the rejected run's
  charge (`run_charge_state.OwedLaunch`), and the run circuit records its start
  in the very write that starts its charge, so the ledgers' own records of that
  start -- the owed start, the run count and its reservation's phase, the usage
  receipts -- are what tell an eligible attempt from one that may have run
  (`correction_standing`), with no window in which a process ran and nothing
  says so.
- `exhausted`: spent -- by the correction's own answer, by a start nobody can
  account for, or given up before any launch. `correction` names the
  correction's own invocation where one returned, `null` where none did.
- `retired`: ended because a reading proved the context it was armed under
  moved.

A resolved record adds `floor`, the lifetime run count the issue had reached
when it resolved, held to the widest number a record holds. A charge's ordinal
orders an issue's invocations and is never reused, so no invocation charged at
or below the floor -- the source, the correction, a correction that may still
have been running -- is ever the source of a fresh allowance: a correction's
own rejected answer stays part of the attempt it was bought by, however often
it is offered.

Read strictly and whole: an object with a key its stage does not spell, or
lacking one, or with any member out of its bound -- a repository slug, a
recorded number, a nonce of the minted shape, a digest, one bounded line each
for the command and the session, a correction not charged after its source on
the same record and cycle, a floor below what it covers, a diagnostic past its
one bounded line -- is no record at all,
answered None, which `carries` tells apart from an absent field.
"""
from __future__ import annotations

import dataclasses
from enum import StrEnum
from functools import partial
from operator import attrgetter
from types import MappingProxyType
from typing import Any

from orchestrator.agents.models import AgentInvocation
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    completion_spelling as _spelling,
    completion_values as _bounds,
    drift as _engine_drift,
    invocations as _invocations,
    report_record_values as _record_values,
    run_ledger_values as _run_ledger_values,
    usage_receipts as _usage_receipts,
)
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads
from orchestrator.workflow.stages.decomposition import state as _state

_STAGE = "stage"
_SOURCE = "source"
_CORRECTION = "correction"
_FLOOR = "floor"

# The longest validation error an attempt keeps for its correction prompt:
# every error the manifest parser spells is one short line, and one past this
# is no error a record holds, so its answer parks as any other.
MAX_DIAGNOSTIC = 1024

# What every stage spells beside its stage and its source, each by its own reader.
_CONTEXT = MappingProxyType({
    "requirements": partial(_payloads.as_hex, lengths=_formats.DIGEST_LENGTHS),
    "command": partial(_bounds.line, limit=_bounds.MAX_COMMAND),
    "session": partial(_bounds.line, limit=_bounds.MAX_SESSION),
    "diagnostic": partial(_bounds.line, limit=MAX_DIAGNOSTIC),
})

# The members of an invocation that name the record and the cycle it ran on.
_RECORD = attrgetter("repo", "issue", "comment", "cycle")

# The decomposer pins a source saves its conversation under, and the member each holds.
_PINS = MappingProxyType({_state._DECOMPOSER_AGENT: "command", _state._DECOMPOSER_SESSION_ID: "session"})


class CorrectionStage(StrEnum):
    """Where one attempt stands on the record."""

    PENDING = "pending"
    EXHAUSTED = "exhausted"
    RETIRED = "retired"


# Every key each stage spells, and nothing else.
_MEMBERS = MappingProxyType({
    stage: frozenset((_STAGE, _SOURCE, *_CONTEXT, *added))
    for stage, added in (
        (CorrectionStage.PENDING, ()),
        (CorrectionStage.EXHAUSTED, (_CORRECTION, _FLOOR)),
        (CorrectionStage.RETIRED, (_FLOOR,)),
    )
})


@dataclasses.dataclass(frozen=True)
class CorrectionSource:
    """The rejected run an allowance is armed for: its invocation, requirements, saved conversation, and its error."""

    invocation: AgentInvocation
    requirements: str
    command: str
    session: str
    diagnostic: str

    def binds(self, reading: PinnedState, issue_number: int) -> bool:
        """Whether `reading` is the record this source was charged on, still in the cycle it ran in.

        A comment a human pinned in place of that one is no record of the
        run, whatever it copied, and a restart has ended the cycle it ran in.
        """
        read_as = (reading.repo_slug or "", issue_number, reading.comment_id, _invocations.cycle_of(reading))
        return _RECORD(self.invocation) == read_as

    def stands_on(self, reading: PinnedState) -> bool | None:
        """Whether the context this source was armed under stands on `reading`; None where nothing proves either.

        False only on evidence that it moved. A requirements baseline is
        evidence only as a digest naming other requirements, and a decomposer
        pin only as a value the record's own reader of that member takes,
        naming another command or session -- or as one absent or `null`: a pin
        retired is a conversation nothing may resume. A pin that reader refuses
        proves nothing either way, and neither does a baseline that is no
        digest.
        """
        pins = [self._pin_moved(reading, pin) for pin in _PINS]
        recorded = reading.get(_engine_drift._USER_CONTENT_HASH)
        baseline = _payloads.as_hex(recorded, _formats.DIGEST_LENGTHS)
        if True in pins or baseline not in {None, self.requirements}:
            return False
        if baseline is None or None in pins:
            return None
        return True

    def charged_after(self, invocation: AgentInvocation | None) -> bool:
        """Whether `invocation` is one that ran on this source's record and in its cycle, under a later charge."""
        if invocation is None or invocation.ordinal <= self.invocation.ordinal:
            return False
        return _RECORD(invocation) == _RECORD(self.invocation)

    def _pin_moved(self, reading: PinnedState, pin: str) -> bool | None:
        """Whether `reading`'s `pin` names other than what this source saved there; None where its reader refuses it."""
        pinned = reading.get(pin)
        if pinned is None:
            return True
        member = _PINS[pin]
        held = _CONTEXT[member](pinned)
        if held is None:
            return None
        return held != getattr(self, member)


@dataclasses.dataclass(frozen=True)
class CorrectionAttempt:
    """One attempt: the source it was armed for, the stage it stands at, and what a resolved one covers."""

    source: CorrectionSource
    stage: CorrectionStage = CorrectionStage.PENDING
    correction: AgentInvocation | None = None
    floor: int | None = None

    @property
    def owed_at(self) -> int:
        """The lifetime run count its one launch is owed at: the charge the rejected run was started under."""
        return self.source.invocation.ordinal

    def resolved(
        self, stage: CorrectionStage, floor: int, correction: AgentInvocation | None = None,
    ) -> CorrectionAttempt:
        """This attempt resolved at `stage`, covering every charge up to `floor` and the ones it names.

        Held to the widest number a record holds: no source charged past it can
        be recorded, so a floor there covers every one that could arm, where a
        floor past it would be one no reader takes.
        """
        covered = max(self.owed_at, floor)
        if correction is not None:
            covered = max(covered, correction.ordinal)
        return dataclasses.replace(
            self, stage=stage, correction=correction, floor=min(covered, _record_values.MAX_RECORDED_NUMBER),
        )

    def resolution(self, raw: dict) -> CorrectionAttempt | None:
        """This pending attempt at the resolved stage `raw` spells, or None where its tail is none this build writes.

        A correction is the attempt's own only where it ran on the source's
        record and cycle under a later charge, and a floor covers both.
        """
        floor = _record_values.as_recorded_number(raw[_FLOOR])
        spelled = raw.get(_CORRECTION)
        correction = None if spelled is None else _invocation(spelled)
        own = spelled is None or self.source.charged_after(correction)
        if floor is None or not own:
            return None
        resolved = self.resolved(self.stage, floor, correction)
        return resolved if resolved.floor == floor else None

    def floor_on(self, reading: PinnedState) -> int | None:
        """The floor this attempt resolves under over `reading`: its strict run count, where that covers every charge.

        None where the count does not read (`run_ledger_values._runs_used_strictly`),
        where it reads below a charge the ledgers still record -- one an owed
        start says a launch was charged past, or one a usage receipt covers --
        or where either record does not read. A floor below a charge taken
        would let that charge's invocation, a correction's own rejected answer
        among them, arm again once the count read as it should.
        """
        used = _run_ledger_values._runs_used_strictly(reading)
        receipts = _usage_receipts.read(reading)
        if used is None or receipts is None or receipts.latest > used:
            return None
        started = _run_ledger_values._owed_started(reading)
        if reading.carries(_run_ledger_values.AGENT_RUN_OWED_STARTED) and (started is None or started >= used):
            return None
        return used

    def covers(self, ordinal: int) -> bool:
        """Whether an invocation charged at `ordinal` belongs to this attempt, so it can never arm another."""
        covered = self.owed_at if self.floor is None else self.floor
        return ordinal <= covered

    def spelled(self) -> dict[str, Any]:
        """The pinned object this attempt is written as, in the JSON types a reading parses it back into."""
        source = self.source
        spelling = {
            _STAGE: self.stage.value,
            _SOURCE: dataclasses.asdict(source.invocation),
            **{member: getattr(source, member) for member in _CONTEXT},
        }
        if self.stage is not CorrectionStage.PENDING:
            spelling[_FLOOR] = self.floor
        if self.stage is CorrectionStage.EXHAUSTED:
            correction = self.correction
            spelling[_CORRECTION] = correction if correction is None else dataclasses.asdict(correction)
        return spelling

    def recordable(self) -> bool:
        """Whether this attempt reads back as itself once written: every member within its bound."""
        return read(PinnedState(state_data={_state._DECOMPOSER_CORRECTION: self.spelled()})) == self


def carries(state: PinnedState) -> bool:
    """Whether the issue CLAIMS a correction attempt, whatever the field holds."""
    return state.carries(_state._DECOMPOSER_CORRECTION)


def read(state: PinnedState) -> CorrectionAttempt | None:
    """The attempt `state` carries: None where it carries none, or carries one nothing can read."""
    raw = state.get(_state._DECOMPOSER_CORRECTION)
    if not isinstance(raw, dict):
        return None
    stage = _payloads.as_member(CorrectionStage, raw.get(_STAGE))
    if stage is None or set(raw) != _MEMBERS[stage]:
        return None
    source = _source(raw)
    if source is None:
        return None
    pending = CorrectionAttempt(source, stage)
    return pending if stage is CorrectionStage.PENDING else pending.resolution(raw)


def _source(raw: dict) -> CorrectionSource | None:
    """The source one attempt's object spells, every member within its bound, or None."""
    invocation = _invocation(raw[_SOURCE])
    context = {member: _CONTEXT[member](raw[member]) for member in _CONTEXT}
    if invocation is None or None in context.values():
        return None
    return CorrectionSource(invocation, **context)


def _invocation(raw: Any) -> AgentInvocation | None:
    """The invocation one pinned object spells, read as a captured completion's is, or None."""
    readers = _spelling._INVOCATION
    if not isinstance(raw, dict) or set(raw) != set(readers):
        return None
    members = {member: readers[member].read(raw[member]) for member in readers}
    return None if _bounds.DAMAGED in members.values() else AgentInvocation(**members)
