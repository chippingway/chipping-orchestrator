# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Evidence a finish of a landed base rewrite settled for its head, proved ready again before a route takes it.

A finish settles the transaction it recorded for the landed head while the
auto-rebase anchor stands (`rewrite_finish_settlement`), and only then
announces the landing, relabels it to `workflow:validating`, and retires the
attempt. A tick lost anywhere in that tail -- before the announcement, between
its notice, its `base_rebased` event, and its checkpoint, between the
checkpoint and the relabel, or between the relabel and the retirement --
leaves the settled evidence current beside the standing attempt, for the
recovery of the push already landed to route on a later tick. The settlement
proved the evidence at its own moment; a route reads it at another, and an
issue edited, a report or review record moved, the artifact edited or deleted
under its receipt, a revision spent past it -- a newer transaction recorded
beside it and then abandoned --, a command configured otherwise, or a landing
or base that moved since leaves evidence that no longer answers for the head
it would be routed with.

These are the primitives a route that takes settled evidence as it stands
proves it ready with (`stands_ready`): a finish
held to the dormant settled-evidence policy
(`rewrite_finish_models.LandedFinish.proves_settled`) -- its evidence phase
(`rewrite_finish_settlement.resolves`) and its coordinator's stops
(`rewrite_finish_stops`) -- and the recovery's answers wherever it reads the
landing moving or keeps the attempt for a reply (`rewrite_landing_moved`,
`rewrite_landing_retirement`) ask them, the finishes those answers build for
their proofs alone held to that policy on every road. No production finish
selects it, so every route a finish takes reads such evidence behind the
settlement step's own record check and the last word over the landing and
the base (`rewrite_finish_captured.stands_before_the_route`). Such a finish
has them read and retire more, as below, and only a caller that builds one
and hands it to the coordinator (`rewrite_finish.finalizes`) or that phase,
or asks them, directly reaches that (`rewrite_finish_settled`); every
production finish keeps the policy every road selects. The proof
(`settled_word`) reads the evidence records over the issue and pinned comment
read afresh, and the requirements of that issue, then, where they neither
move nor hold, the readiness proof every reader relying on current evidence
takes
(`verification_proof.current_evidence_verdict`), and behind it the last word
over its binding (`rewrite_evidence_proof.last_word`), which reads the remote
branch, the base, the requirements, the review and report records, and the
evidence records again over the comment it reads afresh -- so a transaction
recorded beside the evidence while the proof's requests were answered is
never routed past -- and the checkout, the local base ref, and the
configuration behind every request. Every reading is asked for movement and
for a hold side by side, so a record that holds never hides movement the
same reading established, and what the first reading heard stands whatever
the last word's own reading of the comment comes to. A successor another road
settled in the evidence's place after the caller read it is asked of its own
binding in each of those readings of the comment -- its records, and its
requirements beside the issue read with that comment -- and retired whole as
the comment stands, or marked, where it moved there (`_heard`), so the
caller's cached evidence never answers for it. Nothing is run or decided again: the
evidence goes on as it settled, or into history as it was.

- Ready: the route goes on with the evidence current exactly as it settled.
- Moved: any reading that establishes movement invalidates the evidence into
  history whole (`verification_settlement_state.retire_current_evidence`),
  its revision, transcript digest, and tested and source provenance kept, so the
  earlier decision answers for nothing the route carries: the head goes on to
  its route with nothing current, and the fresh reviewer there owes the
  evidence, as the normal workflow has it. The invalidation (`invalidates`)
  is staged on the comment read afresh and guarded by that reading and the
  attempt, so a record another road wrote meanwhile is neither refused nor
  written over; where that comment will not read again or that write does
  not land, it is staged on the tick's own copy and landed as
  `rewrite_finish_writes.INVALIDATION` instead, so movement already read is
  never left for a later reading to find put back. A comment no longer
  carrying that evidence as current, an attempt another road put in place
  of this one, no room for the history entry, or neither write landing holds
  the route instead, and the next proof reads the evidence again over what
  it then reads; so does a pending record the invalidation's write finds
  beside it (`beside_current`), the next finish's to answer. Where the
  comment still carries the evidence for this attempt and the invalidation
  did not land -- no room for its history entry, the comment filled while
  the proof was read, or a write refused or unconfirmed -- the movement is
  recorded against the evidence instead: the base tip the attempt recorded
  its replay as made onto is blanked, in a write that only shrinks the
  comment and that a successor settled in the evidence's place refuses, so
  every later proof of the evidence reads movement
  (`rewrite_evidence_proof.standing_refusal`) and invalidates it once room is
  made -- putting back what moved first revives nothing. A finish held to the
  dormant policy takes in an announcement another finish of the landing put
  on the attempt, retries a refused write once over a fresh reading, retires
  the same receipt over another attempt as the comment stands, and records
  movement no write took under the evidence's own receipt instead
  (`rewrite_finish_marks`).
- Held: a reading nobody could take, a record beside the evidence nobody can
  resolve -- a pending transaction, a handoff not naming it, a revision floor
  nobody can read -- a landing off the head, or a base gone elsewhere holds
  the route with the attempt standing, nothing announced, relabelled, or
  retired -- behind the invalidation, where that reading or another
  establishes movement too -- and the next tick classifies the branch and
  counts the head again. A readable revision spent past the evidence -- on
  the handoff or any history entry that reads on its own beside a floor or
  entries that do not, or on the floor -- is no such record: it outranks the
  evidence for good, so the proof reads it as movement -- whatever the pull
  request reads, and whatever else holds -- rather than every poll holding.
  Beside a pending record only a finish held to the dormant policy reads one,
  past the one revision that record may own (`rewrite_finish_outranking`),
  and only such a finish reads the mark of movement in the evidence's handoff
  place as movement too. Nor is a handoff that names the evidence but
  describes another pull request or head, which the proof refuses the evidence
  over as movement too.

A write a finish makes behind the proof -- its announcement checkpoint, the
record of its event, its debt park, or its retirement -- is refused by a
report or review record another road moved while the notice was posted or the
relabel made. Such a refusal, handed in as `rewrite_finish_writes.BINDING_MOVED`
-- which every write of a finish held to the dormant policy collects -- is
movement read under the evidence too, and so is movement the comment that
refusal was read over records under it -- a mark in its handoff's place, a
revision spent past it, a blank of the attempt's base tip
(`rewrite_finish_stops.observing`) -- which `invalidates_behind` invalidates
however soon the record is put back; any other stop behind the proof -- a
refusal reading neither, a write nobody confirmed, a hold -- leaves the
evidence standing behind requests made since it was proved, and has it proved
ready once more. Movement the record a write that was prepared, landed, or
went out unconfirmed made of the comment reads invalidates it even where the
finish goes on. A head the base has
advanced past again is continued rather than routed, and keeps its evidence
for the rebase behind it: the base reading that made that continuation is
excused from the last word (`rewrite_evidence_proof.ADVANCED`), so it neither
moves nor holds the evidence. `settled_word` and `invalidates` are shaped for
a recovery as well, over the evidence a finish of the attempt settled
(`rewrite_landing_records.settled`), wherever it would read the landing
moving or keep the attempt for a human's reply: the recovery's answers to a
snapshot read off the head (`rewrite_landing_moved`), to a reset, and to a
park that keeps the attempt (`rewrite_landing_retirement`) ask them on every road.
That recovery hands `settled_word` a verdict of its own to ask of each
reading beside the records (`asks`) -- what that very comment records moving
under the evidence, or under a successor read in its place, a base tip read
blank or repointed among it.

Nothing here runs the configured commands, posts an artifact, launches a
developer, or announces anything.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.git.base_sync import (
    attempt_records as _attempt_records,
    state as _base_sync_state,
)
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_evidence_models as _evidence_models,
    rewrite_finish_writes as _writes,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_evidence_proof import Asks, Refusals, Word, _reads_again, last_word
from orchestrator.workflow.engine.rewrite_finish_marks import (
    carries_the_mark,
    marks,
    retires_as_it_stands,
    retires_over_the_attempt,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, LandedFinish
from orchestrator.workflow.engine.rewrite_finish_outranking import outranks
from orchestrator.workflow.engine.verification_current import _handoff_describes
from orchestrator.workflow.engine.verification_subject import requirements_verdict

log = logging.getLogger("orchestrator.workflow")

_UNREAD = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.HOLD,
    "the issue or its pinned comment could not be read again to prove the settled evidence ready",
)

# A revision spent past the evidence, readable beside it: a newer transaction
# recorded and abandoned or dropped outranks it for good, whatever else reads.
_OUTRANKED = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.DEFER,
    "verification evidence newer than the settled record is recorded",
)

# The mark of movement a dormant finish read under the evidence, in its
# handoff's place (`rewrite_finish_marks.marks`): that movement, recorded where
# nothing else could carry it, whatever the comment reads beside it now.
_MARKED = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.DEFER,
    "movement read under the settled record is marked in its handoff's place",
)

# A handoff naming the evidence's receipt and revision that describes another
# pull request or head: a record rewritten by something other than its
# settlement, which the proof refuses the evidence over as well.
_UNDESCRIBED = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.DEFER,
    "the evidence handoff does not describe the settled record",
)


def stands_ready(finish: LandedFinish, current: _records.CurrentEvidence) -> FinishOutcome | None:
    """Prove `current`, settled for `finish`'s landed head, ready again before the route; None to route.

    The readiness proof (`settled_word`), every reading taken and none nobody
    could take hiding movement another took. Movement invalidates `current`
    (`invalidates`), and the route goes on with nothing current unless a
    reading also holds it: one nobody could take, a landing that left the
    head, or a base gone elsewhere -- whose next tick classifies the branch
    and counts the head again, over evidence that movement already
    invalidated. An invalidation that did not land holds the route, and so
    does a pending record beside the comment that write left
    (`beside_current`): a newer transaction recorded meanwhile is the next
    finish's to answer, never one the route may leave owed behind a cleared
    attempt.

    A head the base has advanced past again is continued rather than routed,
    and the evidence stays for the rebase behind it to decide over: the base
    gone past the head is what made that continuation
    (`rewrite_evidence_proof.ADVANCED`), so the last word drops it before it
    takes the first movement and the first hold. It neither moves nor holds
    anything there, and hides nothing else the proof reads moving -- the
    requirements, a record, or the configuration.
    """
    moved, held = settled_word(finish, current)
    why = "" if held is None else f"it could not be proved ready again ({held.refusal})"
    if moved is not None and invalidates(finish, current):
        log.info(
            "issue=#%d invalidated verification evidence revision %d settled for %.8s, running nothing again: %s",
            finish.issue.number, current.revision, finish.head, moved.refusal,
        )
        why = beside_current(finish.state, None) or why
    elif moved is not None:
        why = f"it no longer proves ready ({moved.refusal}), and could not be invalidated"
    if not why:
        return None
    log.warning(
        "issue=#%d holding the route of %.8s over verification evidence revision %d settled for it: %s",
        finish.issue.number, finish.head, current.revision, why,
    )
    return FinishOutcome.HELD


def settled_word(finish: LandedFinish, current: _records.CurrentEvidence, asks: Asks | None = None) -> Word:
    """What `current`, settled for `finish`'s landed head, reads as now: `(moved, held)`.

    The evidence records over the issue and comment read afresh first, beside
    the requirements of that issue (`_records_heard`) -- the mark of movement
    a dormant finish read under `current` in its handoff's place among them,
    on every reading the last word takes as on this one -- and, where none of
    them refuses anything, the readiness proof over them
    (`verification_proof.current_evidence_verdict`). Then the last word over
    `current`'s binding (`rewrite_evidence_proof.last_word`), handed that
    proof as the verdict read first, which asks the evidence records once
    more over its own reading of the comment and sorts what they heard there
    beside its own: a transaction another road recorded beside `current`
    while the proof was answered holds, and one it recorded and abandoned
    there outranks `current` and moves under it -- and the checkout, the
    local base, and the configuration are read behind that reading too, as
    behind every other request. What the first reading heard is answered
    ahead of the last word's, whatever the last word's own reading of the
    comment came to, so movement read before a comment that will not read
    again is never left for a later poll to find put back. Every reading's
    movement and every reading's hold are kept side by side, so none is
    hidden behind another. What `stands_ready` routes over, and what the
    recovery's proof asks before a park keeps the attempt over
    `current` (`rewrite_landing_retirement.retires_unproved`). Both
    readings of the comment ask a successor another road settled in
    `current`'s place after the caller read it of its own binding there too
    (`_heard`), so its movement is never read against `current`'s alone.
    `asks`, where a caller hands one, is asked of each of those readings
    beside the records, under the receipt of the evidence asked there --
    `current`, or a successor in its place -- what the recovery's
    proof reads moving there that the records alone do not, a base tip
    blanked or repointed among it, so movement a reading records stands
    however soon it is put back before the next.
    """
    read = _reads_again(finish) or (None, None)
    first = _heard(finish, current, read[1], read[0], asks)
    proved = None
    if read[1] is not None and not any(first):
        proved = _proof.current_evidence_verdict(_proof.ProofReading(finish.gh, finish.spec, *read))
    moved, held = last_word(
        finish,
        current.binding,
        earlier=proved,
        records=lambda state, issue: _heard(finish, current, state, issue, asks),
    )
    return (
        next((refused for refused in first if refused and not refused.holds), moved),
        next((refused for refused in first if refused and refused.holds), held),
    )


def beside_current(state: PinnedState, current: _records.CurrentEvidence | None) -> str:
    """Why a record beside the head's resolved evidence says nobody can tell what `current` is, or "".

    Any pending record, and -- beside `current`, where there is one -- a
    handoff that does not name it or a revision floor nobody can read. A route
    never goes on over one, and nothing it reads moved under `current` either:
    a newer transaction recorded for the head supersedes it once it settles.
    A readable revision spent past `current` is none of these: a newer
    transaction recorded and then abandoned or dropped beside it outranks it
    for good, so the readiness proof reads it as movement and invalidates it
    (`verification_current.publication_verdict`), rather than every later poll
    holding over evidence no reader will ever be handed.
    """
    if _record_state.carries_pending_evidence(state):
        return "a pending record no finish of this landing can answer stands beside it"
    if current is None:
        return ""
    handoff = _settlement.read_evidence_handoff(state)
    named = None if handoff is None else (handoff.receipt, handoff.revision)
    if named != (current.receipt, current.revision):
        return "the evidence handoff does not name it"
    if _record_state._latest_revision(state) is None:
        return "nobody can say which revision was spent last"
    return ""


def invalidates(finish: LandedFinish, current: _records.CurrentEvidence, *, as_it_stands: bool = True) -> bool:
    """Whether `current`'s invalidation into history landed, in a write of its own; the caller logs it.

    Staged on the comment read afresh, guarded by that reading and the attempt
    as `finish` read it -- for a finish held to the dormant policy, an
    announcement another finish of the landing put on it taken in first, and a
    refused write read, reconciled, and retried once
    (`rewrite_finish_marks.retires_over_the_attempt`). Where neither reading
    took it, it is made over the tick's own copy instead, landed as
    `rewrite_finish_writes.INVALIDATION`, so movement already read is never
    left for a later poll to find put back. False where the comment carries
    another evidence or another attempt -- over which a dormant finish still
    retires or marks the same receipt as the comment stands, unless
    `as_it_stands` is False for a caller that puts its own attempt back first
    (`rewrite_finish_unconfirmed.stands_back`) -- and where nothing took it,
    the movement then recorded against `current`.

    That copy's write is decided only on the evidence records and the attempt,
    never on the publication's pinned fields, so a review, report, or
    publication record another road moved -- often the very movement read --
    is no refusal, and is kept as that road wrote it. Where it did not land --
    no room for the history entry on the tick's copy or on the comment another
    road filled since, or a write refused or never confirmed -- the movement
    is recorded against `current` instead, which stays current: the base tip
    the attempt recorded its replay as made onto is blanked, and with no tip
    nothing proves which base the head was replayed onto, so every later proof
    of `current` defers (`rewrite_evidence_proof.standing_refusal`) and
    invalidates it once room is made, whatever moved put back meanwhile or
    not. The blank only shrinks the comment, so it lands where the entry would
    not, guarded as the invalidation is
    (`rewrite_finish_writes.INVALIDATION`): a successor another road settled
    in `current`'s place refuses it, even where the bounded history dropped
    `current`'s entry and reads as it did, so no tip is blanked under evidence
    that never moved. A tip already blank is left as it is. Neither write is
    decided on the comment as it reads now, so a record another road wrote
    since the tick read it -- a pending record among them -- refuses both; a
    finish held to the dormant policy then records the movement under
    `current`'s own receipt over the comment read afresh
    (`rewrite_finish_marks.marks`), which every later proof under that policy
    reads as the movement it is.
    """
    retired = retires_over_the_attempt(finish, current, as_it_stands=as_it_stands)
    if retired is not None:
        return retired
    staged = _writes.staging(finish)
    if _settlement.read_current_evidence(staged) != current:
        return False
    landed = _settlement.retire_current_evidence(staged)
    if landed and _writes.lands(finish, staged, _writes.INVALIDATION, publication=False) is None:
        return True
    stopped = None
    if _attempt_records._recorded_onto(finish.state):
        marked = _writes.staging(finish)
        marked.set(_base_sync_state._PENDING_REWRITE_BASE, None)
        stopped = _writes.lands(finish, marked, _writes.INVALIDATION, publication=False)
        log.error(
            "issue=#%d verification evidence revision %d settled for %.8s could not be invalidated; keeping it "
            "current, the movement read under it recorded by blanking its base tip (%s)",
            finish.issue.number, current.revision, finish.head, "landed" if stopped is None else stopped.value,
        )
    if stopped is not None and finish.proves_settled:
        marks(finish, current, "neither its invalidation nor its base tip's blank landed over the tick's own copy")
    return False


def invalidates_behind(
    finish: LandedFinish, stopped: FinishOutcome | None, observed: list[_evidence_models.ReportEvidence],
) -> FinishOutcome | None:
    """`stopped`, behind proving again evidence settled for the landed head that the finish leaves standing.

    For a write a finish makes behind the proof -- its announcement
    checkpoint, the record of its event, its park, or its retirement
    (`rewrite_finish`) -- guarded by the records the evidence is bound
    through: a report or review record another road wrote while the notice
    was posted, the relabel made, or the write itself sent refuses the write.
    A refusal that named such a record (`rewrite_finish_writes.BINDING_MOVED`
    in `observed`), or whose comment was read recording movement under the
    evidence -- any refusal in `observed` that does not hold -- is movement
    read under it, so it is invalidated now (`invalidates`), the attempt and
    the newer records kept as the comment carries them, and putting the
    record back before the next poll revives nothing. A record named moved is
    named off the records the tick's state carries, so it is movement under
    the evidence only where those records bind it
    (`verification_proof.recorded_verdict`): a successor another road settled
    bound to newer records, laid over the tick's state from a fresh reading
    without them, is asked only what a refusal's comment records moving off
    its own binding (`rewrite_finish_stops.observing`). Any other stop -- a
    refusal that read neither, a write nobody confirmed, a request behind a
    notice already posted that would not answer -- leaves the evidence
    standing behind requests made since it was proved, so it is proved ready
    once more right away (`stands_ready`), which invalidates it where a
    reading then establishes movement. A finish that went on is proved
    nothing more, save that movement its writes read -- a record that was
    prepared, landed, or went out reading a successor off its own binding
    among it (`rewrite_finish_writes.prepares`, `lands`) -- invalidates the
    evidence all the same, before anything goes on over it.
    """
    current = _settlement.read_current_evidence(finish.state)
    if current is None:
        return stopped
    if current.binding.target.target_head != finish.head:
        return stopped
    moving = [refused for refused in observed if not refused.holds]
    unbound = _writes.BINDING_MOVED in moving and _proof.recorded_verdict(finish.state, current.binding)
    if unbound and not unbound.holds:
        moving = [refused for refused in moving if refused != _writes.BINDING_MOVED]
    if not moving:
        if stopped is not None:
            stands_ready(finish, current)
        return stopped
    if invalidates(finish, current):
        return stopped
    log.warning(
        "issue=#%d verification evidence revision %d settled for %.8s was read moving under the finish's write "
        "and could not be invalidated; the next finish proves it again",
        finish.issue.number, current.revision, finish.head,
    )
    return stopped


def _records_heard(
    current: _records.CurrentEvidence,
    state: PinnedState | None,
    issue: Issue | None = None,
    *,
    settled: bool,
    asks: Asks | None = None,
) -> Refusals:
    """What the evidence records `state` carries refuse `current` over, with nothing requested.

    `state` is a pinned comment read afresh, None where it would not read, and
    `issue` the issue read with it, whose requirements are asked beside the
    records where the caller hands one in -- the first reading, whose full
    proof a hold skips. Movement: requirements the issue moved past
    (`verification_subject.requirements_verdict`), the review and report
    records (`verification_proof.recorded_verdict`), a handoff naming
    `current` that describes another pull request or head (`_UNDESCRIBED`),
    and a revision spent past it (`_OUTRANKED`), as the policy `settled`
    selects reads one (`rewrite_finish_outranking.outranks`): the one every
    road selects reads none beside a pending record, and the dormant
    settled-evidence policy discounts only the one revision that record may
    own, so a pending record holds beside evidence a readable revision
    outranks and hides none of it. The last two the proof would hear only
    behind the pull request, which a reading nobody could take hides them
    behind. Under that policy, the mark of movement a dormant finish read
    under `current` in its handoff's place (`_MARKED`,
    `rewrite_finish_marks.carries_the_mark`) too: that movement, recorded
    where nothing else could carry it, whatever the comment reads beside it
    now and however soon it is put back after this reading. Hold: a comment
    no longer carrying `current` as its current evidence, or carrying a
    record beside it that says it is not the last word on the head
    (`beside_current`) -- a pending transaction among them, whatever revision
    it spent, since the next finish answers it -- and requirements nobody
    could read. Every one is asked whatever the others say, and sorted beside
    the last word's own (`settled_word`), so a hold never hides movement the
    same reading established.
    """
    if state is None:
        return (_UNREAD,)
    beside = "it no longer carries that evidence as current"
    if _settlement.read_current_evidence(state) == current:
        beside = beside_current(state, current)
    handoff = _settlement.read_evidence_handoff(state)
    # The handoff's place: a handoff naming `current` that describes another
    # head, or the mark in its place, which no reader takes for a handoff.
    in_its_place = _MARKED if settled and carries_the_mark(state, current) else None
    names = handoff is not None and handoff.receipt == current.receipt
    if names and not _handoff_describes(state, current):
        in_its_place = _UNDESCRIBED
    heard = (
        None if issue is None else requirements_verdict(
            issue, state, current.binding.target.publication.requirements_revision,
        ),
        _proof.recorded_verdict(state, current.binding),
        in_its_place,
        _OUTRANKED if outranks(state, current, settled=settled) else None,
        _evidence_models.ReportEvidence(_evidence_models.ReportEvidenceVerdict.HOLD, beside) if beside else None,
    )
    return heard if asks is None else (*heard, asks(state, current.receipt))


def _heard(
    finish: LandedFinish,
    current: _records.CurrentEvidence,
    state: PinnedState | None,
    issue: Issue | None = None,
    asks: Asks | None = None,
) -> Refusals:
    """`_records_heard` of `current` over `state`, a comment `settled_word` read afresh, as `finish`'s policy reads it.

    `issue` is the issue read with `state` -- `settled_word`'s first reading
    of the two, or the last word's own -- whose requirements that reading is
    asked beside. Under the dormant
    settled-evidence policy a successor `state` carries current for the landed
    head in `current`'s place -- one another road settled after the caller
    read the evidence it hands in -- is asked of its own binding in that very
    reading first (`_records_heard`): its requirements beside that issue, and
    its review, report, and evidence records. Where any of them refuses it
    there, it is retired whole as the comment then stands, or its movement
    marked under its own receipt (`rewrite_finish_marks.retires_as_it_stands`),
    so putting what moved back before a later reading revives nothing; one
    nothing refuses is left as its road settled it. `current` is answered over
    `state` either way. What `asks` answers of `state`, where a caller hands
    it (`settled_word`), is heard beside the records under each receipt asked
    there, the successor's included.
    """
    carried = None if state is None else _settlement.read_current_evidence(state)
    later = finish.proves_settled and carried is not None and carried.receipt != current.receipt
    if later and carried.binding.target.target_head == finish.head:
        heard = _records_heard(carried, state, issue, settled=True, asks=asks)
        if any(refused and not refused.holds for refused in heard):
            retires_as_it_stands(finish, carried.receipt)
    return _records_heard(current, state, issue, settled=finish.proves_settled, asks=asks)
