# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Unpushed-commit probes over the issue's current-layout branch.

Every probe here inspects the parent clone rather than a per-issue
worktree, so a caller can ask what a branch carries even when the worktree
it belongs to is gone. Only the current-layout name is ever probed for work:
a flat `orchestrator/issue-<n>` branch is no issue's artifact, nothing here
reports it as one to recover or publish, and the creators refuse a checkout
standing on it, so its commits stay where they are for manual disposition.
"""
from __future__ import annotations

import subprocess

from orchestrator.config import models as _config_models
from orchestrator.git import commands, locks
from orchestrator.git.worktrees import naming as _naming


def _branch_has_unpushed_commits(
    spec: _config_models.RepoSpec, issue_number: int,
) -> str | None:
    """Return the issue's branch when it carries unpushed commits, or None.

    The branch is the current-layout `_branch_name(spec, issue_number)` and
    nothing else, so what comes back is always one the rest of the tick could
    act on: the `_handle_implementing` question-relabel guard convicts a
    branch carrying commits no conversation stage vouched for, and names it in
    the operator message so the cleanup hint (`git branch -D <name>`) points
    at the right ref.

    Inspects the parent clone directly so the answer does not depend on a
    per-issue worktree existing on disk. The relabel guard needs this: if
    the operator manually removes the worktree (or
    `_cleanup_question_worktree` partially failed) but the local
    branch survives with question-agent commits, the
    worktree-only `_has_new_commits` / `_worktree_dirty_files`
    checks would report "clean" and the relabel-clear would let
    `_ensure_worktree` restore the branch in a fresh worktree;
    the recovered-worktree shortcut would then push those commits
    as if a dev session authored them.

    Returns None when:

    * the branch does not exist (no state to inspect);
    * it sits exactly at `<remote>/<base>` (a fresh-from-base reset);
    * the `rev-list` itself errors (transient git failure -- the
      caller's later steps will surface the underlying problem if
      it persists).

    Serialized via `_target_root_lock` for the same
    `.git/config.lock` reason described on `_ensure_worktree`;
    `RLock` re-entry keeps callers that already hold the lock
    safe.
    """
    branch = _naming._branch_name(spec, issue_number)
    base_ref = f"refs/remotes/{spec.remote_name}/{spec.base_branch}"
    with locks._target_root_lock(spec.target_root):
        if _branch_commit_count(spec, branch, base_ref) > 0:
            return branch
    return None


def _branch_tip_sha(spec: _config_models.RepoSpec, branch: str) -> str:
    """Return the SHA one named local branch points at, or '' if it has none.

    The absolute-SHA counterpart to `_branch_has_unpushed_commits`: that probe
    answers "is this branch ahead of base", which cannot tell a commit made
    since some moment from commits the branch already carried. A caller
    holding a recorded SHA -- the discussion stage's round anchor -- needs the
    tip itself to compare against, or an issue whose branch arrived with a
    dev's commits reads as having been committed to just now.

    The branch is named by the caller rather than derived, because the caller
    is the one that knows which ref its recorded SHA belongs to: the discussion
    stage records the branch its round opened on beside the anchor, and the
    tip it measures has to be that ref's. Inspects the parent clone, so the
    answer survives the worktree being gone; returns '' when the branch does
    not exist or the read fails, which callers treat as "nothing to
    attribute".
    """
    with locks._target_root_lock(spec.target_root):
        tip_result = commands._git(
            "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}",
            cwd=spec.target_root,
        )
    if tip_result.returncode != 0:
        return ""
    return (tip_result.stdout or "").strip()


def _branch_commit_count(
    spec: _config_models.RepoSpec, branch: str, base_ref: str,
) -> int:
    """Return commits unique to a local branch, or zero on probe failure."""
    local_ref = f"refs/heads/{branch}"
    have_local = commands._git(
        "rev-parse", "--verify", "--quiet", local_ref,
        cwd=spec.target_root,
    ).returncode == 0
    if not have_local:
        return 0
    commit_count_result = commands._git(
        "rev-list", "--count", f"{base_ref}..{local_ref}",
        cwd=spec.target_root,
    )
    if commit_count_result.returncode != 0:
        return 0
    try:
        return _commit_count_from_stdout(commit_count_result)
    except ValueError:
        return 0


def _commit_count_from_stdout(count_result: subprocess.CompletedProcess) -> int:
    """Parse a `git rev-list --count` result, treating empty output as zero."""
    return int((count_result.stdout or "0").strip() or "0")
