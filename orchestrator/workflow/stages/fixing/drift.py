# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The rebase a parked fix will never get from anyone else.

The per-tick base sync deliberately stands down on every `awaiting_human`
park, so a validating-route transient park whose recovery keeps failing can sit
forever while the base moves out from under its worktree -- and the underlying
cause is often that very base advance. This owner is the one exit from that:
classify the drift, say so on the PR, and hand the branch to
`resolving_conflict`, which owns reconciling it before the next reviewer round.

Two drift shapes reconcile through the same label, and telling them apart is
the whole classification: a worktree behind base needs a rebase, while one
already rebased locally but never pushed needs a force-publish over a stale
remote head. Everything else -- a missing worktree, a dirty one an operator may
be inspecting, or a branch genuinely in sync with the PR -- reports no drift,
because there the transient condition really is the blocker and the HITL
contract says a human answers it.

Which parks arrive here is the other half of that, and it is the recovery's to
decide: only a condition that has not resolved does, because only there can a
base advance be the cause. A park the branch reading itself withheld the clear
from never reaches this owner at all -- what is missing there is evidence about
the checkout, and the reconciliation this one hands off to publishes that
checkout with no report debt staged for whatever it turns out to carry.

The `pending_fix_*` bookmarks and in_review watermarks are left untouched on
the way out, so the eventual in_review re-entry still re-discovers the feedback
that started the loop.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.git import commands as _git_commands
from orchestrator.git.verification import probes as _verification_probes, status as _worktree_status
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.fixing import models as _models, state as _state
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


def _stale_pr_head_reason(base_ref: str, pr_head: str, local_head: str) -> str:
    """Explain a live PR head that lags an unpushed local rebase onto base."""
    pr_short = pr_head[:8]
    local_short = local_head[:8]
    return (
        f"already rebased onto `{base_ref}`, but the PR head "
        f"(`{pr_short}`) is stale (local `{local_short}`)"
    )


def _fixing_drift_reason(
    ctx: _models._FixingContext, wt: Path, base_ref: str,
) -> str | None:
    """Classify how a clean parked `fixing` worktree has drifted from its PR,
    or return ``None`` when it is in sync (the transient park is the real
    blocker, not drift).

    Two drift shapes both reconcile via `resolving_conflict`:

      * worktree BEHIND `<remote>/<base>` -> needs a rebase.
      * worktree already rebased locally but the rewrite was never pushed, so
        local HEAD differs from the (stale) remote PR head -> needs a
        force-publish (`_handle_resolving_conflict` recognizes an already-
        rebased worktree and publishes it instead of parking).

    Trusts the once-per-tick base fetch `_refresh_base_and_worktrees` ran
    before dispatch (mirrors `_sync_worktree_with_base`, which also measures
    behind without re-fetching). A stale ref can only undercount (stay parked)
    or, on the rare case the per-tick fetch failed, overcount -- and
    `_handle_resolving_conflict` re-fetches before it acts, so an overcount
    self-corrects. The routing decision is cheap: base drift is a local
    `rev-list HEAD..<remote>/<base>`, and the unpushed-rebase check compares
    local HEAD to `pr.head.sha` (the live remote head fetched this tick).
    """
    behind_r = _git_commands._git(
        "rev-list", "--count", f"HEAD..{base_ref}", cwd=wt,
    )
    if behind_r.returncode != 0:
        return None
    try:
        behind = int((behind_r.stdout or "0").strip() or "0")
    except ValueError:
        return None

    if behind > 0:
        return f"{behind} commit(s) behind `{base_ref}`"

    # On top of base: is the local branch out of sync with the PR head? `pr`
    # was fetched fresh this tick, so `pr.head.sha` is the live remote head. A
    # mismatch means the worktree carries a rebase that was never pushed --
    # `_handle_resolving_conflict` republishes it (over a stale,
    # orchestrator-produced PR head).
    local_head = _verification_probes._head_sha(wt) or ""
    pr_head = getattr(getattr(ctx.pr, "head", None), "sha", None) or ""
    if local_head and pr_head and local_head != pr_head:
        return _stale_pr_head_reason(base_ref, pr_head, local_head)
    return None  # in sync with the PR -> genuine dev question


def _post_fixing_conflict_notice(
    ctx: _models._FixingContext, pr_number: int, drift_reason: str,
) -> None:
    """Post the worktree-drift reroute notice to the PR, swallowing a transient
    comment failure (the relabel still proceeds; the next tick re-fetches)."""
    try:
        _comments._post_pr_comment(
            ctx.gh, pr_number, ctx.state,
            f":mag: PR worktree is out of sync ({drift_reason}) and the "
            f"`{WorkflowLabel.FIXING}` fix-loop is parked on a stuck transient "
            "condition that the self-recovery could not clear. Routing "
            f"`{WorkflowLabel.FIXING}` -> "
            f"`{WorkflowLabel.RESOLVING_CONFLICT}` to reconcile the branch "
            "before the next reviewer round.",
        )
    except Exception:
        log.exception(
            "issue=#%s could not post worktree-drift reroute notice to PR #%s",
            ctx.issue.number, pr_number,
        )


def _route_parked_fixing_to_conflict(
    ctx: _models._FixingContext, drift_reason: str,
) -> None:
    """Relabel a drifted parked `fixing` worktree to `resolving_conflict` so
    its handler reconciles the branch before the next reviewer round.

    The `pending_fix_*` bookmarks and in_review watermarks are left untouched
    so the eventual `in_review` re-entry still re-discovers the feedback
    (mirrors the refresh-time conflict detour).
    """
    pr_number = int(ctx.state.get("pr_number"))
    # Seed `conflict_round` only when absent so a re-entry preserves the cap
    # counter (mirrors `_route_pr_worktree_to_resolving_conflict`).
    if ctx.state.get(_state._CONFLICT_ROUND) is None:
        ctx.state.set(_state._CONFLICT_ROUND, 0)
    ctx.state.set(_state._AWAITING_HUMAN, False)
    ctx.state.set(_state._PARK_REASON, None)
    _post_fixing_conflict_notice(ctx, pr_number, drift_reason)
    ctx.gh.emit_event(
        _state._CONFLICT_ROUND,
        issue_number=ctx.issue.number,
        stage="fixing",
        pr_number=pr_number,
        sha=getattr(getattr(ctx.pr, "head", None), "sha", None) or None,
        action="entered",
        conflict_round=int(ctx.state.get(_state._CONFLICT_ROUND) or 0),
        review_round=int(ctx.state.get(_state._REVIEW_ROUND) or 0),
        retry_count=ctx.state.get("retry_count"),
    )
    log.info(
        "issue=#%s parked `fixing` worktree is out of sync (%s); routing -> "
        "resolving_conflict",
        ctx.issue.number, drift_reason,
    )
    ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.RESOLVING_CONFLICT)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)


def _reconcile_parked_fixing(ctx: _models._FixingContext) -> bool:
    """Hand a stuck validating-route transient `fixing` park to
    `resolving_conflict` on worktree drift.

    Called from the `recovery == "stuck"` branch of
    `_dispatch_validating_recovery` and from nowhere else: that word says
    `_try_recover_validating_transient_park` could not clear the transient
    condition (e.g. `push_failed` keeps failing), while the underlying cause
    may be a base advance that landed under the park. An `"unsettled"` answer
    stops in the dispatch above instead, since there it is the reading of the
    branch that is missing and a reroute would publish the checkout regardless.

    The per-tick base sync (`_sync_pr_worktree_to_base`) deliberately stands
    down on every `awaiting_human` park, so the integration work nobody else
    will do is stranded and the issue sits parked forever.

    Returns False (issue stays parked) when the worktree is missing, dirty (an
    operator may be inspecting a dirty-tree park), or the worktree is already
    in sync with the PR head (the transient condition is the real blocker, not
    drift). Returns True after routing the drift to `resolving_conflict`.
    """
    spec = ctx.spec
    wt = _worktree_paths._worktree_path(spec, ctx.issue.number)
    if not wt.exists():
        return False
    if _worktree_status._worktree_dirty_files(wt):
        return False

    base_ref = f"{spec.remote_name}/{spec.base_branch}"
    drift_reason = _fixing_drift_reason(ctx, wt, base_ref)
    if drift_reason is None:
        return False

    _route_parked_fixing_to_conflict(ctx, drift_reason)
    return True
