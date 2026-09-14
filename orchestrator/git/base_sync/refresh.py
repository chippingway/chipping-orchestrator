# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The per-tick base refresh: which worktrees sync, and by which route.

One authenticated fetch of `origin/<base>` per spec feeds every issue
worktree that survived the previous tick, and what runs here is the sequence
that fetch starts: an in-flight scheduler claim keeps a worktree out from
under the worker still holding it, the `refresh_selection` owner beside this
one answers whether the issue behind a discovered directory lets its branch be
touched at all, a dirty pre-PR tree is left alone, and the lag against base
says whether there is anything to carry over.
What survives is routed by whether pinned state already carries a PR --
`pre_pr` rebases the local branch nobody has pushed yet, while the PR-aware
coordinator has to keep the pushed head and the reviewer's SHA in step.
"""
from __future__ import annotations

from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git import branch_transport as _branch_transport, commands as _commands
from orchestrator.git.base_sync import (
    pr as _pr,
    pre_pr as _pre_pr,
    refresh_selection as _selection,
    state as _state,
)
from orchestrator.git.base_sync.models import _AutoRebaseRequest
from orchestrator.git.verification import status as _worktree_status
from orchestrator.git.worktrees import paths as _paths
from orchestrator.github import client as _client
from orchestrator.scheduler.service import IssueScheduler

log = _state.log


def _worktree_behind_base(
    spec: _config_models.RepoSpec, worktree: Path, issue_number: int,
) -> int | None:
    """Return the base lag, or None when the comparison cannot be read."""
    base_ref = f"{spec.remote_name}/{spec.base_branch}"
    behind_result = _commands._git(
        "rev-list", "--count", f"HEAD..{base_ref}", cwd=worktree,
    )
    if behind_result.returncode != 0:
        log.debug(
            "issue=#%d skipping base sync: rev-list failed: %s",
            issue_number,
            (behind_result.stderr or "").strip(),
        )
        return None
    try:
        return int((behind_result.stdout or "0").strip() or "0")
    except ValueError:
        return None


def _sync_worktree_with_base(
    gh: _client.GitHubClient, spec: _config_models.RepoSpec, worktree: Path, issue_number: int,
) -> None:
    """Bring one per-issue worktree up to date with the configured base.

    Pre-PR worktrees are rebased locally when clean. PR worktrees always
    reach the PR-aware coordinator so a pinned crash-recovery anchor is
    honored even when local HEAD already contains the latest base.

    A lag that cannot be counted at all ends the sync, with one exception: a
    pinned anchor. There the failure IS the answer -- the checkout the
    interrupted attempt left names a commit nothing here can read, so no
    comparison of what it did can be trusted -- and ending the sync would
    leave the anchor for a handler the dispatcher holds back while it stands.
    So it is reset and parked on the PR-aware coordinator's own gates instead.
    """
    issue = _selection._base_sync_issue(gh, issue_number)
    if issue is None:
        return

    state = gh.read_pinned_state(issue)
    if _selection._issue_skips_base_sync(
        issue, issue_number, state, worktree,
    ):
        return

    pr_number = state.get("pr_number")
    if pr_number is None and _worktree_status._worktree_dirty_files(worktree):
        log.debug(
            "issue=#%d skipping base sync: worktree has uncommitted changes",
            issue_number,
        )
        return

    behind = _worktree_behind_base(spec, worktree, issue_number)
    if behind is None:
        if pr_number is not None and state.get(_state._PENDING_PUSH_SHA):
            # No lag to route on, so the request carries none.
            _pr._sync_unreadable_pr_worktree(_AutoRebaseRequest(
                gh, spec, issue, state, worktree, int(pr_number), 0,
            ))
        return
    if pr_number is not None:
        _pr._sync_pr_worktree_to_base(
            gh, spec, issue, state, worktree, int(pr_number), behind,
        )
        return
    if behind:
        _pre_pr._sync_pre_pr_worktree(spec, worktree, issue_number, behind)


def _sync_discovered_worktree(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    worktree: Path,
    issue_number: int,
    scheduler: IssueScheduler | None,
) -> None:
    """Sync one discovered worktree unless its handler is still active."""
    if scheduler is not None and scheduler.is_active(
        spec.slug, issue_number,
    ):
        log.debug(
            "repo=%s issue=#%d active in scheduler; skipping base "
            "sync until the worker completes", spec.slug, issue_number,
        )
        return
    try:
        _sync_worktree_with_base(gh, spec, worktree, issue_number)
    except Exception:
        log.exception(
            "repo=%s issue=#%d base sync failed; continuing",
            spec.slug, issue_number,
        )


def _refresh_base_and_worktrees(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    *,
    scheduler: IssueScheduler | None = None,
) -> None:
    """Fetch `origin/<base>` once for the spec and bring every existing
    per-issue worktree up to date.

    Runs at the start of each tick so a base-branch update on the remote
    propagates into in-flight issue worktrees. The per-stage
    `_ensure_*_worktree` helpers only fetch base on (re)creation, so a
    worktree that survives across ticks would otherwise stay anchored at
    whatever `origin/<base>` looked like when it was first added.

    Two paths depending on whether a PR already exists for the issue:

    * **Pre-PR worktrees** (no `pr_number` in pinned state): rebase
      the local worktree onto `origin/<base>` -- no remote yet, so there
      is nothing to push.

    * **PR-having worktrees** (validating / documenting / in_review /
      fixing): rebasing
      locally WITHOUT pushing would diverge local HEAD from `pr.head.sha` and
      break the validating reviewer (it reads local HEAD, so it would
      review a SHA that isn't on the PR) and
      `_squash_and_force_push`'s `--force-with-lease=<original_head>`
      (the lease compares against the un-rebased remote tip). So
      `_sync_pr_worktree_to_base` attempts the rebase in the refresh
      itself: on a clean rebase it pushes (force-with-lease pinned to
      the pre-rebase SHA), resets `review_round`, and relabels to
      `validating` so the reviewer re-runs against the rewritten
      branch directly; the single docs pass is deferred to the post-
      approval handoff to `documenting` in `_handle_validating`. Only
      when the rebase actually leaves conflicted files does the issue
      get relabeled to `resolving_conflict` -- the
      `_handle_resolving_conflict` handler then drives the dev agent to
      resolve the conflict. Issues already labeled
      `resolving_conflict` are left alone (the handler runs this tick
      anyway); other labels are skipped (no PR worktree to refresh in
      those states).

    Rebase keeps the PR history linear after sibling PRs land. Every
    pushed rebase resets `review_round`, so the reviewer must re-run
    against the rewritten SHA before any merge gate can pass.

    Conflicts on the pre-PR path abort the rebase so the worktree stays
    on its original SHA -- conflict resolution still belongs to
    `_handle_resolving_conflict`. Dirty worktrees are skipped so a
    crash-recovered tree with uncommitted edits is never disturbed
    (mirrors `_on_dirty_worktree`'s rule). All failures are logged at
    info/warning and swallowed: keeping every issue moving matters more
    than perfect base sync.

    `scheduler`, when supplied, is consulted before each per-issue
    worktree sync: an issue whose handler is currently in flight in
    that scheduler is skipped this tick. Without this gate, a polling
    pass can rebase a pre-PR worktree under a still-running agent or
    relabel/state-mutate a PR worktree while its handler is still
    running, racing the base refresh against the live worker. The
    scheduler's `submit` path also rejects a duplicate active issue,
    so the workflow handler itself does not run for the in-flight
    issue this tick -- the refresh skip keeps the worktree contract
    matching that "active issues are skipped until completion"
    guarantee. `None` preserves the legacy behavior so direct test
    invocations that supply no scheduler still refresh every worktree.
    """
    fetch_r = _branch_transport._authed_target_fetch(spec, spec.base_branch)
    if fetch_r.returncode != 0:
        log.warning(
            "repo=%s base fetch of %s/%s failed: %s",
            spec.slug, spec.remote_name, spec.base_branch,
            (fetch_r.stderr or "").strip(),
        )
        return

    root = _paths._repo_worktrees_root(spec)
    if not root.exists():
        return

    for worktree in sorted(root.iterdir()):
        issue_number = _selection._issue_worktree_number(worktree)
        if issue_number is not None:
            _sync_discovered_worktree(
                gh, spec, worktree, issue_number, scheduler,
            )
