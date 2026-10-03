# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A late root an edit re-decomposed around one replacement, and the parent poll that walks it.

The root still holds the ref its own split preserved for the original, which is
running when the edit lands. The re-decomposition tracks one replacement in the
original's place and points it at that ref -- under an umbrella again, or under
a parent that keeps implementation of its own and goes back to it once every
child has resolved. The record is seeded as that split writes it: its attempt,
the replacement on the manifest and beside the original on `late_consumers`,
and the replacement's own pinned comment linked to the parent and carrying the
original's ancestry.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from orchestrator.workflow.late_split import lineage as _lineage, state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.decomposition import blocked as _blocked, umbrella as _umbrella
from orchestrator.workflow.stages.implementing import late_records as _late_records
from tests.support.fakes import make_issue
from tests.workflow.fixtures import _TEST_SPEC, LABEL_DECOMPOSING
from tests.workflow.stages.decomposition import late_cleanup_support as _support, late_test_support as _late
from tests.workflow.stages.decomposition.late_cleanup_support import OwnerSeed, RecordedDelete, SeededUmbrella

# The attempt the replacement's receipt names, which the split records on the
# parent ahead of creating it, and the one a later ordinary split records.
SPLIT_ATTEMPT = "0123456789abcdef"

LATER_ATTEMPT = "fedcba9876543210"

# The child an ordinary re-decomposition of the handed-back parent tracks.
LATER_CHILD = 431


def redecomposed(label: str = _support.UMBRELLA) -> tuple:
    """The re-decomposed root on `label`, and the running replacement it tracks."""
    seeded = _support.split_umbrella(
        _support.LateResourceState.RECONCILED,
        snapshot=_support.LateResourceState.RETAINED,
        child_label=_support.LABEL_READY,
        owner=OwnerSeed(label=label, child_closed=False),
    )
    github = seeded.github
    replacement = make_issue(_support.REPLACEMENT_CHILD, label=_support.LABEL_READY)
    github.add_issue(replacement)
    linked = github.read_pinned_state(replacement)
    linked.set("parent_number", _support.PARENT_NUMBER)
    _lineage.write_late_ancestry(
        linked, _lineage.read_late_ancestry(github.read_pinned_state(github.get_issue(_support.CHILD_NUMBER))),
    )
    github.seed_state(_support.REPLACEMENT_CHILD, **linked.data)
    github.seed_state(_support.PARENT_NUMBER, **{
        **github.pinned_data(_support.PARENT_NUMBER),
        "children": [_support.REPLACEMENT_CHILD],
        "dep_graph": {},
        _support.EXPECTED_CHILDREN: 1,
        "umbrella": label == _support.UMBRELLA,
        "late_consumers": [_support.CHILD_NUMBER, _support.REPLACEMENT_CHILD],
        "split_attempt": SPLIT_ATTEMPT,
    })
    return seeded, replacement


def walk(
    case, seeded: SeededUmbrella, tick=_umbrella._handle_umbrella, outcome=_support.SnapshotOutcome.DELETED,
) -> RecordedDelete:
    """Run the parent's poll, the remote answering every delete with `outcome`."""
    deleted = RecordedDelete(outcome)
    with deleted.answering():
        _support.walk_owner(case, seeded, tick)
    return deleted


def ended(seeded: SeededUmbrella, replacement) -> None:
    """End both consumers the ledger records: the original, and the replacement as `done`."""
    seeded.github.get_issue(_support.CHILD_NUMBER).closed = True
    replacement.closed = True
    seeded.github.set_workflow_label(replacement, _support.LABEL_DONE, guarded=False)


def oversized_candidate(seeded: SeededUmbrella, checkout: Path) -> LateGeneration:
    """Freeze an oversized candidate of the parent's own the way its size gate does, and hand it to adjudication."""
    github = seeded.github
    state = github.read_pinned_state(seeded.parent)
    gate = _late_records._gate(github, _TEST_SPEC, seeded.parent, state, checkout)
    frozen = _late_records._minted(gate, _late_state.read_late_generation(state), _late.OTHER_SHA, _late.BASE_SHA)
    _late_state.write_late_generation(state, replace(frozen, additions=_late.ADDITIONS, threshold=_late.THRESHOLD))
    github.write_pinned_state(seeded.parent, state)
    github.set_workflow_label(seeded.parent, LABEL_DECOMPOSING, guarded=False)
    return frozen


def all_ended() -> SeededUmbrella:
    """A parent with work of its own, waiting on `blocked` with every consumer its ledger records ended."""
    seeded, replacement = redecomposed(_support.LABEL_BLOCKED)
    ended(seeded, replacement)
    return seeded


def handed_back(case) -> SeededUmbrella:
    """A parent with work of its own, every consumer ended, walked back to `ready`."""
    seeded = all_ended()
    walk(case, seeded, _blocked._handle_blocked)
    case.assertEqual(seeded.github.workflow_label(seeded.parent), _support.LABEL_READY)
    return seeded


def resplit(case, label: str) -> SeededUmbrella:
    """The handed-back parent re-split onto `label` by a later edit under an attempt of its own, its child `done`."""
    seeded = handed_back(case)
    github = seeded.github
    github.add_issue(make_issue(LATER_CHILD, label=_support.LABEL_DONE, closed=True))
    github.seed_state(_support.PARENT_NUMBER, **{
        **github.pinned_data(_support.PARENT_NUMBER),
        "children": [LATER_CHILD],
        "umbrella": label == _support.UMBRELLA,
        "split_attempt": LATER_ATTEMPT,
    })
    github.set_workflow_label(seeded.parent, label, guarded=False)
    return seeded
