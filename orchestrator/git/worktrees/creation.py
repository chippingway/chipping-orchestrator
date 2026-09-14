# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Create issue and PR worktrees while preserving their unpushed commits.

Both creators consult the local contribution before removing any checkout.
PR restoration requires a fresh remote branch or an established absence, so a
failed fetch cannot replace a live PR's work with the base. The anchoring owner
handles branch movement after a caller has separately proved it is safe.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git import branch_transport, commands, locks
from orchestrator.git.worktrees import anchoring as _anchoring, naming as _naming, paths, recovery

# The channel is named for the worktree-lifecycle domain rather than for
# this module's path: operators filter the rendered
# `orchestrator.worktree_lifecycle` prefix and attach handlers to it, so
# every owner in this package reports where their filters already point.
log = logging.getLogger("orchestrator.worktree_lifecycle")

_WORKTREE_ADD = ("worktree", "add")

_WORKTREE_REMOVE_FORCE = ("worktree", "remove", "--force")


def _ensure_worktree(
    spec: _config_models.RepoSpec, issue_number: int, *, branch: str | None = None,
) -> Path:
    """Return a worktree on a per-issue branch, reusing one with unpushed work.

    The reuse is what lets the orchestrator survive a crash between codex
    committing and the orchestrator pushing -- without it, the next tick would
    wipe the worktree and we'd burn another codex run on the same prompt.

    `branch` overrides the default `_branch_name(spec, issue_number)`
    derivation so callers can anchor on an already-pinned branch (e.g.
    a legacy `orchestrator/issue-<n>` ref kept in pinned state when
    slug-namespacing landed) instead of forcing the issue onto a new
    branch and orphaning its existing PR.

    All git operations target `spec.target_root` and therefore mutate the
    parent clone's `.git/config`. The per-target_root lock (see
    `_target_root_lock`) serializes concurrent workers so two tick fan-out
    threads cannot collide on `.git/config.lock`. The lock is released
    before the caller starts the long-running agent run.
    """
    with locks._target_root_lock(spec.target_root):
        paths._repo_worktrees_root(spec).mkdir(parents=True, exist_ok=True)
        wt = paths._worktree_path(spec, issue_number)
        if branch is None:
            branch = _naming._branch_name(spec, issue_number)

        if wt.exists():
            if _has_new_commits(spec, wt):
                log.info(
                    "issue=#%d worktree has unpushed commits; reusing",
                    issue_number,
                )
                return wt
            commands._git(
                *_WORKTREE_REMOVE_FORCE, str(wt),
                cwd=spec.target_root,
            )

        branch_transport._authed_target_fetch(spec, spec.base_branch)

        have_branch = commands._git(
            *_anchoring._VERIFY_REF, branch, cwd=spec.target_root,
        ).returncode == 0
        if have_branch:
            worktree_result = commands._git(
                *_WORKTREE_ADD, str(wt), branch, cwd=spec.target_root,
            )
        else:
            worktree_result = commands._git(
                *_WORKTREE_ADD, "-b", branch, str(wt),
                f"{spec.remote_name}/{spec.base_branch}",
                cwd=spec.target_root,
            )
        if worktree_result.returncode != 0:
            raise RuntimeError(
                f"git worktree add failed: {worktree_result.stderr}"
            )
        return wt


def _ensure_pr_worktree(
    spec: _config_models.RepoSpec, issue_number: int, *, branch: str | None = None,
) -> Path:
    """Like `_ensure_worktree`, but restores the local branch from
    `origin/<branch>` when it is missing instead of branching from
    `origin/<base>`.

    `_ensure_worktree`'s fallback (`worktree add -b <branch> ... origin/<base>`)
    is right for a fresh implementing run -- a brand-new PR branch should
    start at the base. It is the WRONG fallback for `_handle_resolving_conflict`:
    once a PR exists, the conflict resolver MUST land on the same branch
    the PR is open against, with the dev's commits intact. A host
    restart, manual cleanup, or `git branch -D` between ticks deletes
    the local ref but leaves the PR's `origin/<branch>` ref alive on
    GitHub; rebuilding off `origin/<base>` would silently discard the
    PR's commits and leave the PR's conflicts unresolved forever.

    The base fallback comes back only when the REMOTE says the branch is
    gone, because then there is nothing left to discard. A local ref
    that is merely missing does not say that, and neither does a
    remote-tracking ref left behind by a fetch that failed. A merged PR whose branch GitHub
    auto-deleted is the case that matters: the issue keeps its
    `pr_number`, so every later tick routes here, and on a host that no
    longer has the local ref -- a fresh clone, an operator's cleanup --
    a hard failure would raise on every tick and the implementer would
    never run again. Whatever that branch carried is in the base by
    then, or was closed unmerged and is unreachable either way, so the
    checkout is rebuilt at the base and the dev starts from what landed.

    All git invocations run from `spec.target_root` (the orchestrator's
    own clone, not the agent-writable worktree) so authenticated fetch
    uses the operator's git config / credential helpers / SSH keys
    directly. The transport hardening that `_push_branch` applies is
    unnecessary for these, which carry no token of their own: the fetch
    that does goes through `branch_transport`, which hardens itself. What a
    linked worktree CAN reach in the parent clone is why the anchor below
    hardens the operations that write there.

    Serialized by the per-target_root lock for the same `.git/config.lock`
    reason described on `_ensure_worktree`.
    """
    with locks._target_root_lock(spec.target_root):
        paths._repo_worktrees_root(spec).mkdir(parents=True, exist_ok=True)
        wt = paths._worktree_path(spec, issue_number)
        if branch is None:
            branch = _naming._branch_name(spec, issue_number)

        if wt.exists():
            if _has_new_commits(spec, wt):
                log.info(
                    "issue=#%d worktree has unpushed commits; reusing",
                    issue_number,
                )
                return wt
            commands._git(
                *_WORKTREE_REMOVE_FORCE, str(wt),
                cwd=spec.target_root,
            )

        # Fetch both base and the PR's remote branch so either path
        # below has a fresh ref to anchor on. The base fetch decides
        # nothing on its own, but the branch fetch decides everything:
        # `refs/remotes/<remote>/<branch>` outlives the fetch that wrote
        # it, so a fetch that failed leaves a ref that still resolves and
        # still looks like the PR's head while naming whatever the last
        # successful fetch saw. The start point below is told whether
        # this one landed for exactly that reason.
        # `_authed_target_fetch` already uses the explicit
        # `+refs/heads/<branch>:refs/remotes/<remote>/<branch>` refspec
        # so single-branch / narrowed clones still create the
        # remote-tracking ref the `worktree add ... <remote>/<branch>`
        # fallback anchors on; the `+` prefix forces non-fast-forward
        # update against `--force-with-lease`-rewritten remote tips.
        _anchoring._fetch_for_restore(spec, issue_number, spec.base_branch)
        fetched = _anchoring._fetch_for_restore(spec, issue_number, branch)

        have_local = commands._git(
            *_anchoring._VERIFY_REF, branch, cwd=spec.target_root,
        ).returncode == 0
        if have_local:
            worktree_result = commands._git(
                *_WORKTREE_ADD, str(wt), branch, cwd=spec.target_root,
            )
        else:
            worktree_result = commands._git(
                *_WORKTREE_ADD, "-b", branch, str(wt),
                _pr_branch_start_point(spec, issue_number, branch, fetched),
                cwd=spec.target_root,
            )
        if worktree_result.returncode != 0:
            raise RuntimeError(
                f"git worktree add failed: {worktree_result.stderr}"
            )
        return wt


def _pr_branch_start_point(
    spec: _config_models.RepoSpec, issue_number: int, branch: str, fetched: bool,
) -> str:
    """Where a PR branch with no local ref left is rebuilt from.

    The PR's own remote head, whenever the remote still has one AND this tick
    just fetched it: the dev's commits live there and only there once the local
    ref is gone, so anchoring on `<remote>/<base>` would hand back a checkout
    the PR's work is missing from -- and the publication that follows would
    force-push that over the PR.

    `fetched` is what makes that ref worth anchoring on. A remote-tracking ref
    outlives the fetch that wrote it, so one left behind by a fetch that failed
    resolves perfectly well and names whatever the last successful fetch saw --
    which on an interrupted publication can be the tip the round opened on.
    Restored there, the recovery reads a branch back at its anchor, retires the
    marker as an operator's reset, and lets the conversation open another round
    while the plan sits published on a pull request nobody recorded. So an
    unrefreshed ref is not used at all: what happens next is decided by asking
    the remote, exactly as a missing ref is.

    The base is the answer only when the remote ITSELF says there is no such
    branch, and then it is the only answer there is. A merged PR whose branch
    GitHub auto-deleted keeps its `pr_number` on the issue, so every later tick
    comes here; naming a ref neither side has would fail the `worktree add` on
    every one of them and the issue would retry forever without an implementer
    ever running.

    A missing remote-tracking ref is NOT that answer on its own. A fetch that
    could not run leaves exactly the same gap -- an expired token, a remote that
    was unreachable, a host that has never fetched this branch -- and reading it
    as a deletion rebuilds a live PR at base, hands the developer a tree its
    commits are missing from, and force-pushes that over the PR. So the remote
    is asked, and only "no such ref" is absence: an unanswerable read or a
    branch that is plainly still there raises instead, leaving the checkout,
    the branch, and the PR exactly as they were for the next tick to retry.
    """
    pr_ref = f"{spec.remote_name}/{branch}"
    have_remote = fetched and commands._git(
        *_anchoring._VERIFY_REF, f"refs/remotes/{pr_ref}", cwd=spec.target_root,
    ).returncode == 0
    if have_remote:
        return pr_ref
    remote_tip = branch_transport._remote_branch_tip(
        spec, spec.target_root, branch,
    )
    if remote_tip is None:
        raise RuntimeError(
            f"cannot restore {branch}: no local ref, no fresh {pr_ref}, and "
            "the remote could not be asked whether that branch still exists",
        )
    if remote_tip:
        raise RuntimeError(
            f"cannot restore {branch}: no local ref and no fresh {pr_ref}, "
            f"but the remote still has that branch at {remote_tip}",
        )
    log.warning(
        "issue=#%d has no local %s and the remote has no such branch; "
        "rebuilding the checkout from %s/%s -- a merged PR's branch is "
        "deleted and what it carried is in the base", issue_number, branch,
        spec.remote_name, spec.base_branch,
    )
    return f"{spec.remote_name}/{spec.base_branch}"


def _has_new_commits(spec: _config_models.RepoSpec, worktree: Path) -> bool:
    commit_count_result = commands._git(
        "rev-list", "--count",
        f"{spec.remote_name}/{spec.base_branch}..HEAD",
        cwd=worktree,
    )
    if commit_count_result.returncode != 0:
        return False
    return recovery._commit_count_from_stdout(commit_count_result) > 0
