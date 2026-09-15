# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Prepare ordinary split plans, create their children, and publish the parent summary.

The parent records the expected child count before creation. Only children
without dependencies are activated after the summary and parent label land.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.decomposition import child_creation as _child_creation, state as _state
from orchestrator.workflow.stages.decomposition.models import _SplitPlan
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


def _prepare_split_plan(
    gh: GitHubClient, issue: Issue, state: PinnedState, plan: _SplitPlan,
) -> None:
    state.set("expected_children_count", len(plan.children_manifest))
    state.set(_state._UMBRELLA, plan.is_umbrella)
    gh.write_pinned_state(issue, state)


def _create_child_issues(
    gh: GitHubClient, issue: Issue, state: PinnedState,
    children_manifest: list, is_umbrella: bool,
) -> _SplitPlan | None:
    """Crash-safe child issue creation loop for a `split` manifest.

    Returns the populated split plan on success, or None when a create/seed
    step failed and the parent was parked (caller must return).

    Crash-safe sequence:
      1. Persist `expected_children_count` (and the umbrella flag) BEFORE
         creating any child. The half-finished recovery uses these to tell
         a partial loop apart from a completed one, and to finalize to the
         right label after a mid-loop SIGKILL.
      2. For each child: create the GitHub issue, then IMMEDIATELY record
         its number in parent state (before any further non-idempotent
         work). A SIGKILL between these two steps is unavoidable; persisting
         first means the worst case is an orphan child without seeded
         `parent_number`, not a duplicate child created by a decomposer
         respawn.
      3. Seed child pinned state. Failure here parks but parent state
         already records the child, so no respawn happens.
    """
    plan = _SplitPlan.start(children_manifest, is_umbrella)
    _prepare_split_plan(gh, issue, state, plan)
    for idx, _child in enumerate(children_manifest):
        if not _child_creation._create_planned_child(gh, issue, state, plan, idx):
            return None
    return plan


def _split_summary(plan: _SplitPlan) -> tuple[str, WorkflowLabel]:
    summary = "\n".join(
        f"- #{number}: {child['title']}" for number, child in plan.created
    )
    if plan.is_umbrella:
        announcement = (
            f":bookmark_tabs: decomposer split this into {len(plan.created)} "
            f"child issue(s); marking parent as `{WorkflowLabel.UMBRELLA}` "
            "(no implementation of its own; will auto-resolve once every "
            f"child resolves):\n\n{summary}"
        )
        return announcement, WorkflowLabel.UMBRELLA
    announcement = (
        f":bookmark_tabs: decomposer split this into {len(plan.created)} "
        f"child issue(s):\n\n{summary}"
    )
    return announcement, WorkflowLabel.BLOCKED


def _activate_initial_split_children(
    gh: GitHubClient, issue: Issue, plan: _SplitPlan,
) -> None:
    # Activation: flip no-dep children from `blocked` to `ready`.
    # Best-effort -- if any flip fails the parent's `_handle_blocked`
    # walk handles it on its next dependency poll (the walk treats a
    # child with no recorded deps as deps-satisfied).
    for idx, (child_number, _) in enumerate(plan.created):
        if str(idx) in plan.dep_graph:
            continue
        try:
            gh.set_workflow_label(gh.get_issue(child_number), WorkflowLabel.READY)
        except Exception:
            log.exception(
                "issue=#%s could not flip child #%d to ready; the parent's "
                "_handle_blocked walk will retry on its next dependency poll",
                issue.number, child_number,
            )


def _finalize_split(
    gh: GitHubClient, issue: Issue, state: PinnedState, plan: _SplitPlan,
) -> None:
    """Post the split summary, flip the parent label, and activate children.

    children/dep_graph/decomposed_at are already durable from the
    incremental writes in `_create_child_issues`. Flip the parent label to
    `blocked` (or `umbrella` when the parent has no implementation work of
    its own), then activate no-dep children. Activation only runs AFTER the
    final parent-state write, so a crash here cannot leave a runnable
    orphan child against a `decomposing`-labeled parent.
    """
    summary_intro, final_label = _split_summary(plan)
    _comments._post_issue_comment(gh, issue, state, summary_intro)
    gh.set_workflow_label(issue, final_label)
    gh.write_pinned_state(issue, state)
    _activate_initial_split_children(gh, issue, plan)
