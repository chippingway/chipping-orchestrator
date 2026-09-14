# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The three probes that have to answer before any branch is overwritten.

Two of them exist for one decision: whether a worktree that is behind its
remote PR head may still be force-published. That is the one case where the
stage rewrites a branch it did not just produce, so both probes are written to
fail closed -- an unreadable fetch, an unparsable count, or an unrecognized head
all answer "no" and leave the conservative park in place.

The third is the worktree itself, and which restorer it uses is the whole
point: rebuilding from the PR branch keeps the PR's commits, while the
base-branch restorer would silently discard them.
"""
from __future__ import annotations

from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git import branch_transport as _branch_transport, commands as _git_commands
from orchestrator.git.worktrees import creation as _worktree_creation, naming as _naming, paths as _worktree_paths
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.conflicts import models as _models


def _ensure_conflict_worktree(ctx: _models._ConflictContext) -> Path:
    """Return the per-issue worktree, restoring it from `origin/<branch>` when
    it has been pruned.

    The PR-aware `_ensure_pr_worktree` (not `_ensure_worktree`) rebuilds from
    the PR branch so the PR's commits survive; `_ensure_worktree` would
    silently rebuild from `origin/<base>` and discard them.
    """
    wt = _worktree_paths._worktree_path(ctx.spec, ctx.issue.number)
    if not wt.exists():
        wt = _worktree_creation._ensure_pr_worktree(
            ctx.spec, ctx.issue.number,
            branch=_naming._resolve_branch_name(
                ctx.state, ctx.spec, ctx.issue.number,
            ),
        )
    return wt


def _pr_head_orchestrator_produced(state: PinnedState, pr) -> bool:
    """True when the remote PR head is a SHA the orchestrator itself recorded.

    Guards the force-publish of a diverged-but-already-rebased branch
    (the `behind > 0` exception in `_guard_diverged_worktree`): the
    orchestrator's own prior head -- the SHA `_handle_documenting`
    persists as `docs_checked_sha` on its success exits -- is the one
    case we can prove is safe to overwrite. An unrecognized head may
    carry a commit pushed directly to the PR branch, so a divergence
    from it must stay parked. PR heads from earlier in the lifecycle
    (the initial implementing push, an intermediate fixing push) are
    not currently recorded anywhere in pinned state, so the exception
    declines those by design rather than guessing.
    """
    head = getattr(getattr(pr, "head", None), "sha", None) or ""
    return bool(head) and head == state.get("docs_checked_sha")


def _already_rebased_onto_base(spec: _config_models.RepoSpec, wt: Path) -> bool:
    """True when the worktree HEAD already sits on top of `<remote>/<base>`.

    Re-fetches base first (the ahead/behind check that calls this runs
    BEFORE the handler's own base fetch lower down) and checks that no
    base commit is missing from HEAD. Used to recognize a worktree the
    dev already rebased in an earlier run -- a no-op rebase that only
    needs publishing, not the diverged-branch park.

    Fails closed on fetch failure: a stale `<remote>/<base>` ref would
    let `rev-list HEAD..<remote>/<base>` report "no missing commits"
    purely because the local mirror predates the real base tip, which
    would incorrectly enable the force-publish path without proving HEAD
    is on the current base.
    """
    fetch = _branch_transport._authed_fetch(
        spec,
        f"+refs/heads/{spec.base_branch}:"
        f"refs/remotes/{spec.remote_name}/{spec.base_branch}",
        cwd=wt,
    )
    if fetch.returncode != 0:
        return False
    base_distance_result = _git_commands._git_hardened(
        "rev-list", "--count",
        f"HEAD..{spec.remote_name}/{spec.base_branch}", cwd=wt,
    )
    if base_distance_result.returncode != 0:
        return False
    try:
        return int((base_distance_result.stdout or "").strip() or 0) == 0
    except ValueError:
        return False
