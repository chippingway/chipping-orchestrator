# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The verification evidence an approval's squash carries onto the head it published.

An approval is proved over current evidence (`approved_evidence`), and that
evidence answers for the head the reviewer was handed. The squash behind the
approval -- a collapse, or a one-commit branch rewritten for its subject alone
-- force-pushes another commit, so past it the pull request stands on a head
no evidence answers for. The rewrite keeps the tree, but nothing may assume
that: the evidence reaches the new head only through a carry-forward decision
(`verification_carry_forward`), which PROVES the tested commit and the new
head both read as the tested tree, the verification context unchanged, the
review subject the evidence answers for still the recorded one and exactly the
one the approval covers -- its report revision and digest and its
requirements with it, never a later review recorded about the new head -- the
pull request standing on the new head, and the source's artifact still the
one that settled.

What that decision earns is a new transaction, recorded in the write that
settles the squash's handoff -- a guarded commit owning the pending record,
the history and revision floor it moves, and the approval's claim beside the
handoff's own fields (`SquashEvidence.writes`) -- the tested commit and tree
unchanged, the new head as the equivalent-tree target, and the source's own
transcript, so the artifact the dispatcher's reconciliation publishes says
which earlier commit ran and never relabels that run as one on the squash. The
approval record is pointed at that transaction in the same write
(`review_approved_evidence`), so
every road that later acts on the approval holds it to evidence answering for
the head it is moving. The reconciliation proves the whole binding again --
the report the subject names, re-read, and the requirements included --
before the transaction is published or becomes current.

The run carried is the approval's own where it has one that binds. Its verify
gate ran the configured commands on the approved head this tick, and a run
that passed there whole (`verification_local_runs.local_run_evidence`) is
what this orchestrator observed: it is carried in place of the evidence the
approval was proved over, as orchestrator-executed evidence naming the
approved head as the commit tested, its own transcript published, over the
same proofs save an artifact it never had
(`verification_carry_forward.local_run_decision`), and the approval's claim
names it with the digest and flags that transcript earns. An empty
configuration runs nothing and binds nothing, and the recovery of a squash an
earlier tick began has no run in hand: there the reviewer's evidence the
approval rests on is what is carried.

A carry is recorded only where the very candidate its write sends -- the
fresh comment, another road's writes since included -- has room for its
record, and to settle it and invalidate it once settled
(`SquashEvidence.admits`): one recorded where it cannot settle would stand
owed and unpublished on every later tick. Where it has not, the evidence is
invalidated in its place, as for a carry the comment has no room to record at
staging (`SquashEvidence.without_room`), in a write carrying no transaction.

The move to `documenting` waits for it. A recorded carry holds the label for
the tick that recorded it, and the next tick's reconciliation, ahead of every
handler, publishes and settles it; the handoff behind the squash then moves
the label (`collapse._finished_handoff`), with no second reviewer. A
publication nobody could confirm holds that tick and is retried on the next,
and so does one that stood down with the carry still owed -- a comment with
no room to settle into, before the post or behind it: the move HOLDS over a
carry still owed for the approval it was recorded for (`carried_onto`), the
handoff kept, until a later tick settles it. One the reconciliation refuses
-- the head moved, the report, the requirements, or the source it copied
edited -- is abandoned with that approval (`verification_carries`), which
the handoff's own proof refuses (`approved_evidence.stands`), so the handoff
is dropped and a fresh reviewer validates the head as it stands.

A carry that settled is not taken on its target alone. Before any label moves
over evidence answering for a head it did not run on -- the relabel the
handoff retries included -- that evidence is proved whole again
(`verification_proof.current_evidence_verdict`): the tested commit and the
head still reading as the tested tree, the applicable review subject still
recorded and the approved one, the context, the publication, the report, and
the requirements. Evidence of a run on the head itself was proved in the
approval's own tick, and only its context is asked again. On the road that
retries the relabel this is asked ahead of the approval's coverage, so the
pull request is the last thing read before the move, and a handoff that
coverage drops takes the settled carry with it (`drops_the_handoff`).

A decision against the evidence -- a tree that is not the tested one or that
nobody could read, a context moved (during the squash included), a pull
request that moved off the head or ended, a review subject replaced or gone,
an artifact gone or edited, or a carry onto the head the approval's claim no
longer names -- is the evidence proved to no longer answer for the pull
request: it is invalidated into history, the approval it was recorded for
retired with it (its subject written null, which no reader takes for an
approval; one another road recorded in its place, of another subject, stands),
and the handoff that would have moved the label over it dropped, in the same
write, so the next tick hands a fresh reviewer the head as it stands. A carry
the comment has no room to record is answered the same way. A pull request or artifact nobody could
read decides nothing: the handoff stands, nothing is recorded, and the next
tick decides again.

Nothing is this owner's where the approval rests on no evidence at all, or on
evidence the records no longer carry as the latest -- a claim on another
record, a later revision spent, a handoff that does not describe it:
`review_coverage._approval_holds` refuses that approval on its own. Evidence
carried onto the head the handoff names is the exception, since only an
approval's claim ever put it there: unclaimed, it is refused here.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from orchestrator.git.verification import models as _verify_models
from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState, pinned_state_body
from orchestrator.workflow.engine import (
    report_evidence_models as _evidence_models,
    verification_carries as _carries,
    verification_carry_forward as _carry_forward,
    verification_current as _current,
    verification_local_runs as _local_runs,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.review_subjects import APPROVED_SUBJECT
from orchestrator.workflow.engine.verification_records import (
    CURRENT_EVIDENCE,
    EVIDENCE_HISTORY,
    PENDING_EVIDENCE,
    REVISION_FLOOR,
    CurrentEvidence,
    PendingEvidence,
)
from orchestrator.workflow.late_split import handoffs as _late_handoffs
from orchestrator.workflow.stages.validating import (
    approved_evidence as _approved_evidence,
    review_claims as _claims,
    review_verdicts as _verdicts,
)

log = logging.getLogger("orchestrator.workflow")

# Why evidence carried onto the head is refused where the approval's claim
# does not name it, and why the move waits on a carry still owed.
_UNCLAIMED = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.DEFER,
    "the approval's evidence claim does not name the evidence carried onto the head",
)

_OWED = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.HOLD,
    "the carry the approval's squash recorded onto the head is still owed to the pull request",
)

# Why a carry is invalidated rather than recorded where the comment its write
# lands on -- another road's writes since included -- has no room for it, to
# settle it, or to invalidate it once settled.
_UNSETTLEABLE = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.DEFER,
    "the pinned comment the carry would be recorded on has no room to settle it",
)

# What invalidating carried evidence writes (`_invalidates`): the evidence, the
# history it goes into, the approval it was carried for, and the squash's
# handoff over it.
INVALIDATES = (CURRENT_EVIDENCE, EVIDENCE_HISTORY, APPROVED_SUBJECT, _late_handoffs.LATE_COLLAPSE_HANDOFF)

# What recording a carry writes (`_records_the_carry`): the transaction owed,
# an earlier one it retires into history, the revision floor it raises, and the
# approval's claim pointed at it -- or, where the comment has no room for it,
# what invalidating the evidence writes instead.
CARRIES = (PENDING_EVIDENCE, EVIDENCE_HISTORY, REVISION_FLOOR, _approved_evidence.APPROVED_EVIDENCE, *INVALIDATES)

# The record beyond those the evidence is bound through that whether a carry
# still answers is read off (`carry_unanswered`): the approval's claim on it.
# The report debt its review subject stands only without is bound already
# (`verification_durable`).
CARRY_ANSWERS_ON = (_approved_evidence.APPROVED_EVIDENCE,)


@dataclass(frozen=True)
class SquashEvidence:
    """What the evidence a recorded approval rests on owes the head its squash published.

    Nothing (`answers`), a `carry` to record, or the verdict `refused` that
    decided against one -- HOLD for a reading nobody could take, or for a
    carry already recorded and still owed.
    `through_a_carry` is evidence that answers only through a carry already
    settled: proved whole again, its tested commit another one than the head.
    """

    carry: _carry_forward.CarryForward | None = None
    refused: _evidence_models.ReportEvidence | None = None
    through_a_carry: bool = False

    @property
    def answers(self) -> bool:
        """Whether the evidence owes the head nothing, so the label may move over it."""
        return self.carry is None and self.refused is None

    @property
    def holds(self) -> bool:
        """Whether nothing was decided: a reading nobody could take, or a carry owed, for the next tick to ask again."""
        return self.refused is not None and self.refused.holds

    @property
    def writes(self) -> tuple[str, ...]:
        """Every field `stages` may write, for the guarded commit carrying it to own: none where it stages nothing."""
        if self.answers or self.holds:
            return ()
        return INVALIDATES if self.carry is None else CARRIES

    def admits(self, candidate: PinnedState) -> str | None:
        """Why the complete candidate a write carrying this decision sends may not land; None where it may.

        Asked of the very candidate a guarded commit sends (`handoff._Held.settles`),
        the fresh comment with every write another road made since laid under
        it, not of the state the carry was staged on: a carry recorded where
        its settlement, or the invalidation that settlement leaves room for
        (`verification_record_state.settled_payload`), would not fit is one the
        reconciliation stands down on every tick, owed and unpublished, and
        the move it holds never comes. A decision that recorded no carry is
        admitted as it stands.
        """
        pending = _record_state.read_pending_evidence(candidate)
        carried = None if self.carry is None else self.carry.binding
        if carried is None or pending is None or pending.binding != carried:
            return None
        settled = _record_state.settled_payload(candidate, pending)
        if settled is not None and len(pinned_state_body(settled)) <= MAX_PINNED_BODY:
            return None
        return _UNSETTLEABLE.refusal

    def without_room(self) -> SquashEvidence:
        """This decision, where its carry has no room to be recorded or settled: refused, invalidating the evidence."""
        return replace(self, carry=None, refused=_UNSETTLEABLE, through_a_carry=False)

    def stages(self, state: PinnedState, issue_number: int) -> None:
        """Stage onto `state` what this decision owes the comment; the caller writes.

        The carry and the approval's claim on it, or -- for a refusal, or a
        carry the comment has no room for -- the evidence invalidated and the
        handoff dropped. Nothing where the decision answers or holds.
        """
        if self.answers or self.holds:
            return
        if self.carry is None or not _records_the_carry(state, issue_number, self.carry):
            _invalidates(state)

    def drops_the_handoff(self, state: PinnedState) -> None:
        """Stage the handoff dropped where the approval no longer covers what stands, and a carry it rests on with it.

        A carry answers for the head it was carried onto only on the
        approval's word -- the approved review, about the commit that was
        tested -- and was recorded only to move the label over that approval.
        So a handoff dropped for a fresh reviewer takes it into history too
        rather than leaving it current over an approval that moves nothing. The
        caller writes.
        """
        if self.through_a_carry:
            _invalidates(state)
        else:
            _late_handoffs.clear_settled_handoff(state)


def carried_onto(
    reading: _proof.ProofReading, head: str | None, run: _verify_models.VerifyResult | None = None,
) -> SquashEvidence:
    """What the evidence the recorded approval rests on owes `head`, the commit its handoff moves the label over.

    `run` is the local verify run the approval's gate made this tick, where
    one was made: carried in place of the evidence the approval rests on
    where it binds (`_carried`). Asked ahead of the comment the write behind
    it is laid over, since the decision is requests of its own; the caller
    stages its answer only where that comment still carries the evidence
    records it was taken over.

    A carry onto `head` already recorded and still owed -- the claim pointed
    at it, its approval standing -- is the reconciliation's to settle, and
    one it stood down on rather than abandoned is one a later tick answers:
    the comment with no room to settle into, before the post or behind it. So
    the move HOLDS over it, the handoff kept, rather than being taken for an
    approval resting on evidence that never settled.
    """
    state = reading.state
    owed = _record_state.read_pending_evidence(state)
    if head and _carries.awaits_settlement(state, owed, head) and _rests_on(state, owed):
        log.info(
            "issue=#%d holds the move over %s for the carry its squash recorded, "
            "still owed to the pull request", reading.issue.number, head,
        )
        return SquashEvidence(refused=_OWED)
    current = _settlement.read_current_evidence(state)
    if not head or current is None:
        return SquashEvidence()
    carried = current.binding.target.target_head == head and current.binding.tested_sha != head
    if not _rests_on(state, current):
        return SquashEvidence(refused=_UNCLAIMED) if carried else SquashEvidence()
    decided = _decided(reading, current, head, run)
    if isinstance(decided, _carry_forward.CarryForward):
        return SquashEvidence(carry=decided)
    return SquashEvidence(refused=None if decided.proved else decided, through_a_carry=carried and decided.proved)


def _rests_on(state: PinnedState, current: CurrentEvidence | PendingEvidence) -> bool:
    """Whether the recorded approval's claim names `current` exactly, and the records still carry it as the latest.

    `current` is the current record, or the carry still owed that the claim
    was pointed at: the latest by the floor it raised, and described by no
    handoff until it settles.

    The verification context is not asked here but by `_decided`, so evidence
    minted under a context that moved is invalidated rather than left current
    for the coverage check to refuse. Anything else -- no claim, a claim on
    other evidence, a later revision spent, a handoff that does not describe
    it -- is evidence this owner does not hold, and is
    `review_coverage._approval_holds`'s to refuse; save evidence carried onto
    the head itself, which answers there only on the approval's word. Without
    the claim naming it -- removed, written null, or pointed elsewhere -- that
    word is gone, and the carry is refused (`carried_onto`) and invalidated
    with the handoff over it, rather than proved by nothing and passed by the
    fallback that holds an approval older than evidence claims to none.
    """
    claim = _verdicts.EvidenceClaim.read(state.get(_approved_evidence.APPROVED_EVIDENCE))
    named = None if claim is None else (claim.receipt, claim.revision, claim.digest)
    if named != (current.receipt, current.revision, current.content_revision):
        return False
    return not _current._outranked(state, current) and (
        isinstance(current, PendingEvidence) or _current._handoff_describes(state, current)
    )


def _decided(
    reading: _proof.ProofReading,
    current: CurrentEvidence,
    head: str,
    run: _verify_models.VerifyResult | None,
) -> _carry_forward.CarryForward | _evidence_models.ReportEvidence:
    """The carry onto `head` the approval's evidence earns, or the verdict on its answering for `head` already.

    Evidence about another head is carried or refused: the approval's own
    local verify run where it binds, else `current`. The run is what this
    orchestrator observed, so where its gate ran the configured commands on
    the approved head it is the evidence carried, as orchestrator-executed
    and naming that head as the commit tested. It is bound against the target
    `current` answers for -- that head and its review -- so only a passing
    run on that very head binds (`verification_local_runs.local_run_evidence`):
    an empty configuration ran nothing and never does, and neither does a
    road that has no run in hand -- the recovery of a squash an earlier tick
    began -- so the reviewer's evidence the approval rests on is carried
    there instead.

    Evidence that answers for `head` only through a carry -- the tested
    commit another one -- is proved whole again before any label moves over
    it (`verification_proof.current_evidence_verdict`): the trees, the
    applicable review subject, the context, the publication, the report, and
    the requirements its settlement was proved over can each have moved or
    stopped reading since. Evidence of a run on `head` itself was proved in
    this approval's own tick, and only its context is asked again.
    """
    binding = current.binding
    if binding.target.target_head != head:
        local = None if run is None else _local_runs.local_run_evidence(run, binding.target)
        if local is None:
            return _carry_forward.carry_forward_decision(reading, head, approved=True)
        return _carry_forward.local_run_decision(reading, *local, head)
    if binding.tested_sha == head:
        verdict = _proof._context_verdict(binding) or _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.PROVED,
        )
    else:
        verdict = _proof.current_evidence_verdict(reading)
    if not verdict.proved:
        log.info(
            "issue=#%d its approval's verification evidence no longer answers "
            "for %s: %s", reading.issue.number, head, verdict.refusal,
        )
    return verdict


def carry_unanswered(state: PinnedState) -> bool:
    """Whether current evidence carried onto a head it did not run on no longer answers for that head.

    A carry answers there only on the approval's word: the approval's claim
    naming it exactly as the latest evidence (`_rests_on`), and the review
    subject it was carried for still standing
    (`verification_current.carry_answers`). Either gone -- the claim removed,
    written null, or pointed elsewhere; the review returned since, removed,
    or replaced -- it answers for nothing, so every reader about to move the
    approval on refuses it (`review_coverage._approval_stands`) and
    `validating`, which owns it, invalidates it (`collapse`). Read off the
    pinned comment alone; False where nothing current is carried.
    """
    current = _settlement.read_current_evidence(state)
    if current is None or current.binding.tested_sha == current.binding.target.target_head:
        return False
    return not (_rests_on(state, current) and _current.carry_answers(state))


def _records_the_carry(state: PinnedState, issue_number: int, carry: _carry_forward.CarryForward) -> bool:
    """Record the carry's transaction and point the approval's claim at it, or say the comment would not take it.

    The claim names the transaction exactly -- its receipt, revision, and
    the digest and flags its own transcript earns, which a carry of the same
    evidence leaves as they were and a local run's transcript sets afresh --
    and is owed to the pull request until it settles. Its record can grow
    with that (`reused` read as `published`), so it is pointed at the
    transaction on a copy first, and the transaction is recorded onto that
    copy: the room the recorder measures -- the record, the settlement it is
    owed, and the invalidation that settlement has to leave room for -- is
    measured with the claim as it will be written, and nothing is staged where
    the comment would not carry it.
    """
    claim = _verdicts.EvidenceClaim.read(state.get(_approved_evidence.APPROVED_EVIDENCE))
    pending = _record_state.mint_pending_evidence(
        state, issue_number, carry.binding, carry.commands, carry.copied_from,
    )
    composed = PinnedState(state_data=dict(state.data))
    recorded = claim is not None and pending is not None
    if recorded:
        _approved_evidence.records(composed, replace(
            claim,
            use=_verdicts.EvidenceUse.PUBLISHED,
            receipt=pending.receipt,
            revision=pending.revision,
            digest=pending.content_revision,
            passed=pending.passed,
            covers=_claims.covers_the_configuration(pending.commands),
        ))
        recorded = _record_state.record_pending_evidence(composed, pending)
    if not recorded:
        log.error(
            "issue=#%d could not record the verification evidence its squash "
            "carries onto %s; invalidating it instead", issue_number, carry.target_head,
        )
        return False
    state.data = composed.data
    return True


def _invalidates(state: PinnedState) -> bool:
    """Retire the evidence the squash moved the pull request past, the approval it answers for, and the handoff over it.

    The approval goes with its evidence: its subject is written null, which
    every reader of an approval refuses (`review_subjects.approval_covers_current`)
    until a fresh reviewer's approval is recorded in its place. Retiring the
    evidence alone would leave an approval whose claim is gone looking like
    one recorded before approvals named evidence, and readers would take it.
    Only that approval, though -- the very subject the evidence answers for
    (`verification_carries.retires_its_approval`), as for a carry abandoned
    before it settled: one another road recorded in its place, of another
    subject, is not this evidence's to retire, and stands as written.
    The approval and the handoff go whether or not the evidence does: a
    retirement the comment has no room for leaves the record standing --
    answering for a head the pull request has left, so it hands no reviewer
    anything -- and writing the approval null and the handoff away only ever
    shrinks the comment, so that refusal is always one the comment can carry.
    Whether the evidence was retired. The caller writes; every field this
    stages is one of `INVALIDATES`, which the commit invalidating an
    unanswered carry owns (`collapse`), as does the commit staging a refused
    carry (`SquashEvidence.writes`).
    """
    current = _settlement.read_current_evidence(state)
    if current is not None:
        _carries.retires_its_approval(state, current.binding)
    retired = _settlement.retire_current_evidence(state)
    _late_handoffs.clear_settled_handoff(state)
    return retired
