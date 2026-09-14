# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Determine the exemption handoff left by a clean rebase or interrupted transfer.

A permission must name this attempt before its phase can classify the
handoff. Damaged or stranded claims remain unvouched, and a published
rotation must still agree with the issue's current exemption.
"""
from __future__ import annotations

from dataclasses import replace as _replace

from orchestrator.git.base_sync import (
    transfer_attempts as _transfer_attempts,
    transfer_publication as _transfer_publication,
    transfer_values as _transfer_values,
)
from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
)
from orchestrator.github.pinned_state import PinnedState
from orchestrator.git.base_sync.state import log


def _carried_by(
    context: _AutoRebaseRecoveryContext, local_head: str,
) -> _transfer_values._Handoff:
    """How far the transfer this interrupted rebase was making got.

    Read off the pinned comment alone, and asked before any of the recovery's
    own effects, because it is what decides which of them the tick owes: a
    permission still outstanding is a receipt that has to be landed, one
    already spent is a route that only has to be finished, and a rewrite the
    grant never reached is evidence that has to be assembled afresh.

    Asked of the PERMISSION rather than of the commit the exemption names, for
    the reason every other reader of this record is: the grant writes the
    permission and the debt in one write for one commit, so a group whose
    target somebody edited would otherwise be invisible here and the caller
    would carry on as though no transfer had ever been in flight.

    Asked of the EXEMPTION first, before any permission standing beside it is
    believed. A permission is a claim about moving one verdict, and what says
    which verdict is the exemption and the identity under it -- so a group
    something damaged after the grant went down leaves a permission that still
    reads back whole over a verdict nothing can name. Believed there, the
    settlement re-asks a permit whose accepted contribution cannot be
    fingerprinted, the ordinary gate measures the replay instead, and a change
    a human already ruled on is published and announced as though it had been.

    Asked by PRESENCE where the record has to be absent for the answer to be
    `NOTHING`, which is the difference between an issue that never earned a
    verdict and one whose record something damaged. The fail-closed readers
    answer both with a bare None -- rightly, since the gate's only move is to
    measure -- and a caller that took that for "no verdict in flight" would
    finish a route over an exemption still naming the commit a human ruled on.
    So a comment claiming an exemption it cannot show whole is `UNVOUCHED`,
    and only a comment claiming none at all is `NOTHING`.

    The settlement PROOF is asked the same way and for the same reason. It is
    written by the statement that settles a transfer and dropped by the write
    behind the record it feeds, so one standing beside a phase, a reading, or
    an authorization this build cannot account for is a checkpoint saying two
    things at once. It is invisible to the readers above -- they answer for
    the permission, not for what was reported about it -- and the road it
    would let through clears the anchor and files no record of the move.

    Costs no git and no request. Every answer is a field this issue already
    carries, which is what lets the ordinary recovery -- the overwhelming
    majority, on issues that never earned an exemption -- pay nothing for a
    question that is not about it.
    """
    # Lazy for the reason every upward reach in this package is: the record
    # sits in the workflow layer above it.
    from orchestrator.workflow.late_split import (
        exemption_reading as _exemption_reading,
        rewrite_reading as _rewrite_reading,
    )
    if _exemption_reading.unreadable_exemption(context.state) or (
        _rewrite_reading.stranded_transfer_proof(context.state)
    ):
        return _transfer_values._Handoff.UNVOUCHED
    standing = _standing_permission(context, local_head)
    if standing is not None:
        return standing
    if _foreign_debt(context, local_head):
        return _transfer_values._Handoff.UNVOUCHED
    if _exemption_reading.read_exemption(context.state) is None:
        return _transfer_values._Handoff.NOTHING
    return _transfer_values._Handoff.UNRECORDED


def _standing_permission(
    context: _AutoRebaseRecoveryContext, local_head: str,
) -> _transfer_values._Handoff | None:
    """What a permission already on the comment says about this head, or None.

    None where the comment carries no claim this recovery has to answer for,
    and a transfer that is OVER is the larger half of that. A settled record
    is never cleared, so it outlives the attempt that earned it: the exemption
    it moved is on the rewritten commit, the pull request is standing on that
    commit, and the next base advance anchors its own rebase to exactly that
    head. A settled record whose `to_sha` IS this attempt's anchor is
    therefore the previous rotation's history rather than a claim about this
    one -- and read as a claim it would be bound by a lease belonging to that
    earlier attempt, come back as a group nobody can vouch for, and park an
    attempt that has not started. So it is passed over, and the evidence for
    THIS replay is assembled afresh like any other. A settled record naming
    any other commit is passed over for the plainer reason that the head in
    hand is not the one it is about.

    A group the EXEMPTION has moved past is passed over one step earlier, and
    it is asked exactly as the grant asks it. The end a record's phase binds
    is held to the commit this issue exempts, so a later adjudication accepting
    fresh work leaves the whole group describing a commit nothing exempts --
    which the fail-closed reader answers with a bare None, indistinguishable
    from the damaged record it is not. Read as damage, one settled rotation
    would park every rebase this issue could ever earn again, since nothing
    clears that group but the next grant. `claims_the_exemption` is what tells
    the two apart, and a record it calls stale is history rather than a claim,
    on the same terms the writer replaces it under.

    Everything else is a claim, and a claim is believed only where every field
    of it agrees with the attempt this recovery is finishing. A group this
    build cannot read back whole, one still outstanding for some other commit,
    one whose DEBT does not agree with it, and one whose lease, contribution,
    or publication belongs to some other attempt -- including one the attempt's
    own replay record contradicts -- are all refused rather than replaced: the
    group is the only account there is of how the exemption came to name what
    it names, and a caller that acted on one it could not tie to the attempt in
    front of it would be finishing somebody else's work.
    """
    # Lazy for the reason every upward reach in this package is: the record
    # sits in the workflow layer above it.
    from orchestrator.workflow.late_split import (
        rewrite_reading as _rewrite_reading,
    )
    if not _rewrite_reading.claims_the_exemption(context.state):
        return None
    authorization = _rewrite_reading.read_rewrite_authorization(context.state)
    if authorization is None:
        return _transfer_values._Handoff.UNVOUCHED
    settled = _transfer_values._is_settled(authorization)
    rewrite = authorization.rewrite
    if settled and rewrite.to_sha == context.pending_pre_rebase_sha:
        return None
    if rewrite.to_sha != local_head:
        return None if settled else _transfer_values._Handoff.UNVOUCHED
    return _claimed_by_this_attempt(context, authorization, local_head)


def _claimed_by_this_attempt(context, authorization, local_head) -> _transfer_values._Handoff:
    """What a whole permission for the head in hand is, once it is bound.

    Whole and about this commit is where the fail-closed reader stops; which
    ATTEMPT it belongs to is what the two questions here add, and both have to
    be answered before a caller acts on it.
    """
    if not _transfer_attempts._made_by_this_attempt(context, authorization, local_head):
        return _transfer_values._Handoff.UNVOUCHED
    if _transfer_values._is_settled(authorization):
        return _transfer_values._Handoff.SETTLED
    return _transfer_publication._outstanding_or_unvouched(context.state, authorization.rewrite)


def _rotated_onto(state: PinnedState, local_head: str) -> bool:
    """Whether the record now says the verdict is on this commit.

    The one answer a settlement cannot take on trust from the call that made
    it. A permit granted before the gate is re-asked inside it, so anything
    that moved in between leaves the push landed and the verdict where it was
    -- and a landed push with no rotation behind it is a route a recovery may
    not finish, since finishing drops the anchor that would bring it back.

    Read as the whole record rather than as the phase alone, like every other
    reader of this group: a permission announcing itself published over fields
    nothing here understands has not been shown to have moved anything.
    """
    # Lazy for the reason every upward reach in this package is: the record
    # sits in the workflow layer above it.
    from orchestrator.workflow.late_split import (
        exemption_reading as _exemption_reading,
        rewrite_reading as _rewrite_reading,
        rewrite_values as _rewrite_values,
    )
    authorization = _rewrite_reading.read_rewrite_authorization(state)
    if authorization is None:
        return False
    if authorization.phase != _rewrite_values.LateRewritePhase.PUBLISHED:
        return False
    if authorization.rewrite.to_sha != local_head:
        return False
    return _exemption_reading.is_exempt(state, local_head)


def _foreign_debt(
    context: _AutoRebaseRecoveryContext, local_head: str,
) -> bool:
    """Whether a debt with no permission beside it is somebody else's.

    Asked only once no permission stands, because a permission and its debt
    are one grant and the reader above already holds each to the other. What
    is left is the debt on its own, and it has one honest shape: the approval
    the ordinary gate records for THIS replay before its push -- the commit on
    this checkout, leased to this attempt's anchor, and readable whole. That
    is exactly the record the refresh's freeze sets aside for its own
    interrupted work, which is why an approval leased to the anchor reaches a
    recovery at all.

    Anything else that reaches one is a claim the freeze let through on its
    lease alone. A debt naming another commit says a push is owed for work
    this checkout is not, and one whose basis or lease cannot be read cannot
    say what it is. Read as no transfer, the replay is measured and
    force-pushed and the gate's own write replaces that debt with one of its
    own -- overwriting the only account of the push it recorded.
    """
    # Lazy for the reason every upward reach in this package is: the debt
    # sits in the workflow layer above it.
    from orchestrator.workflow.stages.implementing import late_parks
    if late_parks._unreadable_approval(context.state):
        return True
    owed = late_parks._approved_commit(context.state)
    if not owed:
        return False
    if owed != local_head:
        return True
    return late_parks._approved_lease(context.state) != (
        context.pending_pre_rebase_sha
    )


def _permits_the_publication(
    context: _AutoRebaseRecoveryContext, local_head: str, rewrite=None,
) -> bool:
    """Whether the permit still licenses this recovery to publish.

    Asked BEFORE the gated publication rather than through it, and that is
    the whole of what makes this road safe. The gate's answer to a permit
    that declines is the ordinary cumulative reading, which is right for a
    rebase deciding whether to publish and wrong on a recovery twice over: a
    count under the ceiling reports a publication landed with the verdict
    still on the commit a human ruled on, and a count over it routes an
    adjudicated change into a second adjudication with a pull request already
    open over the work. There is nothing on this road to decide -- the push
    the interrupted tick never made is already leased -- so the only question
    is whether the permission may be spent, and a refusal is a refusal. The
    gate is told the same thing on the way in, so a permit that stops holding
    between this ask and its own is refused there rather than measured.

    Asked over the evidence this recovery holds: the record the grant left,
    where there is one, and otherwise the rewrite re-derived for a grant the
    crash came before -- which is what `late_transfer` reads when a caller
    hands in no rewrite of its own. Every term is re-derived there: the
    publication this call freezes, the one the issue records, the checkout,
    the lease as an object this host holds, the issue read afresh, and both
    contributions fingerprinted from the objects themselves. A grant
    re-writes nothing, since the payload it would stage is the one already on
    the comment.

    The entry is frozen here for the same reason the permit needs one at all:
    it is the pull request read this tick, before any effect, and the terms
    the record claims are checked against it rather than against themselves.
    """
    # Lazy for the reason every upward reach in this package is: the permit
    # and the entry it is asked over sit in the workflow layer above it.
    from orchestrator.workflow.stages.implementing import (
        late_overflow as _overflow,
        late_records as _records,
        late_transfer as _transfer,
    )
    gate = _records._gate(
        context.gh, context.spec, context.issue, context.state,
        context.worktree,
    )
    entered = _records._Entered(
        head=context.pending_pre_rebase_sha or "",
        reconciling=True,
        candidate=local_head,
    )
    entry = _overflow._frozen_entry(gate, entered)
    if not entry.is_frozen:
        log.warning(
            "issue=#%d auto-rebase recovery cannot enter the publication its "
            "interrupted rewrite was made against (%s); the transfer it owes "
            "is left standing",
            context.issue.number, entry.refusal,
        )
        return False
    gate = _replace(
        gate, entry=entry, candidate=local_head, reconciling=True,
        rewrite=rewrite,
    )
    return bool(_transfer._carried_over(gate, local_head))


def _left_mid_transfer(state: PinnedState) -> bool:
    """Whether a permission on this comment still says a push is owed.

    Asked where a recovery is about to walk away from an attempt rather than
    finish it, and asked of the record alone: no fetch, no checkout, no
    comparison -- none of which the caller is on a road to make. What it needs
    to know is only whether walking away would leave a human's verdict
    licensed onto a commit no push carried, with the approval debt granted
    beside it still standing.

    Fail-closed in the same direction every reader of this record is. A group
    this build cannot read back whole answers yes, because "not shown to be
    over" is the only reading available to a caller deciding whether it is
    safe to forget one -- and so does any group beside an exemption the
    comment claims and cannot show, since nothing can then say which verdict
    the group is about.

    A group the EXEMPTION has moved past is the one exception, passed over
    exactly as `_standing_permission` passes it over. A settled rotation is
    never cleared, so a later adjudication accepting fresh work leaves it
    describing a commit nothing exempts -- which the fail-closed reader
    answers with the same bare None a damaged group gets. Read as owed, that
    history would hold every attempt this issue makes under a relabel, however
    untouched, in a park nothing it did could release.
    """
    # Lazy for the reason every upward reach in this package is: the record
    # sits in the workflow layer above it.
    from orchestrator.workflow.late_split import (
        exemption_reading as _exemption_reading,
        rewrite_reading as _rewrite_reading,
    )
    if not _rewrite_reading.carries_rewrite_authorization(state):
        return False
    if _exemption_reading.unreadable_exemption(state):
        return True
    if not _rewrite_reading.claims_the_exemption(state):
        return False
    return _rewrite_reading.outstanding_permission(state)
