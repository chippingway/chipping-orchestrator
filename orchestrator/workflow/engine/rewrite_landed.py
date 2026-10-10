# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The recovery of a base rewrite whose push an interrupted tick already landed, from its observation to its finish.

The recovery (`rewrite_recovery`) reaches this with the remote and the
checkout agreeing on one head past the anchor: the push the dead tick made
landed, whether or not its answer ever came back. Nothing is pushed a second
time and nothing is measured -- what the dead tick still owes is some tail of
its settlement and its finish. The git owners read the facts: the candidate
the attempt left (`git/base_sync/recovery_push.py`) and why the pinned record
does not account for the landing (`git/base_sync/landed_recovery.py`). Every
decision is made here, in the order the recovery has always kept:

- An attempt made for another publication than the issue now records parks
  with HEAD, the anchor, and the record where they stand.
- The checkout is read as the candidate it stands for, and held to the head
  the recovery's fetch classified: every refusal below, and the voucher the
  finish takes on trust for a replay the attempt never got to name, is about
  that head. A candidate naming any other -- the checkout and the branch both
  moved since, or a head that no longer reads -- makes nothing, and the next
  tick classifies what it then finds.
- A landing the record does not account for parks the same way: a mark
  naming another head, a head nothing this attempt wrote vouches for, a
  checkout not provably clean beneath a verdict, a transfer the receipt and
  debt do not account for. Every finish drops the anchor -- the only thing
  that brings this road back to a publication it could not account for -- so
  each is asked before anything is said or written.
- A settled transfer whose record never reached the sinks is reported next
  (`stages/implementing/late_transfer_telemetry.py`): its proof is the one
  fact no later reading could re-derive, and the report drops it durably.
- A permission still outstanding owes the receipt, the paid debt, and the
  rotation its push never got to write, and they ride a leased no-op. The
  permit is asked before the gate and the gate is told it is the only licence
  (`git/base_sync/transfer_permits.py`), so a refusal is never measured; the
  push is the git owner's proof of the candidate at the remote, leased to the
  candidate itself (`rewrite_publication.CandidatePush`), which sends nothing.
  A refusal, a no-op that did not land, or a rotation the gate did not make
  parks with HEAD and the anchor where they stand, and a hold writes only
  what the gate left.
- Anything else is observed (`git/base_sync/rewrite_transport.py`): the remote
  read as it stands, with no push at all, which is how an accepted push whose
  answer was lost is finished without a second one.

What the proof or the observation found is handed to the one finish every
landing gets (`rewrite_finish.finishes_the_recovery`): the debt and the room
it needs, the announcement checkpoint, the evidence decision, the route, and
the attempt's retirement, with the human reply that brought the attempt back
spent. A mark already naming this head says its notice and its event are out,
so that finish repeats neither and finishes only the route. One that finds
the remote no longer on the head, or a base it cannot count the head against,
makes nothing, and the next tick classifies whatever it then finds.

The evidence decision resumes where the dead tick left it
(`rewrite_finish_evidence`). A tick that died before its evidence write
landed -- before the configured commands ran, or behind a run that completed
-- captured nothing, so the commands run again on the landed head. A run or
carry it captured is never made again: it is routed with its own transcript
and provenance once its binding proves again, and abandoned, with nothing
run, where the requirements, the report or review subject, the configuration,
the heads, or the base moved since. Nothing on this road launches a developer.

Run under the issue writer claim the base refresh (`base_refresh`) takes
before the issue is read and holds through the route.
"""
from __future__ import annotations

import logging

from orchestrator.git.base_sync import (
    landed_recovery as _landed_recovery,
    recovery_push as _recovery_push,
    replay_evidence as _replay_evidence,
    replay_publication_parks as _replay_publication_parks,
    replay_transfer_parks as _replay_transfer_parks,
    rewrite_transport as _rewrite_transport,
    transfer_permits as _transfer_permits,
    transfers as _transfers,
)
from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
)
from orchestrator.git.base_sync.rewrite_handoffs import _RewriteCandidate
from orchestrator.git.base_sync.transfer_values import _Handoff
from orchestrator.workflow.engine import (
    rewrite_finish as _finish,
    rewrite_publication as _rewrite_publication,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_push as _late_push,
    late_records as _late_records,
    late_transfer_telemetry as _transfer_telemetry,
)

log = logging.getLogger("orchestrator.workflow")


def recovers(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    carried: _Handoff,
) -> bool:
    """Finish the route behind a push the pull request already carries; whether the recovery owns the tick.

    `carried` says how far the interrupted tick got with the transfer beside
    the attempt, for `completed`'s head. The checkout is read as the candidate
    it stands for before anything is refused, so the tree a verdict's landing
    is held clean is the reading that candidate carries, and a candidate that
    is not that head is no landing anything here was asked about. False only
    where the finish found the base advanced past the landed head again, and
    this tick's rebase goes on from it.
    """
    if _replay_evidence._made_for_another_publication(context, completed):
        return _replay_publication_parks._park_foreign_publication_recovery(context, completed)
    candidate = _recovery_push._recovered_candidate(context, completed)
    if _left_the_fetched_head(context, completed, candidate):
        return True
    refusal = _landed_recovery._unfinishable(context, completed.head, carried, candidate.checkout.status)
    if refusal:
        return _replay_transfer_parks._park_unfinished_recovery(context, completed, refusal)
    _transfer_telemetry._reports_a_settled_transfer(_gate(context))
    if carried == _Handoff.OUTSTANDING:
        return _settles(context, completed, candidate)
    landing = _rewrite_transport._observes_the_landing(context.spec, context.worktree, candidate)
    return _finish.finishes_the_recovery(context, landing)


def _left_the_fetched_head(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    candidate: _RewriteCandidate,
) -> bool:
    """Whether the checkout no longer proves to the head the recovery's fetch classified; logged where it does not.

    What vouches for a landing is asked of that head: the record naming it,
    or the permission bound to it where the record never got to. A checkout
    and a branch somebody moved together since would agree on another head,
    and observed or proved, that head would be announced and routed on a
    voucher it never had. So nothing is made for it -- no park either, since
    a move is no fact about this attempt -- and the next tick's own fetch
    classifies the branch as it then finds it.
    """
    moved = candidate.rewritten_head != completed.head
    if moved:
        log.warning(
            "issue=#%d the checkout left %.8s, the head PR #%d was fetched standing on, before its landing could be "
            "finished (it now reads %r); finishing nothing until a later tick classifies it again",
            context.issue.number, completed.head, context.pr_number, candidate.rewritten_head[:8],
        )
    return moved


def _settles(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    candidate: _RewriteCandidate,
) -> bool:
    """Receipt the landing through the leased no-op that proves it, and finish what it proved.

    Entered on the anchor and named against the landed commit, exactly as the
    interrupted tick entered it: the anchor is the head the permit was granted
    against, and a pull request standing on the rewrite instead is this
    issue's own push having landed, which the debt the grant recorded is what
    lets the entry freeze.

    There is nothing to measure on this road. A count under the ceiling would
    report the settlement landed with the permission still outstanding, and a
    count over it would route an adjudicated change into a second adjudication
    with the pull request already carrying the work -- so the gate is held to
    the permit, and the permit decides whether the permission may be spent.
    """
    landed = completed.head
    if not _transfer_permits._permits_the_publication(context, landed):
        return _replay_transfer_parks._park_unfinished_recovery(
            context, completed, _landed_recovery._REFUSED_PERMIT,
        )
    push = _rewrite_publication.CandidatePush(candidate)
    published = _late_push._publishes(
        _gate(context),
        completed.branch,
        _late_gate_models._Entered(
            head=context.pending_pre_rebase_sha, reconciling=True, candidate=landed, permit_only=True,
        ),
        transport=push,
    )
    if published.held and not published.refused:
        context.gh.write_pinned_state(context.issue, context.state)
        return True
    unsettled = _unsettled(context, landed, published, push)
    if unsettled:
        return _replay_transfer_parks._park_unfinished_recovery(context, completed, unsettled)
    return _finish.finishes_the_recovery(context, push.landing)


def _unsettled(
    context: _AutoRebaseRecoveryContext,
    landed: str,
    published: _late_push._PushedCandidate,
    push: _rewrite_publication.CandidatePush,
) -> str:
    """Why a leased no-op that the gate did not hold settled nothing, or "".

    A permit the gate refused publishes nothing, and measuring is the one
    thing this road may not fall back on. A no-op that did not land is a
    remote that moved between this tick's fetch and the proof. And one that
    landed with the verdict still where it was is a permit that stopped
    holding inside the gate, which only the rotation read back can tell.
    """
    if published.refused:
        return _landed_recovery._REFUSED_PERMIT
    if push.landing is None or not published.landed:
        return _landed_recovery._REFUSED_NO_OP
    if not _transfers._rotated_onto(context.state, landed):
        return _recovery_push._UNROTATED.format(published=landed)
    return ""


def _gate(context: _AutoRebaseRecoveryContext) -> _late_gate_models._Gate:
    """The size gate's subject for this recovery's issue and checkout."""
    return _late_records._gate(context.gh, context.spec, context.issue, context.state, context.worktree)
