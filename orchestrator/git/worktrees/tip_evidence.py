# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tri-state commit-tip reads and remote-backed containment proofs.

Local tracking refs cannot prove publication: only the authenticated remote
answer may clear a commit before an artifact holding it is removed."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git import branch_transport
from orchestrator.git.worktrees import evidence_reads as _evidence_reads
from orchestrator.git.worktrees.models import BranchTip, ProbeAnswer

log = logging.getLogger("orchestrator.worktree_lifecycle")


# The exit status git answers a question with when the answer is no, as
# opposed to the ones that mean it could not answer at all. `rev-parse
# --verify --quiet` and `merge-base --is-ancestor` both spell their negative
# this way, and both spell an unreadable repository 128.
_GIT_NEGATIVE = 1

_LOCAL_REF_PREFIX = "refs/heads/"

# What every tip read asks for: the object id, or silence and an exit status
# that says which kind of no this is. Without `--quiet` a ref that does not
# resolve is a complaint on stderr and exit 128, which is the status a
# repository that would not open answers with -- and the two must not arrive
# as one.
_VERIFY_QUIETLY = ("--verify", "--quiet")

_HEAD = "HEAD"


def _resolved_tip(
    resolved: subprocess.CompletedProcess | None, subject: str,
) -> BranchTip:
    """What one `rev-parse --verify --quiet` established, in three answers.

    `--verify --quiet` is what makes them separable: git exits 0 with the
    object id on stdout, 1 with nothing when what was named does not resolve,
    and 128 when the repository itself would not answer. A caller that only
    tested for a non-zero exit would read the last as the second and reclaim
    an artifact on the strength of a repository it could not open.

    Every caller here names a ref in full or names `HEAD`, so a branch named
    like an option cannot be read as one and a branch sharing a tag's name
    cannot be resolved to the tag instead. An exit of 0 with nothing on stdout
    is not a reading either -- nothing here produces it, which is exactly why
    it is answered as the failure it would be.
    """
    if resolved is None:
        return BranchTip(answer=ProbeAnswer.UNREADABLE)
    if resolved.returncode == _GIT_NEGATIVE:
        return BranchTip(answer=ProbeAnswer.REFUTED)
    tip_sha = (resolved.stdout or "").strip()
    if resolved.returncode != 0 or not tip_sha:
        log.debug(
            "could not resolve %s: %s",
            subject, (resolved.stderr or "").strip(),
        )
        return BranchTip(answer=ProbeAnswer.UNREADABLE)
    return BranchTip(answer=ProbeAnswer.CONFIRMED, sha=tip_sha)


def _local_branch_tip(spec: _config_models.RepoSpec, branch: str) -> BranchTip:
    """The commit one local branch in this clone stands on.

    The commit rather than a count of what the branch is ahead by, because
    everything the caller asks next is asked about an object id: whether the
    base contains it, whether the remote is standing on it, whether a pull
    request was made of it. A count answers none of those and cannot be
    compared against anything a pull request reports.

    `REFUTED` is the branch not being there. The scan named it a moment
    earlier, so between the two reads it was deleted -- by a human, by
    another tick's teardown -- which leaves nothing to reclaim rather than
    something to protect.
    """
    ref = f"{_LOCAL_REF_PREFIX}{branch}"
    return _resolved_tip(
        _evidence_reads._clone_read(spec, "rev-parse", *_VERIFY_QUIETLY, ref),
        f"{ref} in {spec.target_root}",
    )


def _checkout_tip(worktree: Path) -> BranchTip:
    """The commit this checkout's HEAD stands on.

    What removing the checkout would take with it. A linked worktree keeps a
    HEAD and a reflog of its own, and when no ref points at the commit HEAD
    names -- a branch deleted out from under a live checkout, which git
    permits through `update-ref` -- those two are the only things keeping that
    commit reachable. The removal takes both.

    `REFUTED` is a HEAD that names no commit, which is that exact state: the
    symbolic ref is still there and still spells this issue's branch, so every
    reading of WHOSE checkout it is comes back the same, and only resolving it
    says that what it holds cannot be named. `UNREADABLE` is the read that
    could not say either way. Both leave a caller nothing to prove the commit
    with, which is not the same as proving there is nothing to lose.
    """
    return _resolved_tip(
        _evidence_reads._hardened_read(worktree, "rev-parse", *_VERIFY_QUIETLY, _HEAD),
        f"HEAD in {worktree}",
    )


def _published_tip(spec: _config_models.RepoSpec, branch: str) -> BranchTip:
    """What the REMOTE says one branch is at, ignoring every local ref.

    The evidence a reclaim is entitled to lean on, and the reason it is not
    read off `refs/remotes/<remote>/<branch>`: that ref is local, it lives in
    the object store every per-issue worktree shares, and an agent can point
    it wherever it likes. Asked of the mirror, a branch that was never pushed
    anywhere reads as one the remote agrees with, and a base repointed onto an
    agent's own tip reads as a base that carries its work.

    Its three answers are the transport's own, mapped: `None` is a read that
    established nothing -- no token, a repository whose config could hijack
    the transport, an unreachable remote -- and the empty string is the remote
    answering that it does not carry this branch. That second one is the
    ordinary terminal shape rather than a problem: a merged pull request's
    head branch is deleted there.

    The clone is named as the tree the read runs in, so the transport-config
    refusal in front of it inspects the repository this classification is
    about rather than a per-issue checkout that may already be gone.

    The transport answers with `None` for the failures it recognizes and
    raises for the ones underneath them -- a git that cannot be spawned, a
    clone that has been removed since the scan named it, an askpass script
    the host would not let this process write. Those are the same answer to
    this caller, and the boundary is here rather than left to the caller
    because a probe whose contract is three answers must not have a fourth:
    an exception out of a classification takes down every other candidate in
    the pass along with this one.
    """
    try:
        published = branch_transport._remote_branch_tip(
            spec, spec.target_root, branch,
        )
    except Exception:
        log.warning(
            "could not ask the remote what %r is at from %s",
            branch, spec.target_root, exc_info=True,
        )
        return BranchTip(answer=ProbeAnswer.UNREADABLE)
    if published is None:
        return BranchTip(answer=ProbeAnswer.UNREADABLE)
    if not published:
        return BranchTip(answer=ProbeAnswer.REFUTED)
    return BranchTip(answer=ProbeAnswer.CONFIRMED, sha=published)


def _base_contains(
    spec: _config_models.RepoSpec, base: BranchTip, revision: str,
) -> ProbeAnswer:
    """Whether the base the remote named already carries `revision`.

    The proof that an artifact's commits are not lost by deleting it: a tip
    the base contains is work that has already landed, whatever route it took
    to get there. BOTH ends are things the caller established -- the base from
    the remote itself, the tip from the artifact that is about to go -- so
    nothing an agent can write decides the answer. Naming
    `refs/remotes/<remote>/<base>` here instead would hand that decision back
    to the object store the agent shares.

    A base the remote would not answer for, and one it says does not exist,
    arrive where a comparison that could not be taken arrives: there is
    nothing to measure against, so nothing about the revision is established.
    That is decided here rather than by each caller, so no caller can reach
    the comparison holding a base nobody named.

    The comparison itself is local, and it is sound there: ancestry between
    two object ids is content-addressed, and the hardened envelope turns off
    the two ways a repository can be told to serve one commit under another's
    name.

    `REFUTED` is git's own no. Anything else -- a base commit this clone has
    not fetched, a revision it cannot resolve, a repository that would not
    open -- is `UNREADABLE`, since none of them establishes that the base
    carries the commit and none of them establishes that it does not.
    """
    if base.answer is not ProbeAnswer.CONFIRMED:
        return ProbeAnswer.UNREADABLE
    contained = _evidence_reads._clone_read(
        spec, "merge-base", "--is-ancestor", revision, base.sha,
    )
    if contained is None:
        return ProbeAnswer.UNREADABLE
    if contained.returncode == 0:
        return ProbeAnswer.CONFIRMED
    if contained.returncode == _GIT_NEGATIVE:
        return ProbeAnswer.REFUTED
    log.debug(
        "could not measure %s against %s in %s: %s",
        revision, base.sha, spec.target_root, (contained.stderr or "").strip(),
    )
    return ProbeAnswer.UNREADABLE
