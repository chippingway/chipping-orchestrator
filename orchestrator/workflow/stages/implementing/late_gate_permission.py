# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Determine why a named candidate may publish without another measurement.

An exemption requires its operator authorization, a debt requires its
permission, and a past push requires its publication receipt. The switch
only admits new work after these existing records have answered.
"""
from __future__ import annotations

from orchestrator import config
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.implementing import (
    late_approval_reading as _late_approval_reading,
    late_authority as _authority,
    late_delivery as _delivery,
    late_publication_state as _late_publication_state,
    late_transfer_reading as _late_transfer_reading,
)
from orchestrator.workflow.stages.implementing.late_gate_models import _Gate

_ADJUDICATED = "was adjudicated as one change an operator authorized"

_APPROVED = "is the commit this gate approved and has still to push"

_PUBLISHED = "is the commit this stage has already pushed"

_SWITCHED_OFF = "is new work the size gate is switched off for"


def _admitted_by(decided: str) -> str:
    """The basis the debt a candidate admitted without a reading rests on.

    One road past the measurement is a human's -- the exemption an operator
    authorized -- and the debt it leaves may be spent only while that
    authorization can still be read. Every other road is a record this
    workflow made for itself and re-derives on the next tick, so the debt
    behind one answers for its own bypass and the tick after a crash spends it
    without asking anybody.

    Said here rather than at the write, because the answer above is what knows
    and a proof taken a second time is a second chance to fail.
    """
    if decided != _ADJUDICATED:
        return str(_late_approval_reading.LateApprovalBasis.UNMEASURED)
    return str(_late_approval_reading.LateApprovalBasis.ADJUDICATION)


def _approved_on_a_reading(
    gate: _Gate, candidate_sha: str,
) -> bool:
    """Whether this commit's debt rests on a decision this gate already made.

    An approval is the gate's own answer brought back by a crash, which is
    what makes skipping the reading for it a repeat rather than a bypass. One
    exception, and it is the only approval that was never a reading at all: a
    commit an approval names because a rewrite TRANSFER let it past. What
    licensed that push is a permit, granted on terms -- a pull request, a
    stage, a record, two fingerprints -- that can each stop being true between
    the grant and the tick that comes back to pay the debt.

    So a debt an OUTSTANDING permission stands beside defers to the permit,
    which `late_transfer` re-asks in full over the record the grant left. That
    is asked of the permission rather than of the commit it names, because the
    two go down in one write for one commit: an approval beside an outstanding
    permission is either the one it licensed or evidence the record disagrees
    with itself, and a hand-edited target would otherwise make the permit
    invisible and leave the approval looking ordinary.

    Refused, the ordinary cumulative gate measures the rewrite like any other
    candidate: an oversized change nothing may publish unmeasured is exactly
    what an unvalidatable permission leaves behind.

    A debt the EXEMPTION left defers on the same footing and for the same
    reason, and `late_authority` is where its provenance is read. The
    settlement writes the approval and the exemption in one breath, so an
    approval resting on that adjudication is the adjudication wearing another
    field -- and where nothing authorizes the exemption, nothing authorizes
    the debt either. A gate-owned approval, which is every approval for a
    candidate the reading found at or below the ceiling, is untouched by it:
    that one is this gate's own answer brought back by a crash, and no human
    was ever owed a decision about it.
    """
    if _late_approval_reading._approved_commit(gate.state) != candidate_sha:
        return False
    if _authority._unauthorized_debt(gate, candidate_sha):
        return False
    return not _late_transfer_reading._licensed_by_a_permit(gate.state)


def _already_decided(
    gate: _Gate,
    candidate_sha: str,
    delivered: _delivery._Delivered,
) -> str:
    """Why the RECORD says this commit needs no reading, or "" if it does not.

    Four records say a commit was already DECIDED about, and they say it the
    same way: by naming one commit and only it, so anything committed on top
    of any of them is work nobody decided about and is measured as the fresh
    candidate it is.

    The first is the exemption, and it is asked as a PAIR with the
    authorization beside it. What the exemption records is that an
    adjudication ruled the change one coherent whole, which is an agent's
    answer; what an operator's authorization records is that a human who read
    it agreed to publish past the ceiling. Only the two together are a bypass
    -- a guard against agents putting unreviewed bulk on a pull request may
    not be waived by an agent saying it should be -- so a commit only the
    exemption names goes to the ordinary cumulative gate, which is what an
    older binary's automatic exemption gets and what a hand-edited or
    half-written authorization costs. The pair outlives the publication
    because the gate would otherwise measure the same candidate past the same
    ceiling forever.

    The approval is this gate's own -- with two exceptions, a permit that
    granted it, which defers to that permit rather than answering on the
    object id alone, and the debt an unauthorized exemption left, which is
    that exemption wearing another field and defers to the same reading -- and
    it lives only until the push it licenses lands: the write that
    approves a candidate drops the generation naming it, so a crash before the
    push brings the same commit back here with nothing left to say it was
    already settled. Measuring it again is not a second opinion -- the base
    has moved since, so it is a different question -- and answering it can
    route work a human already adjudicated straight back into adjudication.

    Between the two sits the one answer an unauthorized exemption still earns:
    a commit the pull request this call FROZE is ALREADY standing on. The push
    would move nothing, so what would be held back is the bookkeeping behind a
    publication that has happened -- and published work under a stage nothing
    will advance is worse than the unmeasured push this rule exists to stop,
    which is not on offer either way.

    The publication record is that same window read from its far end, and the
    one that matters most because the effects are already out, and it is the
    one asked against the REMOTE rather than off the record alone: a receipt
    naming a commit the pull request has since moved off records a
    publication that is over, and work the remote no longer carries is work
    this gate has not decided about. past the push
    the branch is on the remote and a pull request carries it, while the label
    still says implementing until the relabel lands. A relabel that failed
    leaves the next tick reading a published branch as work nobody has ruled
    on, and an oversized answer there would route it to adjudication with
    nothing left to hold back -- the one outcome this gate exists to prevent.
    So the commit is recognized rather than re-read, the pull request that
    already carries it is reused, and the relabel is finished.

    What the receipt is held to is `late_delivery`'s, and it differs by seam
    rather than being skipped on either. A call taken PAST a publication froze
    the pull request and the head it is standing on, and the receipt is held
    to BOTH: the head says the work is there, and the number says it is there
    because of the push this record is about. One taken before it froze
    neither, so the same question goes to the remote -- the pull request the
    record names, open, on the branch this seam would push, standing on this
    exact commit -- because a note that is never cleared is not on its own
    evidence that anything still carries the work.
    """
    if _authority._publishes_on_an_exemption(gate, candidate_sha):
        return _ADJUDICATED
    standing = _authority._already_on_its_pull_request(gate, candidate_sha)
    if standing:
        return standing
    if _approved_on_a_reading(gate, candidate_sha):
        return _APPROVED
    if _late_publication_state._published_commit(gate.state) != candidate_sha:
        return ""
    vouched = _delivery._receipt_answers_alone(gate, delivered, candidate_sha)
    return _PUBLISHED if vouched else ""


def _needs_no_measuring(
    gate: _Gate,
    recorded: LateGeneration,
    candidate_sha: str,
    delivered: _delivery._Delivered,
) -> str:
    """Why this commit publishes without a reading, or "" where it needs one.

    The records that say a commit was already decided about come first, and
    `_already_decided` beside this owns all of them, the publication its own
    pull request already carries included.

    The switch is the last answer and is asked last, here rather than at the
    door, for the one state the door could not settle. An approval keeps
    the switch from bypassing, because a commit this gate decided has to be
    published under the id it decided about -- and that is a claim about ONE
    commit, which nothing can check until the head is proved. Past that proof
    and not it, the approval describes work this branch has moved past: the
    candidate in hand is new work, and new work is exactly what the switch
    keeps out of the gate. A record already in the gate, and a call answering
    a reading the gate itself took, are neither -- and the second is asked as
    `answering` rather than as the wider "no developer ran", which a rebase, a
    resolution, and a recovery push each set over work this gate has never
    seen.

    "A record already in the gate" is a record about THIS commit, which is the
    same claim by one commit and only it every record above is recognized by. A
    generation naming some OTHER candidate is one a resumed developer's fresh
    commit has moved past, and the fresh commit is new work: measured where
    the switch is on, published untouched where it is off, and in both cases
    the superseded record is retired rather than left over a commit nothing
    will publish. Read as "in the gate" instead, an install with the switch
    off measures exactly the work it turned the gate off for.
    """
    decided = _already_decided(gate, candidate_sha, delivered)
    if decided:
        return decided
    already_read = (
        recorded.candidate_sha == candidate_sha or gate.answering
    )
    if config.DECOMPOSE or already_read:
        return ""
    return _SWITCHED_OFF
