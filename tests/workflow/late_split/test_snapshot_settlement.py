# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether a split's own record can say its snapshot is there for a new consumer.

A replacement child may be pointed only at a ref its parent's own split still
holds, so what that split's ledger says about the ref decides the pointer. Two
answers settle it -- the ref is held, or a reclamation has taken it -- and a
record that gives neither is one nothing can seed a replacement from.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from types import MappingProxyType

from orchestrator.workflow.late_split import entitlement as _entitlement
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.late_split.obligations import (
    LateObligations,
    LateResource,
    LateResourceKind,
    LateResourceState,
)
from orchestrator.workflow.late_split.phases import LatePhase

OWNER = 41

SHA_LENGTH = 40

CANDIDATE_SHA = "a" * SHA_LENGTH

CHILD = 411

REF = "refs/orchestrator/late-split/issue-41/cycle-3/gen-1"

# Another cycle's ref on the same ledger: a restarted issue keeps what its
# earlier cycle is owed.
EARLIER_REF = "refs/orchestrator/late-split/issue-41/cycle-2/gen-1"


def _split(*snapshots: LateResource, **overrides) -> LateGeneration:
    """The owner's settled split, recording `snapshots` beside its one child."""
    return replace(
        LateGeneration(
            cycle_id=3,
            generation=1,
            root_issue=OWNER,
            current_issue=OWNER,
            lineage_depth=0,
            candidate_sha=CANDIDATE_SHA,
            phase=LatePhase.CLEANING_UP,
            split_children=(CHILD,),
            obligations=LateObligations(resources=snapshots, consumers=(CHILD,)),
        ),
        **overrides,
    )


def _entry(state: LateResourceState, ref: str = REF) -> LateResource:
    return LateResource(LateResourceKind.SNAPSHOT_REF, ref, state)


_HELD = _entry(LateResourceState.RETAINED)

# Records whose split settled what its snapshot is: held for a new consumer,
# or passed to a reclamation -- deciding, done, or a delete the remote refused.
_SETTLED = MappingProxyType({
    "held": _split(_HELD),
    **{
        f"released {state.value}": _split(_entry(state))
        for state in (LateResourceState.RECLAIMING, LateResourceState.RECONCILED, LateResourceState.FAILED)
    },
    "released beside an earlier cycle's held ref": _split(
        _entry(LateResourceState.RECONCILED), _entry(LateResourceState.RETAINED, EARLIER_REF),
    ),
    "released under an identity a retirement dropped": replace(
        _split(_entry(LateResourceState.RECONCILED)), cycle_id=0, generation=0,
    ),
    "no split of its own": LateGeneration(cycle_id=3, generation=1, root_issue=OWNER, current_issue=OWNER),
})

# Records that proved a split and cannot say whether its ref is there for one
# more consumer, each with a fragment of the reason given.
_UNSETTLED = MappingProxyType({
    "a consumer ledger no child can be added to": (
        replace(_split(_HELD), obligations=replace(_split(_HELD).obligations, opaque_consumers='["#57"]')),
        "no child can be recorded",
    ),
    "a held ref with no candidate": (_split(_HELD, candidate_sha=""), "no child can be recorded"),
    "a held ref under an identity a retirement dropped": (
        replace(_split(_HELD), cycle_id=0, generation=0), "no child can be recorded",
    ),
    "an unreadable resource ledger": (
        replace(_split(_HELD), obligations=replace(_split(_HELD).obligations, opaque_resources='["x"]')),
        "cannot be told",
    ),
    "a ref never proved": (_split(_entry(LateResourceState.PENDING)), "neither held nor released"),
    "a ref held and released at once": (
        _split(_HELD, _entry(LateResourceState.RECONCILED)), "neither held nor released",
    ),
    "no entry for its own ref": (
        _split(_entry(LateResourceState.RETAINED, EARLIER_REF)), "neither held nor released",
    ),
})


class SnapshotSettlementTest(unittest.TestCase):
    """A held or released ref is an answer; anything else is a refusal."""

    def test_a_settled_snapshot_answers(self) -> None:
        for shape, generation in _SETTLED.items():
            with self.subTest(shape=shape):
                self.assertIsNone(_entitlement.unsettled_snapshot(generation, OWNER))

    def test_an_unsettled_snapshot_is_refused(self) -> None:
        for shape, (generation, reason) in _UNSETTLED.items():
            with self.subTest(shape=shape):
                self.assertIn(reason, _entitlement.unsettled_snapshot(generation, OWNER) or "")


if __name__ == "__main__":
    unittest.main()
