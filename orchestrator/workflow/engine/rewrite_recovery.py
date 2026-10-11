# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The recovery an interrupted automatic PR base rewrite is owed, in the order it has always been asked.

An attempt an earlier tick anchored and never finished is answered before any
new rebase of the branch begins, and the workflow's base-rewrite coordinator
(`base_rewrite`) hands it here (`decides`). What is decided here is the road
and the order; every fact a road is chosen on is a git owner's, and so is
every road that ends the attempt without publishing or finishing anything --
a clear, or a park. Both roads that reach a landing -- a retry, and a push
found already landed -- hand it to the one finish every landing gets
(`rewrite_finish`):

- A label the refresh does not drive is answered first, with a clear or a
  park and nothing fetched (`git/base_sync/replay_cleanup.py`).
- The branch is fetched and the checkout read (`git/base_sync/snapshot.py`).
  A checkout still standing on the anchor is the unstarted attempt's clear,
  which lets this tick's rebase go on, or the rollback's park.
- Before any road a snapshot it read chooses is taken, a verification
  transaction an earlier finish captured for the head it announced is
  abandoned unless the remote and the checkout both read on that head
  (`rewrite_landing_moved`): every other road clears, resets, or parks the
  attempt without taking that transaction's route, and the landing it was
  captured for has moved under it. An abandonment that did not land holds
  the tick instead, with nothing reset, cleared, or parked, so the attempt
  stands for the next tick to abandon it again. A snapshot nobody could take
  ends in the git owner's abort, which resets the checkout onto the anchor and
  clears the attempt; a reset that landed is itself movement, so the
  transaction is abandoned on the state the park writes, in the one write
  that releases the attempt, or neither is written.
- The remote head completes the comparison, and how far the transfer beside
  the attempt got is read off the comment (`git/base_sync/transfers.py`).
- A remote standing on the checkout is a push that already landed, and the
  road that finishes it without pushing again is the workflow's own
  (`rewrite_landed`).
- A remote that is not is a replay nothing published, the road this owner
  answers. It is refused for a foreign publication, a finish already
  announced, a rollback, a transfer nobody can vouch for, and a checkout the
  record disowns, in that order (`git/base_sync/replay_refusals.py`). Past
  those it is retried (`rewrite_retry`) where the record names the checkout
  over a remote still on the anchor, or where the transfer vouches for a
  replay the attempt never got to record. Anything else is read off the
  counts: a pair of zeros over two heads that disagree and a remote with
  commits of its own park, and a strictly-ahead branch is retried under the
  anchor's lease.

Run under the issue writer claim the base refresh (`base_refresh`) takes
before the issue is read and holds through the route; nothing here asks for
one of its own.
"""
from __future__ import annotations

from dataclasses import replace
from functools import partial

from orchestrator.git.base_sync import (
    outcomes as _outcomes,
    recovery as _recovery,
    replay_cleanup as _replay_cleanup,
    replay_evidence as _replay_evidence,
    replay_refusals as _replay_refusals,
    snapshot as _snapshot,
    transfers as _transfers,
)
from orchestrator.git.base_sync.models import (
    _AutoRebaseContext,
    _AutoRebaseDecision,
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
)
from orchestrator.git.base_sync.state import _AWAITING_HUMAN, _PR_REFRESH_DETOUR_LABELS
from orchestrator.git.base_sync.transfer_values import _Handoff
from orchestrator.workflow.engine import (
    rewrite_landed as _rewrite_landed,
    rewrite_landing_moved as _landing_moved,
    rewrite_retry as _rewrite_retry,
)


def decides(
    context: _AutoRebaseContext, consumed_comment_id: int | None,
) -> _AutoRebaseDecision:
    """Run the recovery a pinned anchor is owed, and say whether this tick's rebase may go on.

    A recovery that answered the anchor -- finished it, parked it, or found
    nothing it could verify -- owns the tick. One that let it go on did so
    over a head the base may still be ahead of, and the trusted reply that
    released a park this refresh left goes on with it only while that park
    still stands: a recovery that took the park down spent the reply, and the
    rebase behind it may not spend it again.
    """
    if not context.pending_pre_rebase_sha:
        return _AutoRebaseDecision(True, consumed_comment_id)
    if recovers(_recovery._recovery_context(context, consumed_comment_id)):
        return _AutoRebaseDecision(should_continue=False)
    if not context.state.get(_AWAITING_HUMAN):
        consumed_comment_id = None
    return _AutoRebaseDecision(True, consumed_comment_id)


def recovers(context: _AutoRebaseRecoveryContext) -> bool:
    """Route an interrupted auto-rebase on the record it left; whether the recovery owns the tick.

    Three steps, in order, each answered by what the attempt and its transfer
    left rather than by the label, HEAD, and the counts alone: an ineligible
    label keeps any record a clear would strand, an unmoved HEAD is the
    shortcut only for an attempt that never started, and a checkout the pull
    request is not standing on is classified off the pair of SHAs the attempt
    recorded and how far the transfer beside them got. False only where HEAD
    still stands on the anchor of an attempt that never started, and the
    ordinary rebase goes on from it on this same tick -- or where a finish
    left a landed head the base has advanced past again.

    Every road that resets the checkout drops the attempt in one write, and
    the recovery's answer to that movement rides it: the context the roads
    are handed carries `rewrite_landing_moved.abandons_over_the_reset`, which
    the git owner asks once a reset landed and before the drop.
    """
    owing = replace(context, settles_over_a_reset=partial(_landing_moved.abandons_over_the_reset, context))
    if owing.label not in _PR_REFRESH_DETOUR_LABELS:
        return _replay_cleanup._answers_an_ineligible_label(owing)
    observed = _snapshot._fetch_recovery_snapshot(owing)
    if observed is None:
        return True
    if observed.local_head and observed.local_head == owing.pending_pre_rebase_sha:
        return _routes_an_unmoved_head(owing, observed)
    return _routes_the_comparison(owing, observed)


def _routes_an_unmoved_head(
    context: _AutoRebaseRecoveryContext,
    observed: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Route a checkout standing on the anchor, once nothing captured for the announced head stands.

    Every road from here clears or resets the attempt, so a transaction an
    earlier finish captured for the head it announced is abandoned first, and
    one the abandonment could not retire holds the tick with the attempt
    standing (`rewrite_landing_moved.abandons_off_the_landing`).
    """
    if not _landing_moved.abandons_off_the_landing(context, observed):
        return True
    return _replay_cleanup._finish_an_unmoved_head(context, observed)


def _routes_the_comparison(
    context: _AutoRebaseRecoveryContext,
    observed: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Route a changed-head recovery on the record and the compare together.

    Two classifications rather than one, taken together because the answer is
    the pair. Where the REMOTE stands says which effect the dead tick got as
    far as -- still on the anchor and the push never went out, on the rewrite
    and it did, anywhere else and somebody moved the branch out of band. What
    the pinned comment CARRIES says which of the transfer's own writes it got
    as far as, and both roads are handed it: the evidence a permit is decided
    on where something is left to publish, and the account a landed head is
    finished against where nothing is. It costs no git and no request.

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
    completed = _snapshot._complete_recovery_snapshot(context, observed)
    if completed is None:
        return True
    if not _landing_moved.abandons_off_the_landing(context, completed):
        return True
    carried = _transfers._carried_by(context, completed.head)
    if completed.local_head and completed.local_head == completed.remote_head:
        return _rewrite_landed.recovers(context, completed, carried)
    return _routes_an_unpublished_head(context, completed, carried)


def _routes_an_unpublished_head(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    carried: _Handoff,
) -> bool:
    """Route a checkout the pull request is not standing on.

    What survives every refusal beside this is the retry the anchor exists
    for -- reached on the pair of heads the attempt recorded, on the
    transfer that vouches for a replay the attempt was still recording, or,
    for a remote neither of them accounts for, on the counts over an attempt
    that recorded nothing at all. Where the transfer is the only voucher, it
    is the only thing the retry may publish on.
    """
    refused = _replay_refusals._refused_before_the_retry(context, completed, carried)
    if refused is not None:
        return refused
    in_flight = _replay_evidence._is_an_attempt_in_flight(context, completed, carried)
    if in_flight or _replay_evidence._is_this_attempts_rewrite(context, completed):
        return _rewrite_retry.retries(context, completed, carried, permit_alone=in_flight)
    return _routes_a_moved_remote(context, completed, carried)


def _routes_a_moved_remote(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    carried: _Handoff,
) -> bool:
    """Route a remote neither SHA this recovery holds accounts for.

    Reached once the pull request is proved to be standing on neither the
    rewrite this branch carries nor the anchor the rebase pinned before git
    ran, or once nothing on the comment can say the checkout is this
    attempt's -- so whatever is on either side arrived from somewhere the
    record does not describe. The counts are what is left to tell those
    apart, and they answer the question they were always about: a pair of
    zeros over two heads that disagree is a reading that did not happen, a
    remote with commits of its own is one a force-push would drop, and a
    strictly-ahead branch is a lease this recovery may still try -- the push
    is pinned to the anchor, so a remote that is not on it refuses the
    publication rather than being overwritten.
    """
    if completed.ahead == 0 and completed.behind == 0:
        return _outcomes._reject_unknown_recovery_comparison(context, completed)
    if completed.behind > 0:
        return _outcomes._park_diverged_recovery(context, completed)
    return _rewrite_retry.retries(context, completed, carried)
