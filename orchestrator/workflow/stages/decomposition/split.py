# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The order a `split` manifest becomes child issues in, and why it is that order.

Creating a child issue is not undoable and the process can die between any two
statements, so every write here is placed to make the worst crash recoverable
rather than to read well. `expected_children_count` and the umbrella flag go
down before the first child exists, because they are what tells the next tick's
recovery a partial loop from a finished one. Each child's number is then
recorded in the parent BEFORE anything else is done with it, so a crash in that
window costs an orphan child the operator can see rather than a duplicate the
respawned decomposer would create. Seeding the child's own pinned state comes
last for the same reason: it can fail into a park while the parent already
knows the child exists.

The final activation walk runs after the parent's last state write, so a crash
between them cannot leave a runnable child pointing at a parent still labeled
`decomposing`. Its label flips are best-effort -- a child with no recorded
dependencies reads as deps-satisfied on the parent's next `_handle_blocked`
walk, which is the retry.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import settings as config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments, guards as _guards, usage as _usage
from orchestrator.workflow.stages.decomposition import state as _state
from orchestrator.workflow.stages.decomposition.models import _SplitPlan
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


def _prepare_split_plan(
    gh: GitHubClient, issue: Issue, state: PinnedState, plan: _SplitPlan,
) -> None:
    state.set("expected_children_count", len(plan.children_manifest))
    state.set(_state._UMBRELLA, plan.is_umbrella)
    gh.write_pinned_state(issue, state)


def _child_initial_labels() -> list[str]:
    """Labels every split child is born with: only the initial `blocked`
    workflow label. Activation later flips no-dep children to `ready`.
    """
    return [WorkflowLabel.BLOCKED]


def _write_child_pinned_state(
    gh: GitHubClient, new_issue: Issue, parent_number: int,
) -> None:
    """Write a freshly-created child's initial pinned state (parent link and
    creation stamp)."""
    child_state = PinnedState()
    child_state.set(_state._PARENT_NUMBER, parent_number)
    child_state.set(_state._CREATED_AT, _usage._now_iso())
    gh.write_pinned_state(new_issue, child_state)


def _park_child_create_failure(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    idx: int,
    child: dict,
) -> None:
    log.exception(
        "issue=#%s could not create child %d (%r)",
        issue.number, idx, child.get("title"),
    )
    _guards._park_awaiting_human(
        gh, issue, state,
        f"{config.HITL_MENTIONS} could not create child issue index={idx} "
        f"({child.get('title')!r}); manual intervention needed (check "
        "orchestrator logs).",
        reason="child_create_failed",
    )
    gh.write_pinned_state(issue, state)


def _persist_created_child(
    gh: GitHubClient, issue: Issue, state: PinnedState, plan: _SplitPlan,
) -> None:
    state.set(_state._CHILDREN, [number for number, _ in plan.created])
    if plan.dep_graph:
        state.set("dep_graph", plan.dep_graph)
    state.set("decomposed_at", _usage._now_iso())
    gh.write_pinned_state(issue, state)


def _seed_created_child(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    new_issue: Issue,
    child: dict,
) -> bool:
    try:
        _write_child_pinned_state(gh, new_issue, issue.number)
    except Exception:
        log.exception(
            "issue=#%s could not seed pinned state on child #%d",
            issue.number, new_issue.number,
        )
        _guards._park_awaiting_human(
            gh, issue, state,
            f"{config.HITL_MENTIONS} created child #{new_issue.number} "
            f"({child.get('title')!r}) but could not seed its pinned state "
            "with `parent_number`; manual intervention needed (seed "
            "parent_number on the child or close it).",
            reason="child_seed_failed",
        )
        gh.write_pinned_state(issue, state)
        return False
    return True


def _create_planned_child(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    plan: _SplitPlan,
    idx: int,
) -> bool:
    child = plan.children_manifest[idx]
    try:
        new_issue = gh.create_child_issue(
            title=child["title"],
            body=child["body"],
            parent_number=issue.number,
            labels=_child_initial_labels(),
        )
    except Exception:  # noqa: BLE001 - the failed create is parked for a human, not raised through
        _park_child_create_failure(gh, issue, state, idx, child)
        return False
    plan.record(idx, new_issue.number, child)
    _persist_created_child(gh, issue, state, plan)
    return _seed_created_child(gh, issue, state, new_issue, child)


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
        if not _create_planned_child(gh, issue, state, plan, idx):
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
    # walk handles it on the next tick (the walk treats a child with
    # no recorded deps as deps-satisfied).
    for idx, (child_number, _) in enumerate(plan.created):
        if str(idx) in plan.dep_graph:
            continue
        try:
            gh.set_workflow_label(gh.get_issue(child_number), WorkflowLabel.READY)
        except Exception:
            log.exception(
                "issue=#%s could not flip child #%d to ready; the parent's "
                "_handle_blocked walk will retry on the next tick",
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
