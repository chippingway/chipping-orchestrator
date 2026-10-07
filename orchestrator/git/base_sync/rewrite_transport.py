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
of a publication that has happened. The same holds the other way round: a
candidate prepared over a remote already on it is read again too, since that
claim of a landing is only as good as the moment it was read.

That reading and the push are two calls (`_refused_before_the_push`,
`_pushes_the_candidate`), so a caller with a question of its own to ask
between them -- whether the publication ended while the remote was being read
-- asks it immediately before anything is sent. A candidate the fresh reading
finds already standing is sent nothing; a caller that would finish it proves
it first with a push leased to the candidate itself (`_proves_the_landing`),
which git answers only while the branch is still there.

That reading is what makes an uncertain response a recorded fact rather than
a failure. A push can land and lose its answer on the way back, and a caller
that took every failure for a rejection would roll a published branch back
onto a lease the pull request has already left. So the remote is read again,
and only a branch shown elsewhere is a rejection.

Nothing here decides what an outcome means for the issue -- no size policy, no
announcement, no route, no pinned-state write. The workflow's ordinary
publication of a clean rebase makes its push here, once the size gate and the
transfer permit have ruled on the candidate
(`workflow/engine/rewrite_publication.py`), and so does the crash recovery's
retry of a replay nothing published (`workflow/engine/rewrite_retry.py`); the
observation of a landing is dormant until the recovery of one takes it up. See
`rewrite_handoffs`.
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

# The refusals a candidate's own readings may give that are read again before
# the push rather than answered off the preparation: none at all, and a remote
# already standing on the candidate, which is a landing only as of that reading.
_READ_AGAIN = frozenset((None, _RewriteRefusal.PUBLISHED))


def _publishes_the_candidate(
    spec: _config_models.RepoSpec,
    worktree: Path,
    candidate: _RewriteCandidate,
) -> _LandedRewrite:
    """Push exactly `candidate` onto its branch, leased to its original head.

    The reading and the push in one call, for a caller with nothing to ask
    between them. A refusal sends nothing and comes back with the remote
    reading it was decided on; an accepted push comes back with the remote at
    the candidate, which is what git's answer to a leased update says.
    """
    refused = _refused_before_the_push(spec, worktree, candidate)
    if refused is not None:
        return refused
    return _pushes_the_candidate(spec, worktree, candidate)


def _refused_before_the_push(
    spec: _config_models.RepoSpec,
    worktree: Path,
    candidate: _RewriteCandidate,
) -> _LandedRewrite | None:
    """What `candidate` comes to with nothing sent, as the push would find it; None where it may go out.

    A refusal on the candidate's own readings is answered without touching
    git again, save the one that claims a landing: a remote the candidate was
    prepared standing on is read again like everything else. The fresh
    reading refuses in the candidate's own order, so a remote on the candidate
    is PUBLISHED only where the head, the tree, and the base still hold -- it
    claims a landing, and excuses nothing else a push would have been refused
    on. One that has left the candidate since it was read there is refused as
    moved, back onto the anchor included, which is somebody's rollback rather
    than a branch to publish over.
    """
    prepared = candidate.refusal
    if prepared not in _READ_AGAIN:
        return _refused(candidate, candidate.remote, prepared)
    now = _rewrite_facts._rereads_the_candidate(spec, worktree, candidate)
    refusal = _rewrite_facts._moved_since(worktree, candidate, now)
    if prepared is not None:
        refusal = refusal or _RewriteRefusal.MOVED_REMOTE
    if refusal is None:
        return None
    return _refused(candidate, now.remote, refusal)


def _pushes_the_candidate(
    spec: _config_models.RepoSpec,
    worktree: Path,
    candidate: _RewriteCandidate,
) -> _LandedRewrite:
    """Push `candidate` leased to its original head, with no reading of its own ahead of it.

    For a caller that has just had `_refused_before_the_push` answer None.
    """
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


def _proves_the_landing(
    spec: _config_models.RepoSpec,
    worktree: Path,
    candidate: _RewriteCandidate,
) -> _LandedRewrite:
    """Prove at the remote that the branch still stands on `candidate`, sending nothing.

    A push of the candidate leased to the candidate itself: the branch already
    carries it, so there is nothing to send, and git answers it only where the
    lease still holds -- the one proof taken atomically at the remote rather
    than off a reading a foreign push may have overtaken since. Proved, it is
    the publication refused as already published that it was.

    An answer git did not confirm is settled by reading the remote again, and
    a remote still on the candidate is that same refusal: the proof had
    nothing to send whatever became of its answer, so it never reads as a push
    this tick made. A remote anywhere else is a rejection, and one nobody
    could read is uncertain, as a push's is.
    """
    rewritten = candidate.rewritten_head
    proved = branch_transport._push_branch(
        spec, worktree, candidate.branch,
        force_with_lease=rewritten,
        revision=rewritten,
    )
    standing = ref_transport._RefRead(sha=rewritten) if proved else branch_transport._remote_branch_read(
        spec, worktree, candidate.branch,
    )
    if standing.sha == rewritten:
        return _LandedRewrite(
            candidate=candidate,
            outcome=_PushOutcome.REFUSED,
            remote=standing,
            refusal=_RewriteRefusal.PUBLISHED,
        )
    log.warning(
        "PR #%d base rewrite %s on %s could not be proved standing; the remote now reads %s",
        candidate.attempt.pr_number, rewritten[:8], candidate.branch,
        standing.detail if standing.sha is None else standing.sha,
    )
    outcome = _PushOutcome.UNCERTAIN if standing.sha is None else _PushOutcome.REJECTED
    return _LandedRewrite(candidate=candidate, outcome=outcome, remote=standing)


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
