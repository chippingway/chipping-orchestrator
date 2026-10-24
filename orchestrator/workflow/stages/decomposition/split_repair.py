# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The seed a recovered split writes onto one recorded child.

Its caller, `recovery`, holds the child across the read this decides on and
the write it makes, since both are that child's record: under the child's
writer claim, with nothing taken outside it. That reading is held to admission
before the parent's record is asked anything about it, and a record admission
refuses -- at the reading, or at the write a human's edit since then leaves
it to refuse -- raises `child_claims.ChildRefused` with nothing written to the
child: no link, no lineage, no park lifted, and no version stamped onto it.

The repair writes no drift baseline. The create's answer the split hashed one
off is gone with the tick that made it, the parent keeps no manifest to render
the creation content from, and the child's receipt proves which slice it was
cut for, not what it said -- so its body, edited or not, is never read as what
it was created saying. A baseline the split's own seed landed is kept as it
stands, and a child seeded here without one is left with it missing, which
holds nothing here.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.decomposition import (
    child_claims as _child_claims,
    child_creation as _child_creation,
    late_child_content as _late_child_content,
    replacement_lineage as _replacement_lineage,
    split_seeds as _split_seeds,
    state as _state,
)


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
    and of the finalize that would let anything start it. A child whose own
    record admission refuses is asked none of that: it raises
    `child_claims.ChildRefused`, since nothing on that record can be read.
    Its drift baseline is left exactly as the record carries it, or missing.
    """
    child_issue = gh.get_issue(int(child_number))
    child_state = _child_claims.admitted_child(issue.number, child_issue, gh.read_pinned_state(child_issue))
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
    _child_creation._complete_seed(child_state, issue.number, seed.ancestry, baseline=None)
    _child_claims.write_seed(gh, issue.number, child_issue, child_state)
    return None
