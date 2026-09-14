# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Finish an interrupted rebase whose push the pull request already carries.

The post-publication half of the vouched-replay recovery, and dormant: the
coordinator in `replay_recovery` still finalizes a published head directly,
and nothing in production enters this route until the activation reaches it.

A landed rewrite is finished once and only where the pinned comment accounts
for it. A foreign publication, a mark naming another head, a head nothing this
attempt wrote vouches for, a checkout that is not provably clean beneath a
verdict, and a transfer the receipt and debt do not account for all park with
HEAD and the anchor where they stand -- the remote already carries the head,
so there is nothing to reset onto. What survives is one of three finishes,
chosen by the record: an announced route owes only its route and its write, an
outstanding permission owes the leased no-op `landed_settlement` makes, and
everything else owes the ordinary finish.
"""
from __future__ import annotations

from orchestrator.git.base_sync import (
    attempts,
    landed_settlement as _landed_settlement,
    outcomes,
    persistence,
    replay_evidence as _replay_evidence,
    replay_publication_parks as _replay_publication_parks,
    replay_transfer_parks as _replay_transfer_parks,
    transfer_publication as _transfer_publication,
)
from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
)
from orchestrator.git.base_sync.transfer_values import _Handoff
from orchestrator.git.verification import status as _worktree_status

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

# The handoffs whose own permission ties a landed head to this attempt where
# the attempt record never got to name it. Neither is called what it is until
# its lease, its commit, and its publication are this attempt's own.
_BOUND_BY_THEIR_PERMISSION = frozenset((_Handoff.OUTSTANDING, _Handoff.SETTLED))


def _finish_published_recovery(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    carried: _Handoff,
) -> bool:
    """Finish the route behind a rewrite the pull request already carries.

    The push landed before the crash, so nothing is measured, no agent runs,
    and nothing is force-rewritten: what the dead tick still owed is some tail
    of its settlement and its finish. Every refusal is asked before any of
    that, because every finish drops the anchor -- the only thing that brings
    this route back to a publication it could not account for.
    """
    if _replay_evidence._made_for_another_publication(context, completed):
        return _replay_publication_parks._park_foreign_publication_recovery(
            context, completed,
        )
    refusal = _unfinishable(context, completed.head, carried)
    if refusal:
        return _replay_transfer_parks._park_unfinished_recovery(
            context, completed, refusal,
        )
    return _finishes_the_landed_route(context, completed, carried)


def _unfinishable(
    context: _AutoRebaseRecoveryContext, landed: str, carried: _Handoff,
) -> str:
    """Why the landed route may not be finished on this tick, or "".

    The mark first, since it is about the finish itself: one naming another
    head cannot say whether the notice and the audit event are already out.
    Then whether the landing is this attempt's at all -- the pull request and
    the checkout agreeing proves only that they agree, and somebody who moved
    both leaves exactly that. Then the tree, under a verdict only: a finish
    hands the issue to a reviewer, and a verdict riding a commit beside loose
    work is not one anybody can say describes what is under review. A tree
    that could not be read is not a clean one. And last whether the record
    accounts for what landed.
    """
    if attempts._foreign_mark(context.state, landed):
        return _FOREIGN_MARK
    if not _vouched_landing(context, landed, carried):
        return _UNPROVEN_LANDING.format(published=landed or "an unreadable head")
    if carried != _Handoff.NOTHING and not _worktree_status._worktree_status(context.worktree).is_clean:
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


def _finishes_the_landed_route(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    carried: _Handoff,
) -> bool:
    """Take the last step a landed rewrite is still owed, exactly once.

    A settled transfer whose record never reached the sinks is reported first:
    its proof is the one fact no later reading could re-derive, and the report
    drops it durably, so no later poll reports the same move again. Then the
    record picks the finish. A mark naming this head owes only the route and
    the write, since the notice and the `base_rebased` event already went out
    ahead of it. An outstanding permission owes the receipt the leased no-op
    buys. Everything else owes the ordinary finish.
    """
    _reports_a_lost_settlement(context)
    if attempts._already_announced(context.state, completed.head):
        return persistence._write_the_finished_route(context, completed.head)
    if carried == _Handoff.OUTSTANDING:
        return _landed_settlement._settle_published_recovery(context, completed)
    return outcomes._finalize_already_published_recovery(context, completed)


def _reports_a_lost_settlement(context: _AutoRebaseRecoveryContext) -> None:
    """Make the record a settled transfer never got to report, where one is owed."""
    # Lazy for the reason every upward reach in this package is: the record
    # and the sinks it goes to sit in the workflow layer above it.
    from orchestrator.workflow.stages.implementing import (
        late_records as _records,
        late_transfer_telemetry as _transfer_telemetry,
    )
    _transfer_telemetry._reports_a_settled_transfer(_records._gate(
        context.gh, context.spec, context.issue, context.state,
        context.worktree,
    ))
