# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The evidence a landed base rewrite's finish resolves, published and settled under its anchor before it announces.

A fresh run or a carry the finish's evidence step records for the landed head
(`rewrite_finish_evidence`) is a pending evidence transaction whose artifact
the pull request is still owed. The finish answers it itself, with the
auto-rebase attempt still standing (`settles`), through the reconciliation's
own answer (`verification_transaction.answers`): the post scoped by the
transaction's receipt (`verification_publishing`) and the one guarded commit
that makes it current (`verification_settling`), with no artifact protocol of
its own. Only once that is resolved (`resolves`) does the finish announce the
landing -- its notice, its `base_rebased` event, and the round reset --
relabel the issue to `workflow:validating`, and retire the attempt; the
dispatcher's reconciliation stands aside while the anchor stands, so nothing
else publishes it meanwhile.

The proof is the reconciliation's, over a reading that names the anchor
(`verification_proof.ProofReading.anchored`) and the issue fetched afresh for
it, so the requirements the publication's proof hashes are the issue's as it
reads right then rather than as the tick read it. Ahead of the post and again
ahead of the settlement, behind the pull request, the branch and the
checkout, the trees, the configuration, the review subject, the settled report
re-read at its location, and the requirements, the anchor's own proof reads the
landing over again (`_anchored`, over `rewrite_evidence_proof.last_word`): the
remote branch and the checkout still on the head, and the base still the tip
its replay was made onto. The post and the settlement each ask it once more
behind all of their own requests, then the issue fetched again with its
requirements hashed over that reading, and the configuration last
(`verification_unguarded`), so a head pushed, a base advanced, an issue
edited, or a command configured otherwise while the report or the base was
read refuses them too.
Every write the answer makes -- the post's prepared room, the settlement, a
retirement, an abandonment -- is decided on the attempt as the finish read it
as well (`ProofReading.rests_on`), so an attempt that no longer reads as the
finish holds it refuses them. Inside the writer claim no write of the
finish's moves the attempt or the evidence records but the answer's own, so a
comment the answer leaves carrying another attempt or another pending record
is a record nothing here may adopt: the finish holds with it kept exactly as
it reads, before anything abandons over it or clears it (`_answered_alone`).
A settlement of the answered transaction itself is told apart from the
answer's own by nothing: where the answer's commit was refused, its ledger
write takes the comment in whole (`verification_settling`), so an edit from
outside that settled the transaction while its artifact was posted is routed
over as though this finish had settled it.
A revision already settled or spent past, a pull request that ended, and any
refusal short of a reading nobody could take retire the transaction into
history (`verification_carries.abandons_on_refusal`), since no route behind the
anchor answers it, and the head goes to the fresh reviewer, who owes the
evidence.

What the answer comes to decides the route:

- Settled, or retired: the transaction is resolved -- current with its
  transcript and revision as recorded and its artifact posted once, or the
  fresh reviewer's to answer -- and the route goes on behind the last word
  over the landing and the base (`rewrite_finish_captured.stands_before_the_route`).
- Still owed -- a post or a settlement nobody confirmed, a reading nobody
  could take, a settlement the comment had no room for or whose commit a
  moved record or comment refused, an issue that stopped being live work
  while the artifact was posted: the transaction is proved again
  (`rewrite_finish_captured.proved_again`) and the last word asked over it, so
  one any reading establishes movement under -- a review or report record, the
  requirements, the configuration, the landing, the base -- is abandoned and
  the route goes on where nothing holds it -- a refusal the answer itself read
  (`verification_proof.ProofReading.observed`), kept as it was read, a bound
  record read moved under the settlement and a base read gone elsewhere among
  them, is that movement however the world reads by then, so one put back
  before the last word reads it is abandoned over all the same. One nothing
  moved under is HELD
  with nothing announced and the attempt standing, and the recovery of the
  push already landed answers it again on a later tick: an artifact an earlier
  post landed, its response lost included, is found under its receipt rather
  than posted again, and settled once, with nothing run again and no
  developer launched.

A finish behind one that already settled the transaction -- its commit landed
and the process died, or the commit's answer was lost -- finds the current
evidence answering for the landed head and routes it as it stands, with
nothing decided, run, invalidated, posted, or settled again, but only while the
records agree it is the last word on the head: no pending record beside it,
the handoff naming it, and no revision spent past it. A newer transaction
recorded for the head beside it is answered as any captured one is, and
supersedes it once it settles; any other disagreement holds the route. The
evidence is not proved ready again here: the reviewer the route hands it to
proves it current before relying on it
(`verification_proof.current_evidence_verdict`), and is handed none where
anything it rests on moved since it settled. So evidence a requirements edit,
or a report or review subject refreshed, moved under between the settlement
and this finish stays current behind the route rather than being invalidated
into history ahead of it.
"""
from __future__ import annotations

import logging
from functools import partial

from orchestrator.git.base_sync import attempts as _attempts
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    rewrite_finish_captured as _captured,
    rewrite_finish_evidence as _evidence,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
    verification_transaction as _transaction,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence
from orchestrator.workflow.engine.rewrite_evidence import invalidates_current
from orchestrator.workflow.engine.rewrite_evidence_proof import MOVEMENT, _reads_again, last_word
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, LandedFinish
from orchestrator.workflow.engine.rewrite_landing_records import capture_answered, out_of_step, resolved

log = logging.getLogger("orchestrator.workflow")


def resolves(finish: LandedFinish) -> FinishOutcome | None:
    """Resolve the evidence `finish`'s landed head is routed with, before anything announces it; None to go on.

    A head the base advanced past again is routed with none: a transaction an
    earlier finish recorded for it is abandoned before its continuation is
    announced (`rewrite_finish_evidence.continues`), and nothing is decided or
    settled for it -- evidence an earlier finish settled for it is kept for
    the rebase behind it. For any other head the evidence step decides and
    records it (`rewrite_finish_evidence.settles`) and a transaction it
    recorded is published and settled here (`settles`) -- and so is a newer
    transaction recorded for the head beside evidence an earlier finish
    already settled for it, which then supersedes that evidence rather than
    leaving it current. Settled evidence with nothing beside it is taken with
    nothing decided, run, posted, or settled again, but only while the records
    agree it is the last word on the head -- no pending record at all, the
    handoff naming it, and no revision spent past it -- behind the last word
    over the landing and the base. Evidence taken under a configuration no
    longer in place is the evidence step's to invalidate as it decides the
    head afresh.

    Any of those out of step holds the route, since nobody can say what was
    owed, and so does any pending record about another head beside evidence
    an earlier finish of this landing already retired for it, current
    evidence or none (`_holds_out_of_step`) -- by the records, or by the
    receipt the finish put on the attempt once the history no longer keeps
    the run: that record was not written by this landing's finish, whose own
    recording would have retired it, so it stands with the attempt for
    whoever answers it. That one holds a continuation too, since announcing
    it, resetting the round, and retiring the attempt would leave the record
    owed behind a cleared attempt.
    """
    held = _holds_out_of_step(finish)
    if held is not None:
        return held
    if finish.behind:
        return _evidence.continues(finish)
    current = _settlement.read_current_evidence(finish.state)
    standing = current is not None and current.binding.target.target_head == finish.head and (
        _captured.recorded(finish, logged=False) is None
    )
    if not standing or invalidates_current(finish):
        return _evidence.settles(finish) or settles(finish)
    log.info(
        "issue=#%d already settled verification evidence revision %d for %.8s; settling and running nothing again",
        finish.issue.number, current.revision, finish.head,
    )
    return _captured.stands_before_the_route(finish)


def settles(finish: LandedFinish) -> FinishOutcome | None:
    """Publish and settle the transaction recorded for the landed head under the standing anchor; None to route.

    None too where nothing is recorded for the head -- the decision ran or
    recorded nothing, or the last word behind it abandoned what it recorded --
    since the evidence is then the fresh reviewer's. Anything else is where
    the finish stops, with nothing announced, relabelled, or retired. Every
    write the answer makes is decided on the attempt as this finish read it
    (`verification_proof.ProofReading.rests_on`), and a comment the answer
    leaves carrying another attempt or another pending record -- one no write
    of this finish's put there (`_answered_alone`) -- holds before anything
    proves, abandons, announces, or clears over it, so that record stands
    exactly as it reads. Once nothing is recorded for the head any more --
    settled or retired by the answer, or abandoned by the last word behind it
    -- the records that left are resolved afresh (`resolves`), with nothing
    recorded to answer this time, before anything is announced or routed:
    current evidence its handoff does not name, or a revision spent past it,
    holds the route with the attempt standing, and current evidence the
    configuration moved past is invalidated, with nothing run again, rather
    than routed or held over. A transaction still owed goes to the last word
    over the first movement the answer read, where it read any -- a refusal of
    its binding, a bound record read moved, or a base read gone elsewhere,
    put back since or not, sorted as the last word sorts its own readings
    (`rewrite_evidence_proof.MOVEMENT`) -- and otherwise over its proof taken
    again.
    """
    pending = _captured.recorded(finish, logged=False)
    if pending is None:
        return None
    attempt = _commit_models.PinnedCommit.capture(finish.state, prerequisites=_attempts._ATTEMPT_KEYS)
    read = _reads_again(finish)
    proof = _proof.ProofReading(
        finish.gh,
        finish.spec,
        finish.issue if read is None else read[0],
        finish.state,
        anchored=partial(_anchored, finish), rests_on=tuple(_attempts._ATTEMPT_KEYS), observed=[],
    )
    if read is not None:
        _transaction.answers(proof, pending)
    if read is None or not _answered_alone(finish, pending, attempt):
        log.warning(
            "issue=#%d holding the route of %.8s: the issue would not read again, or another attempt or "
            "evidence record stands where verification evidence revision %d was answered",
            finish.issue.number, finish.head, pending.revision,
        )
        return FinishOutcome.HELD
    movements = [refused for refused in proof.observed if not refused.holds or refused in MOVEMENT]
    return _behind_the_answer(finish, pending, movements)


def _behind_the_answer(
    finish: LandedFinish, pending: _records.PendingEvidence, movements: list[ReportEvidence],
) -> FinishOutcome | None:
    """Where the route goes once `pending` was answered, over the movement the answer read; None to route.

    `movements` is what the answer read, sorted as the last word sorts its
    own readings (`rewrite_evidence_proof.MOVEMENT`). A transaction settled
    or retired by the answer is resolved afresh. One still owed goes to the
    last word over the first such movement, or over its proof taken again,
    and is resolved afresh once that word abandons it.
    """
    if _captured.recorded(finish, logged=False) is None:
        return resolves(finish)
    proof = movements[0] if movements else _captured.proved_again(finish, pending)
    stopped = _captured.stands_before_the_route(finish, proof=proof)
    if stopped is not None or _captured.recorded(finish, logged=False) is None:
        return stopped or resolves(finish)
    log.warning(
        "issue=#%d holding the route of %.8s: verification evidence revision %d is still owed to its pull request",
        finish.issue.number, finish.head, pending.revision,
    )
    return FinishOutcome.HELD


def _anchored(finish: LandedFinish) -> ReportEvidence | None:
    """The anchor's own proof of the landed head, asked behind every other reading of a proof under it; or None.

    The landing read over again with no binding (`rewrite_evidence_proof.last_word`):
    the remote branch, the base the replay was made onto, the checkout, and the
    local base ref it counts against -- so a head pushed or a base advanced
    while the publication's or the settlement's requests were answered refuses
    them. Movement first, then a reading nobody could take.
    """
    moved, held = last_word(finish)
    return moved or held


def _answered_alone(
    finish: LandedFinish, pending: _records.PendingEvidence, attempt: _commit_models.PinnedCommit,
) -> bool:
    """Whether the comment the answer left is `pending`'s alone: owed still, or settled or retired with nothing beside.

    Any other pending record, one nobody can read, or `pending` gone with no
    trace of its settlement or retirement is a record no write of this
    finish's made, which it may neither prove `pending`'s refusals over nor
    route past; and so is an attempt other than `attempt`, the one the finish
    captured before the answer.
    """
    state = finish.state
    if attempt.moved(state.data):
        return False
    if _record_state.carries_pending_evidence(state):
        return _record_state.read_pending_evidence(state) == pending
    current = _settlement.read_current_evidence(state)
    receipts = {entry.receipt for entry in _settlement.read_evidence_history(state) or ()}
    if current is not None:
        receipts.add(current.receipt)
    return pending.receipt in receipts


def _holds_out_of_step(finish: LandedFinish) -> FinishOutcome | None:
    """HELD, logged, where another record stands beside evidence an earlier finish of this landing resolved; or None.

    Asked by `resolves` before the evidence is resolved, and again over the
    records a settlement's answer left (`settles`), before anything is
    announced or routed. The current evidence counts only where it answers
    for the landed head -- while the attempt stands nothing but a finish of
    this landing settles evidence for it -- under the context configured now,
    and never for a continuation, which routes none: evidence the
    configuration moved past is the evidence step's to invalidate
    (`rewrite_evidence.invalidates_current`), not a last word the route is
    held over, which would hold it for good. None where nothing was settled
    or retired for the head yet -- by the records
    (`rewrite_landing_records.resolved`), or, once the history no longer
    keeps the run, by the receipt the finish put on the attempt
    (`rewrite_landing_records.capture_answered`) -- and where a transaction is
    recorded for the head, which the finish answers itself. Otherwise any
    record out of step beside that evidence holds
    (`rewrite_landing_records.out_of_step`).
    """
    current = _settlement.read_current_evidence(finish.state)
    if current is not None and current.binding.target.target_head != finish.head:
        current = None
    if finish.behind or invalidates_current(finish):
        current = None
    settled = resolved(finish.state, finish.head) or capture_answered(finish.state)
    beside = ""
    if settled and _captured.recorded(finish, logged=False) is None:
        beside = out_of_step(finish.state, current)
    if not beside:
        return None
    log.warning(
        "issue=#%d holding the route of %.8s: the verification evidence already resolved for it is out of step: %s",
        finish.issue.number, finish.head, beside,
    )
    return FinishOutcome.HELD
