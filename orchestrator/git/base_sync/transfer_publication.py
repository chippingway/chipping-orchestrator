# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Read transfer debt and publication receipts before accepting a recovered rebase.

An unreadable approval or missing whole receipt cannot prove settlement.
The receipt must name the attempt's pre-rebase head and pull request; all
workflow record imports remain deferred to the reads that require them.
"""
from __future__ import annotations

from orchestrator.git.base_sync import (
    transfer_values as _transfer_values,
)
from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
)
from orchestrator.github.pinned_state import PinnedState

# The two handoffs a landed rewrite can be ACCOUNTED for under: the transfer
# finished, or none was ever granted and the ordinary gate published it. Both
# leave a receipt naming the commit, which is what the accounting is read off.
_ACCOUNTABLE = frozenset((_transfer_values._Handoff.SETTLED, _transfer_values._Handoff.UNRECORDED))


# Why a rewrite the pull request already carries is one the pinned comment
# cannot account for. Each is worded for the operator who has to reconcile it,
# because what they all end in is a park nobody but a human clears.
_UNREADABLE_CLAIM = (
    "a transfer record this build cannot read whole is standing over the "
    "commit this issue exempts"
)

_UNSETTLED_CLAIM = "the transfer standing here is `{handoff}` rather than over"

_UNRECEIPTED = (
    "no whole receipt on the pinned comment records `{published}` as pushed "
    "from `{anchor}` onto PR #{publication}, so whether the verdict this "
    "rebase was carrying ever moved cannot be said"
)

_UNPAID = (
    "a push is still recorded as owed for `{owed}`, so the write that should "
    "have settled this publication did not land whole"
)

_DAMAGED_DEBT = (
    "an approval standing over this publication cannot be read whole, so "
    "whether a push is still owed for it cannot be said"
)


def _outstanding_or_unvouched(state: PinnedState, rewrite) -> _transfer_values._Handoff:
    """A permission for the head in hand, held to the debt written with it.

    The grant is ONE write of two records for one commit: the permission that
    says what a push may carry a human's verdict over, and the debt that says
    the push is owed and what it is pinned to. They are written together
    precisely so a reader can hold each to the other, and this is that reader.

    A permission standing beside a debt that names another commit, another
    lease, or nothing at all is a comment something took apart. Read as
    outstanding, the settlement re-asks the permit -- and a permit that grants
    RE-WRITES both records, so the missing half would be reconstructed from
    the very claim nobody could check and the push would go out under it. So
    the pair is asked before the handoff is called outstanding, and a
    disagreement is the refusal every other unvouchable record here gets.

    Read through the same fail-closed readers the debt's own owner uses: a
    hand-edited value is no approval, which is exactly the disagreement this
    is looking for. Those readers answer for two of the group's three members,
    so the third is asked by PRESENCE beside them: a debt claiming a basis
    this build cannot name is a group something took apart, and read as the
    two members that happen to agree it would license the permit-only push
    over a record nobody can show whole.
    """
    # Lazy for the reason every upward reach in this package is: the debt
    # sits in the workflow layer above it.
    from orchestrator.workflow.stages.implementing import late_approval_reading as _late_approval_reading
    if _late_approval_reading._unreadable_approval(state):
        return _transfer_values._Handoff.UNVOUCHED
    owed = _late_approval_reading._approved_commit(state) == rewrite.to_sha
    if owed and _late_approval_reading._approved_lease(state) == rewrite.lease:
        return _transfer_values._Handoff.OUTSTANDING
    return _transfer_values._Handoff.UNVOUCHED


def _unaccounted_publication(
    context: _AutoRebaseRecoveryContext, local_head: str, carried: _transfer_values._Handoff,
) -> str:
    """Why a rewrite the pull request already carries is unexplained, or "".

    Asked of the road that has nothing left to publish and only a route to
    finish, and it is what decides whether finishing is safe. That route
    clears the recovery anchor, resets the review round, and hands the issue
    to the reviewer -- which on an issue carrying no verdict is exactly right
    and costs nothing, since there is no transfer for a missing record to
    strand.

    On an issue that WAS carrying one it is the opposite. The anchor is the
    only thing that brings this recovery back, so clearing it over an
    exemption still on the old commit, a debt nothing paid, or a receipt
    nobody wrote leaves the next tick to measure the rewrite as a fresh
    candidate -- past the same ceiling, and back into adjudication with the
    pull request already carrying the work. So those states park with the
    anchor left pinned instead, and a human settles what is on the comment.

    Two handoffs can be accounted for, and both by the same record: a transfer
    that FINISHED wrote the receipt in the same statement as the rotation, and
    a rewrite no permit ever licensed was published by the ordinary cumulative
    gate, which wrote one too. That receipt is read WHOLE -- the commit it
    names, the head it was pinned to, and the publication it went onto, held
    against this recovery's own anchor and pull request -- because a receipt
    is never cleared and on its own goes on naming a commit this stage pushed
    rounds ago, vouching for any pull request somebody rewound onto it. The
    head and the number are what date it to THIS attempt, and the attempt is
    exactly what has to be accounted for. The debt beside it is asked as well,
    through the reader below, since the two go down in one write and either
    one standing without the other is that write not having landed whole.

    A group nobody can read is refused outright: it is the only account there
    is of how the exemption came to name what it names, and a route finished
    over it would be acting on evidence nothing checked.
    """
    if carried == _transfer_values._Handoff.NOTHING:
        return ""
    if carried not in _ACCOUNTABLE:
        if carried == _transfer_values._Handoff.UNVOUCHED:
            return _UNREADABLE_CLAIM
        return _UNSETTLED_CLAIM.format(handoff=carried)
    if _receipted_publication(context) != local_head:
        return _UNRECEIPTED.format(
            published=local_head,
            anchor=context.pending_pre_rebase_sha,
            publication=context.pr_number,
        )
    return _unsettled_debt(context.state)


def _unsettled_debt(state: PinnedState) -> str:
    """Why the debt beside a receipted publication is unfinished, or "".

    The other half of the write that settles one. A receipt and the drop of
    the approval it pays go down together, so an approval still standing over
    a receipted commit is that write not having landed whole -- and so is a
    group this build cannot read back, which is why the claim is asked by
    PRESENCE. The fail-closed readers answer "nothing owed" for a commit a
    hand edit truncated exactly as they answer for one the drop blanked, and
    read as the second a group standing over a commit nobody can name would
    pass as a debt somebody paid.
    """
    # Lazy for the reason every upward reach in this package is: the debt
    # sits in the workflow layer above it.
    from orchestrator.workflow.stages.implementing import late_approval_reading as _late_approval_reading
    if _late_approval_reading._unreadable_approval(state):
        return _DAMAGED_DEBT
    owed = _late_approval_reading._approved_commit(state)
    return _UNPAID.format(owed=owed) if owed else ""


def _rolled_back_publication(
    context: _AutoRebaseRecoveryContext, local_head: str, carried: _transfer_values._Handoff,
) -> bool:
    """Whether the record says this replay reached a remote no longer on it.

    Asked once the pull request has been proved to be standing somewhere other
    than the commit the checkout carries, and it is the difference between a
    push that never went out and one somebody undid. Two records say the
    replay was there: a transfer that SETTLED, whose write says the exemption
    moved onto a commit the pull request really had, and the whole receipt
    beside it, which says the same thing for a replay no permit ever licensed.

    Either way the pull request has since been rolled back, and the head it
    was rolled back to is the very anchor a retry would lease its force-push
    against. That lease would be satisfied, the push would land, and the
    rollback would be gone -- which is the one outcome a lease exists to
    prevent. So it parks as the externally moved remote it is.

    Silent for every attempt whose push simply never went out, which is the
    ordinary interrupted rebase: nothing records a landing, so nothing here
    claims one.
    """
    if carried == _transfer_values._Handoff.SETTLED:
        return True
    return bool(local_head) and _receipted_publication(context) == local_head


def _receipted_publication(context: _AutoRebaseRecoveryContext) -> str:
    """The commit this attempt's own push is recorded as having landed.

    The receipt asked as the three-term question its owner publishes, with
    both of the terms that date it supplied from the attempt in hand: the
    anchor this recovery pinned, which a rewind cannot produce, and the pull
    request it is finishing, which a replacement opened over the same ref is
    not. Empty is every other receipt on the comment -- an earlier push of
    this issue's, or one this build cannot tie to any publication at all.
    """
    # Lazy for the reason every upward reach in this package is: the receipt
    # sits in the workflow layer above it.
    from orchestrator.workflow.stages.implementing import late_publication_state as _late_publication_state
    return _late_publication_state._publication_from(
        context.state, context.pending_pre_rebase_sha, context.pr_number,
    )


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
    from orchestrator.workflow.stages.implementing import late_approval_reading as _late_approval_reading
    if _late_approval_reading._unreadable_approval(context.state):
        return True
    owed = _late_approval_reading._approved_commit(context.state)
    if not owed:
        return False
    if owed != local_head:
        return True
    return _late_approval_reading._approved_lease(context.state) != (
        context.pending_pre_rebase_sha
    )
