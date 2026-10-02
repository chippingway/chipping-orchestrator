# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An issue inside a late lineage, as the ordinary decomposer would meet it.

What reaches that decomposer is an issue a genuine edit rerouted to
`workflow:decomposing`: an umbrella a late split made, or a child one made.
Its pinned comment still carries everything the late path wrote -- the split's
own record where it split, the ancestry where a split made it -- and that is
the state seeded here, with every late group written through its own owner,
so the replacement lineage reads the wire shape a live issue carries.
"""
from __future__ import annotations

from dataclasses import replace

from orchestrator.git.snapshots import mirrors as _snapshot_mirrors
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    ancestry as _ancestry,
    endings as _endings,
    lineage as _lineage,
    models as _late_models,
    obligations as _obligations,
    phases as _late_phases,
    state as _late_state,
)
from orchestrator.workflow.stages.decomposition import replacement_lineage as _replacement_lineage
from tests.support.fakes import make_issue
from tests.workflow.fixtures import _TEST_SPEC

SHA_LENGTH = 40

# The issue being re-decomposed, and the child its own late split made before
# the edit orphaned it.
PARENT = 41

ORIGINAL = 411

# The root above a descendant parent, the adjudication that cut the parent from
# it, and the issue a descendant that never split was cut from.
ANCESTOR = 4

ANCESTOR_CYCLE = 2

GRANDPARENT = 40

# The parent's own split: cycle 3, generation 1, over candidate `a...`.
CYCLE = 3

GENERATION = 1

CANDIDATE_SHA = "a" * SHA_LENGTH

BASE_SHA = "b" * SHA_LENGTH

SNAPSHOT_REF = "refs/orchestrator/late-split/issue-41/cycle-3/gen-1"

# This repository's copy of the snapshot, and another repository's copy of the
# same three numbers: a `REPOS` entry sharing the clone, whose own issue 41
# split into other work.
OWN_MIRROR = _snapshot_mirrors.local_snapshot_ref(_TEST_SPEC, SNAPSHOT_REF)

FOREIGN_MIRROR = _snapshot_mirrors.local_snapshot_ref(replace(_TEST_SPEC, slug="another/repository"), SNAPSHOT_REF)

EDITED_BODY = "the issue, as a human last edited it"

HELD = _obligations.LateResourceState.RETAINED

# What a root's replacement is born with: its lineage, and that lineage pointed
# at the snapshot the root's own split holds for it.
ROOT_LINEAGE = _ancestry.LateAncestry(
    root_issue=PARENT, lineage_depth=1, parent_issue=PARENT, cycle_id=CYCLE, generation=GENERATION,
)

ROOT_REPLACEMENT = replace(ROOT_LINEAGE, snapshot_ref=SNAPSHOT_REF, snapshot_sha=CANDIDATE_SHA, mirror_first=True)


def own_split(*ref_states: _obligations.LateResourceState, **overrides) -> _late_models.LateGeneration:
    """The parent's settled split, one entry for its snapshot at each of `ref_states`.

    Held once unless a case names other states. Rooted at the parent at depth
    0 unless a case names the lineage a descendant's own split was minted in.
    """
    held = tuple(
        _obligations.LateResource(_obligations.LateResourceKind.SNAPSHOT_REF, SNAPSHOT_REF, ref_state)
        for ref_state in ref_states or (HELD,)
    )
    made = _obligations.LateResource(_obligations.LateResourceKind.CHILD, str(ORIGINAL))
    return replace(
        _late_models.LateGeneration(
            cycle_id=CYCLE,
            generation=GENERATION,
            root_issue=PARENT,
            current_issue=PARENT,
            lineage_depth=0,
            candidate_sha=CANDIDATE_SHA,
            base_sha=BASE_SHA,
            phase=_late_phases.LatePhase.CLEANING_UP,
            links_announced=True,
            split_children=(ORIGINAL,),
            obligations=_obligations.LateObligations(resources=(*held, made), consumers=(ORIGINAL,)),
        ),
        **overrides,
    )


def cut_from_ancestor(depth: int = 1, parent: int = ANCESTOR) -> _ancestry.LateAncestry:
    """The ancestry a late split wrote on the parent, `depth` below the root, pointed at that split's ref."""
    return _ancestry.LateAncestry(
        root_issue=ANCESTOR,
        lineage_depth=depth,
        parent_issue=parent,
        cycle_id=ANCESTOR_CYCLE,
        generation=GENERATION,
        snapshot_ref=f"refs/orchestrator/late-split/issue-{parent}/cycle-{ANCESTOR_CYCLE}/gen-{GENERATION}",
        snapshot_sha=CANDIDATE_SHA,
        mirror_first=True,
        scope="the slice this issue was cut for",
    )


def record(
    generation: _late_models.LateGeneration | None = None,
    ancestry: _ancestry.LateAncestry | None = None,
    **edits,
) -> PinnedState:
    """The parent's pinned comment, each late group written through its own owner.

    `edits` lands over the groups as written, the way a hand edit or another
    binary's write would.
    """
    state = PinnedState()
    if generation is not None:
        _late_state.write_late_generation(state, generation)
    if ancestry is not None:
        _lineage.write_late_ancestry(state, ancestry)
    state.data.update(edits)
    return state


def retired(ref_state: _obligations.LateResourceState, cycle: int | None = CYCLE) -> PinnedState:
    """The parent's split once a retirement took its identity off, keeping its ledgers.

    `cycle` is the one the retirement recorded dropping, or None where nothing
    says which.
    """
    state = record(_late_models.LateGeneration(obligations=own_split(ref_state).obligations))
    if cycle is not None:
        _endings.record_retired_cycle(state, cycle)
    return state


def decide(state: PinnedState, body: str = EDITED_BODY) -> _replacement_lineage.ReplacementLineage:
    """What the parent's replacements would be seeded with, read off `state` and `body`."""
    return _replacement_lineage.read_replacement_lineage(state, make_issue(PARENT, body=body), _TEST_SPEC)
