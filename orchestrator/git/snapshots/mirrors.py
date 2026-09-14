# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Local snapshot mirrors, qualified by repository and verified before teardown.

The remote operations in `refs.py` hold the target-root lock across a fetch and
its resolution here. Reclamation proves this mirror absent before deleting the
remote ref, so a surviving mirror still establishes that reclamation is owed.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git import commands, locks
from orchestrator.git.snapshots import namespace
from orchestrator.git.worktrees import naming as _naming

log = logging.getLogger("orchestrator.git_plumbing")

# What separates a truncated repository segment from the digest that keeps it
# injective, in the spelling the branch namespace already uses for its own
# lossy rewrites.
_DIGEST_MARK = "__h"


def local_snapshot_ref(spec: _config_models.RepoSpec, ref: str) -> str:
    """The local ref THIS repository's copy of one snapshot lands under.

    The repository segment is the same sanitized slug the per-issue branch
    namespace is built from, so what keeps two `REPOS` entries off one
    another's branches keeps them off one another's snapshots. Published
    because the child a split creates is told to read the snapshot out of this
    name, so the instruction and the fetch have to be one string.

    Bounded here rather than by the namespace, because bounding it is a
    rewrite and a rewrite has to stay injective: configuration bounds a slug
    at nothing, so a long one is replaced by a prefix of itself plus the
    content digest the branch namespace already uses for its own lossy
    rewrites. Two repositories with a shared prefix therefore still land on
    two refs, which is the whole property the segment exists for.
    """
    return namespace.local_snapshot_ref(
        ref=ref, repository=_repository_segment(spec.slug),
    )


def local_snapshot_present(
    spec: _config_models.RepoSpec, worktree: Path, *, ref: str, sha: str,
) -> bool:
    """Whether this host still holds its copy of one snapshot, at `sha`.

    The free half of "is this snapshot still there", and it is sound because
    of the ORDER a reclamation runs in rather than as a guess about it: the
    mirror is taken down first and the remote ref is not touched until it has
    provably gone, so a mirror still here says this host has reclaimed
    nothing. That is enough for a reader that only needs to know whether it
    may still reuse the candidate, and it costs a local `rev-parse` and no
    network at all -- which is what keeps a per-tick guard off the wire for
    every child of a live split.

    `sha` is the commit the caller was promised, and it is required rather
    than optional because this ref lives in the object store the agents' own
    worktrees share. A name that resolves to SOMETHING says only that a ref
    exists under it: an agent -- or anything else with the clone -- can point
    it at whatever it likes, and a reader that asked about existence alone
    would then answer "not reclaimed" for a mirror carrying another commit
    entirely. That answer is spent twice over: the child resumes against work
    nobody adjudicated, and the remote it would otherwise have asked -- the
    one that would have said `ABSENT` or `MISMATCH` and parked it -- is never
    asked at all. So the reading is an identity check, and only the exact
    candidate this ref preserved answers yes.

    Peeled to a commit by the resolution below, so a mirror pointed at a tag
    object wrapping the candidate still answers for the candidate; every other
    commit, and every unreadable store, answers no and sends the caller to the
    remote, which is the authority anyway.
    """
    if not sha:
        return False
    return _local_ref_sha(worktree, local_snapshot_ref(spec, ref)) == sha


def _repository_segment(slug: str) -> str:
    """A ref-safe, bounded, injective segment naming one repository."""
    sanitized = _naming._sanitize_branch_segment(slug)
    if len(sanitized) <= namespace.MAX_REPOSITORY_SEGMENT:
        return sanitized
    digest = _naming._slug_digest(slug)
    kept = namespace.MAX_REPOSITORY_SEGMENT - len(digest) - len(_DIGEST_MARK)
    return _DIGEST_MARK.join((sanitized[:kept], digest))


def _mirror_dropped(
    spec: _config_models.RepoSpec, worktree: Path, ref: str,
) -> bool:
    """Take this host's copy of a snapshot down, and say whether it went.

    Answered by a READ rather than by an exit code, for the reason every
    teardown in this repository is: `update-ref -d` is best-effort against a
    ref store other worktrees of the same clone share, and a caller whose next
    step depends on the answer may not trust the return of the command that
    was supposed to produce it. A ref that was never fetched is already gone
    and answers yes without a complaint of its own.

    What depends on the answer is the remote delete above it, and through that
    the child-side reuse guard: a mirror is what says "no reclamation has
    happened" without spending a request, so one left standing beside a
    reclaimed remote ref is a child cleared to work from a candidate nobody
    vouches for any more. A mirror nothing deletes also holds the snapshot's
    objects against `gc` for as long as the clone lives.

    Which is why the read has to ESTABLISH the mirror is gone rather than
    merely fail to find it: a delete that failed and a verification that could
    not run are the same tick, and that tick is precisely the one this order
    exists to stop.
    """
    mirror = local_snapshot_ref(spec, ref)
    with locks._target_root_lock(spec.target_root):
        dropped = commands._git_hardened(
            "update-ref", "-d", mirror, cwd=worktree,
        )
        gone = _local_ref_absent(worktree, mirror)
    if gone:
        return True
    log.error(
        "%s: local snapshot %s was not proven gone (%s); leaving %s on the "
        "remote rather than reclaiming it behind a copy that may outlive it",
        spec.slug, mirror, (dropped.stderr or "").strip(), ref,
    )
    return False


def _local_ref_absent(worktree: Path, ref: str) -> bool:
    """Whether the ref store was read and holds nothing under `ref`.

    An established absence rather than a resolution that failed, and the two
    are different answers however alike they look: `rev-parse` reports a ref
    that is not there, a git directory that has gone, and a store nothing can
    read with the same non-zero exit. A teardown verified through it therefore
    reads "could not ask" as "already gone" -- so the one tick where both the
    delete and the check fail is the one that takes the remote ref while this
    host's copy is still standing, which is the exact state the child-side
    guard cannot tell from a world nothing was reclaimed in, and it lasts
    until a receipt lands.

    `for-each-ref` separates the two by exit code: it succeeds and names
    nothing when the store holds no such ref, and fails when the store could
    not be read at all. What it printed is matched by name rather than
    counted, because a ref is also a prefix pattern -- what was asked about is
    this exact ref, and something nested under its name is not it.
    """
    listed = commands._git_hardened(
        "for-each-ref", "--format=%(refname)", "--end-of-options", ref,
        cwd=worktree,
    )
    if listed.returncode != 0:
        log.error(
            "could not read %s in %s: %s",
            ref, worktree, (listed.stderr or "").strip(),
        )
        return False
    return ref not in (listed.stdout or "").split()


def _local_ref_sha(worktree: Path, ref: str) -> str | None:
    """Resolve a fetched snapshot ref in this checkout, or None.

    Hardened for the reason every read of an agent-writable worktree is, and
    for the one that matters most to a commit named by id: `refs/replace/` and
    the graft file both make git answer for one commit under another's name,
    and both live in the clone the agent's worktree shares. Peeled to a commit
    so a ref somebody pointed at a tag object reads as the work rather than as
    the label on it.
    """
    resolved = commands._git_hardened(
        "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}",
        cwd=worktree,
    )
    named = (resolved.stdout or "").strip()
    if resolved.returncode != 0 or not named:
        return None
    return named
