# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Create and seed ordinary split children in the durable publication order.

The parent records each created child before its pinned state is seeded.
Creation and seeding failures park the parent with the corresponding receipt.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import guards as _guards, usage as _usage
from orchestrator.workflow.stages.decomposition import state as _state
from orchestrator.workflow.stages.decomposition.models import _SplitPlan
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")



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
