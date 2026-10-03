# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A late root an edit re-decomposed around one replacement, and the parent poll that walks it.

The root sits at depth 0 and still holds the ref its own split preserved for
the original, which is running when the edit lands. The umbrella's poll
reroutes the edit, and the decomposer re-plans it with one replacement, which
the split itself points at that ref and records beside the original on
`late_consumers` -- under an umbrella again, or under a parent that keeps
implementation of its own and goes back to it once every child has resolved.
Or the split dies right behind that replacement's create, before anything
records it.
"""
from __future__ import annotations

import contextlib
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

from orchestrator.workflow.late_split import models as _late_models, state as _late_state
from orchestrator.workflow.stages.decomposition import blocked as _blocked, run as _decomposing, umbrella as _umbrella
from orchestrator.workflow.stages.implementing import late_records as _late_records
from tests.support.fakes import make_issue
from tests.workflow.fixtures import _TEST_SPEC, LABEL_DECOMPOSING, _agent, _manifest
from tests.workflow.stages.decomposition import (
    late_cleanup_support as _support,
    late_crash_support as _crash,
    late_test_support as _late,
)
from tests.workflow.stages.decomposition.late_cleanup_support import OwnerSeed, RecordedDelete, SeededUmbrella

# What the edited root is re-decomposed into, by the label its parent waits on
# afterwards: one replacement under an umbrella again, or one that runs first
# under a parent that goes back to work of its own after it.
REPLACEMENT_MANIFESTS = MappingProxyType({
    _support.UMBRELLA: _manifest(
        '{"decision": "split", "umbrella": true, "rationale": "re-planned", '
        '"children": [{"title": "A", "body": "the whole of it, as the edit now asks"}]}'
    ),
    _support.LABEL_BLOCKED: _manifest(
        '{"decision": "split", "umbrella": false, "rationale": "re-planned", '
        '"children": [{"title": "A", "body": "the groundwork, as the edit now asks"}]}'
    ),
})

# The attempt a later ordinary split of the handed-back parent records.
LATER_ATTEMPT = "fedcba9876543210"

# The child that later split tracks.
LATER_CHILD = 431

_STALE_BASELINE = "the requirements before the edit"


def redecomposed(case, label: str = _support.UMBRELLA, *, dying: bool = False) -> tuple:
    """The re-decomposed root on `label`, and the running replacement its split created and released.

    `dying` kills the split right behind that create instead: the parent stays
    on `workflow:decomposing` with the attempt's markers and a register short
    of its count, and nothing records the replacement -- on the ledger least of
    all.
    """
    seeded = _support.split_umbrella(
        _support.LateResourceState.RECONCILED,
        snapshot=_support.LateResourceState.RETAINED,
        child_label=_support.LABEL_READY,
        owner=OwnerSeed(child_closed=False),
    )
    seeded.github.seed_state(_support.PARENT_NUMBER, **{
        **seeded.github.pinned_data(_support.PARENT_NUMBER),
        "late_lineage_depth": 0,
        "user_content_hash": _STALE_BASELINE,
    })
    _support.walk_owner(case, seeded)
    with contextlib.ExitStack() as interruption:
        if dying:
            interruption.enter_context(case.assertRaises(KeyboardInterrupt))
            interruption.enter_context(_crash.killed_after(seeded.github, "create_child_issue"))
        case._run(
            lambda: _decomposing._handle_decomposing(seeded.github, _TEST_SPEC, seeded.parent),
            run_agent=_agent(session_id="replanned", last_message=REPLACEMENT_MANIFESTS[label]),
        )
    case.assertEqual(seeded.github.workflow_label(seeded.parent), LABEL_DECOMPOSING if dying else label)
    return seeded, seeded.github.created_child_issues[0]


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


def oversized_candidate(seeded: SeededUmbrella, checkout: Path) -> _late_models.LateGeneration:
    """Freeze an oversized candidate of the parent's own the way its size gate does, and hand it to adjudication."""
    github = seeded.github
    state = github.read_pinned_state(seeded.parent)
    gate = _late_records._gate(github, _TEST_SPEC, seeded.parent, state, checkout)
    frozen = _late_records._minted(gate, _late_state.read_late_generation(state), _late.OTHER_SHA, _late.BASE_SHA)
    _late_state.write_late_generation(state, replace(frozen, additions=_late.ADDITIONS, threshold=_late.THRESHOLD))
    github.write_pinned_state(seeded.parent, state)
    github.set_workflow_label(seeded.parent, LABEL_DECOMPOSING, guarded=False)
    return frozen


def all_ended(case) -> SeededUmbrella:
    """A parent with work of its own, waiting on `blocked` with every consumer its ledger records ended."""
    seeded, replacement = redecomposed(case, _support.LABEL_BLOCKED)
    ended(seeded, replacement)
    return seeded


def handed_back(case) -> SeededUmbrella:
    """A parent with work of its own, every consumer ended, walked back to `ready`."""
    seeded = all_ended(case)
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
