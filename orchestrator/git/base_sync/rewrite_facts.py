# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Reading what a rebase left behind, and whether it still stands there.

Preparing a candidate is reading it: the head the checkout is on, proved the
way the size gate proves the commit it measures, the trees on either side of
the rewrite, the hardened worktree status, the head counted against the base
it was replayed onto, and the remote's own answer for the branch. Each is asked
of the owner that already hardens that read -- the measurement's head proof,
the verification probes, the branch-geometry count, and the authenticated
branch read -- so none of them gains a second spelling here.

The same readings are taken again immediately before a push, because the
worktree is writable between the reading and the publication: a commit landing
on top, an edit beside it, or a base ref something rewound would each leave the
push naming one commit while the evidence describes another. The remote is read
again too, and that is what keeps a candidate from being sent twice: a frozen
candidate still carries the reading it was prepared with, so once its push has
landed -- or landed and lost its answer -- only a fresh reading shows the branch
already standing on it. The lease covers what is left, the moment between that
reading and the push.

Once a candidate has landed, the evidence its head is routed with is held to
the base it was counted against: whether the remote's base is still on that
tip, and whether the head over it is the anchor's replay and nothing more
(`_standing_on_the_remote_base`), a base advanced, rewound, or repointed since
being no ground a verification of the head may be recorded or routed on.

The workflow's ordinary publication of a clean rebase reads a candidate here
(`workflow/engine/rewrite_publication.py`), and so do both roads its recovery
takes an interrupted attempt down -- the retry of a replay nothing published
(`workflow/engine/rewrite_retry.py`) and the finish of a push that already
landed (`workflow/engine/rewrite_landed.py`) -- over the remote head the
recovery verified (`recovery_push`); see `rewrite_handoffs`.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git import branch_transport, commands, ref_transport
from orchestrator.git.base_sync.rewrite_handoffs import (
    _BaseStanding,
    _CheckoutReading,
    _RewriteAttempt,
    _RewriteCandidate,
    _RewriteRefusal,
)
from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.git.publication import probes as _publication_probes
from orchestrator.git.verification import (
    probes as _verification_probes,
    status as _worktree_status,
)

# The checkout's own head, resolved and peeled by the same proof the size gate
# and the implementing checkout guards read it with, so no two of them can
# disagree about which commit a worktree is on.
_HEAD = "HEAD"


def _reads_the_checkout(
    spec: _config_models.RepoSpec, worktree: Path,
) -> _CheckoutReading:
    """Read the commit, tree, status, and base standing of one checkout.

    The tree and the base are asked of the proved id rather than of `HEAD`,
    since `HEAD` is a moving name and a tree read a moment later may be
    another commit's. A head that could not be proved reads as "" and takes
    everything asked of it down with it, rather than letting git resolve an
    empty revision to whatever `HEAD` has become.
    """
    proved = _measurement_commits._prove_candidate_commit(worktree, _HEAD)
    head = proved.sha if proved.is_frozen else ""
    return _CheckoutReading(
        head=head,
        tree=_verification_probes._tree_sha(worktree, head),
        status=_worktree_status._worktree_status(worktree),
        base=_standing_on_the_base(spec, worktree, head),
    )


def _standing_on_the_base(
    spec: _config_models.RepoSpec, worktree: Path, head: str,
) -> _publication_probes._BranchDivergence:
    """Count `head` against the base ref the rebase replayed it onto.

    The local `<remote>/<base>` ref, which the refresh fetched before it
    rebased: it is what the replay sits over, and the tip it resolves to is
    what a later reading is compared with. What the remote ITSELF says the base
    is stays the size gate's question, which freezes it for the measurement.
    """
    if not head:
        return _publication_probes._BranchDivergence()
    return _publication_probes._branch_divergence(
        spec, worktree, spec.base_branch, head,
    )


def _standing_on_the_remote_base(
    spec: _config_models.RepoSpec, worktree: Path, candidate: _RewriteCandidate,
) -> _BaseStanding:
    """Whether `candidate`'s head still stands where its reading counted it against the base.

    Asked of a landing whose push is already out, by the evidence policy
    before it records or routes anything over it (`workflow/engine/
    rewrite_base_standing.py`), so a base that moved after the head was
    counted -- while its commands ran, or between the tick that made a
    decision and the recovery taking it -- is told apart from one that did
    not. The remote is asked rather than the local ref: that ref is the
    reading the candidate was counted from, and only the remote says the
    base has gone elsewhere since. Nothing is fetched, so the shared ref every
    other worktree counts from is left as the tick's own fetch set it.

    A base still on that tip can have been rewound to it before the reading
    was taken -- by the recovery's own fetch, say -- and then the head carries
    the commits the base dropped beside its replay. A rebase onto the tip
    replays exactly the anchor's commits the tip lacks by patch, merges left
    out, which is how `git rebase` itself picks them; a head carrying more over
    the tip than that is no replay onto it.
    """
    counted = candidate.checkout.base
    anchor = candidate.attempt.anchor
    if not (counted.readable and anchor):
        return _BaseStanding.UNREAD
    remote = branch_transport._remote_branch_read(spec, worktree, spec.base_branch).sha
    if remote is None:
        return _BaseStanding.UNREAD
    if remote != counted.tip:
        return _BaseStanding.MOVED
    replayed = commands._git_hardened(
        "rev-list", "--count", "--cherry-pick", "--right-only", "--no-merges",
        f"{counted.tip}...{anchor}", "--",
        cwd=worktree,
    )
    count = (replayed.stdout or "").strip()
    if replayed.returncode != 0 or not count.isdigit():
        return _BaseStanding.UNREAD
    return _BaseStanding.DROPPED if counted.ahead > int(count) else _BaseStanding.STANDING


def _prepares_the_candidate(
    spec: _config_models.RepoSpec,
    worktree: Path,
    attempt: _RewriteAttempt,
    branch: str,
    remote: ref_transport._RefRead | None = None,
) -> _RewriteCandidate:
    """Read the candidate a finished rebase left in `worktree`.

    Read whole even where an early fact already refuses it, so the record
    says what every reading found rather than where this owner stopped
    looking. The remote is asked through the authenticated branch read, which
    tells a branch the remote does not carry ("") from a read that established
    nothing (None) and keeps the scrubbed line saying why.

    `remote` is a reading of the branch the caller has already taken and
    decided on, and the candidate carries it rather than a second one: the
    recovery that resumes an interrupted attempt fetches the branch, resolves
    its head, and classifies the checkout against exactly that head. Whatever
    the remote does after it is the publication's to find, since the push
    reads the branch again first.
    """
    return _RewriteCandidate(
        attempt=attempt,
        branch=branch,
        original_tree=_verification_probes._tree_sha(worktree, attempt.anchor),
        checkout=_reads_the_checkout(spec, worktree),
        remote=branch_transport._remote_branch_read(spec, worktree, branch) if remote is None else remote,
    )


def _rereads_the_candidate(
    spec: _config_models.RepoSpec,
    worktree: Path,
    candidate: _RewriteCandidate,
) -> _RewriteCandidate:
    """`candidate` with its checkout and its remote read again, as a push finds them.

    The attempt, the branch, and the original tree are the candidate's own and
    are carried over unread: the attempt is what was pinned before git ran, and
    the replaced commit's tree cannot change under its id.
    """
    return replace(
        candidate,
        checkout=_reads_the_checkout(spec, worktree),
        remote=branch_transport._remote_branch_read(spec, worktree, candidate.branch),
    )


def _moved_since(
    worktree: Path, candidate: _RewriteCandidate, now: _RewriteCandidate,
) -> _RewriteRefusal | None:
    """Why `now`, the candidate read again, may not be pushed, or None where it may.

    A head that left the candidate is the moved-candidate refusal. The same
    head re-read through the candidate's own rule then catches a tree dirtied
    or a base made unreadable since, and a remote that is no longer on the
    anchor -- on the candidate itself where an earlier push of it landed, which
    is refused rather than sent again. Last the base, which may move on its own
    -- see `_base_moved` -- and which a remote already on the candidate does
    not excuse: that is a claim of a landing, and a landing over a base that
    no longer carries the replay's tip is no publication to stand on either.
    """
    if now.rewritten_head != candidate.rewritten_head:
        return _RewriteRefusal.MOVED_CHECKOUT if now.rewritten_head else _RewriteRefusal.UNREADABLE_HEAD
    standing = now.refusal
    if standing not in {None, _RewriteRefusal.PUBLISHED}:
        return standing
    return _base_moved(worktree, candidate.checkout.base.tip, now.checkout.base.tip) or standing


def _base_moved(
    worktree: Path, observed: str, current: str,
) -> _RewriteRefusal | None:
    """Refuse a base ref that no longer carries the tip the replay sits over.

    Reachability rather than equality, the rule the transfer permit holds a
    rewritten base to, because a base advances on its own: another fetch on
    the same clone moves the ref forward between the reading and the push,
    and the candidate is still a replay onto history the base carries. A tip
    the base no longer contains is a rewind or a repoint, and publishing over
    it would hand the pull request commits the base branch dropped.
    """
    if current == observed:
        return None
    if _verification_probes._commit_contains(worktree, observed, current):
        return None
    return _RewriteRefusal.MOVED_BASE
