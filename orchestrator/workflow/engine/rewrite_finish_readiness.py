# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Evidence a finish of a landed base rewrite settled for its head, proved ready again before the route takes it.

A finish settles the transaction it recorded for the landed head while the
auto-rebase anchor stands (`rewrite_finish_settlement`), and only then
announces the landing, relabels it to `workflow:validating`, and retires the
attempt. A tick lost anywhere in that tail -- before the announcement, between
its checkpoint and the relabel, or between the relabel and the retirement --
leaves the settled evidence current beside the standing attempt, and the
recovery of the push already landed finishes the route on a later tick from
the announcement mark and the label the dead tick left, with nothing decided,
run, posted, or settled again. The settlement proved the evidence at its own
moment; the route reads it at another, and an issue edited, a report or review
record moved, the artifact edited or deleted under its receipt, a revision
spent past it -- a newer transaction recorded beside it and then abandoned --,
a command configured otherwise, or a landing or base that moved since leaves
evidence that no longer answers for the head it would be routed with.

So every route that takes settled evidence as it stands -- the settling
tick's own, every recovery of it, and one whose evidence step abandoned a
newer transaction recorded beside it and left it current
(`rewrite_finish_settlement.settles`) -- proves it ready again first
(`stands_ready`): the readiness proof every reader relying on current evidence
takes (`verification_proof.current_evidence_verdict`), over the issue and
pinned comment read afresh, and behind it the last word over its binding
(`rewrite_evidence_proof.last_word`), which reads the remote branch, the base,
the requirements and the review and report records, the checkout, the local
base ref, and the configuration once more.

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
  the route instead, and the next recovery proves the evidence again over
  what it then reads; so does a pending record the invalidation's write
  finds beside it (`beside_current`), the next finish's to answer.
- Held: a reading nobody could take, a landing off the head, or a base gone
  elsewhere holds the route with the attempt standing, nothing announced,
  relabelled, or retired -- behind the invalidation, where the reading is
  movement too -- and the next tick classifies the branch and counts the
  head again.

The finish's own announcement checkpoint and retirement come behind the
proof, and a report or review record another road moves while the notice is
posted or the relabel made refuses them: that refusal is movement read under
the evidence too, which is invalidated before the finish stops
(`invalidates_behind`).

The recovery's helpers (`rewrite_landing_moved`) ask the same proof
(`settled_word`) and the same invalidation (`invalidates`) of evidence a
finish of the attempt settled, wherever a snapshot reads the landing moving
or a park would keep the attempt for a human's reply, so no reset, rollback
park, or reply revives a decision the landing moved under.

Nothing here runs the configured commands, posts an artifact, launches a
developer, or announces anything.
"""
from __future__ import annotations

import logging

from orchestrator.git.base_sync import attempts as _attempts
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    report_evidence_models as _evidence_models,
    rewrite_finish_writes as _writes,
    verification_durable as _durable,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_evidence_proof import Word, _reads_again, last_word
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, LandedFinish

log = logging.getLogger("orchestrator.workflow")

_UNREAD = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.HOLD,
    "the issue or its pinned comment could not be read again to prove the settled evidence ready",
)

# What an invalidation writes: the current record, and the history it enters.
_INVALIDATES = (_records.CURRENT_EVIDENCE, _records.EVIDENCE_HISTORY)


def stands_ready(finish: LandedFinish, current: _records.CurrentEvidence) -> FinishOutcome | None:
    """Prove `current`, settled for `finish`'s landed head, ready again before the route; None to route.

    The readiness proof (`settled_word`), every reading taken and none nobody
    could take hiding movement another took. Movement invalidates `current`
    (`_invalidates`), and the route goes on with nothing current unless a
    reading also holds it: one nobody could take, a landing that left the
    head, or a base gone elsewhere -- whose next tick classifies the branch
    and counts the head again, over evidence that movement already
    invalidated.
    """
    moved, held = settled_word(finish, current)
    stopped = None if moved is None else _invalidates(finish, current, moved.refusal)
    if stopped is not None or held is None:
        return stopped
    log.warning(
        "issue=#%d holding the route of %.8s: verification evidence revision %d settled for it could not be "
        "proved ready again (%s)",
        finish.issue.number, finish.head, current.revision, held.refusal,
    )
    return FinishOutcome.HELD


def settled_word(finish: LandedFinish, current: _records.CurrentEvidence) -> Word:
    """What `current`, settled for `finish`'s landed head, reads as now: `(moved, held)`.

    The readiness proof over the issue and comment read afresh (`_readiness`),
    handed to the last word over `current`'s binding as the verdict read
    first (`rewrite_evidence_proof.last_word`). Asked by the route here and by
    the recovery's helpers before a park keeps the attempt
    (`rewrite_landing_moved.abandons_unproved`).
    """
    return last_word(finish, current.binding, earlier=_readiness(finish, current))


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


def invalidates(finish: LandedFinish, current: _records.CurrentEvidence) -> bool:
    """Whether `current`'s invalidation into history landed, in a write of its own; the caller logs it.

    Staged on the comment read afresh and committed guarded by that reading
    and by the attempt as `finish` read it, so only the current record and the
    history are written and every other field stays as the comment carries
    it. Where that comment would not read again, or that write was refused or
    went unconfirmed, the invalidation is staged on the tick's own copy and
    landed as `rewrite_finish_writes.INVALIDATION` instead, decided only on
    the evidence records and the attempt -- so movement the caller already
    read is never left behind a comment that would not read, for a later poll
    to find put back and take the decision as current. False where the
    comment carries another attempt or no longer carries `current` as current,
    where neither reading has room for the history entry, or where neither
    write landed.
    """
    attempt = _commit_models.PinnedCommit.capture(finish.state, prerequisites=_attempts._ATTEMPT_KEYS)
    durable = _durable.durable_comment(finish.gh, finish.issue, finish.state)[0]
    if durable is not None:
        if attempt.moved(durable.data):
            return False
        if _settlement.read_current_evidence(durable) != current:
            return False
        guard = _durable.guarded(durable, _INVALIDATES, _attempts._ATTEMPT_KEYS)
        if _settlement.retire_current_evidence(durable):
            refused = _durable.lands(finish.gh, finish.issue, finish.state, guard, durable)
            if refused is None:
                return True
    staged = _writes.staging(finish)
    if _settlement.read_current_evidence(staged) != current or not _settlement.retire_current_evidence(staged):
        return False
    return _writes.lands(finish, staged, _writes.INVALIDATION) is None


def invalidates_behind(
    finish: LandedFinish, stopped: FinishOutcome | None, observed: list[_evidence_models.ReportEvidence],
) -> FinishOutcome | None:
    """`stopped`, behind invalidating evidence settled for the landed head that a refused write read moving under.

    For the finish's announcement checkpoint and its retirement
    (`rewrite_finish`), each proved ready before it and each guarded by the
    records the evidence is bound through: a report or review record another
    road wrote while the notice was posted, the relabel made, or the write
    itself sent refuses the write. A refusal that named such a record
    (`rewrite_finish_writes.BINDING_MOVED` in `observed`) is movement read
    under the evidence, so it is invalidated now (`invalidates`), the attempt
    and the newer records kept as the comment carries them, and putting the
    record back before the next poll revives nothing. A refusal that named
    none -- the comment moved under the edit itself, or only a newer
    transaction recorded for the head, the next finish's to answer -- has the
    evidence proved ready once more right away (`stands_ready`), which
    invalidates it only where a reading then establishes movement. A write
    that landed, one nobody confirmed, and a stop that was no write pass
    through with nothing read.
    """
    current = _settlement.read_current_evidence(finish.state)
    if stopped is not FinishOutcome.REFUSED or current is None:
        return stopped
    if current.binding.target.target_head != finish.head:
        return stopped
    if _writes.BINDING_MOVED not in observed:
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


def _readiness(finish: LandedFinish, current: _records.CurrentEvidence) -> _evidence_models.ReportEvidence:
    """The readiness proof of `current` over the issue and pinned comment read afresh.

    A proof that holds on a reading nobody could take stopped there, so the
    review and report records the comment carries are asked beside it
    (`verification_proof.recorded_verdict`), and a refusal of theirs is the
    answer instead. A comment no longer carrying `current` as its current
    evidence, or carrying a record beside it that says it is not the last word
    on the head (`beside_current`), holds rather than moving under it: what
    the comment carries then is for the next finish to resolve afresh.
    """
    read = _reads_again(finish)
    if read is None:
        return _UNREAD
    issue, state = read
    beside = "it no longer carries that evidence as current"
    if _settlement.read_current_evidence(state) == current:
        beside = beside_current(state, current)
    if beside:
        return _evidence_models.ReportEvidence(_evidence_models.ReportEvidenceVerdict.HOLD, beside)
    found = _proof.current_evidence_verdict(_proof.ProofReading(finish.gh, finish.spec, issue, state))
    if not found.holds:
        return found
    return _proof.recorded_verdict(state, current.binding) or found


def _invalidates(finish: LandedFinish, current: _records.CurrentEvidence, why: str) -> FinishOutcome | None:
    """Invalidate `current` on the route (`invalidates`); None to route on, HELD where it did not land.

    HELD too where the comment that write left carries a pending record
    beside it (`beside_current`): a newer transaction recorded meanwhile is
    the next finish's to answer, never one the route may leave owed behind a
    cleared attempt.
    """
    if not invalidates(finish, current):
        log.warning(
            "issue=#%d holding the route of %.8s: verification evidence revision %d settled for it no longer "
            "proves ready (%s), and could not be invalidated",
            finish.issue.number, finish.head, current.revision, why,
        )
        return FinishOutcome.HELD
    log.info(
        "issue=#%d invalidated verification evidence revision %d settled for %.8s, running nothing again: %s",
        finish.issue.number, current.revision, finish.head, why,
    )
    beside = beside_current(finish.state, None)
    if not beside:
        return None
    log.warning("issue=#%d holding the route of %.8s: %s", finish.issue.number, finish.head, beside)
    return FinishOutcome.HELD
