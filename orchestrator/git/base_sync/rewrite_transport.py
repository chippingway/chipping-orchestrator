# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Publishing one exact rewrite candidate, and observing where it landed.

The push names the candidate's rewritten head and is leased against its
original one, so a checkout that moved publishes nothing it did not read and a
pull request somebody pushed to since rejects the update instead of being
overwritten. Both go through the branch transport's hardened push; this owner
adds only the refusals `rewrite_facts` reads ahead of it and the reading that
classifies a push git did not confirm.

The refusals are taken on the checkout and the remote as they stand when the
push is about to go out, never on the readings a candidate was prepared with
alone. A candidate is a frozen record, and the same one handed in after its
push landed still says the remote is on the anchor: only the fresh reading
shows the branch already standing on it, which is what refuses a second push
of a publication that has happened.

That reading is what makes an uncertain response a recorded fact rather than
a failure. A push can land and lose its answer on the way back, and a caller
that took every failure for a rejection would roll a published branch back
onto a lease the pull request has already left. So the remote is read again,
and only a branch shown elsewhere is a rejection.

Nothing here decides what an outcome means for the issue -- no size policy, no
announcement, no route, no pinned-state write. Dormant until the workflow's
base-rewrite coordinator calls it; see `rewrite_handoffs`.
"""
from __future__ import annotations

from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git import branch_transport, ref_transport
from orchestrator.git.base_sync import rewrite_facts as _rewrite_facts
from orchestrator.git.base_sync.rewrite_handoffs import (
    _LandedRewrite,
    _PushOutcome,
    _RewriteCandidate,
    _RewriteRefusal,
)
from orchestrator.git.base_sync.state import log


def _publishes_the_candidate(
    spec: _config_models.RepoSpec,
    worktree: Path,
    candidate: _RewriteCandidate,
) -> _LandedRewrite:
    """Push exactly `candidate` onto its branch, leased to its original head.

    A candidate that refuses on its own readings is answered without touching
    git again. Otherwise the checkout and the remote are read once more and
    the push goes out only where that reading refuses nothing. A refusal sends
    nothing and comes back with the remote reading it was decided on; an
    accepted push comes back with the remote at the candidate, which is what
    git's answer to a leased update says.
    """
    if candidate.refusal is not None:
        return _refused(candidate, candidate.remote, candidate.refusal)
    now = _rewrite_facts._rereads_the_candidate(spec, worktree, candidate)
    refusal = _rewrite_facts._moved_since(worktree, candidate, now)
    if refusal is not None:
        return _refused(candidate, now.remote, refusal)
    accepted = branch_transport._push_branch(
        spec, worktree, candidate.branch,
        force_with_lease=candidate.original_head,
        revision=candidate.rewritten_head,
    )
    if accepted:
        return _LandedRewrite(
            candidate=candidate,
            outcome=_PushOutcome.ACCEPTED,
            remote=ref_transport._RefRead(sha=candidate.rewritten_head),
        )
    return _unconfirmed(spec, worktree, candidate)


def _refused(
    candidate: _RewriteCandidate,
    remote: ref_transport._RefRead,
    refusal: _RewriteRefusal,
) -> _LandedRewrite:
    """Record a publication a guard stopped, with nothing sent."""
    log.warning(
        "PR #%d base rewrite %s -> %s on %s not published: %s",
        candidate.attempt.pr_number, candidate.original_head[:8],
        candidate.rewritten_head[:8], candidate.branch, refusal,
    )
    return _LandedRewrite(
        candidate=candidate,
        outcome=_PushOutcome.REFUSED,
        remote=remote,
        refusal=refusal,
    )


def _unconfirmed(
    spec: _config_models.RepoSpec,
    worktree: Path,
    candidate: _RewriteCandidate,
) -> _LandedRewrite:
    """Classify a push git answered with a failure by reading the remote again.

    A branch shown anywhere but the candidate is a rejection: the lease held,
    or the push never reached the remote, and either way nothing of it is
    there. A branch shown ON the candidate, or one nobody could read, is the
    uncertain response -- the record's `landed` says which.
    """
    after = branch_transport._remote_branch_read(spec, worktree, candidate.branch)
    rejected = after.sha is not None and after.sha != candidate.rewritten_head
    outcome = _PushOutcome.REJECTED if rejected else _PushOutcome.UNCERTAIN
    log.warning(
        "PR #%d base rewrite push of %s onto %s leased to %s answered a "
        "failure; the remote now reads %s, so the push is %s",
        candidate.attempt.pr_number, candidate.rewritten_head[:8],
        candidate.branch, candidate.original_head[:8],
        after.detail if after.sha is None else after.sha, outcome,
    )
    return _LandedRewrite(candidate=candidate, outcome=outcome, remote=after)


def _observes_the_landing(
    spec: _config_models.RepoSpec,
    worktree: Path,
    candidate: _RewriteCandidate,
) -> _LandedRewrite:
    """Read where the remote has `candidate`'s branch now, pushing nothing.

    For a rewrite an earlier tick may already have published: an accepted
    push whose tick never came back is recovered from this reading, and
    never from a second push of the same commit.
    """
    standing = branch_transport._remote_branch_read(
        spec, worktree, candidate.branch,
    )
    return _LandedRewrite(
        candidate=candidate, outcome=_PushOutcome.OBSERVED, remote=standing,
    )
