# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where a landed rewrite's finish stops short of its route, and what the dormant policy proves around each stop.

The coordinator (`rewrite_finish.finalizes`) stops short of a route at a
landing the pinned record does not account for, at the park a debt with no
room takes, and wherever a write of its announcement or its retirement does
not land -- refused, unconfirmed, or raising. Each of those stops is taken
here, and it answers for both policies a finish can be held to: a finish not
held to the dormant settled-evidence policy
(`rewrite_finish_models.LandedFinish.proves_settled`) stops exactly as the
policy every road selects has it, the last word over a transaction still
recorded for the head asked behind it and nothing more read. One held to it
proves evidence settled for the head ready around the stop, so movement read
under that evidence -- however soon what moved is put back -- invalidates it
whole before anything keeps it standing for a later finish:

- `unfinishable` proves that evidence, and a captured transaction whole,
  beside an attempt still standing, leaving a successor that proof found
  recorded behind its invalidation owed as written; where the attempt is
  retired or another road replaced it, it reads nothing more, save evidence
  carrying the mark of movement an earlier finish recorded under that receipt
  (`rewrite_finish_unconfirmed.retires_the_marked`).
- `ahead_of_the_park` proves that evidence and a captured transaction whole
  ahead of the park a debt with no room takes, which keeps both for the reply.
- `relabels` routes the issue to `workflow:validating` once for the head
  (`rewrite_finish_announced.relabelled`), behind the relabel's own record
  (`rewrite_finish_announced.relabels_once`), the evidence proved ready ahead
  of the relabel and behind one that raised -- over the evidence the comment
  carries by then -- the label and the attempt read again behind that proof's
  requests, settled evidence that reading records moving invalidated, and
  holds where the label could not be read again or another attempt stands, so
  nobody relabels twice or over an attempt not its own.
- `observing` is where a stop's guarded writes collect the movement their
  refusals read (`rewrite_finish_writes.lands`) -- a binding record named
  moved, and what the comment a refusal was read over records under the
  evidence, asked of it the moment it is read: the prerequisite's own reading
  of a captured transaction (`rewrite_finish_settled.reads_moving`), or, over
  settled evidence, a blank of the attempt's base tip and what the readiness
  proof hears moving in the records alone (`_reads_moving`).
- `behind_the_announcement` and `behind_the_write` answer a stop of the
  announcement, the park, or the retirement with that evidence proved ready
  once more and invalidated over any movement a refusal read
  (`rewrite_finish_readiness.invalidates_behind`) -- behind a write nobody
  confirmed, over the attempt as that write may have left it
  (`rewrite_finish_unconfirmed`), movement the comment that reconciliation
  read records kept as the movement it is however soon it is put back -- a
  successor another road recorded behind those writes left owed as written.

Nothing here runs the configured commands, posts an artifact, launches a
developer, or announces anything.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from functools import partial

from orchestrator.git.base_sync import (
    attempt_records as _attempt_records,
    attempts as _attempts,
    state as _base_sync_state,
)
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    report_evidence_models as _evidence_models,
    rewrite_finish_captured as _captured,
    rewrite_finish_readiness as _readiness,
    rewrite_finish_rechecks as _rechecks,
    rewrite_finish_settled as _settled,
    rewrite_finish_unconfirmed as _unconfirmed,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_announced import relabelled, relabels_once
from orchestrator.workflow.engine.rewrite_finish_marks import retires_as_it_stands
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, LandedFinish
from orchestrator.workflow.engine.verification_proof import ProofReading
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# The base tip the attempt recorded its replay as made onto, which a proof
# blanks to record movement read under the evidence where nothing else has
# room (`rewrite_finish_readiness._invalidates_on_the_tick`).
_TIP = _base_sync_state._PENDING_REWRITE_BASE

# That blank, read by a refusal of one of the coordinator's own writes: the
# movement it records, however soon the tip is put back.
_BLANKED = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.DEFER,
    "the attempt's base tip was read blanked under a write finishing the landing, recording movement read under "
    "the evidence",
)


def unfinishable(finish: LandedFinish) -> FinishOutcome:
    """UNFINISHABLE, behind the last word over what an earlier finish captured for a landing nothing accounts for.

    A transaction a finish of this landing captured for its head is proved
    again whole and abandoned where anything it rests on moved
    (`rewrite_finish_captured.stands_before_the_route`), so putting what moved
    back before a later finish revives nothing. A finish held to the
    settled-evidence policy proves settled evidence ready first
    (`rewrite_finish_settled.stands_ready_if_settled`) while its attempt
    stands; one finding it retired or replaced reads nothing more, save
    evidence carrying the mark of movement an earlier finish recorded under
    that receipt, which is retired whole where room allows
    (`rewrite_finish_unconfirmed.retires_the_marked`). Where that proof holds
    over a transaction its fresh reading behind an invalidation laid over the
    tick's state (`rewrite_finish_rechecks.rechecks_behind`) -- one another road
    recorded right behind that write -- the hold is honoured: that record
    stands as its road wrote it, owed for whoever answers it, and no last word
    is taken over it.
    """
    standing = finish.anchor and finish.state.get(_base_sync_state._PENDING_PUSH_SHA) == finish.anchor
    if finish.proves_settled and not standing:
        _unconfirmed.retires_the_marked(finish)
        return FinishOutcome.UNFINISHABLE
    captured = _captured.recorded(finish, logged=False)
    stopped = _settled.stands_ready_if_settled(finish)
    if stopped is not None and _captured.recorded(finish, logged=False) != captured:
        log.warning(
            "issue=#%d leaving the verification evidence recorded for %.8s behind its readiness proof owed as written",
            finish.issue.number, finish.head,
        )
        return FinishOutcome.UNFINISHABLE
    return _captured.stands_before_the_route(finish, behind=FinishOutcome.UNFINISHABLE, whole=True)


def ahead_of_the_park(finish: LandedFinish) -> FinishOutcome | None:
    """Prove what an earlier finish made for the head ahead of the park a debt with no room takes; None to park.

    Nothing is read for a finish not held to the settled-evidence policy. For
    one that is, settled evidence is proved ready
    (`rewrite_finish_settled.stands_ready_if_settled`), since the park keeps it
    for the reply, a proof that holds holding the park too; and a captured
    transaction is proved again whole and abandoned where anything moved
    (`rewrite_finish_captured.stands_before_the_route`).
    """
    if not finish.proves_settled:
        return None
    stopped = _settled.stands_ready_if_settled(finish)
    if stopped is not None or _captured.recorded(finish, logged=False) is None:
        return stopped
    return _captured.stands_before_the_route(finish, whole=True)


def relabels(finish: LandedFinish, observed: ProofReading, *, announced: bool) -> FinishOutcome | None:
    """Relabel `finish`'s issue to `workflow:validating` where nobody has for the head; None to go on.

    `announced` is whether the tick read the mark down for the landed head.
    Every finish but one held to the settled-evidence policy relabels unless
    that mark and the tick's label say the issue is already there, and
    records nothing of it. Such a finish reads the mark, the relabel's own
    record, and the label afresh (`rewrite_finish_announced.relabelled`),
    proves settled evidence ready ahead of a relabel it makes
    (`rewrite_finish_settled.stands_ready_if_settled`) -- a proof that holds
    holding the relabel too -- and once more behind one that raised, over the
    evidence records the comment carries by then, so a successor another road
    settled while the relabel was made is proved on its own binding -- and
    holds the route, the evidence proved, where the label would not read.
    That proof makes requests of its own, and another finish of the landing
    may relabel while they are answered, or another road put an attempt of
    its own in place, so behind them the comment is read afresh -- this
    landing's own bookkeeping taken in, settled evidence that reading records
    moving invalidated over `observed`'s classifier -- a successor it carries
    in that evidence's place asked on its own binding -- and the route held with
    nothing relabelled where it no longer carries the attempt this finish
    holds (`rewrite_finish_rechecks.stands_afresh`) or would not read -- and
    the label once more, so the relabel, and its stage-entry event, is not
    made twice. The relabel lands behind its record
    (`rewrite_finish_announced.relabels_once`), and a record that did not land
    has the evidence invalidated over a binding record its refusal read
    moving, or proved ready once more (`rewrite_finish_readiness.invalidates_behind`).
    """
    made = relabelled(finish, announced=announced)
    if made:
        return None
    attempt = _commit_models.PinnedCommit.capture(finish.state, prerequisites=_attempts._ATTEMPT_KEYS)
    stopped = _settled.stands_ready_if_settled(finish)
    goes_on = stopped is None and made is not None
    if goes_on and finish.proves_settled and not _rechecks.stands_afresh(finish, attempt, observed):
        return FinishOutcome.HELD
    if goes_on:
        made = relabelled(finish, announced=announced)
    if made:
        return None
    if stopped is not None or made is None:
        return stopped or FinishOutcome.HELD
    if finish.proves_settled:
        stopped = relabels_once(finish, observed, partial(_settled.stands_ready_if_settled, afresh=True))
    else:
        finish.gh.set_workflow_label(finish.issue, WorkflowLabel.VALIDATING)
    return _readiness.invalidates_behind(finish, stopped, observed.observed)


def observing(finish: LandedFinish) -> ProofReading:
    """A reading the guarded writes of `finish`'s announcement, park, or retirement collect refusals on.

    Each refusal over a bound record lands on its `observed` list
    (`rewrite_finish_writes.lands`) -- as movement under settled evidence,
    for a finish held to the settled-evidence policy, where a binding record
    moved (`rewrite_finish_writes.BINDING_MOVED`). Such a finish also has the
    comment any refusal of moved records was read over -- its preparation's
    fresh reading, or the one its strict edit found moved -- asked what it
    records moving behind the attempt as captured here, before those writes:
    under a transaction captured for the head, the prerequisite's own reading
    of it (`rewrite_finish_settled.reads_moving`), and otherwise under evidence
    settled for the head (`_reads_moving`). Any other finish reads nothing.
    """
    classifies = None
    if finish.proves_settled:
        attempt = _commit_models.PinnedCommit.capture(finish.state, prerequisites=_attempts._ATTEMPT_KEYS)
        pending = _captured.recorded(finish, logged=False)
        current = _settlement.read_current_evidence(finish.state)
        if pending is not None:
            classifies = partial(_settled.reads_moving, finish, pending, attempt)
        elif current is not None and current.binding.target.target_head == finish.head:
            classifies = partial(_reads_moving, finish, current.receipt, attempt)
    reading = ProofReading(finish.gh, finish.spec, finish.issue, finish.state, observed=[])
    return replace(reading, classifies_a_move=classifies)


def behind_the_announcement(
    finish: LandedFinish, stopped: FinishOutcome | None, observed: ProofReading,
) -> FinishOutcome | None:
    """`stopped`, where the announcement or the debt's park stopped the route, behind the last word; None to route.

    The last word is taken over a transaction still recorded for the head
    behind any stop (`rewrite_finish_captured.stands_before_the_route`). A
    finish held to the settled-evidence policy -- which asks this behind a
    request that raised too, as UNCONFIRMED -- first takes in the bookkeeping
    an unconfirmed record or checkpoint may have landed
    (`rewrite_finish_unconfirmed.takes_in_the_announcement`), the comment that
    reconciliation read asked what it records moving under the evidence too
    (`observing`), proves settled evidence ready once more, invalidated over
    any movement a refusal or that reading read
    (`rewrite_finish_readiness.invalidates_behind`), and proves the
    transaction again whole, the first such movement (`observed`) handed to
    the word as its proof, so a record put back revives nothing. That
    movement was read under what the stop's writes found recorded for the
    head -- each of them decided on every bound record, so none lays another
    road's record over the tick's state -- and answers for nothing else: a
    transaction that reconciliation or that invalidation's fresh reading laid
    there in its place, one another road recorded behind those writes, is left
    owed as written, with no last word taken over it.
    """
    if stopped is None:
        return None
    if not finish.proves_settled:
        return _captured.stands_before_the_route(finish, behind=stopped)
    captured = _captured.recorded(finish, logged=False)
    reconciled = _unconfirmed.takes_in_the_announcement(finish) if stopped is FinishOutcome.UNCONFIRMED else None
    if reconciled is not None:
        observed.reads(reconciled)
    _readiness.invalidates_behind(finish, stopped, observed.observed)
    if _captured.recorded(finish, logged=False) != captured:
        log.warning(
            "issue=#%d leaving the verification evidence recorded for %.8s behind its announcement owed as written",
            finish.issue.number, finish.head,
        )
        return stopped
    moved = next(iter(observed.observed), None)
    return _captured.stands_before_the_route(finish, proof=moved, behind=stopped, whole=True)


def behind_the_write(finish: LandedFinish, stopped: FinishOutcome, observed: ProofReading) -> FinishOutcome:
    """`stopped`, where the route's retirement did not land, behind proving settled evidence once more.

    A finish held to the settled-evidence policy invalidates settled evidence
    a refusal read a binding record moving under, or proves it ready once
    more where the refusal read none (`rewrite_finish_readiness.invalidates_behind`),
    so putting that record back first revives nothing; any other finish stops
    with nothing read.

    A retirement nobody confirmed may have landed all the same, taking the
    attempt with it. Settled evidence is proved over the attempt as this
    finish read it; where the proof reads movement, the evidence is
    invalidated over that attempt -- put back first, exactly as read, where
    that retirement took it (`rewrite_finish_unconfirmed.stands_back`) -- or,
    with no room, the movement recorded by blanking its base tip, or by the
    mark where the attempt no longer fits, so every later finish of the
    landing retires the evidence whole and the attempt behind it with nothing
    said or relabelled twice. Where another road put a new attempt in this
    one's place before the proof, the same receipt is retired over the
    comment as it stands, or marked (`rewrite_finish_marks.retires_as_it_stands`),
    that attempt and a successor under another receipt kept.
    """
    if not finish.proves_settled:
        return stopped
    current = _settlement.read_current_evidence(finish.state)
    unconfirmed = stopped is FinishOutcome.UNCONFIRMED and current is not None
    if not unconfirmed or current.binding.target.target_head != finish.head:
        return _readiness.invalidates_behind(finish, stopped, observed.observed)
    moved = _readiness.settled_word(finish, current)[0]
    if moved is None:
        return stopped
    invalidated = _readiness.invalidates(finish, current, as_it_stands=False)
    if not invalidated and _unconfirmed.stands_back(finish, current):
        invalidated = _readiness.invalidates(finish, current, as_it_stands=False)
    elif not invalidated:
        invalidated = retires_as_it_stands(finish, current.receipt)
    log.warning(
        "issue=#%d verification evidence revision %d settled for %.8s moved behind a retirement nobody confirmed "
        "(%s); invalidated: %s",
        finish.issue.number, current.revision, finish.head, moved.refusal, invalidated,
    )
    return stopped


def _reads_moving(
    finish: LandedFinish, receipt: str, attempt: _commit_models.PinnedCommit, state: PinnedState,
) -> _evidence_models.ReportEvidence | None:
    """The movement `state`, a comment a refusal of `finish`'s own write read, records under `receipt`; or None.

    A blank of the base tip of `attempt`, the one captured before the writes,
    beside every other member as captured or advanced by this landing's own
    announcement (`rewrite_finish_rechecks.stands_as_read`): the blank a proof
    records movement under the evidence with (`_BLANKED`). And, where `state`
    carries evidence current under `receipt`, what the readiness proof hears
    moving in the records alone (`rewrite_finish_readiness._records_heard`):
    the mark of movement in its handoff's place, a readable revision spent
    past it, a review or report record moved, or a handoff naming it that
    describes another head. A transition of the evidence records alone -- a
    newer transaction recorded beside it, discounted the one revision it may
    own, or a successor settled under another receipt -- reads none, and
    nothing that holds is kept: the stop is proved ready again behind it
    instead.
    """
    moved = attempt.moved(state.data)
    blanked = _TIP in moved and not _attempt_records._recorded_onto(state)
    if blanked and _rechecks.stands_as_read(finish, attempt, state, blank_aside=True):
        return _BLANKED
    carried = _settlement.read_current_evidence(state)
    if carried is None or carried.receipt != receipt:
        return None
    heard = _readiness._records_heard(carried, state, settled=True)
    return next((refused for refused in heard if refused and not refused.holds), None)
