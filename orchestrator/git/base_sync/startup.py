# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Anchoring one auto-rebase, and the two ways starting it can end badly.

The pre-rebase SHA is the whole reason these helpers live together. It is the
lease a later force-push is pinned to and the anchor a crashed tick is
recovered from, so it has to be readable before git is allowed to move HEAD
and pinned before the rewrite runs -- an attempt that mutated the worktree
first and recorded the anchor second would leave a tick that died in between
with a rewritten branch nobody can compare against. Reading it fails closed,
and a rebase that then fails is aborted back onto it before the outcome is
routed: conflicted files are the dev agent's work, anything else is a park.

The attempt's own terms go down in the anchor's own statement for the same
reason the anchor does: they are what a later tick re-asks this attempt's
publication checks against, and read off the issue after a crash they would
compare today with today. So does the base tip the rebase is about to replay
onto, frozen off `<remote>/<base>` before git runs: that ref lives in a store
the worktree can write, so a reading taken once git has returned may name a
commit the replay was never made onto, and the evidence a landed head is later
routed with is held to this frozen tip (`attempt_records._recorded_onto`). A
ref that no longer names it once the rebase returns -- moved while git ran --
leaves the attempt naming no base at all, which proves nothing.
"""
from __future__ import annotations

from github.PullRequest import PullRequest

from orchestrator import config
from orchestrator.git import commands
from orchestrator.git.base_sync import attempts, conflicts, persistence, pre_pr
from orchestrator.git.base_sync.models import _AutoRebaseContext
from orchestrator.git.base_sync.state import (
    _AWAITING_HUMAN,
    _PARK_REASON,
    _PENDING_PUSH_SHA,
    _PENDING_REWRITE_BASE,
    _PENDING_REWRITE_PR,
    _PENDING_REWRITE_STAGE,
    _REASON_AUTO_BASE_REBASE_FAILED,
    log,
)
from orchestrator.git.publication import probes as publication_probes
from orchestrator.git.verification import probes


def _park_unreadable_pre_rebase_head(context: _AutoRebaseContext) -> None:
    """Fail closed when the lease and recovery anchor cannot be read."""
    log.error(
        "issue=#%d cannot read local HEAD before auto base rebase; "
        "parking awaiting human (no rebase attempted)",
        context.issue.number,
    )
    spec = context.spec
    persistence._park_auto_rebase_failure(
        context.gh,
        context.issue,
        context.state,
        message=(
            f"{config.HITL_MENTIONS} PR #{context.pr_number} is "
            f"{context.behind} commit(s) behind "
            f"`{spec.remote_name}/{spec.base_branch}`, "
            "but the orchestrator could not read local `HEAD` on "
            "the per-issue worktree before attempting the auto "
            "rebase. Force-with-lease pushes and the crash-recovery "
            "anchor both require a known pre-rebase SHA, so the "
            "rebase was skipped. Inspect the worktree's git state "
            "and reply on this issue with anything to retry."
        ),
        reason=_REASON_AUTO_BASE_REBASE_FAILED,
    )


def _record_auto_rebase_attempt(
    context: _AutoRebaseContext,
    before_sha: str,
    consumed_comment_id: int | None,
) -> None:
    """Persist the anchor, the attempt's terms, and any retry unpark.

    All of it before git runs, because every field here is something the
    branch moving would make unanswerable. The anchor is the head the pull
    request is standing on and the head the force-push behind this rebase is
    leased against. The TERMS beside it -- the pull request this attempt
    publishes onto and the stage it was entered from -- are what a later tick
    re-asks the attempt's own publication checks against: read off the issue
    then they would compare today with today, and a relabel or a repoint made
    while the process was down would pass as this tick's own.

    They go down here rather than with the head the rebase produces, and that
    is what makes the window between `git rebase` returning and the write
    recording its output recoverable at all. A crash there leaves a checkout
    on a replay nothing names -- but the terms on the comment still say which
    publication the attempt in flight was for.

    The base tip the rebase will replay onto is frozen here too
    (`_frozen_base`), before git runs, for the same reason: read once the
    replay exists it would be whatever the ref says then.
    """
    if consumed_comment_id is not None:
        context.state.set("last_action_comment_id", consumed_comment_id)
        context.state.set(_AWAITING_HUMAN, False)
        context.state.set(_PARK_REASON, None)
    context.state.set(_PENDING_PUSH_SHA, before_sha)
    context.state.set(_PENDING_REWRITE_PR, context.pr_number)
    context.state.set(_PENDING_REWRITE_STAGE, str(context.label))
    context.state.set(_PENDING_REWRITE_BASE, _frozen_base(context) or None)
    context.gh.write_pinned_state(context.issue, context.state)


def _frozen_base(context: _AutoRebaseContext) -> str:
    """The commit `<remote>/<base>` names in `context`'s checkout now, or "" where it reads as none.

    Resolved by the reading every later count of the replay takes
    (`publication.probes._branch_divergence`), so the tip frozen here and the
    one a landed head is counted against are spelled by one owner.
    """
    base = publication_probes._branch_divergence(context.spec, context.worktree, context.spec.base_branch)
    return base.tip if base.readable else ""


def _handle_failed_auto_rebase(
    context: _AutoRebaseContext,
    pr: PullRequest,
    conflicted_files: list[str],
) -> None:
    """Abort a failed rebase, then route conflicts or park other failures."""
    abort = commands._git_hardened("rebase", "--abort", cwd=context.worktree)
    if abort.returncode != 0:
        log.warning(
            "issue=#%d base rebase failed and abort failed: %s",
            context.issue.number,
            (abort.stderr or "").strip(),
        )
    attempts._clears_the_attempt(context.state)
    if conflicted_files:
        conflicts._route_pr_worktree_to_resolving_conflict(
            context.gh,
            context.spec,
            context.issue,
            context.state,
            context.pr_number,
            label=context.label,
            behind=context.behind,
            conflicted_files=conflicted_files,
            pr_head_sha=getattr(pr.head, "sha", None) or None,
        )
        return

    log.warning(
        "issue=#%d base rebase failed without conflicted files; "
        "parking awaiting human (refresh-only recovery on a new "
        "issue comment)",
        context.issue.number,
    )
    spec = context.spec
    persistence._park_auto_rebase_failure(
        context.gh,
        context.issue,
        context.state,
        message=(
            f"{config.HITL_MENTIONS} PR #{context.pr_number} is "
            f"{context.behind} commit(s) behind "
            f"`{spec.remote_name}/{spec.base_branch}` "
            "and the auto rebase failed for a non-conflict reason "
            "(planted hook, smudge filter, permissions, ...). The "
            "worktree was restored to the pre-rebase SHA via "
            "`git rebase --abort`. Investigate the worktree / hooks, "
            "then reply on this issue with anything once the "
            "underlying problem is fixed; the next polling tick will "
            "re-attempt the auto rebase."
        ),
        reason=_REASON_AUTO_BASE_REBASE_FAILED,
    )


def _start_auto_rebase(
    context: _AutoRebaseContext,
    pr: PullRequest,
    consumed_comment_id: int | None,
) -> str | None:
    """Anchor and execute the rebase, returning the known pre-rebase SHA."""
    before_sha = probes._head_sha(context.worktree) or ""
    if not before_sha:
        _park_unreadable_pre_rebase_head(context)
        return None
    _record_auto_rebase_attempt(context, before_sha, consumed_comment_id)
    succeeded, conflicted_files = pre_pr._rebase_base_into_worktree(
        context.spec, context.worktree,
    )
    if not succeeded:
        _handle_failed_auto_rebase(context, pr, conflicted_files)
        return None
    if _frozen_base(context) != (context.state.get(_PENDING_REWRITE_BASE) or ""):
        # The ref moved while git ran, so nothing says which tip the replay
        # sits on; the replay's own record carries the blank.
        context.state.set(_PENDING_REWRITE_BASE, None)
    return before_sha
