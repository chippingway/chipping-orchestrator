# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Putting the PR worktree back on the real PR head, or refusing to continue.

Every step here fails closed, and the thing it is failing closed against is
specific: a local docs commit authored before the body edit is exactly what the
next tick's recovered-commit shortcut would push without spawning an agent, and
under `SQUASH_ON_APPROVAL=off` it would apply cleanly on top of the next
approval. So a fetch, probe, reset, or clean that cannot prove the worktree is
back on `<remote>/<branch>` parks the issue rather than letting the unwind
report success.

The ahead/behind probe is spelled out here rather than reached through the
shared divergence reading, and what it buys is the DETAIL: this park is the one
an operator has to debug a git invocation from, so the exit code, stderr, and
stdout the probe answered with go into the log beside it. Both fail closed --
neither reports a reading that did not happen as a clean worktree, which is
what would let the stale commit survive. The reset is paired with `git clean -fd` because
`reset --hard` leaves untracked files -- and a docs agent's output is often a
new file or a new directory under `docs/` that no reviewer ever approved.
"""
from __future__ import annotations

import logging
from contextlib import suppress

from orchestrator.config import settings as config
from orchestrator.git import branch_transport as _branch_transport, commands as _git_commands
from orchestrator.git.verification import status as _worktree_status
from orchestrator.workflow.stages.documenting import models as _models, parks as _parks
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


def _documenting_drift_fetch(ctx: _models._DocumentingContext, wt) -> bool:
    """Fetch `<remote>/<branch>` before the drift-unwind ahead/behind probe.

    Returns True on success; on a fetch failure parks with `fetch_failed` and
    returns False -- a stale local docs commit against the OLD body silently
    riding into the next approval is worse than parking.
    """
    spec = ctx.spec
    branch = ctx.branch
    fetch_branch = _branch_transport._authed_fetch(
        spec,
        f"+refs/heads/{branch}:refs/remotes/{spec.remote_name}/{branch}",
        cwd=wt,
    )
    if fetch_branch.returncode != 0:
        log.error(
            "issue=#%d documenting drift fetch failed: %s",
            ctx.issue.number, (fetch_branch.stderr or "").strip(),
        )
        _parks._park_documenting(
            ctx,
            f"{config.HITL_MENTIONS} `git fetch "
            f"{spec.remote_name} {branch}` failed while routing "
            f"documenting drift back to `{WorkflowLabel.VALIDATING}`; the "
            "local "
            "worktree may carry an unpushed docs commit against "
            "the OLD body -- see orchestrator logs.",
            "fetch_failed",
        )
        return False
    return True


def _documenting_drift_probe(ctx: _models._DocumentingContext, wt):
    """Probe the worktree's ahead/behind vs. `<remote>/<branch>`.

    Run the probe inline rather than through the shared divergence reading,
    which answers the same question and fails closed the same way: what this
    road wants beside its park is the exit code, stderr, and stdout git
    answered with, since this is the park an operator debugs a git invocation
    from. A reading that established nothing is a park either way -- read as
    "in sync" it would silently let an unpushed local docs commit against the
    OLD body survive into the next final-docs hop's recovered-commit
    shortcut.

    Returns `(ahead, behind)` on success; on a probe failure parks with
    `worktree_reset_failed` and returns None.
    """
    spec = ctx.spec
    branch = ctx.branch
    probe = _git_commands._git_hardened(
        "rev-list", "--left-right", "--count",
        f"refs/remotes/{spec.remote_name}/{branch}...HEAD",
        cwd=wt,
    )
    parts = (probe.stdout or "").strip().split()
    if probe.returncode == 0 and len(parts) == 2:
        with suppress(ValueError):
            return int(parts[1]), int(parts[0])
    log.error(
        "issue=#%d documenting drift ahead/behind probe "
        "failed (rc=%s stderr=%s stdout=%s)",
        ctx.issue.number, probe.returncode,
        (probe.stderr or "").strip(),
        (probe.stdout or "").strip(),
    )
    _parks._park_documenting(
        ctx,
        f"{config.HITL_MENTIONS} could not probe local vs. "
        f"`{spec.remote_name}/{branch}` while routing "
        f"documenting drift back to `{WorkflowLabel.VALIDATING}`; the "
        "local "
        "worktree may carry an unpushed docs commit against "
        "the OLD body -- see orchestrator logs.",
        "worktree_reset_failed",
    )
    return None


def _documenting_drift_hard_reset(ctx: _models._DocumentingContext, wt) -> bool:
    """Hard-reset + clean the worktree to `<remote>/<branch>`.

    `git reset --hard` drops local docs commits / tracked edits; the follow-up
    `git clean -fd` removes untracked docs files and any under-`docs/` subdirs
    the docs agent created but the reviewer never approved. Returns True on
    success; on a git failure parks with `worktree_reset_failed` and returns
    False.
    """
    spec = ctx.spec
    branch = ctx.branch
    reset = _git_commands._git_hardened(
        "reset", "--hard", f"{spec.remote_name}/{branch}", cwd=wt,
    )
    if reset.returncode != 0:
        log.error(
            "issue=#%d documenting drift reset failed "
            "(rc=%s stderr=%s)",
            ctx.issue.number, reset.returncode,
            (reset.stderr or "").strip(),
        )
        _parks._park_documenting(
            ctx,
            f"{config.HITL_MENTIONS} `git reset --hard "
            f"{spec.remote_name}/{branch}` failed while "
            "routing documenting drift back to "
            f"`{WorkflowLabel.VALIDATING}`; the local worktree still "
            "carries docs work against the OLD body -- "
            "see orchestrator logs.",
            "worktree_reset_failed",
        )
        return False
    clean = _git_commands._git_hardened("clean", "-fd", cwd=wt)
    if clean.returncode != 0:
        log.error(
            "issue=#%d documenting drift clean failed "
            "(rc=%s stderr=%s)",
            ctx.issue.number, clean.returncode,
            (clean.stderr or "").strip(),
        )
        _parks._park_documenting(
            ctx,
            f"{config.HITL_MENTIONS} `git clean -fd` "
            "failed while routing documenting drift back "
            f"to `{WorkflowLabel.VALIDATING}`; the local worktree may "
            "still carry untracked docs files against "
            "the OLD body -- see orchestrator logs.",
            "worktree_reset_failed",
        )
        return False
    return True


def _reset_documenting_drift_worktree(
    ctx: _models._DocumentingContext, wt,
) -> bool:
    """Reconcile the PR worktree to `<remote>/<branch>` while routing
    documenting drift back to `validating`.

    A recovered local docs commit (a prior tick committed but parked
    before the push landed -- ahead > 0 vs. `<remote>/<branch>`) was
    authored against the OLD body; leaving it on disk would let the next
    final-docs tick's recovered-commit shortcut push it without ever
    spawning a fresh docs agent against the new requirements --
    especially under `SQUASH_ON_APPROVAL=off`, where the
    reviewer-approved head is the dev's PR head (no rewrite gap), so the
    recovered docs commit applies cleanly on top of the next approval.
    Fetch the branch, probe ahead/behind, and hard-reset + clean any
    local docs work (including uncommitted / untracked edits) so the next
    approved round starts from the actual PR head.

    Reset whenever the worktree is ahead (a recovered commit), behind (the
    remote PR head moved past local HEAD, so the reviewer must re-evaluate the
    actual head), or dirty (`_worktree_dirty_files` surfaces both
    modified-tracked and untracked paths, so any non-empty list is a cleanup
    trigger).

    Returns True on success (worktree in sync). Returns False when a git
    step failed and the issue was parked -- a stale local commit silently
    riding into the next approval is worse than parking.
    """
    if not _documenting_drift_fetch(ctx, wt):
        return False
    probe = _documenting_drift_probe(ctx, wt)
    if probe is None:
        return False
    ahead, behind = probe
    dirty = _worktree_status._worktree_dirty_files(wt)
    if ahead > 0 or behind > 0 or dirty:
        return _documenting_drift_hard_reset(ctx, wt)
    return True
