# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Handing a genuinely conflicted auto-rebase to the stage that resolves it.

`resolving_conflict` is reserved for a rebase that actually left conflicted
files, so a merely-behind-base branch the orchestrator can rewrite on its own
never arrives here and the label keeps meaning "a dev agent or a human has to
look at this". The round counter is seeded only when it is absent, because a PR
that keeps re-entering has to exhaust the cap rather than restart it, while a
handed head the last episode's counted round left behind is dropped, since it
is that episode's claim and not this one's -- and so is the publication record
a body edit's resume in that episode left beside a report since settled. The
relabel is what hands the work on -- the refresh runs before the handlers in
the same tick, so `_handle_resolving_conflict` picks the worktree up
immediately -- and the pinned state is written after it, so the counter is
committed by the same call that publishes every other durable field.
"""
from __future__ import annotations

import inspect
from typing import Any

from orchestrator.git.base_sync.models import _ConflictRouteContext
from orchestrator.git.base_sync.state import (
    _CONFLICT_HANDED_SHA,
    _CONFLICT_RESUME_KEYS,
    _CONFLICT_ROUND,
    _REVIEW_ROUND,
    log,
)
from orchestrator.workflow.state import WorkflowLabel, stage_name

_CONFLICT_ROUTE_SIGNATURE = inspect.Signature((
    inspect.Parameter("gh", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("spec", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("issue", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("state", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("pr_number", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("label", inspect.Parameter.KEYWORD_ONLY),
    inspect.Parameter("behind", inspect.Parameter.KEYWORD_ONLY),
    inspect.Parameter("conflicted_files", inspect.Parameter.KEYWORD_ONLY),
    inspect.Parameter("pr_head_sha", inspect.Parameter.KEYWORD_ONLY),
))


def _post_conflict_route_notice(context: _ConflictRouteContext) -> None:
    """Announce the conflicted rebase on the PR, best effort."""
    # Lazy import: the comment owner sits in the workflow layer above this
    # package, so binding it at module load would make every git-side
    # import pay for the GitHub client and prompt state it pulls in.
    from orchestrator.workflow.engine import comments as _comments
    spec = context.spec
    base_ref = f"{spec.remote_name}/{spec.base_branch}"
    try:
        _comments._post_pr_comment(
            context.gh, context.pr_number, context.state,
            f":mag: PR is {context.behind} commit(s) behind "
            f"`{base_ref}` and the auto "
            f"rebase left {len(context.conflicted_files)} conflicted file(s); "
            "orchestrator is attempting auto-resolution via the dev "
            f"agent (label: `{WorkflowLabel.RESOLVING_CONFLICT}`).",
        )
    except Exception:  # noqa: BLE001 - the PR notice is best effort at the GitHub boundary
        log.exception(
            "issue=#%s could not post auto-rebase notice to PR #%s",
            context.issue.number, context.pr_number,
        )


def _emit_conflict_route_event(context: _ConflictRouteContext) -> None:
    """Emit the `conflict_round` "entered" record for this route."""
    context.gh.emit_event(
        _CONFLICT_ROUND,
        issue_number=context.issue.number,
        stage=stage_name(context.label),
        pr_number=context.pr_number,
        sha=context.pr_head_sha or None,
        action="entered",
        conflict_round=int(context.state.get(_CONFLICT_ROUND) or 0),
        review_round=int(context.state.get(_REVIEW_ROUND) or 0),
        retry_count=context.state.get("retry_count"),
    )


def _route_pr_worktree_conflict_context(
    context: _ConflictRouteContext,
) -> None:
    """Persist and announce a normalized auto-rebase conflict route."""
    # Match `_handle_in_review`'s seeding: only initialize `conflict_round`
    # when absent, so a re-entry preserves the cap counter and a
    # perpetually-stuck PR can't ping-pong between handlers indefinitely.
    if context.state.get(_CONFLICT_ROUND) is None:
        context.state.set(_CONFLICT_ROUND, 0)
    # A head the last episode's counted round handed on, left by a write that
    # never landed, describes that episode's move rather than this one: read
    # here it would hand the conflicted head straight back to review. The
    # publication record a body edit's resume left beside a report since
    # settled is that episode's too, and read here it would park a report of
    # this one as the account of a commit it never described.
    for spent in (_CONFLICT_HANDED_SHA, *_CONFLICT_RESUME_KEYS):
        if context.state.get(spent) is not None:
            context.state.set(spent, None)

    _post_conflict_route_notice(context)
    log.info(
        "issue=#%d behind %s/%s by %d commit(s) with %d conflicted "
        "file(s); routing %r -> resolving_conflict so the handler "
        "drives the dev agent",
        context.issue.number,
        context.spec.remote_name,
        context.spec.base_branch,
        context.behind,
        len(context.conflicted_files),
        context.label,
    )
    _emit_conflict_route_event(context)
    context.gh.set_workflow_label(
        context.issue,
        WorkflowLabel.RESOLVING_CONFLICT,
    )
    context.gh.write_pinned_state(context.issue, context.state)


def _route_pr_worktree_to_resolving_conflict(
    *args: Any,
    **kwargs: Any,
) -> None:
    """Relabel a PR-having issue to `resolving_conflict` for real conflicts.

    Called by `_sync_pr_worktree_to_base` when the auto-rebase left
    unresolved conflicted files. Seeds `conflict_round` only when
    absent (so a re-entry preserves the cap counter and a perpetually-
    stuck PR can't ping-pong indefinitely), posts a PR notice naming
    the conflicted files, emits the `conflict_round` "entered" audit
    event, and flips the workflow label so the existing
    `_handle_resolving_conflict` handler picks the work up on the
    same tick (the handler runs after the refresh in `tick()`).

    `pr_head_sha` is the remote PR head SHA at the time the rebase
    was attempted -- threaded in by the caller from the same
    `gh.get_pr(pr_number)` it uses for the PR-state gate -- so the
    emitted `conflict_round` `action="entered"` record carries the
    same `sha` field every other emit site populates
    (`docs/observability.md` documents it as part of the event shape).
    """
    bound_fields = _CONFLICT_ROUTE_SIGNATURE.bind(*args, **kwargs)
    _route_pr_worktree_conflict_context(
        _ConflictRouteContext(**bound_fields.arguments),
    )


_route_pr_worktree_to_resolving_conflict.__signature__ = (
    _CONFLICT_ROUTE_SIGNATURE
)
