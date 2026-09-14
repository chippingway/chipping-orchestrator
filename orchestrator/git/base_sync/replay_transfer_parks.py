# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Refuse a recovered replay whose verdict transfer cannot be completed.

An unlicensed replay returns to the anchor through the guarded rollback.
A push that already landed keeps its checkout and recovery records for
reconciliation. These outcomes serve the vouched-replay route.
"""
from __future__ import annotations

from orchestrator import config
from orchestrator.git.base_sync import persistence, recovery_notices as _recovery_notices
from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
)
from orchestrator.git.base_sync.state import (
    _REASON_AUTO_BASE_REBASE_FAILED,
    _REASON_AUTO_BASE_REBASE_PUSH_FAILED,
    log,
)


def _park_unfinished_recovery(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
    detail: str,
) -> bool:
    """Park, without a reset, a landed push this tick may not finish.

    The push went out and the route behind it could not be closed. `detail` is
    the reason it could not, and it is the operator's whole starting point.

    HEAD is deliberately left alone. Every other park here resets onto the
    pre-rebase anchor because that is the head the remote still carries; here
    the remote carries the rewrite instead, so a reset would take the checkout
    off work the pull request has and hand the next reader a branch behind its
    own publication.

    The anchor stays pinned with it, and that is what makes the park
    recoverable rather than terminal. It is also the whole reason this park
    exists rather than the ordinary relabel: the anchor is the only thing that
    brings this recovery back, so clearing it over a verdict that may not have
    moved leaves the next tick to measure a rewrite a human already ruled on
    and route it into adjudication a second time. A human's reply re-enters
    this route, the remote is read again, and whatever it turns out to be is
    classified from scratch.
    """
    local_short = _recovery_notices._short(recovery_snapshot.head)
    log.warning(
        "issue=#%d auto-rebase recovery: PR #%d carries %s and this tick "
        "cannot finish the route behind it (%s); leaving HEAD and the "
        "recovery anchor exactly as they are and parking awaiting human",
        context.issue.number, context.pr_number, local_short, detail,
    )
    persistence._park_auto_rebase_failure(
        context.gh,
        context.issue,
        context.state,
        message=(
            f"{config.HITL_MENTIONS} crash recovery for PR "
            f"#{context.pr_number}: the rebased branch reached the remote, so "
            f"PR #{context.pr_number} carries `{local_short}` -- but the "
            f"route behind that push cannot be finished safely because "
            f"{detail}. HEAD has NOT been reset: the worktree is standing on "
            "the commit the PR carries. Investigate the pinned comment and "
            "the remote branch, then reply on this issue with anything once "
            "they are reconciled."
        ),
        reason=_REASON_AUTO_BASE_REBASE_PUSH_FAILED,
    )
    return True


def _park_unvouched_recovery(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Restore the anchor rather than measure a record nobody can read.

    The comment claims something about the commit this issue exempts -- a
    transfer group short of a member, an exemption it cannot show whole, an
    identity taken under a scheme this build does not compute -- or a push
    owed for some other commit with no permission explaining it, and the
    branch is standing on a replay with nothing on the remote yet.

    Every other road from here ends in the ordinary cumulative gate, and for
    an adjudicated change that is the wrong answer twice over: the replay is
    measured past the same ceiling and routed into a second adjudication, with
    a pull request already open over the work, on the strength of a record
    nothing checked. The permit refuses the same claim for the same reason, so
    there is nothing this tick could do with it but ask.

    So the branch goes back onto the anchor -- the head the remote still
    carries, so nothing is lost that the reflog does not have -- and the issue
    parks. The record itself is left exactly as it stands: a group this reader
    cannot vouch for is the only account there is of how the exemption came to
    name what it names, and the rollback drops only what it can read whole.
    """
    local_short = _recovery_notices._short(recovery_snapshot.head)
    pre_rebase_short = _recovery_notices._short(context.pending_pre_rebase_sha)
    log.warning(
        "issue=#%d auto-rebase recovery: the pinned comment claims an "
        "exemption, a transfer, or a debt this build cannot tie to this "
        "attempt; resetting %s onto the anchor and parking rather than "
        "measuring or pushing on a record nothing checked",
        context.issue.number, local_short,
    )
    persistence._reset_clear_and_park(
        context,
        context.pending_pre_rebase_sha,
        message=(
            f"{config.HITL_MENTIONS} crash recovery for PR "
            f"#{context.pr_number}: this issue's pinned comment claims an "
            "adjudication exemption, a transfer of one, or a publication debt "
            "that the orchestrator cannot tie to this rebase, and the "
            f"interrupted rebase left `{local_short}` on the branch. Publishing "
            "it would act on a record nothing could check -- sending a change "
            "a human already ruled on back into adjudication, or overwriting "
            "a push somebody else is still owed -- so HEAD has been reset to "
            f"the pre-rebase SHA `{pre_rebase_short}` and nothing was pushed. "
            "Repair the `late_exempt_*` / `late_rewrite_*` / `late_approved_*` "
            "fields on the pinned comment, then reply on this issue with "
            "anything to retry."
        ),
        reason=_REASON_AUTO_BASE_REBASE_FAILED,
    )
    return True


def _park_refused_permit_recovery(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Restore the anchor when the permit for an unpushed replay refuses.

    The branch is standing on a rewrite of a commit an adjudication accepted
    and the push it was made for never went out. The permit is the whole of
    what may let that push out here: measured instead, an oversized replay
    goes back into adjudication with a pull request already open over the
    work, and a small one is force-pushed and the route finished with the
    verdict still on the commit a human ruled on.

    So the branch goes back onto the anchor -- the head the remote carries
    wherever a retry was ever possible -- and the issue parks. The permission
    the rollback finds goes with the object it was granted for, on the
    rollback's own terms: the replay is on no branch after the reset, so a
    claim about a push that will never happen is dropped, and the exemption
    stays exactly where the adjudication put it.
    """
    local_short = _recovery_notices._short(recovery_snapshot.head)
    pre_rebase_short = _recovery_notices._short(context.pending_pre_rebase_sha)
    log.warning(
        "issue=#%d auto-rebase recovery: no permit licenses %s to publish and "
        "there is nothing else this road may publish it on; resetting onto "
        "the anchor rather than measuring an adjudicated change again",
        context.issue.number, local_short,
    )
    persistence._reset_clear_and_park(
        context,
        context.pending_pre_rebase_sha,
        message=(
            f"{config.HITL_MENTIONS} crash recovery for PR "
            f"#{context.pr_number}: an earlier tick rebased this branch onto "
            "the advanced base and died before pushing, and the permission "
            f"that would let `{local_short}` publish as the change a human "
            "already adjudicated no longer holds -- the pull request, the "
            "stage, the checkout, the leased head, or the two contributions "
            "no longer agree, and the orchestrator log names which. "
            "Publishing it on anything else would send that change back into "
            f"adjudication, so HEAD has been reset to `{pre_rebase_short}` "
            "and nothing was pushed. Reconcile the pinned comment and reply "
            "on this issue with anything to retry."
        ),
        reason=_REASON_AUTO_BASE_REBASE_FAILED,
    )
    return True


def _park_unproven_replay_recovery(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Restore the anchor where nothing can vouch for a replay in flight.

    The attempt died between `git rebase` and the write that names what it
    produced, so the terms are on the comment, the anchor is on the remote,
    and no id anywhere names the commit the checkout is standing on. The one
    thing that can still say whose work it is, is the verdict this issue
    carries: the permit re-fingerprints the contribution in front of it
    against the pair a human ruled on, and a replay of that change proves out
    where a checkout somebody rebuilt does not.

    Reached where that evidence will not assemble at all -- a semantic record
    this issue never earned or nothing can read, a base the remote would not
    name, an object this host does not hold. There is nothing left to prove
    the head by, and the road behind this one is the ordinary cumulative
    reading, which answers a different question: a count says how big a
    change is, never whose it is. Measured and pushed on that, a worktree
    rebuilt from elsewhere lands on the pull request under a lease the anchor
    satisfies.

    So the branch goes back onto the anchor the remote is still carrying and
    the issue parks. Nothing is lost that the reflog does not have, and the
    rebase this branch is still owed is one the next tick makes for itself
    once a human has said the checkout is where they want it.
    """
    local_short = _recovery_notices._short(recovery_snapshot.head)
    pre_rebase_short = _recovery_notices._short(context.pending_pre_rebase_sha)
    log.warning(
        "issue=#%d auto-rebase recovery: the attempt died before recording "
        "the replay it made and nothing on this issue can vouch for %s; "
        "resetting onto the anchor rather than publishing a head no record "
        "and no verdict names",
        context.issue.number, local_short,
    )
    persistence._reset_clear_and_park(
        context,
        context.pending_pre_rebase_sha,
        message=(
            f"{config.HITL_MENTIONS} crash recovery for PR "
            f"#{context.pr_number}: an earlier tick rebased this branch and "
            "died before it could record which commit that produced, so "
            f"nothing on this issue vouches for `{local_short}` -- and this "
            "issue carries no adjudication verdict the contribution could be "
            "proved against instead. Publishing it would force-push a head "
            "no record names over the pull request, so HEAD has been reset "
            f"to `{pre_rebase_short}` (the head the pull request carries) "
            "and nothing was pushed; the replay is still in `git reflog`. "
            "Check the worktree and reply on this issue with anything to "
            "have the rebase made again."
        ),
        reason=_REASON_AUTO_BASE_REBASE_FAILED,
    )
    return True
