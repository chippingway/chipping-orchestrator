# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Create and seed ordinary split children in the durable publication order.

The parent records each created child before its pinned state is seeded, and
the write that records it is also the one that puts it on the snapshot's
consumer ledger where the plan's lineage owes it a pointer. The seed is the
parent link and that lineage: nothing of the parent's own size gate -- its
measurement, its exemption, or an exact-commit authorization -- is carried
across. The same seed completes a child the split's recovery repairs
(`_complete_seed`). A create or a seed write that fails parks the parent with
the corresponding receipt.

A child is dispatchable the moment it exists, so a seed made inside
`child_claims.claiming()` is written under the child's own writer claim, onto
the record the child carries by then: another poller on this host may have
reached it first and held it for the seed it lacked. A child that poller is
still writing is left unseeded on the plan (`_SplitPlan.unseeded`) and the loop
goes on, for the split's recovery to seed under the claim on a later tick. No
production split seeds there yet: until the dispatch takes the claim, each
seed is written fresh and the split finalizes as it always has.
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
    """Seed a freshly-created child: the parent link, the creation stamp, and
    the late ancestry its lineage owes it, if any.

    Inside `child_claims.claiming()`, read and added to rather than written
    fresh, under the claim the caller holds. Whatever another poller wrote to
    the child first -- the hold the dispatcher puts on a child whose seed is
    missing -- sits on the one pinned comment every reader takes, and a fresh
    record would land in a second comment beside it that no reader takes,
    leaving the child held unseeded.
    """
    child_state = gh.read_pinned_state(new_issue) if _child_claims.claims_children() else PinnedState()
    _complete_seed(child_state, parent_number, ancestry)
    gh.write_pinned_state(new_issue, child_state)


def _complete_seed(child_state: PinnedState, parent_number: int, ancestry: LateAncestry | None) -> None:
    """Write what a recorded child's seed lacks, and take off the park its missing seed earned.

    The parent link only where it is missing, stamped as created now where
    nothing stamped it, and the owed ancestry where the split or its repair
    names one. A child recorded on a parent still creating or recovering its
    split was never released, so the only parks it can be wearing are the ones
    that missing seed earned: the dispatcher's hold on a seed its receipt does
    not match, and the unattributed-child park a `blocked` tick takes on one
    with no parent link. Left standing past the write that answers it, either
    would meet the child at its implementer, which would wait on a reply
    nobody owes. A record no park was written to is left without one, so a
    seed nobody reached first is exactly the link, the stamp, and the lineage.
    """
    if not _state._links_to(child_state.get(_state._PARENT_NUMBER), parent_number):
        child_state.set(_state._PARENT_NUMBER, parent_number)
        if not child_state.get(_state._CREATED_AT):
            child_state.set(_state._CREATED_AT, _usage._now_iso())
    if ancestry is not None:
        _lineage.write_late_ancestry(child_state, ancestry)
    if child_state.carries(_state._AWAITING_HUMAN) or child_state.carries(_state._PARK_REASON):
        child_state.set(_state._AWAITING_HUMAN, False)
        child_state.set(_state._PARK_REASON, None)


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
    """Seed the child this split just created, or park the parent naming it.

    Under the child's own writer claim inside `child_claims.claiming()`,
    since the child is on GitHub, and dispatchable, from the moment the
    create returns. A claim another poller on this host holds is no failure:
    the child is already recorded, so it is left on the plan as unseeded and
    the loop goes on -- the caller that sees `plan.unseeded` leaves the split
    to its recovery, which seeds it under the claim once that poller lets
    go. Only a seed that could not be written parks.
    """
    _, child = plan.created[-1]
    try:
        with _child_claims.held_child(gh, issue.number, new_issue.number) as held:
            if held:
                _write_child_pinned_state(
                    gh, new_issue, issue.number, plan.lineage.child_ancestry(state, new_issue.number),
                )
            else:
                plan.unseeded.append(new_issue.number)
    except Exception:
        log.exception(
            "issue=#%s could not seed pinned state on child #%d",
            issue.number, new_issue.number,
        )
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
