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
as well (`ProofReading.rests_on`), so an attempt another road put in its place
refuses them, and a finish whose state took that attempt in all the same holds
before anything abandons over it or clears it. So does one whose state took in
a newer transaction another road recorded in the answered one's place: that
successor stands as its road wrote it, with the history and revision floor that
road left, for the next finish to answer, rather than taking the refusals of
the transaction it replaced. A revision already settled or
spent past, a pull request that ended, and any refusal short of a reading
nobody could take retire the transaction into history
(`verification_carries.abandons_on_refusal`), since no route behind the anchor
answers it, and the head goes to the fresh reviewer, who owes the evidence.

What the answer comes to decides the route:

- Settled, or retired: the transaction is resolved -- current with its
  transcript and revision as recorded and its artifact posted once, or the
  fresh reviewer's to answer -- and the route goes on behind the last word
  over the landing and the base (`rewrite_finish_captured.stands_before_the_route`),
  settled evidence proved ready again first (`rewrite_finish_readiness`).
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
  before the last word reads it is abandoned over all the same. One nothing moved under is HELD
  with nothing announced and the attempt standing, and the recovery of the
  push already landed answers it again on a later tick: an artifact an earlier
  post landed, its response lost included, is found under its receipt rather
  than posted again, and settled once, with nothing run again and no
  developer launched.

A finish behind one that already settled the transaction -- its commit landed
and the process died, or the commit's answer was lost, or the tail behind it
died before the announcement, the relabel, or the retirement -- finds the
current evidence answering for the landed head and routes it with nothing
decided, run, posted, or settled again, but only while the records agree it is
the last word on the head: no pending record beside it, the handoff naming it,
and a revision floor somebody can read. A newer transaction recorded for the
head beside it is answered as any captured one is, and supersedes it once it
settles; any other disagreement holds the route. Whatever settled it, that
evidence is proved ready again before every route takes it
(`rewrite_finish_readiness.stands_ready`) -- one a newer transaction was
abandoned beside included (`stands_ready_if_settled`):
anything it is bound to that moved since its settlement, or a revision spent
past it, which outranks it for good, invalidates it into history whole, and
the head goes on to the fresh reviewer.
"""
from __future__ import annotations

import logging
from functools import partial

from orchestrator.git.base_sync import attempt_records as _attempt_records, attempts as _attempts
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
from orchestrator.workflow.engine.rewrite_evidence_proof import MOVEMENT, _reads_again, last_word, standing_refusal
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, LandedFinish
from orchestrator.workflow.engine.rewrite_finish_readiness import beside_current, invalidates, stands_ready
from orchestrator.workflow.engine.rewrite_landing_records import capture_answered, resolved

log = logging.getLogger("orchestrator.workflow")


def resolves(finish: LandedFinish) -> FinishOutcome | None:
    """Resolve the evidence `finish`'s landed head is routed with, before anything announces it; None to go on.

    A head the base advanced past again is routed with none: a transaction an
    earlier finish recorded for it is abandoned before its continuation is
    announced (`rewrite_finish_evidence.continues`), and nothing is decided or
    settled for it. For any other head the evidence step decides and records it
    (`rewrite_finish_evidence.settles`) and a transaction it recorded is
    published and settled here (`settles`) -- and so is a newer transaction
    recorded for the head beside evidence an earlier finish already settled
    for it, which then supersedes that evidence rather than leaving it
    current. Settled evidence with nothing beside it is taken with nothing
    decided, run, posted, or settled again, but only while the records agree
    it is the last word on the head -- no pending record at all, the handoff
    naming it, and a revision floor somebody can read -- and only once it
    proves ready again (`rewrite_finish_readiness.stands_ready`), which
    invalidates it where anything it is bound to moved since it settled, a
    revision spent past it included -- a newer transaction abandoned beside
    it outranks it for good, which no route may carry and no poll may hold
    over -- and holds the route where a reading could not be taken. One taken
    under a configuration no longer in place is invalidated as every movement
    under settled evidence is (`rewrite_finish_readiness.invalidates`), before
    the evidence step decides the head afresh: where that does not land --
    no room for its history entry among the reasons -- the movement is
    recorded against it and the route held, so putting the configuration back
    before room is made revives nothing. Any
    of those out of step holds the route, since nobody can say what was owed
    -- and so does any pending record about another head beside evidence an
    earlier finish of this landing already retired for it, current evidence
    or none (`_holds_out_of_step`) -- by the records, or by the receipt the finish
    put on the attempt once the history no longer keeps the run: that record
    was written after this landing's own,
    which recording its own would have retired, so it is another road's,
    unresolved, and stands with the attempt for whoever answers it. That one
    holds a continuation too, since announcing it, resetting the round, and
    retiring the attempt would leave the record owed behind a cleared attempt.
    """
    held = _holds_out_of_step(finish)
    if held is not None:
        return held
    if finish.behind:
        return _evidence.continues(finish)
    current = _settlement.read_current_evidence(finish.state)
    standing = current is not None and current.binding.target.target_head == finish.head
    captured = _captured.recorded(finish, logged=False)
    if standing and captured is None and invalidates_current(finish):
        if not invalidates(finish, current):
            log.warning(
                "issue=#%d holding the route of %.8s: verification evidence revision %d settled for it was taken "
                "under a configuration no longer in place, and could not be invalidated",
                finish.issue.number, finish.head, current.revision,
            )
            return FinishOutcome.HELD
        standing = False
    if not standing or captured is not None:
        return _evidence.settles(finish) or settles(finish)
    log.info(
        "issue=#%d already settled verification evidence revision %d for %.8s; settling and running nothing again",
        finish.issue.number, current.revision, finish.head,
    )
    return stands_ready(finish, current)


def settles(finish: LandedFinish) -> FinishOutcome | None:
    """Publish and settle the transaction recorded for the landed head under the standing anchor; None to route.

    None too where nothing is recorded for the head -- the decision ran or
    recorded nothing, or the last word behind it abandoned what it recorded --
    since the evidence is then the fresh reviewer's, save evidence an earlier
    finish settled for the head that is still current beside a newer
    transaction the decision abandoned: that is proved ready again
    (`stands_ready_if_settled`), and the revision the
    abandoned transaction spent past it alone invalidates it, so no route
    carries it and no later poll holds over it. Anything else is where
    the finish stops, with nothing announced, relabelled, or retired. Every
    write the answer makes is decided on the attempt as this finish read it
    (`verification_proof.ProofReading.rests_on`), and a finish whose state
    took in another road's record along the way -- a ledger entry the answer
    committed alone over a comment carrying a new attempt, or a newer
    transaction recorded in place of `pending` (`_answered_alone`) -- holds
    before anything proves, abandons, announces, or clears over it, so that
    record stands as its road wrote it, for the next finish to answer. Once
    nothing is recorded for the head any more -- settled or retired by the
    answer, or abandoned by the last word behind it -- the records that left
    are resolved afresh (`resolves`), with nothing recorded to answer this
    time, before anything is announced or routed: a settlement another road
    made while this one was published with a handoff that does not name its
    current evidence comes in with the comment the answer adopted and holds
    the route with the attempt standing, current evidence the configuration
    moved past is invalidated, with nothing run again, rather than routed or
    held over, and current evidence for the head -- the one this answer
    settled, or one an earlier finish settled that a revision this answer
    retired outranks -- is proved ready again before the route takes it. A
    transaction still owed goes to the last word over the first movement the
    answer read, where it read any -- a refusal of its binding, a bound record
    read moved, or a base read gone elsewhere, put back since or not, sorted as
    the last word sorts its own readings (`rewrite_evidence_proof.MOVEMENT`) --
    and otherwise over its proof taken again.
    """
    pending = _captured.recorded(finish, logged=False)
    if pending is None:
        return stands_ready_if_settled(finish)
    attempt = _commit_models.PinnedCommit.capture(finish.state, prerequisites=_attempts._ATTEMPT_KEYS)
    observed: list[ReportEvidence] = []
    read = _reads_again(finish)
    if read is not None:
        _transaction.answers(_proof.ProofReading(
            finish.gh, finish.spec, read[0], finish.state, anchored=partial(_anchored, finish),
            rests_on=tuple(_attempts._ATTEMPT_KEYS), observed=observed,
        ), pending)
    if read is None or not _answered_alone(finish, pending, attempt):
        log.warning(
            "issue=#%d holding the route of %.8s: the issue would not read again, or another road's attempt or "
            "evidence record stands where verification evidence revision %d was answered",
            finish.issue.number, finish.head, pending.revision,
        )
        return FinishOutcome.HELD
    if _captured.recorded(finish, logged=False) is None:
        return resolves(finish)
    stopped = _captured.stands_before_the_route(finish, proof=_proof_behind(finish, pending, observed))
    if stopped is not None or _captured.recorded(finish, logged=False) is None:
        return stopped or resolves(finish)
    log.warning(
        "issue=#%d holding the route of %.8s: verification evidence revision %d is still owed to its pull request",
        finish.issue.number, finish.head, pending.revision,
    )
    return FinishOutcome.HELD


def _proof_behind(
    finish: LandedFinish, pending: _records.PendingEvidence, observed: list[ReportEvidence],
) -> ReportEvidence:
    """What the last word over `pending` is handed as its proof: the first movement the answer read, or a fresh proof.

    Movement is sorted as the last word sorts its own readings: every refusal
    that defers, and the two holds that read movement rather than a reading
    that did not happen -- a landing off its head, a base gone elsewhere
    (`rewrite_evidence_proof.MOVEMENT`). Where the answer read none, the
    transaction is proved again over the issue and comment read afresh.
    """
    movements = (refused for refused in observed if not refused.holds or refused in MOVEMENT)
    return next(movements, None) or _captured.proved_again(finish, pending)


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

    Any other pending record -- a newer transaction another road recorded in
    its place, or one nobody can read -- or `pending` gone with no trace of
    its settlement or retirement is another road's, which this finish may
    neither prove `pending`'s refusals over nor route past; and so is an
    attempt other than `attempt`, the one the finish captured before the
    answer.
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

    Asked by `resolves` before the evidence is resolved, and by `settles` again
    over the records its answer left, before anything is announced or routed
    -- since a settlement or retirement another road made while this one was
    published comes in with the comment that answer adopted. The current
    evidence counts only where it answers for the landed head -- while the
    attempt stands nothing but a finish of this landing settles evidence for
    it -- under the context configured now, and never for a continuation,
    which routes none: evidence the configuration moved past is the evidence
    step's to invalidate (`rewrite_evidence.invalidates_current`), not a last
    word the route is held over, which would hold it for good. None where nothing
    was settled or retired for the head yet -- by the records
    (`rewrite_landing_records.resolved`), or, once the history no longer
    keeps the run, by the receipt the finish put on the attempt
    (`rewrite_landing_records.capture_answered`) -- and where a transaction is
    recorded for the head, which the finish answers itself. Otherwise any
    pending record -- about another head, or one nobody can read -- is out of
    step, and so, beside that current evidence, are a handoff that does not
    name it and a revision floor nobody can read
    (`rewrite_finish_readiness.beside_current`). A readable revision spent
    past it is no hold: it outranks that evidence, which the readiness proof
    then invalidates rather than holding every later poll over it.
    """
    state = finish.state
    current = None if finish.behind else _settlement.read_current_evidence(state)
    if current is not None and current.binding.target.target_head != finish.head:
        current = None
    if invalidates_current(finish):
        current = None
    settled = resolved(state, finish.head) or capture_answered(state)
    out_of_step = ""
    if settled and _captured.recorded(finish, logged=False) is None:
        out_of_step = beside_current(state, current)
    if not out_of_step:
        return None
    log.warning(
        "issue=#%d holding the route of %.8s: the verification evidence already resolved for it is out of step: %s",
        finish.issue.number, finish.head, out_of_step,
    )
    return FinishOutcome.HELD


def stands_ready_if_settled(finish: LandedFinish, *, or_the_base: bool = False) -> FinishOutcome | None:
    """`stands_ready` over evidence settled current for `finish`'s landed head, where any is; None to go on.

    For a route whose evidence step left nothing recorded for the head
    (`settles`): where a newer transaction recorded beside settled evidence
    was abandoned, that evidence is still current, and the route may not
    carry it unproved. And for the retirement behind the relabel
    (`rewrite_finish`), the last write of the route, `or_the_base` set: the
    announcement and the relabel are requests made after the evidence was
    resolved, and a base advanced while they were answered has the route held
    with the attempt standing rather than retired over a head the base has
    left behind -- settled evidence proved ready over the landing and the base
    and invalidated over what moved, and a head with none current for it (the
    fresh reviewer's responsibility handed off, or evidence of the replaced
    head deferred) held to the base tip its replay was made onto alone, by the
    last word over the base (`rewrite_finish_captured.stands_before_the_route`),
    so the recovery continues the head to another rebase. Such a head carries
    no decision the landing could move under: a head pushed over it meanwhile
    is the pull request's to show the validating stage, which reads it afresh.
    An attempt that records no such tip -- one blanked to record movement
    under the evidence (`rewrite_finish_readiness`,
    `rewrite_recovery_parks.records_the_reset`), one blanked because the base
    moved while git ran, or a legacy attempt pinned before the tip was among
    its members -- proves nothing about which base the head was replayed
    onto, which every proof reads as refusing the evidence rather than the
    route: its head is held instead to the base this tick counted it against
    (`rewrite_evidence_proof.standing_refusal`), so a base advanced while the
    announcement or the relabel was answered still holds the route.
    """
    current = _settlement.read_current_evidence(finish.state)
    stopped = None
    if current is not None and current.binding.target.target_head == finish.head:
        stopped = stands_ready(finish, current)
    elif or_the_base:
        stopped = _captured.stands_before_the_route(finish, landing=False)
    unproven = not _attempt_records._recorded_onto(finish.state)
    if stopped is not None or not (or_the_base and unproven):
        return stopped
    counted = finish.landed.candidate.checkout
    moved = standing_refusal(finish, onto=counted.base.tip)
    if moved is None or not moved.holds:
        return None
    log.warning(
        "issue=#%d holding the route of %.8s: its attempt records no base tip, and the base this tick counted "
        "it against reads otherwise now (%s)",
        finish.issue.number, finish.head, moved.refusal,
    )
    return FinishOutcome.HELD
