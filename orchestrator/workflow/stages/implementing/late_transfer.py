# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Grant or refuse an exemption transfer and persist its permission with publication debt.

Evidence, publication, checkout, owner, base, and authorization checks run
in their fixed order before contribution proof. Failed writes restore the
previous state; a proved rollback abandons only its outstanding permission.
"""
from __future__ import annotations

import logging

from orchestrator.workflow.late_split import (
    exemption_reading as _exemption_reading,
    rewrite_reading as _rewrite_reading,
    rewrite_values as _rewrite_values,
    rewrites as _rewrites,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_transfer_checkout as _late_transfer_checkout,
    late_transfer_contribution as _late_transfer_contribution,
    late_transfer_evidence as _late_transfer_evidence,
    late_transfer_reading as _late_transfer_reading,
    late_verdict_debt as _late_verdict_debt,
)

log = logging.getLogger("orchestrator.workflow")

# What the gate reports a carried-over candidate as, spelled the way the log
# line it joins reads.
_CARRIED_OVER = "carries an adjudicated change through a workflow rewrite"


def _carried_over(gate: _late_gate_models._Gate, candidate_sha: str) -> str:
    """Carry the exemption onto this rewritten commit, or "" if it may not.

    Answered before anything is measured and before anything is pushed, and
    answered in silence for every candidate that is not a rewrite of an
    accepted one: a squash of work nobody adjudicated is the ordinary case,
    and a line about it on every approval would say nothing.

    Past that, a refusal IS worth a line. What it means is that a change a
    human already ruled on is about to be measured again and may be routed
    back into adjudication with the branch already approved, so the reason is
    said out loud even though nothing is parked over it.

    A caller with no evidence of its own is answered from the RECORD, which is
    what makes the crash between a grant and the push it licensed recoverable
    on the same terms it was granted on. The recovery that republishes an
    approved commit has no plan behind it and no rewrite to describe, so the
    permission already on the comment supplies both ends of both pairs, the
    publication, and the lease -- and every question is asked again over them.
    Believed instead of re-asked, a hand-edited record, a repointed pull
    request, or a relabelled issue would each push an oversized rewrite that
    nothing revalidated.
    """
    rewrite = gate.rewrite or _late_transfer_reading._outstanding_rewrite(gate.state, candidate_sha)
    if rewrite is None or rewrite.to_sha != candidate_sha:
        return ""
    identity = _exemption_reading.read_semantic_identity(gate.state)
    if identity is None or identity.exempt_sha != rewrite.from_sha:
        return ""
    permit = _permit(gate, rewrite, identity)
    if not permit.is_granted:
        log.info(
            "issue=#%d may not carry the exemption for %s onto the rewritten "
            "%s (%s); measuring it as a fresh candidate",
            gate.issue.number, rewrite.from_sha, rewrite.to_sha,
            permit.refusal,
        )
        return ""
    granted = _authorized(
        gate, rewrite, permit.fingerprint, identity.fingerprint,
    )
    return _CARRIED_OVER if granted else ""


def _permit(
    gate: _late_gate_models._Gate,
    rewrite: _rewrite_values.LateRewrite,
    identity: _exemption_reading.LateSemanticIdentity,
) -> _late_transfer_contribution._Permit:
    """Everything a transfer is granted on, asked in the order it costs.

    The evidence's own shape first, because it costs nothing and no later
    question means anything without it. Then the authorization already on the
    comment, which is the one thing a grant would DESTROY rather than merely
    read. Then the publication, which this call has already read. Then the two
    local git reads -- the checkout, and the lease as an object this host has
    to hold. Then the two requests: the issue, and the branch the rewritten
    contribution claims to be read over, which is the one end no digest can
    prove for itself. And the fingerprints last, because they are the heaviest
    reading in the domain -- every object either contribution names is read
    back in full -- and there is no point taking them for a transfer something
    cheaper has already refused.

    The operator authorization behind the exemption is asked with them rather
    than at the door for that same reason: proving one is a fingerprint, since
    every other term of an authorization is the pinned comment agreeing with
    itself. Its own reading is the first of the three, because a transfer that
    may not happen at all should not pay for the two that compare
    contributions.
    """
    for question in (
        _late_transfer_evidence._unusable_evidence,
        _late_transfer_reading._unreadable_authorization,
        _late_transfer_evidence._disagreeing_publication,
        _late_transfer_checkout._unproven_checkout,
        _late_transfer_checkout._unproven_lease,
        _late_transfer_checkout._unconfirmed_owner,
        _late_transfer_checkout._unproven_base,
        _late_transfer_reading._unauthorized_exemption,
    ):
        refusal = question(gate, rewrite)
        if refusal:
            return _late_transfer_contribution._Permit(refusal=refusal)
    permit = _late_transfer_contribution._equal_contributions(gate, rewrite, identity)
    if permit.refusal:
        return permit
    disagreeing = _late_transfer_reading._disagreeing_authorization(gate, permit.fingerprint)
    return _late_transfer_contribution._Permit(refusal=disagreeing) if disagreeing else permit


def _authorized(
    gate: _late_gate_models._Gate,
    rewrite: _rewrite_values.LateRewrite,
    fingerprint: str,
    recorded: str,
) -> bool:
    """Record what licenses this rewrite to publish, durably, before any push.

    The PERMISSION rather than the move. The exemption stays exactly on the
    commit a human ruled on and the identity beside it stays with it, because
    the commit this permission is about is on no remote yet: rotated here, a
    push that never lands would leave a verdict on an object only this host
    has, and every later tick would read the accepted work at HEAD as carrying
    none. The rotation belongs to the write that receipts the landed push,
    where it goes down with the account of what the remote carries or not at
    all -- so what this records is a permission that stands until that write
    spends it.

    What licenses THIS tick's publication is the permit itself, handed back to
    the gate -- so nothing has to be rotated early for the push to be allowed.

    Two things go down together. The authorization is what says the move was
    earned rather than assumed: it names both pairs, the rewrite that produced
    the second, and the publication it was made against, which is what lets
    the receipt spend exactly this permission and a rollback drop exactly it.

    And the DEBT is the second, because the account of what the branch carries
    and the account of where it has still to go may not be split across two
    writes. A rewrite has already replaced the branch's commits with one by
    the time this runs, so a process dying between a record that explains that
    commit and a debt naming the push it is owed comes back to a one-commit
    branch, a remote still on the head it replaced, and nothing saying a push
    is outstanding -- and the next squash finds a single commit, takes the
    nothing-to-squash road, and reports success without measuring or pushing
    anything, so reviewer-approved work reaches the merge button neither
    counted nor on the remote. Carried on this write instead, the
    reconciliation ahead of the next handler finds the debt, republishes the
    commit under the lease the rewrite froze, and settles the transfer with
    it. The verdict that follows this call finds the debt already down for the
    same commit and leaves it exactly as it is.

    Ahead of the push rather than behind it, for the reason every other record
    this gate writes goes down before the effect it is about: a process dying
    in between comes back to an issue that says a push is owed for the commit
    on its branch and what that push is allowed to carry over.

    Answers whether that write landed. A comment GitHub refused records no
    permission, so the caller may not report one either.
    """
    before = dict(gate.state.data)
    log.info(
        "issue=#%d carries the exemption for %s onto %s: the %s rewrite left "
        "the contribution the adjudication accepted (%s) unchanged",
        gate.issue.number, rewrite.from_sha, rewrite.to_sha,
        rewrite.kind, recorded,
    )
    _rewrites.record_rewrite_authorization(gate.state, rewrite, fingerprint)
    _late_verdict_debt._stages_unmeasured_debt(
        gate, rewrite.to_sha, rewrite.lease,
    )
    return _persisted(gate, before)


def _persisted(gate: _late_gate_models._Gate, before: dict) -> bool:
    """Make the staged transfer durable, or put the comment back as it was.

    A write GitHub refuses is a transfer that did not happen, and the one
    thing that must not survive it is the belief that it did. Everything above
    is staged in memory on the pinned state the whole tick shares, so a
    refusal left as it stands would hand every owner behind this one an
    exemption on a commit no comment names -- and the first of them to write
    for its own reasons would make that until-then-imaginary move durable.

    So the payload is put back exactly as it was found and the permit is
    refused: the rewritten commit falls through to the ordinary cumulative
    size gate, which is the same answer every other refusal here gives, and
    the tick carries on rather than ending in an exception the gate never
    returned from and the caller could not roll its rewrite back for.

    Restored by content rather than by re-reading GitHub, because the read
    that would supply one is the request that just failed -- and because what
    this owes is exactly the payload the call started from, which it holds.

    A payload the staging did not change is already durable and spends no
    request: that is what a recovery re-asking the permit over the record the
    grant left arrives at, and a write there would cost a request to say what
    the comment already says.
    """
    if gate.state.data == before:
        return True
    try:
        gate.gh.write_pinned_state(gate.issue, gate.state)
    except Exception:
        log.warning(
            "issue=#%d could not record the transfer it granted onto %s; "
            "leaving the exemption where the adjudication put it and "
            "measuring the rewrite as a fresh candidate",
            gate.issue.number, gate.state.get(_exemption_reading.LATE_EXEMPT_SHA),
            exc_info=True,
        )
        gate.state.data.clear()
        gate.state.data.update(before)
        return False
    return True


def _abandoned_authorization(gate: _late_gate_models._Gate, restored: str) -> bool:
    """Drop the permission a rolled-back rewrite will never spend.

    A force-push the remote refuses is followed by a reset onto the head the
    rewrite found the branch on, so the object the permission was granted FOR
    is on no branch any more -- only the reflog still has it. The exemption
    itself needs no repair, because the grant never moved it: it is the commit
    a human ruled on and has been the whole time. What is left over is the
    permission, and it names a rewritten commit nothing will ever push.

    Left standing it is a claim about this issue's exemption that no later
    write spends and no reader can act on -- and the next rewrite would be
    deciding whether to replace a record describing a push that never
    happened. So it goes with the commit it was about.

    Only an `authorized` record is dropped, and only one this reader can vouch
    for entirely. A `published` one describes a transfer the pull request
    already carries and the exemption has already moved for; a record missing
    or damaged in any field describes a permission nobody can check, and
    dropping it would throw away the only account of how the exemption came to
    name what it names.

    Answers whether it changed anything, so the caller writes the pinned
    comment exactly when there is something in it to make durable.
    """
    authorization = _rewrite_reading.read_rewrite_authorization(gate.state)
    if authorization is None or not _put_back(authorization.rewrite, restored):
        return False
    if authorization.phase != _rewrite_values.LateRewritePhase.AUTHORIZED:
        return False
    _rewrites.clear_rewrite_authorization(gate.state)
    log.info(
        "issue=#%d dropped the permission a refused rewrite held to carry its "
        "exemption onto %s, which its branch was reset off",
        gate.issue.number, authorization.rewrite.to_sha,
    )
    return True


def _put_back(rewrite: _rewrite_values.LateRewrite, restored: str) -> bool:
    """Whether this reset landed where the rewrite found the branch.

    Two ends of the record answer it, because which of them the branch was
    standing on beforehand is a fact about the REWRITE rather than about the
    exemption. A squash collapses the accepted commit itself, so the head it
    replaced is the commit the contribution came from. A refresh-time base
    rebase replays whatever the branch had and reads the pre-rebase anchor for
    itself, so what a reset goes back to there is the head the force-push was
    leased against -- which is the accepted commit only while the branch was
    standing exactly on it, and the equality of the two contributions never
    claimed that it was.

    Held to the record's own ends rather than to "anywhere but the rewritten
    commit", which is the fail-closed rule every other reader of this group
    follows: a reset nothing here can tie to the permission in front of it is
    not this rewrite's rollback, and the group is the only account there is of
    how the exemption came to name what it names.
    """
    return restored in (rewrite.from_sha, rewrite.lease)
