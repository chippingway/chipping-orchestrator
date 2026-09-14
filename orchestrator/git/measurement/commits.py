# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The two commits a size measurement is taken between, each proven first.

Both ends are object ids this owner establishes, never refs the count is left
to resolve for itself, because everything the number is used for outlives the
tick that took it. The candidate is adjudicated over several ticks and a
restart, so a reading of `HEAD` here and a diff of `HEAD` a moment later are
answers about two different commits the instant anything moves the branch. The
base is worse than moving: `refs/remotes/<remote>/<base>` names the base but
lives in the object store the issue's own worktree shares, so an agent that
commits its code, repoints that ref at its own commit, and commits again leaves
a base-relative diff measuring its work against itself. What the REMOTE says
the branch is at is the one answer nothing on this host can rewrite.

Proving is a separate step from naming for the same reason it is elsewhere in
this package: a diff that names a commit git cannot resolve FAILS, and a failed
read is a candidate with no size rather than a small one. The two ends prove it
differently. The remote's tip is routinely an id this clone has not fetched yet
-- the base moves on its own between the tick's fetch and the measurement
minutes later -- so the object is fetched and re-asked for, and only an id the
store really holds is handed back. The candidate is peeled instead: an id that
will not peel to a commit is one this host does not have, which is work made
somewhere else and nothing here may substitute a newer HEAD for it, and an id
that peels to a DIFFERENT one was a label on the work rather than the work.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git import branch_transport, commands
from orchestrator.git.measurement.models import (
    FrozenCommit,
    MeasurementFailure,
    _BaseObject,
)
from orchestrator.git.verification import probes as verification_probes

# The channel the authenticated transport already reports on: the reads below
# are an `ls-remote`, a fetch, and a `rev-parse`, so an operator following a
# measurement that could not be taken is reading the same plumbing they filter
# for when a fetch or a push misbehaves.
log = logging.getLogger("orchestrator.git_plumbing")

# What a base the remote answered for -- with "" -- is reported as. The read
# succeeded, so there is no stderr to quote and nothing failed; what stopped
# the freeze is the answer itself, and an operator told only "the base could
# not be frozen" would go looking for a transport fault that never happened.
_NO_SUCH_BRANCH = "the remote does not carry that branch"

# What a fetch that failed silently is reported as, so a base this host still
# lacks always says something. A fetch reporting nothing and a fetch that
# reported a reason are the same failure to the caller, and only one of them
# leaves an operator anywhere to start.
_FETCH_SAID_NOTHING = "the fetch reported no reason"


def _freeze_base_commit(
    spec: _config_models.RepoSpec, worktree: Path,
) -> FrozenCommit:
    """Freeze the exact commit the remote says the base branch is at.

    Frozen, not merely read: the id is what this candidate is measured against
    now and what every retry after a crash measures against too, so a base that
    advances mid-adjudication cannot change a candidate's size or its verdict.

    Both ways the remote read can come back empty are one answer here. None is
    the read having failed -- a missing token, a worktree whose config could
    hijack the transport, an unreachable remote -- and "" is the remote saying
    it does not carry that branch; neither establishes a commit, and a
    measurement with one end missing is a failure to measure rather than a
    small candidate.

    An id the remote DID name and this host cannot read comes back beside its
    failure rather than instead of it. Nothing may measure against it -- that
    is what `is_frozen` refuses -- but it is the only record of which commit
    this attempt was about, and a caller that persisted the failure without it
    would have nothing to retry: the next pass would ask the remote again and
    freeze whatever the branch had moved to since, measuring a different pair
    under the same generation.

    Whichever way it stops, what the step said for itself comes back with the
    typed reason. The two are read minutes and a process apart -- the failure
    is persisted, reported on both sinks, and turned into a park a human reads
    -- and by then nothing else holds the line git wrote. Both members reach
    this owner already scrubbed, so recording one cannot publish a token.
    """
    read = branch_transport._remote_branch_read(
        spec, worktree, spec.base_branch,
    )
    if not read.sha:
        detail = read.detail or _NO_SUCH_BRANCH
        log.warning(
            "%s: the remote would not name %s, so the base a candidate in %s "
            "is measured against could not be frozen: %s",
            spec.slug, spec.base_branch, worktree, detail,
        )
        return FrozenCommit(
            failure=MeasurementFailure.BASE_UNREADABLE, detail=detail,
        )
    base = _base_object_present(spec, worktree, read.sha)
    if base.present:
        return FrozenCommit(sha=read.sha)
    log.warning(
        "%s: base %s of %s is not in the local object store even after a "
        "fetch, so no diff can be taken against it: %s",
        spec.slug, read.sha, spec.base_branch, base.detail,
    )
    return FrozenCommit(
        sha=read.sha,
        failure=MeasurementFailure.BASE_ABSENT,
        detail=base.detail,
    )


def _base_object_present(
    spec: _config_models.RepoSpec, worktree: Path, base_sha: str,
) -> _BaseObject:
    """Whether the frozen base is readable here, fetching once if it is not.

    The fetch lands in `target_root`, whose object store this linked worktree
    shares, so what it brings is readable from the checkout the diff is taken
    in. Its exit status is deliberately not the answer: a fetch that reported
    success without bringing this commit leaves the caller exactly where a
    failed one does, so the store is asked again either way.

    What the fetch SAID is kept even though what it returned decides nothing,
    and that is not a contradiction: the store answers whether a diff can be
    taken, while the line git wrote is the only thing that tells an operator
    which fetch to fix. Every caller here is asking about one exact object --
    the base this attempt froze, or the one a record already names -- so the
    fetch either supplied that commit or it did not, and a caller left with a
    bare "no" cannot tell a network that was down from a branch the remote
    rewrote.
    """
    if verification_probes._commit_present(worktree, base_sha):
        return _BaseObject(present=True)
    fetched = branch_transport._authed_target_fetch(spec, spec.base_branch)
    if verification_probes._commit_present(worktree, base_sha):
        return _BaseObject(present=True)
    return _BaseObject(
        detail=commands._first_reported_line(fetched.stderr or "")
        or _FETCH_SAID_NOTHING,
    )


def _prove_candidate_commit(worktree: Path, revision: str) -> FrozenCommit:
    """Resolve `revision` to the one commit id a measurement may name.

    Two questions, because they fail differently and a caller has to tell them
    apart. Resolving is the first: `--verify` makes git answer with exactly one
    id or with nothing, so a branch name that no longer exists, a detached
    checkout with no commit on it, or a hand-edited revision comes back as a
    reading that established nothing instead of as a list a caller would take
    the first line of. `--end-of-options` keeps a revision that begins with a
    dash from being read as a flag.

    Being a commit this repository holds is the second, and it is asked by
    peeling rather than by looking the id up as it stands. Two answers come out
    of that one step. An id whose object is missing cannot be peeled, which is
    the reading a SHA recorded on another host produces: git resolves a full
    object id to itself whether or not this repository has ever seen it, so it
    comes back from the first step looking exactly like a commit that is here,
    and the diff that would spend it fails -- reporting no paths and no lines,
    which is what a candidate that changes nothing reports too. And an id that
    IS here but is not a commit -- an annotated tag, whose own object is a tag
    pointing at one -- peels to the commit it names, so what gets recorded is
    the work rather than the label somebody put on it. A record naming a tag
    object would be evidence about the wrong kind of thing: nothing downstream
    could compare it to a branch tip, and the tag can be moved or deleted while
    the commit cannot.

    An id that resolved and would not peel comes back BESIDE its failure, the
    way an unreadable base does. Nothing may measure against it -- `is_frozen`
    refuses it -- but it is the only record of which commit this attempt was
    about, and a caller that reported it and dropped it would leave the retry
    with nothing to ask for: the next pass would prove whatever the checkout
    points at by then and measure that instead. A revision that would not
    resolve at all names nothing, and comes back naming nothing.

    Hardened for the reason every read of an agent-writable worktree is, and
    for one that is specific to naming commits by id: `refs/replace/<oid>` and
    the graft file both make git serve one commit under another's name, and
    both are writable from the worktree the agent runs in. The hardened
    envelope turns object replacement off, so the id proved here is the commit
    that will be measured and published rather than a stand-in for it.
    """
    resolved = commands._git_hardened(
        "rev-parse", "--verify", "--end-of-options", revision, cwd=worktree,
    )
    named = (resolved.stdout or "").strip()
    if resolved.returncode != 0 or not named:
        log.warning(
            "candidate revision %r does not resolve in %s: %s",
            revision, worktree, (resolved.stderr or "").strip(),
        )
        return FrozenCommit(failure=MeasurementFailure.CANDIDATE_UNREADABLE)
    peeled = commands._git_hardened(
        "rev-parse", "--verify", "--end-of-options", f"{named}^{{commit}}",
        cwd=worktree,
    )
    candidate_sha = (peeled.stdout or "").strip()
    if peeled.returncode != 0 or not candidate_sha:
        log.warning(
            "candidate %s is not a commit %s can read, so its size cannot be "
            "measured here: %s",
            named, worktree, (peeled.stderr or "").strip(),
        )
        return FrozenCommit(
            sha=named, failure=MeasurementFailure.CANDIDATE_ABSENT,
        )
    return FrozenCommit(sha=candidate_sha)
