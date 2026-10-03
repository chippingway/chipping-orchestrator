# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Create and seed ordinary split children in the durable publication order.

The parent records each created child before its pinned state is seeded, and
the write that records it is also the one that puts it on the snapshot's
consumer ledger where the plan's lineage owes it a pointer. The seed is the
parent link and that lineage, written fresh: nothing of the parent's own size
gate -- its measurement, its exemption, or an exact-commit authorization --
is carried across. The seed is written under the child's own writer claim, since
a child is dispatchable the moment it exists. Creation and seeding failures --
a refused claim among them -- park the parent with the corresponding receipt.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import guards as _guards, usage as _usage
from orchestrator.workflow.late_split import lineage as _lineage
from orchestrator.workflow.late_split.ancestry import LateAncestry
from orchestrator.workflow.stages.decomposition import child_claims as _child_claims, state as _state
from orchestrator.workflow.stages.decomposition.models import _SplitPlan
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")



def _child_initial_labels() -> list[str]:
    """Labels every split child is born with: only the initial `blocked`
    workflow label. Activation later flips no-dep children to `ready`.
    """
    return [WorkflowLabel.BLOCKED]


def _write_child_pinned_state(
    gh: GitHubClient, new_issue: Issue, parent_number: int, ancestry: LateAncestry | None,
) -> None:
    """Write a freshly-created child's initial pinned state: the parent link,
    the creation stamp, and the late ancestry its lineage owes it, if any."""
    child_state = PinnedState()
    child_state.set(_state._PARENT_NUMBER, parent_number)
    child_state.set(_state._CREATED_AT, _usage._now_iso())
    if ancestry is not None:
        _lineage.write_late_ancestry(child_state, ancestry)
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
    gh: GitHubClient, issue: Issue, state: PinnedState, plan: _SplitPlan, child_number: int,
) -> None:
    state.set(_state._CHILDREN, [number for number, _ in plan.created])
    plan.lineage.protect(state, child_number)
    state.set("decomposed_at", _usage._now_iso())
    gh.write_pinned_state(issue, state)


def _seed_created_child(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    plan: _SplitPlan,
    new_issue: Issue,
) -> bool:
    """Seed the child this split just created, or park the parent naming it."""
    _, child = plan.created[-1]
    if not _seeded_under_claim(gh, issue, state, plan, new_issue):
        _guards._park_awaiting_human(
            gh, issue, state,
            f"{config.HITL_MENTIONS} created child #{new_issue.number} "
            f"({child.get('title')!r}) but could not seed its pinned state "
            "with `parent_number` and any late lineage it inherits; manual "
            "intervention needed (seed them on the child or close it).",
            reason="child_seed_failed",
        )
        gh.write_pinned_state(issue, state)
        return False
    return True


def _seeded_under_claim(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    plan: _SplitPlan,
    new_issue: Issue,
) -> bool:
    """Whether the child's initial pinned state was written, under its own writer claim.

    The child is on GitHub, and dispatchable, from the moment the create
    returns, so another poller on this host may already be writing it -- and
    a seed written past that would race the child's own handler for its
    pinned comment. A refused claim is a seed this split could not make.
    """
    try:
        with _child_claims.held_child(gh, issue.number, new_issue.number) as held:
            if not held:
                return False
            _write_child_pinned_state(
                gh, new_issue, issue.number, plan.lineage.child_ancestry(state, new_issue.number),
            )
    except Exception:
        log.exception(
            "issue=#%s could not seed pinned state on child #%d",
            issue.number, new_issue.number,
        )
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
    _persist_created_child(gh, issue, state, plan, new_issue.number)
    return _seed_created_child(gh, issue, state, plan, new_issue)
