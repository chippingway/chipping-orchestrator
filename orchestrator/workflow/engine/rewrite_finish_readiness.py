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
record moved, the artifact edited or deleted under its receipt, a newer
revision spent, a command configured otherwise, or a landing or base that
moved since leaves evidence that no longer answers for the head it would be
routed with.

So every route that takes settled evidence as it stands -- the settling
tick's own, and every recovery of it -- proves it ready again first
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
  evidence, as the normal workflow has it. The invalidation is staged on the
  comment read afresh and guarded by that reading and the attempt, so a record
  another road wrote meanwhile is neither refused nor written over; one that
  does not land, a comment no longer carrying that evidence as current or as
  the last word on the head (`beside_current`), an attempt another road put
  in place of this one, or a comment with no room for the history entry holds
  the route instead, and the next recovery proves the evidence again over
  what it then reads.
- Held: a reading nobody could take, a landing off the head, or a base gone
  elsewhere holds the route with the attempt standing, nothing announced,
  relabelled, or retired -- behind the invalidation, where the reading is
  movement too -- and the next tick classifies the branch and counts the
  head again.

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
    verification_durable as _durable,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_evidence_proof import _reads_again, last_word
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

    The readiness proof over the issue and comment read afresh, handed to the
    last word over `current`'s binding as the verdict read first, so every
    reading is taken and none nobody could take hides movement another took.
    Movement invalidates `current` (`_invalidates`), and the route goes on
    with nothing current unless a reading also holds it: one nobody could
    take, a landing that left the head, or a base gone elsewhere -- whose
    next tick classifies the branch and counts the head again, over evidence
    that movement already invalidated.
    """
    moved, held = last_word(finish, current.binding, earlier=_readiness(finish, current))
    stopped = None if moved is None else _invalidates(finish, current, moved.refusal)
    if stopped is not None or held is None:
        return stopped
    log.warning(
        "issue=#%d holding the route of %.8s: verification evidence revision %d settled for it could not be "
        "proved ready again (%s)",
        finish.issue.number, finish.head, current.revision, held.refusal,
    )
    return FinishOutcome.HELD


def beside_current(state: PinnedState, current: _records.CurrentEvidence | None) -> str:
    """Why a record beside the head's resolved evidence says `current` is not the last word on it, or "".

    Any pending record, and -- beside `current`, where there is one -- a
    handoff that does not name it or a revision spent past it. A route never
    goes on over one, and nothing it reads moved under `current` either: a
    newer transaction recorded for the head supersedes it once it settles.
    """
    if _record_state.carries_pending_evidence(state):
        return "a pending record no finish of this landing can answer stands beside it"
    if current is None:
        return ""
    handoff = _settlement.read_evidence_handoff(state)
    named = None if handoff is None else (handoff.receipt, handoff.revision)
    if named != (current.receipt, current.revision):
        return "the evidence handoff does not name it"
    if _record_state._latest_revision(state) != current.revision:
        return "a revision past it was spent, or nobody can say which"
    return ""


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
    """Invalidate `current` into history in its own write (`_lands_the_invalidation`); None to route on, else HELD."""
    if not _lands_the_invalidation(finish, current):
        log.warning(
            "issue=#%d holding the route of %.8s: verification evidence revision %d settled for it no longer "
            "proves ready (%s), and could not be invalidated over the pinned comment read again",
            finish.issue.number, finish.head, current.revision, why,
        )
        return FinishOutcome.HELD
    log.info(
        "issue=#%d invalidated verification evidence revision %d settled for %.8s, running nothing again: %s",
        finish.issue.number, current.revision, finish.head, why,
    )
    return None


def _lands_the_invalidation(finish: LandedFinish, current: _records.CurrentEvidence) -> bool:
    """Whether `current`'s invalidation landed, staged on the comment read afresh and guarded by that reading.

    Guarded by the attempt as `finish` read it too, so only the current record
    and the history are written and every other field stays as the comment
    carries it. False where the comment would not read again, carries another
    attempt, no longer carries `current` as current or as the last word on the
    head (`beside_current`) -- a newer transaction recorded beside it is the
    next finish's to answer, not one this write may route past -- has no room
    for the entry, or did not take the write.
    """
    attempt = _commit_models.PinnedCommit.capture(finish.state, prerequisites=_attempts._ATTEMPT_KEYS)
    durable = _durable.durable_comment(finish.gh, finish.issue, finish.state)[0]
    if durable is None or attempt.moved(durable.data):
        return False
    if _settlement.read_current_evidence(durable) != current:
        return False
    if beside_current(durable, current):
        return False
    guard = _durable.guarded(durable, _INVALIDATES, _attempts._ATTEMPT_KEYS)
    if not _settlement.retire_current_evidence(durable):
        return False
    return _durable.lands(finish.gh, finish.issue, finish.state, guard, durable) is None
