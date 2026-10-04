# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The repair a recovered split makes of each recorded child before it finalizes.

A child the split recorded and never seeded -- one a crash cut off, or one
another poller on this host held when the split went to seed it -- carries no
parent link and none of the lineage it was owed, and is likely parked by its
own `blocked` pass as unattributed. Each is held to the lineage the parent's
record proves (`ReplacementLineage.repair`) and to the receipt stamped for its
slot, and seeded in one write that lifts the park its missing seed earned. A
lineage no longer proved, or a child the split cannot recognize as its own,
parks the parent instead. Each child is repaired under its own writer claim or
not at all: one another poller on this host is writing stops the recovery
there without a park, and the next tick resumes it.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import guards as _guards
from orchestrator.workflow.stages.decomposition import (
    child_claims as _child_claims,
    child_creation as _child_creation,
    late_child_content as _late_child_content,
    replacement_lineage as _replacement_lineage,
    split_seeds as _split_seeds,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")


def _seed_orphan_child_state(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    child_number,
    lineage: _replacement_lineage.ReplacementLineage,
) -> str | None:
    """Backfill `parent_number` (and creation stamp) and the owed ancestry on
    an orphan child so the parent's dependency walk can find it again, and
    its own size gate reads the lineage it was born into -- lifting, in the
    same write, the park its missing seed earned.

    Answers why this child may not be finalized, or None once it is repaired.
    It is held to the parent's record before anything is written -- the
    recognition `ReplacementLineage.repair` applies, and the receipt stamped
    for its slot (`split_seeds.stamp_lapse`) -- and a child refused keeps
    exactly what it carried. One owed the snapshot the consumer ledger no
    longer names is recorded there again, in a parent write ahead of its seed
    and of the finalize that would let anything start it.
    """
    child_issue = gh.get_issue(int(child_number))
    child_state = gh.read_pinned_state(child_issue)
    seed = lineage.repair(
        state, issue.number, int(child_number), child_state,
        _late_child_content._named_snapshots(getattr(child_issue, "title", None), getattr(child_issue, "body", None)),
    )
    refusal = seed.refusal or _split_seeds.stamp_lapse(gh, issue, state, child_issue, lineage.ancestry)
    if refusal is not None:
        return refusal
    if seed.protect:
        lineage.protect(state, int(child_number))
        gh.write_pinned_state(issue, state)
    attributed = _state._links_to(child_state.get(_state._PARENT_NUMBER), issue.number)
    if attributed and seed.ancestry is None:
        return None
    _child_creation._complete_seed(child_state, issue.number, seed.ancestry)
    gh.write_pinned_state(child_issue, child_state)
    return None


def _repair_recovered_child(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    child_number,
    lineage: _replacement_lineage.ReplacementLineage,
) -> bool:
    """Repair one recorded child under its own writer claim, or stop the recovery.

    The claim is taken in front of the read the repair decides on and held
    through its write, because both are the child's record. A child another
    poller on this host is writing is not one this tick may repair, and not
    one it may finalize past either -- so the recovery stops where it stands,
    parking nothing, and the next tick's recovery asks again. The children
    repaired before it carry exactly what they were owed.
    """
    try:
        with _child_claims.held_child(gh, issue.number, child_number) as held:
            if not held:
                return False
            refusal = _seed_orphan_child_state(gh, issue, state, child_number, lineage)
    except Exception:
        log.exception(
            "issue=#%s could not repair orphan child #%s during "
            "decomposition recovery", issue.number, child_number,
        )
        _guards._park_awaiting_human(
            gh, issue, state,
            f"{config.HITL_MENTIONS} could not repair child #{child_number} "
            "during decomposition recovery (seed `parent_number`, and any "
            "late lineage it inherits, on its pinned state); manual "
            "intervention needed (check orchestrator logs).",
            reason="child_seed_failed",
        )
        gh.write_pinned_state(issue, state)
        return False
    if refusal is not None:
        _replacement_lineage.park_unproved(gh, issue, state, refusal)
        return False
    return True


def _repair_recovered_children(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue, state: PinnedState, children: list,
) -> bool:
    """Repair every recorded child, or park where their lineage is unproved.

    The lineage is asked before any child is touched, because a repair that
    seeded some children and then refused the rest would leave a split half
    one lineage and half none -- and the park that refusal takes is what keeps
    all of them from being finalized into the walk that starts them. A child
    whose own ancestry is refused stops the walk the same way; the children
    seeded before it carry exactly what they were owed either way.
    """
    lineage = _replacement_lineage.read_replacement_lineage(state, issue, spec)
    if lineage.refusal is not None:
        _replacement_lineage.park_unproved(gh, issue, state, lineage.refusal)
        return False
    return all(
        _repair_recovered_child(gh, issue, state, child_number, lineage)
        for child_number in children
    )
