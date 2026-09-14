# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The single route from an interrupted auto-rebase to one terminal answer.

The verified facts arrive from ``snapshot`` and the answers live in
``outcomes``; what this owner adds is the order they are asked in, and that
order is the safety property. An ineligible label is cleared before anything
is fetched, an unmoved HEAD falls back to the normal rebase flow before any
comparison is trusted, and equality with the remote is checked before the
ahead/behind counts are -- so the reissued force-push is only ever reached by
a head proven to be ahead of a remote the tick actually read. Anything else
parks. The legacy keyword signature is bound here too, because the flat
callers still pass the pre-context argument list this route derives its
context from.

What the remote says is only half of what an interrupted rebase has to be
classified by, because the rebase may have been carrying a human's verdict
onto the commit it produced. ``transfers`` answers the other half off the
pinned comment -- how far the transfer's own writes got -- and the road that
still has something to publish is handed it. A rewrite the grant never reached
is given re-derived evidence, so the replay is decided on the transfer the
dead tick would have asked for rather than measured past the same ceiling and
adjudicated a second time with a pull request open over the work.

The counts are a fallback for one state alone -- a comment carrying no record
of a replay at all -- and the window between git returning and the write that
names one has a road of its own, where the head is proved by what it
contributes rather than by an id nobody wrote down. Every state neither of
those covers -- a record this build cannot read, one naming another commit, a
tree carrying uncommitted changes, a remote somebody rolled back -- is
fail-closed: the branch goes back onto the anchor and a human is asked.

The count of questions this carries is what the subject costs rather than a
module that outgrew itself. One interrupted attempt is classified on two
readings taken together -- where the remote stands, and how far the transfer's
own writes got -- and the ORDER those questions are asked in is the safety
property. Split across owners, the order would live nowhere and each half
would be free to reach the push on a question the other had already refused.
"""
from __future__ import annotations

import inspect
from typing import Any

from orchestrator.git.base_sync import (
    outcomes,
    persistence,
    publication,
    snapshot,
    transfers,
)
from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
    _PendingRewrite,
)
from orchestrator.git.base_sync.state import _PR_REFRESH_DETOUR_LABELS
from orchestrator.git.verification import probes as verification_probes

# Why a push that landed could not be finished, in the operator's own terms.
# Spelled at the seam that answers for it rather than beside the park, which
# takes whatever reason its caller established.
_UNROTATED = (
    "the push went out and the verdict did not move with it, so the "
    "permission granted for `{published}` is still outstanding"
)

_RECOVERY_SIGNATURE = inspect.Signature((
    inspect.Parameter("gh", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("spec", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("issue", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("state", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("worktree", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("pr_number", inspect.Parameter.KEYWORD_ONLY),
    inspect.Parameter("label", inspect.Parameter.KEYWORD_ONLY),
    inspect.Parameter(
        "pending_pre_rebase_sha",
        inspect.Parameter.KEYWORD_ONLY,
    ),
    inspect.Parameter(
        "pending_rewrite",
        inspect.Parameter.KEYWORD_ONLY,
        default=_PendingRewrite(),
    ),
    inspect.Parameter("behind", inspect.Parameter.KEYWORD_ONLY, default=0),
    inspect.Parameter(
        "unparking_consumed_max",
        inspect.Parameter.KEYWORD_ONLY,
        default=None,
    ),
))


def _retry_recovery_push(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
    carried: transfers._Handoff = transfers._Handoff.NOTHING,
    *,
    permit_alone: bool = False,
) -> bool:
    """Publish a verified ahead-only recovery head and finalize its state.

    Measured before it is published, like every other push onto a pull request
    the remote already carries: the head this recovery found is one an earlier
    tick rebased and never pushed, so nothing on this branch has been read
    against the base it now sits on.

    Unless the branch is standing on a rewrite of a commit an adjudication
    accepted, which is the one candidate that may be published without a
    reading. `carried` says how far the interrupted tick got with that
    transfer, and what this call owes it is the evidence: a permission the
    grant already recorded is what `late_transfer` re-asks the permit over,
    and a rewrite that never reached one is re-derived here so the replay is
    not measured past the same ceiling and adjudicated a second time with a
    pull request open over the work.

    Where there IS such a transfer, the permit is the whole of what may let
    this push out. It is asked before the gate and the gate is told the same,
    so a refusal is a refusal on both sides of that seam rather than a
    fall-through to the cumulative reading -- which on this road would
    force-push a replay nothing vouched for and clear the recovery with the
    verdict still on the commit a human ruled on. The rotation is read back
    afterwards for the same reason, since a permit that stopped holding
    between the two asks leaves the push landed and the verdict where it was.

    `permit_alone` says the caller holds no id vouching for this checkout at
    all -- the attempt was still in flight when the process died -- so the
    evidence is the only thing that can. Evidence that will not assemble parks
    there rather than falling through, because the fall-through is the
    ordinary cumulative reading and measuring a commit is not a way of
    establishing whose it is.
    """
    dirty_files = verification_probes._worktree_dirty_files(context.worktree)
    if dirty_files:
        return outcomes._park_dirty_recovery(
            context, recovery_snapshot, dirty_files,
        )
    rewrite = transfers._reconstructed(
        context, recovery_snapshot.head, carried,
    )
    licensed = rewrite is not None or carried == transfers._Handoff.OUTSTANDING
    if permit_alone and not licensed:
        return outcomes._park_unproven_replay_recovery(
            context, recovery_snapshot,
        )
    if licensed and not transfers._permits_the_publication(
        context, recovery_snapshot.head, rewrite,
    ):
        return outcomes._park_refused_permit_recovery(
            context, recovery_snapshot,
        )
    return _pushes_the_recovered_head(
        context, recovery_snapshot, rewrite, licensed,
    )


def _pushes_the_recovered_head(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
    rewrite,
    licensed: bool,
) -> bool:
    """Reissue the interrupted push and finalize what it earns.

    `licensed` says a transfer this recovery already knows about is the whole
    of what may let the push out, and it is passed to the gate as well as
    asked ahead of it: a permit that stops holding between the two asks is
    refused there rather than measured, and one that stops holding after the
    push leaves the verdict where it was, which the rotation read below
    catches.
    """
    landed = recovery_snapshot.head
    records = publication._gate_records()
    published = publication._gated_publication()._publishes(
        records._gate(
            context.gh, context.spec, context.issue, context.state,
            context.worktree,
        ),
        recovery_snapshot.branch,
        records._Entered(
            head=context.pending_pre_rebase_sha or "", reconciling=True,
            # The head this recovery verified against the remote and the one
            # the finalize below records as published. The gate proves the
            # checkout again, and a commit that landed between the two
            # readings would be the one pushed while the notice and the event
            # named this one -- so the candidate is bound and a moved checkout
            # refuses instead.
            candidate=landed,
            rewrite=rewrite,
            permit_only=licensed,
        ),
    )
    unfinished = _unfinished_recovery_push(
        context, recovery_snapshot, published, licensed,
    )
    if unfinished is not None:
        return unfinished
    return persistence._finalize_recovered_rebase(
        context,
        local_head=landed,
        method="crash_recovery_pushed",
        notice=outcomes._pushed_recovery_notice(context, landed),
    )


def _unfinished_recovery_push(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
    published,
    licensed: bool,
) -> bool | None:
    """What a reissued push that did not finish owes, or None where it did.

    Four answers before the finalize, and each is a different tick. A permit
    the gate refused publishes nothing and parks here, since measuring is the
    one thing this road may not fall back on. A hold is a tick the gate
    finished for itself -- parked, or handed to the adjudication -- and only
    the flags it left in memory are owed a write. A push that went out and
    failed is the caller's own park. And a push that landed without the
    verdict moving with it is a permit that stopped holding inside the gate.
    """
    if published.refused:
        return outcomes._park_refused_permit_recovery(
            context, recovery_snapshot,
        )
    if published.held:
        # The gate took the candidate this recovery was finishing, so the
        # finalize behind this -- the notice, the event, the `validating`
        # route -- is not this tick's. The park it left is written here, since
        # nothing else would.
        context.gh.write_pinned_state(context.issue, context.state)
        return True
    if not published.landed:
        return outcomes._park_failed_recovery_push(context, recovery_snapshot)
    landed = recovery_snapshot.head
    if licensed and not transfers._rotated_onto(context.state, landed):
        return outcomes._park_unfinished_recovery(
            context, recovery_snapshot, _UNROTATED.format(published=landed),
        )
    return None


def _recover_pending_auto_base_rebase_context(
    context: _AutoRebaseRecoveryContext,
) -> bool:
    """Route an interrupted auto-rebase from verified local/remote state."""
    if context.label not in _PR_REFRESH_DETOUR_LABELS:
        return snapshot._clear_ineligible_recovery(context)

    recovery_snapshot = snapshot._fetch_recovery_snapshot(context)
    if recovery_snapshot is None:
        return True
    if (
        recovery_snapshot.local_head
        and recovery_snapshot.local_head == context.pending_pre_rebase_sha
    ):
        return snapshot._clear_unchanged_recovery(context)

    return _route_recovery_snapshot(context, recovery_snapshot)


def _route_recovery_snapshot(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Route a changed-head recovery from its completed local/remote compare.

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
    carried: transfers._Handoff,
) -> bool:
    """Route a checkout the pull request is not standing on.

    Three refusals before the one road that pushes, in the order the evidence
    for them costs nothing to read. A remote the record says already carried
    this replay has been rolled back by somebody, and the anchor a retry would
    lease against is the head they rolled it back to. A transfer record nobody
    can vouch for would reach the ordinary cumulative gate and send an
    adjudicated change into a second adjudication. And an attempt record that
    does not vouch for the checkout -- damaged, or whole and naming some other
    commit -- is the same refusal one field over: read as the window it
    resembles, it would fall through to the counts, and a strictly-ahead
    checkout would be measured and force-pushed on the strength of a claim
    nothing could check.

    What is left is the retry the anchor exists for, and -- for a remote
    neither pinned head accounts for -- the counts, over an attempt that
    recorded nothing at all.
    """
    if transfers._rolled_back_publication(context, completed.head, carried):
        return outcomes._park_rolled_back_recovery(context, completed)
    if carried == transfers._Handoff.UNVOUCHED:
        return outcomes._park_unvouched_recovery(context, completed)
    if _unclaimed_checkout(context, completed):
        return outcomes._park_unrecorded_recovery(context, completed)
    in_flight = _is_an_attempt_in_flight(context, completed, carried)
    if in_flight or _is_this_attempts_rewrite(context, completed):
        return _retry_recovery_push(
            context, completed, carried, permit_alone=in_flight,
        )
    return _route_a_moved_remote(context, completed, carried)


def _is_an_attempt_in_flight(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    carried: transfers._Handoff,
) -> bool:
    """Whether this is the window between `git rebase` and its own record.

    The narrowest window the attempt has and the only one no id can close: the
    rebase produced a commit, the write naming it never happened, and what the
    comment still carries is the terms the attempt was entered under and the
    anchor the remote is standing on. Every id-based road refuses this
    checkout, rightly -- nothing wrote the head down, so nothing can say it is
    this attempt's work.

    Something else can. An issue whose exemption names the commit the pull
    request carries has a pair a human ruled on recorded on it, and the permit
    re-fingerprints the checkout's contribution against that pair before it
    licenses anything: a replay of the accepted change proves out, and a
    commit somebody else left does not. So the road is opened only where there
    IS such a verdict to prove against, and the push behind it is permitted or
    it does not happen.

    Both other halves are still required, and for the reasons they always
    were. The remote has to be standing exactly on the anchor, which is what
    says no push of this attempt's ever landed and what the force-with-lease
    is pinned to. And the terms have to read back whole, since the permit's
    publication checks are asked against them.
    """
    if carried != transfers._Handoff.UNRECORDED:
        return False
    if completed.remote_head != context.pending_pre_rebase_sha:
        return False
    recorded = context.pending_rewrite
    return recorded.is_declared and not recorded.sha


def _unclaimed_checkout(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Whether a record was written and does not vouch for this checkout.

    The counts behind this refusal are a fallback for one state and one only:
    an attempt that reached no record of a REPLAY, which is either a comment
    from before this record existed or the window between git returning and
    the write that names what it produced. There they are all a recovery has
    on its own, and a strictly-ahead branch is a fast-forward the anchor lease
    loses nothing to.

    Every other absence is a claim. A group something took a member out of,
    and a whole group naming some OTHER commit, both leave a checkout the
    attempt does not vouch for -- and read as the window they resemble, the
    counts would measure it and force-push it under a lease a rebuilt
    worktree, an operator's reset, and a branch pointed at other work all
    satisfy. So a record of the replay having been written at all is what
    decides which road is available, and a comment carrying none is the only
    one that reaches the counts.

    The TERMS on their own are not that claim. They go down with the anchor,
    before git can move the branch, so a comment carrying them and no head
    says an attempt was in flight rather than anything about the checkout --
    and the road that answers for that window vouches for the head by what it
    contributes instead.
    """
    recorded = context.pending_rewrite
    return recorded.left_a_replay and not recorded.names(completed.head)


def _is_this_attempts_rewrite(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Whether the checkout is the replay this attempt made, over its anchor.

    Both halves, and neither is enough alone. The REMOTE has to be standing
    exactly on the anchor the rebase pinned before git ran, which is what says
    no push of this attempt's landed and what the force-with-lease behind the
    retry is pinned to. And the CHECKOUT has to be the head that attempt
    recorded as its own replay, which is the only thing that says the
    divergence in front of this tick is the rebase's work rather than a
    worktree somebody rebuilt, an operator's reset, or a branch pointed
    somewhere else -- every one of which satisfies the same lease and would
    take the candidate off the pull request.

    Empty provenance answers no, and what happens then depends on which
    emptiness it is. A comment carrying the attempt's terms and no head is the
    window between git returning and the write that records the replay, and
    the road beside this one answers for it on the evidence rather than on an
    id. A comment carrying nothing at all is an attempt from before this
    record existed, and there the recovery falls back to the counts it always
    used: a strictly-ahead branch is a fast-forward the anchor lease loses
    nothing to, and a divergent one parks.
    """
    if completed.remote_head != context.pending_pre_rebase_sha:
        return False
    return context.pending_rewrite.names(completed.head)


def _route_a_moved_remote(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    carried: transfers._Handoff,
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
    return _retry_recovery_push(context, completed, carried)


def _recover_pending_auto_base_rebase(
    *args: Any,
    **kwargs: Any,
) -> bool:
    """Finalize a clean auto-base-rebase interrupted by a prior crash.

    The pinned pre-rebase SHA distinguishes an unchanged worktree, an
    already-published rewrite, an ahead-only rewrite that still needs a
    push, and a branch that diverged through an out-of-band update. Returns
    False only when HEAD still equals the anchor and the normal rebase flow
    should continue on the same tick.
    """
    bound_fields = _RECOVERY_SIGNATURE.bind(*args, **kwargs)
    bound_fields.apply_defaults()
    context = _AutoRebaseRecoveryContext(**bound_fields.arguments)
    return _recover_pending_auto_base_rebase_context(context)


_recover_pending_auto_base_rebase.__signature__ = _RECOVERY_SIGNATURE
