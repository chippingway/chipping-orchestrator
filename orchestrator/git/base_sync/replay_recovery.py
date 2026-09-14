# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Coordinate the dormant vouched-replay recovery in its required decision order.

No production selector enters this route. It checks label and unmoved-head
cleanup before comparison, recognizes a published head before considering a
retry, and refuses foreign publication, prior announcement, rollback, damaged
transfer, and unclaimed checkout in that order. Only then may recorded or
transfer-vouched replay evidence authorize the shared recovery push; counts
remain the fallback for a head neither form of evidence describes.
"""
from __future__ import annotations

from orchestrator.git.base_sync import (
    outcomes,
    recovery_push as _recovery_push,
    replay_cleanup as _replay_cleanup,
    replay_evidence as _replay_evidence,
    replay_refusals as _replay_refusals,
    snapshot,
    transfer_values as _transfer_values,
    transfers,
)
from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
)
from orchestrator.git.base_sync.state import _PR_REFRESH_DETOUR_LABELS


def _recover_vouched_replay_context(
    context: _AutoRebaseRecoveryContext,
) -> bool:
    """Route an interrupted auto-rebase on the record it left -- DORMANT.

    The three steps of ordinary recovery, in the same order, each answered by
    what the attempt and its transfer left rather than by the label, HEAD, and
    the counts alone: an ineligible label keeps any record a clear would
    strand, an unmoved HEAD is the shortcut only for an attempt that never
    started, and a checkout the pull request is not standing on is classified
    off the pair of SHAs the attempt recorded and how far the transfer beside
    them got.

    No production selector calls this. The refresh enters `recovery` and
    nothing else, so this road, the permit-only push behind it, and every park
    it adds are reached by their own tests alone, and wait for the change that
    selects them. `context.pending_rewrite` is read here and nowhere on the
    running route, which is why the caller has to supply it.
    """
    if context.label not in _PR_REFRESH_DETOUR_LABELS:
        return _replay_cleanup._answers_an_ineligible_label(context)

    recovery_snapshot = snapshot._fetch_recovery_snapshot(context)
    if recovery_snapshot is None:
        return True
    if (
        recovery_snapshot.local_head
        and recovery_snapshot.local_head == context.pending_pre_rebase_sha
    ):
        return _replay_cleanup._finish_an_unmoved_head(context, recovery_snapshot)

    return _route_vouched_snapshot(context, recovery_snapshot)


def _route_vouched_snapshot(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Route a changed-head recovery on the record and the compare together.

    Two classifications rather than one, taken together because the answer is
    the pair. Where the REMOTE stands says which effect the dead tick got as
    far as -- still on the anchor and the push never went out, on the rewrite
    and it did, anywhere else and somebody moved the branch out of band. What
    the pinned comment CARRIES says which of the transfer's own writes it got
    as far as, and that is what the road with something left to publish is
    handed: the evidence a permit is decided on. It costs no git and no
    request, so the road that has nothing left to publish pays nothing for a
    question it does not ask.

    The unpublished road is answered by exact SHAs rather than by the
    ahead/behind counts, and for the interrupted rebase that is the whole
    difference between finishing and parking. A rebase REPLAYS the branch: the
    commit the pull request still carries is on no local history afterwards,
    so git counts the branch as behind its own publication -- ahead by the
    replay and the base it moved onto, behind by the object it replaced. Read
    off those counts, the canonical pre-push recovery is indistinguishable
    from a remote somebody else pushed to, and the tick that only ever needed
    to reissue its push parks instead. What tells them apart is the pair of
    heads the attempt itself recorded: the anchor the remote must still be
    standing on, and the replay the checkout must still be.
    """
    completed = snapshot._complete_recovery_snapshot(
        context, recovery_snapshot,
    )
    if completed is None:
        return True
    if completed.local_head and completed.local_head == completed.remote_head:
        return outcomes._finalize_already_published_recovery(
            context, completed,
        )
    return _route_an_unpublished_head(
        context, completed, transfers._carried_by(context, completed.head),
    )


def _route_an_unpublished_head(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    carried: _transfer_values._Handoff,
) -> bool:
    """Route a checkout the pull request is not standing on.

    What survives every refusal beside this is the retry the anchor exists
    for -- reached on the pair of heads the attempt recorded, or, for a remote
    neither of them accounts for, on the counts over an attempt that recorded
    nothing at all.
    """
    refused = _replay_refusals._refused_before_the_retry(context, completed, carried)
    if refused is not None:
        return refused
    in_flight = _replay_evidence._is_an_attempt_in_flight(context, completed, carried)
    if in_flight or _replay_evidence._is_this_attempts_rewrite(context, completed):
        return _recovery_push._retry_recovery_push(
            context, completed, carried, permit_alone=in_flight,
        )
    return _route_a_moved_remote(context, completed, carried)


def _route_a_moved_remote(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    carried: _transfer_values._Handoff,
) -> bool:
    """Route a remote neither SHA this recovery holds accounts for.

    Reached once the pull request is proved to be standing on neither the
    rewrite this branch carries nor the anchor the rebase pinned before git
    ran, so whatever is on it arrived from somewhere else. The counts are what
    is left to tell those apart, and they answer the question they were always
    about: a pair of zeros over two heads that disagree is a reading that did
    not happen, a remote with commits of its own is one a force-push would
    drop, and a strictly-ahead branch is a lease this recovery may still try
    -- the push is pinned to the anchor, so a remote that is not on it refuses
    the request rather than being overwritten.
    """
    if completed.ahead == 0 and completed.behind == 0:
        return outcomes._reject_unknown_recovery_comparison(context, completed)
    if completed.behind > 0:
        return outcomes._park_diverged_recovery(context, completed)
    return _recovery_push._retry_recovery_push(context, completed, carried)
