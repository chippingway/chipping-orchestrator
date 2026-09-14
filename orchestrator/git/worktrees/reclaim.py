# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The three teardown steps a maintenance pass spends a proof on.

Every step here is pinned to a commit somebody established, and every one of
them is refused by git itself when what it finds is not that commit. That is
the whole difference between this owner and the best-effort teardown in
``cleanup``: a stage handler tearing down the issue it has just driven knows
what the artifacts are, and a stale ref there is tidiness. A maintenance pass
knows only what a reading told it some seconds ago, and between the reading and
the mutation an agent can commit, a human can push, and a checkout can be
written in -- so what it deletes has to be the thing that was proved and
nothing else.

The pinning is git's, not this module's, which is what makes it hold against a
race rather than merely against a slow reader:

* the checkout is removed WITHOUT `--force`, so git's own refusal over a
  modified or untracked tree stands between the proof and the deletion;
* the remote branch goes under a lease naming the proven commit, so a branch
  pushed since is refused by the remote rather than overwritten here;
* the local ref goes through `update-ref -d` with the proven commit as its
  expected value, so a branch an agent committed onto is refused by the ref
  store -- and with `--no-deref`, so a symbolic ref of that name is deleted as
  itself rather than followed to whatever it points at.

Nothing here decides WHETHER a step should run, in what order, or what a
failure costs: that is ``maintenance``'s, which is also the only caller. Each
step answers a single bool -- whether the artifact is now gone -- and an
absence is that answer too, so a pass repeating over a teardown that half
finished takes the rest of it and reports the part already done as done.

A single bool means every step's boundary is total. Underneath them are a
process spawn, a per-root lock, a token lookup, an askpass script written to
disk, and a session around all of it: each answers for the failures it
recognizes and raises for the ones beneath them. An exception out of one step
would end the pass for every OTHER candidate behind this one -- which is the
one way a refused deletion can cost more than the artifact it is about -- so
what leaves this module is always the answer "not gone", with the reason in
the log.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git import commands, locks, ref_transport

# The channel is named for the worktree-lifecycle domain rather than for this
# module's path: operators filter the rendered `orchestrator.worktree_lifecycle`
# prefix and attach handlers to it, so a step that would not run reports where
# their filters already point.
log = logging.getLogger("orchestrator.worktree_lifecycle")

_LOCAL_REF_PREFIX = "refs/heads/"

# The removal git refuses over a tree carrying anything of its own. The forcing
# flag is absent by design and not by omission: it is the only thing standing
# between a proof taken seconds ago and a tree an agent has written in since.
_WORKTREE_REMOVE = ("worktree", "remove")

# The deletion that states what the caller established the ref was at, and
# refuses to follow a symbolic ref of that name to somewhere else.
_REF_DELETE = ("update-ref", "--no-deref", "-d")


def _still_there(worktree: Path) -> bool:
    """Whether anything is still at the path this checkout was found at.

    `lstat` rather than `exists`, so a symlink left where the checkout was
    answers for itself instead of for whatever it points at -- and so a host
    that will not answer at all is not read as an absence. A path that is
    genuinely gone is the one failure that is not a refusal: the checkout this
    pass was to remove is not there, which is the state the removal was for.
    """
    try:
        worktree.lstat()
    except FileNotFoundError:
        return False
    except OSError as read_error:
        log.warning(
            "could not read the checkout %s before removing it: %s",
            worktree, read_error,
        )
    return True


def _remove_recognized_worktree(
    spec: _config_models.RepoSpec, worktree: Path,
) -> bool:
    """Remove one recognized checkout, without forcing anything.

    True when the checkout is no longer on this host, an absence included: a
    pass re-running over a teardown that already took the tree has nothing left
    to do about it, and reporting that as a failure would keep the candidate
    reported forever.

    Not forced, which is the point of the step. `worktree remove` refuses a
    tree carrying modified or untracked paths, so the classification's own
    reading of the tree is backed by git's at the moment of the deletion --
    the one reading a race cannot get in front of. What git does NOT refuse
    over is a path the repository's own ignore rules cover, which is why the
    classification asks about those separately and keeps the candidate itself.

    Held under the lock every mutation of this clone's worktrees and branches
    serializes on, and run hardened for the reason every read of these paths
    is: the checkout is a tree an agent writes in and it shares a clone with
    the repository this command runs in, so a planted `core.hooksPath` or
    `core.fsmonitor` would run on the removal too.
    """
    if not _still_there(worktree):
        return True
    try:
        with locks._target_root_lock(spec.target_root):
            removed = commands._git_hardened(
                *_WORKTREE_REMOVE, str(worktree), cwd=spec.target_root,
            )
    except Exception:
        log.warning(
            "could not run the removal of the checkout %s",
            worktree, exc_info=True,
        )
        return False
    if removed.returncode != 0:
        log.warning(
            "the checkout %s was not removed: %s",
            worktree, (removed.stderr or "").strip(),
        )
        return False
    return True


def _delete_remote_branch_at(
    spec: _config_models.RepoSpec, branch: str, tip_sha: str,
) -> bool:
    """Delete one branch on the remote, leased to the commit that was proved.

    Through the ref transport rather than the GitHub API, because the lease is
    what makes this safe to run at all: the API's delete takes a branch name
    and removes whatever is under it, while a leased push states the commit the
    caller established was there and is refused by the remote when the branch
    has moved on. A branch somebody pushed to between the proof and here is not
    the branch anybody cleared.

    The clone is named as the tree the push runs in, so the transport-config
    refusal in front of it inspects the repository this pass is about rather
    than a per-issue checkout that has just been removed.

    The boundary is total for the reason the other two steps carry one: the
    transport answers False for the failures it recognizes -- a token it could
    not resolve, a config that could hijack it, a remote that refused -- and
    raises for the ones underneath, from a git it could not spawn to an askpass
    script the host would not let this process write. Both are the same answer
    here, and letting the second out would take every candidate still behind
    this one down with it.
    """
    try:
        return ref_transport._delete_remote_ref(
            spec,
            spec.target_root,
            ref=f"{_LOCAL_REF_PREFIX}{branch}",
            expected=tip_sha,
        )
    except Exception:
        log.warning(
            "could not ask the remote to let go of %r at %s",
            branch, tip_sha, exc_info=True,
        )
        return False


def _delete_local_ref_at(
    spec: _config_models.RepoSpec, branch: str, tip_sha: str,
) -> bool:
    """Delete one local branch, only while it still stands on the proved commit.

    `update-ref -d <ref> <oldvalue>` rather than `branch -D`, for the two
    things the plumbing form says that the porcelain one does not. It names the
    commit the ref must still be at, so a branch an agent has committed onto
    since the proof is refused by the ref store instead of deleted on the
    strength of a stale reading. And `--no-deref` deletes the ref that was
    named rather than the one it might point at, so a symbolic ref left under a
    branch name cannot redirect the deletion at another branch entirely.

    False on every answer that is not git's own success, the missing ref
    included: `update-ref` fails when there is nothing to delete, and this
    module does not paper over that -- the caller reads what the branch is at
    first, and an absence is its answer to give.

    Held under the lock the worktree mutations and every other ref write in
    this clone serialize on.
    """
    ref = f"{_LOCAL_REF_PREFIX}{branch}"
    try:
        with locks._target_root_lock(spec.target_root):
            deleted = commands._git_hardened(
                *_REF_DELETE, ref, tip_sha, cwd=spec.target_root,
            )
    except Exception:
        log.warning(
            "could not run the deletion of %s in %s",
            ref, spec.target_root, exc_info=True,
        )
        return False
    if deleted.returncode != 0:
        log.warning(
            "%s was not deleted at %s: %s",
            ref, tip_sha, (deleted.stderr or "").strip(),
        )
        return False
    return True
