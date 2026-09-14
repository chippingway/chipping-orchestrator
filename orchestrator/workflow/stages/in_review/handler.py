# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One in_review tick, in the order its questions have to be asked.

The terminals come first so an external human merge wins over anything this
stage would otherwise compute -- the PR landing is the answer to every
remaining question.

The fresh-feedback scan comes before the drift check, and the order is load
bearing rather than stylistic. `user_content_hash` covers the title, the body,
AND every human issue-thread comment, so a plain review comment moves it
exactly like a body edit does. Asking drift first would resume the dev and
bounce the issue to `validating` for a comment that should have recorded
`pending_fix_*` bookmarks and flipped to `fixing`, which is the documented
contract for issue-thread feedback on an open PR.

The missing-`pr_number` park is the one question asked before the context
exists: without a pinned PR there is nothing to fetch, and the stage refuses
to infer one -- the issue got here by a manual relabel, so a human relabels it
back.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import guards as _guards, terminals as _terminals
from orchestrator.workflow.stages.in_review import (
    drift as _drift,
    feedback as _feedback,
    merge_gate as _merge_gate,
    models as _models,
)
from orchestrator.workflow.state import WorkflowLabel


def _park_missing_pr_number(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> None:
    """Park a manually-relabeled in_review issue that has no pinned `pr_number`.
    We don't infer the PR -- park once and let the human relabel back.
    """
    if state.get("awaiting_human"):
        return
    _guards._park_awaiting_human(
        gh, issue, state,
        # The two names the human has to type into GitHub are the labels
        # verbatim; the prose before them names the stage.
        f"{config.HITL_MENTIONS} `in_review` without a pinned `pr_number`; "
        "manual relabeling suspected. Set the workflow label back to "
        f"`{WorkflowLabel.VALIDATING}` (or `{WorkflowLabel.IMPLEMENTING}`) "
        "after fixing.",
        reason="missing_pr_number",
    )
    gh.write_pinned_state(issue, state)


def _handle_in_review(gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue) -> None:
    """Drive an in_review issue toward done / rejected, or hand fresh PR
    feedback off to the `fixing` stage.

    The handler always re-checks PR state (merged/closed) first so an external
    human merge wins over any orchestrator-side logic. Fresh actionable PR
    feedback on any of the four surfaces (issue thread, PR conversation,
    inline review, review summary) records pending-fix metadata in pinned
    state and flips the label to `fixing` immediately -- the dev resume and
    hand-back-to-`validating` cycle moves to the `fixing` handler. The
    orchestrator never merges from here: humans drive the merge. A
    mergeable PR whose current head completed the reviewer-approved
    final-docs handoff (or carries a real GitHub APPROVED review), with
    no standing human CHANGES_REQUESTED on that head, earns a one-shot
    HITL ping per head SHA so the human knows the PR is ready. An
    unmergeable PR parks awaiting human attention (no `resolving_conflict`
    route from this stage).

    User-content drift (a human edited the issue title/body while the PR
    was open) takes the dev-resume path here; both a pushed fix and a
    no-commit ACK bounce DIRECTLY back to `validating` (with
    `review_round` reset) so the reviewer re-evaluates against the
    updated body. Docs do not run on the drift exit: the single docs
    pass is deferred to the final-docs handoff after reviewer approval.
    """
    state = gh.read_pinned_state(issue)
    pr_number = state.get("pr_number")

    if pr_number is None:
        # Manual relabel from outside the validating path.
        _park_missing_pr_number(gh, issue, state)
        return

    ctx = _models._InReviewContext(
        gh, spec, issue, state, gh.get_pr(int(pr_number)), pr_number,
    )

    # Drain the shared PR/issue terminal arcs (merged PR -> `done`,
    # closed PR -> `rejected`, open PR + manually-closed issue ->
    # `rejected` without branch cleanup). The closed-with-merged-PR
    # path (Resolves #N auto-close) is handled by the merged branch
    # inside the helper, so the open-PR + closed-issue arc only fires
    # for issues a human closed directly.
    #
    # Caveat: once the helper
    # flips a manually-closed (but PR-still-open) issue to `rejected`,
    # the dispatcher's terminal-label branch is a no-op AND
    # `list_pollable_issues` only sweeps closed issues still labeled
    # `in_review` / `resolving_conflict`. A later PR close is never
    # observed by the orchestrator, so the operator must clean up the
    # worktree, local branch, and remote branch manually for the
    # "close issue first, then close PR" ordering.
    if _terminals._drain_review_pr_terminals(
        gh, spec, issue, state, ctx.pr, stage="in_review",
    ):
        return

    if _feedback._consume_fresh_feedback(ctx):
        return

    if _drift._handle_user_content_drift(ctx):
        return

    _merge_gate._handle_mergeable_gate(ctx)
