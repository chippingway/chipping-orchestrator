# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Prove that a snapshot's complete consumer ledger has ended before reclamation.

A cancelled partial split uses its recorded seal or count, and a pre-split
phase proves completeness only when no child publication began. Every
consumer in that complete ledger must be freshly known closed.
"""
from __future__ import annotations

from orchestrator.github.issues import issue_is_closed
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    formats as _formats,
)
from orchestrator.workflow.late_split.models import (
    LateGeneration,
)
from orchestrator.workflow.late_split.phases import LatePhase
from orchestrator.workflow.stages.decomposition import (
    late_cleanup_reading as _late_cleanup_reading,
    state as _state,
)
from orchestrator.workflow.stages.decomposition.models import _ChildScan

# The count the split transaction writes before it creates its first child,
# in the same write as `splitting`. It is the stage's own key rather than this
# domain's, and it is read here for one reason: it is durable evidence that a
# transaction began which no later write of the PHASE can erase.
_EXPECTED_CHILDREN = "expected_children_count"

# The phases that come BEFORE the split loop, where the whole account of the
# children cut from this generation's ref is "there are none yet": `splitting`
# goes down and is persisted ahead of the first create, so a record standing
# earlier has made no child at all.
#
# That is a claim about the record as much as about the phase, and it is held
# to the record rather than taken on the phase's word -- because a phase is
# not only written forwards. The post-agent owner check writes `owner_check`
# over whatever boundary it interrupts, so a transaction re-entered after a
# crash reads as one of these with a half-filled ledger standing behind it,
# and believing the phase there would delete the ref out from under whichever
# child the loop had already created. So a record naming any child at all is
# not one of these however it is labelled.
_PRE_SPLIT_PHASES = frozenset((
    LatePhase.MEASURING,
    LatePhase.HOLDING_PLAN_PR,
    LatePhase.ADJUDICATING,
    LatePhase.OWNER_CHECK,
    LatePhase.SNAPSHOTTING,
))

# The phases PAST the loop, where the ledger is whole whatever it holds: the
# transaction moves on only once every child has been created AND recorded,
# and one that could not be leaves the record parked where it stands. These
# are the only boundaries whose word is enough on its own.
_SETTLED_SPLIT_PHASES = frozenset((
    LatePhase.SUPERSEDING,
    LatePhase.CLEANING_UP,
))


def _reclaimable(
    state: PinnedState, generation: LateGeneration, scan: _ChildScan,
) -> bool:
    """Whether every direct consumer this snapshot records is terminal.

    Asked of a scan taken this tick, and asked again from scratch on every
    visit -- a consumer read as closed once is not a fact this ledger latches.
    A human who reopens one before the delete lands has a live consumer again,
    and the answer the next reading gives is the one that decides.

    Fail-closed: a consumer the scan does not carry, one whose read failed, or
    a consumer ledger this binary could not type is a consumer that may still
    be cutting from the ref, and deleting on the strength of a reading nobody
    gave would destroy the only copy of work a child was told to reuse.

    All of which is about the consumers the ledger NAMES, and the prior
    question is whether it names all of them -- see `_whole_ledger`. Asked
    first, because every proof below is only as complete as the list it walks.
    """
    if _late_cleanup_reading._unwritable(generation) or generation.has_opaque_ledger:
        return False
    if not _whole_ledger(state, generation):
        return False
    return all(_ended(scan, consumer) for consumer in generation.consumers)


def _whole_ledger(state: PinnedState, generation: LateGeneration) -> bool:
    """Whether the ledger names every child cut from this generation's ref.

    The question the per-consumer proof rests on, and the record's own phase
    is what answers it. The split creates a child issue and records it in two
    steps -- it must, since a child on GitHub the parent does not record is a
    child nothing would come back to -- so while `splitting` stands the list
    may be short by one that already exists, and a list of ended consumers
    proves nothing about the child it has not reached. That window is where a
    partial ledger would otherwise authorize the delete, unread and untold.
    Either side of it the list is whole: nothing has been created yet, or the
    loop ran to the end and the transaction moved on.

    It is also what makes an EMPTY ledger a fact rather than a gap, which is
    what left a ref nothing would ever reclaim: the snapshot is retained
    before the first child exists, so an owner a human closed in that interval
    has no consumers because there are none, and `all(())` settles it.

    A loop the RECORD proves finished is whole at any boundary, which is
    asked before the phase is consulted at all -- see `_every_child_recorded`.
    Two writers make that necessary and neither is a bug: `splitting` is
    written before the first create and again beside every child recorded, so
    the phase alone cannot say which end of the loop a record sits at; and a
    retried transaction rewrites `snapshotting` over whatever it reached, so a
    finished split can come back wearing the boundary it started from.

    A boundary before the loop is believed only as far as the record bears it
    out -- see `_split_began`. A pinned comment written by a binary that
    rewound its own phase is exactly what that reading is for: the guard on
    the record stops new rewinds and migrates nothing, so what has to answer
    for one already in flight is evidence no phase write ever touched. Past
    the loop the phase needs no corroboration: the transaction reaches
    `superseding` only once every child is created and recorded.

    A SEALED ledger answers ahead of all of it. The count can only ever be
    reached by a loop that ran to the end of its manifest, and a cancelled one
    never will: the children it did not make are ones nothing is going to
    make. So the loop that stopped writes down that its register is final --
    which it only does where every child that exists is already on it -- and
    that is a stronger reading than the count, not a weaker one.

    Believed only for the cycle it NAMES. The seal is a decomposition key
    rather than a late one, so no write that ends a generation drops it, and
    a later cycle on the same issue reads a seal its own split never wrote. A
    partial register would then look final, and the delete below would take
    the ref that cycle's unrecorded children were cut from.

    Which phase answers, for a cycle whose own `phase` field has been taken
    over by its cancellation, is `_accounted_at`'s question.
    """
    boundary = _accounted_at(generation)
    if boundary in _SETTLED_SPLIT_PHASES:
        return True
    if _state._ledger_is_sealed(
        state.get(_state._SPLIT_LEDGER_SEALED), generation.cycle_id,
    ):
        return True
    if _every_child_recorded(state, generation):
        return True
    if boundary not in _PRE_SPLIT_PHASES:
        return False
    return not _split_began(state, generation)


def _every_child_recorded(
    state: PinnedState, generation: LateGeneration,
) -> bool:
    """Whether the split loop reached the end of the manifest it was given.

    Asked of every boundary, because more than one of them is ambiguous.
    `splitting` is written before the first create AND again beside every
    child recorded, the last one included, so a record standing there is
    either a loop mid-flight or one that finished and died before the step
    that would have moved it on. `snapshotting` is the same question one
    retry later: a transaction resumed after a park rewrites it over whatever
    boundary it had reached, so a finished split comes back wearing the one it
    started from. Reading either as mid-flight retains a ref no later pass can
    ever release, because nothing revisits a cancelled owner to move a phase
    for it.

    What separates them is the count the transaction wrote ahead of its first
    create, against the positional register it appends to as each child is
    recorded. The register is written in the SAME step as the consumer and
    the child obligation, so reaching the count means every child exists and
    every one of them is on the ledgers this proof walks.

    Fail-closed on anything else. A count that is not a positive whole number
    is a field this binary cannot act on, and a register short of it is the
    window this whole question exists for.
    """
    expected = state.get(_EXPECTED_CHILDREN)
    if not _formats.whole_number(expected) or expected <= 0:
        return False
    return len(generation.split_children) >= expected


def _split_began(state: PinnedState, generation: LateGeneration) -> bool:
    """Whether this record shows a split transaction that already started.

    Two signs, and only one of them survives a phase somebody moved. The
    ledgers are the obvious one: a consumer or a split child recorded here is
    a child this generation made, whatever boundary the record is wearing.

    The other is the one that matters, because the window this question exists
    for is the window where the ledgers say NOTHING. A child is created before
    the write that records it, so a loop that died between the two leaves an
    empty ledger and a real issue on GitHub -- and the count the transaction
    puts down BEFORE its first create, in the same write as `splitting`, is
    then the only thing left. A binary that rewound the phase over it (which
    is what every record already in flight was written by) left that count
    exactly where it was, so this is what upgrades one rather than believing
    the boundary it now wears.

    A stale count from an ordinary decomposition of the same issue reads the
    same way, and is meant to: an issue that split into children became an
    umbrella with no implementation of its own, so reaching the late gate at
    all takes a human moving its label -- and being wrong in that direction
    keeps a ref, holds a terminal, and says so on every visit, where being
    wrong in the other deletes the only copy of a child's work.
    """
    if state.get(_EXPECTED_CHILDREN) is not None:
        return True
    return bool(generation.consumers or generation.split_children)


def _accounted_at(generation: LateGeneration) -> LatePhase | None:
    """The boundary whose account of the consumers this ref is judged by.

    Ordinarily the phase the record stands at. A cancelled cycle is the one
    that needs asking, because `cancelling` is itself a boundary and it
    overwrites the one the cancellation interrupted -- a generation cancelled
    while its split loop was running and one cancelled long past it would
    otherwise read alike, and the reading they would share proves nothing, so
    every ref either of them holds would be retained for good.

    So the cancellation keeps the phase it interrupted, and that is what is
    asked here. A cancelled record that kept none -- one an older binary
    marked, or one whose own field was damaged -- answers with something
    outside the set, which retains the ref: a cancellation is exactly when
    nobody is coming back to prove a partial ledger whole.
    """
    if generation.cancelled:
        return generation.cancelled_phase
    return generation.phase


def _ended(scan: _ChildScan, consumer: int) -> bool:
    """Whether a fresh read says this recorded consumer has ended.

    The issue's own state, not its label. All three dispositions that end a
    consumer -- reaching `done`, being `rejected`, and a human closing it --
    close the issue, and none of them survives a reopen. A LABEL does:
    reopening a child leaves `done` or `rejected` exactly where it was, so a
    reading taken off the label would call a child that is live again terminal
    and delete the only copy of the work it came back for.

    `done` still covers a nested split, for the reason it always did: a child
    that reached it has published, so its own descendants are past needing the
    ancestor -- and it reached it by being finished and closed.

    The close is asked through the shared predicate rather than by reading an
    attribute here, because the only spelling a real issue carries it under is
    `state`. A consumer the scan never fetched is `None`, which is not closed,
    so an unknown or unreadable consumer keeps the ref.
    """
    return issue_is_closed(scan.issues.get(int(consumer)))
