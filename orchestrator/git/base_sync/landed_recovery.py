# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Why a rewrite the pull request already carries may not be finished.

The git half of the recovery of a push an interrupted tick landed: the
workflow's road for it (`workflow/engine/rewrite_landed.py`) asks here, over
the head the recovery's fetch found the remote and the checkout agreeing on,
whether the pinned comment accounts for that landing at all. A mark naming
another head, a head nothing this attempt wrote vouches for, a checkout that
is not provably clean beneath a verdict, and a transfer the receipt and debt
do not account for are each a reason, worded for the operator the park that
holds HEAD and the anchor where they stand is addressed to -- the remote
already carries the head, so there is nothing to reset onto. So are the two
ways the leased no-op that settles an outstanding permission can fail to.

Readings and reasons only. Nothing here parks, pushes, announces, routes, or
writes, and nothing reaches the workflow layer above: the parks are
`replay_transfer_parks`', and the finish of a landing that survives every
reason is the workflow's own.
"""
from __future__ import annotations

from orchestrator.git.base_sync import (
    attempts,
    transfer_publication as _transfer_publication,
)
from orchestrator.git.base_sync.models import _AutoRebaseRecoveryContext
from orchestrator.git.base_sync.transfer_values import _Handoff
from orchestrator.git.verification.status import _WorktreeStatus

# Why a landed rewrite's route could not be finished, in the operator's own
# terms: each is the detail the unfinished-route park names.
_FOREIGN_MARK = (
    "a finish on this attempt recorded that it had already announced some "
    "other commit, so whether this one was announced cannot be told from the "
    "comment"
)

_UNPROVEN_LANDING = (
    "the pull request and the checkout agree on `{published}` and nothing "
    "this attempt recorded names it, so the publication in front of this tick "
    "is not one it can show it made"
)

_LOOSE_TREE = (
    "the worktree is not provably clean, so the commit the verdict rides is "
    "not the checkout a reviewer would be sent to"
)

_ANNOUNCED_UNSETTLED = (
    "a finish recorded announcing this publication while the permission "
    "granted for it is still outstanding, so the write that settled it did "
    "not land whole"
)

# Why the receipt an outstanding permission owes could not be taken.
_REFUSED_PERMIT = (
    "the permit that would license the settlement refused this tick -- the "
    "pull request, the stage, the checkout, the lease, or the two "
    "contributions no longer agree with the permission on the comment, and "
    "the orchestrator log names which"
)

_REFUSED_NO_OP = (
    "the `--force-with-lease` no-op that would have receipted it, leased "
    "against that same commit, did not land -- the remote branch moved after "
    "this tick read it"
)

# The handoffs whose own permission ties a landed head to this attempt where
# the attempt record never got to name it. Neither is called what it is until
# its lease, its commit, and its publication are this attempt's own.
_BOUND_BY_THEIR_PERMISSION = frozenset((_Handoff.OUTSTANDING, _Handoff.SETTLED))


def _unfinishable(
    context: _AutoRebaseRecoveryContext,
    landed: str,
    carried: _Handoff,
    status: _WorktreeStatus,
) -> str:
    """Why the landed route may not be finished on this tick, or "".

    The mark first, since it is about the finish itself: one naming another
    head cannot say whether the notice and the audit event are already out.
    Then whether the landing is this attempt's at all -- the pull request and
    the checkout agreeing proves only that they agree, and somebody who moved
    both leaves exactly that. Then the tree, under a verdict only: a finish
    hands the issue to a reviewer, and a verdict riding a commit beside loose
    work is not one anybody can say describes what is under review. `status`
    is the checkout's own reading, and one that could not be taken is not a
    clean one. And last whether the record accounts for what landed.
    """
    if attempts._foreign_mark(context.state, landed):
        return _FOREIGN_MARK
    if not _vouched_landing(context, landed, carried):
        return _UNPROVEN_LANDING.format(published=landed or "an unreadable head")
    if carried != _Handoff.NOTHING and not status.is_clean:
        return _LOOSE_TREE
    return _unaccounted(context, landed, carried)


def _vouched_landing(
    context: _AutoRebaseRecoveryContext, landed: str, carried: _Handoff,
) -> bool:
    """Whether something this attempt wrote says the landed head is its own.

    The attempt's record of its replay is the ordinary answer. The one window
    it cannot name is the replay the permit alone published, where the terms
    stand with no head: there the permission that push was licensed by is the
    voucher, since it is bound to the anchor, the terms, and the adjudicated
    pair before it is read as outstanding or settled. A comment carrying no
    record of the attempt vouches for nothing.
    """
    recorded = context.pending_rewrite
    if recorded.names(landed):
        return True
    in_flight = recorded.is_declared and not recorded.sha
    return in_flight and carried in _BOUND_BY_THEIR_PERMISSION


def _unaccounted(
    context: _AutoRebaseRecoveryContext, landed: str, carried: _Handoff,
) -> str:
    """Why the record does not account for this landing, or "".

    An outstanding permission owes its account rather than having to show one:
    the receipt, the paid debt, and the rotation are what the leased no-op
    writes. A finish announces only a settled landing, though, so a mark beside
    a permission still outstanding is a settlement that did not land whole.
    """
    if carried != _Handoff.OUTSTANDING:
        return _transfer_publication._unaccounted_publication(
            context, landed, carried,
        )
    if attempts._carries_an_announcement(context.state):
        return _ANNOUNCED_UNSETTLED
    return ""
