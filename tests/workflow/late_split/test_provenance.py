# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which late lineage an ordinary decomposition's children would inherit."""
from __future__ import annotations

import unittest
from dataclasses import replace
from types import MappingProxyType

from orchestrator.git.snapshots import namespace as _namespace
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    ancestry as _ancestry,
    endings as _endings,
    entitlement as _entitlement,
    lineage as _lineage,
    provenance as _provenance,
    state as _late_state,
)
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.late_split.obligations import (
    LateObligations,
    LateResource,
    LateResourceKind,
    LateResourceState,
)
from orchestrator.workflow.late_split.phases import LatePhase

SHA_LENGTH = 40

# The root of the lineage, and the split it ran: cycle 3, generation 1, which
# made #57 and #58 out of candidate `a...`.
ROOT = 41

ROOT_CYCLE = 3

ROOT_GENERATION = 1

ROOT_SHA = "a" * SHA_LENGTH

ROOT_REF = "refs/orchestrator/late-split/issue-41/cycle-3/gen-1"

# One of the root's children, which later split candidate `c...` in its own
# cycle 1, generation 2, into #60 and #61.
CHILD = 57

CHILD_CYCLE = 1

CHILD_GENERATION = 2

CHILD_SHA = "c" * SHA_LENGTH

CHILD_REF = "refs/orchestrator/late-split/issue-57/cycle-1/gen-2"

GRANDCHILDREN = (60, 61)

GRANDCHILD = GRANDCHILDREN[0]

# An issue that is neither the root nor #57.
STRANGER = 50

BASE_SHA = "b" * SHA_LENGTH

BRANCH = "orchestrator/issue-41"

# The wire entry the ledger records the root's snapshot under.
SNAPSHOT_ENTRY = MappingProxyType({"kind": "snapshot_ref", "target": ROOT_REF, "state": "retained"})

# What an issue that reached this workflow another way carries.
LEGACY_STATE = MappingProxyType({"dev_agent": "codex", "branch": BRANCH, "parent_number": 12})

# The root's own split, as its retirement onto `umbrella` leaves it.
ROOT_SPLIT = LateGeneration(
    cycle_id=ROOT_CYCLE,
    generation=ROOT_GENERATION,
    root_issue=ROOT,
    current_issue=ROOT,
    lineage_depth=0,
    candidate_sha=ROOT_SHA,
    base_sha=BASE_SHA,
    phase=LatePhase.CLEANING_UP,
    obligations=LateObligations(
        resources=(
            LateResource(LateResourceKind.SNAPSHOT_REF, ROOT_REF, LateResourceState.RETAINED),
            LateResource(LateResourceKind.CHILD, str(CHILD)),
            LateResource(LateResourceKind.BRANCH, BRANCH, LateResourceState.RECONCILED),
        ),
        consumers=(CHILD, CHILD + 1),
    ),
    split_children=(CHILD, CHILD + 1),
)

# What the root's pinned comment carries once that split has settled.
ROOT_RECORDS = (ROOT_SPLIT,)

# What the root's split seeded #57 with.
CHILD_ANCESTRY = _ancestry.LateAncestry(
    root_issue=ROOT,
    lineage_depth=1,
    parent_issue=ROOT,
    cycle_id=ROOT_CYCLE,
    generation=ROOT_GENERATION,
    snapshot_ref=ROOT_REF,
    snapshot_sha=ROOT_SHA,
    mirror_first=True,
    base_branch="main",
    scope="the slice #57 owns",
)

# The receipt the root's split stamps into #57's body, and the lineage the
# reuse guard writes back off it when the seed never landed: the identity the
# receipt carries, and no root or depth.
RECEIPT = _ancestry.child_marker(issue=ROOT, cycle=ROOT_CYCLE, generation=ROOT_GENERATION, index=0)

CLAIMED_ANCESTRY = _ancestry.child_lineage(RECEIPT)

# A live cycle on the root that has split nothing yet, and one on #57 minted
# off its ancestry: both inherit nothing of their own while they are whole.
ADJUDICATING_ROOT = LateGeneration(
    cycle_id=2, generation=1, root_issue=ROOT, current_issue=ROOT, lineage_depth=0,
    candidate_sha=ROOT_SHA, phase=LatePhase.ADJUDICATING,
)

ADJUDICATING_CHILD_RECORDS = (CHILD_ANCESTRY, LateGeneration(
    cycle_id=2, generation=1, root_issue=ROOT, current_issue=CHILD, lineage_depth=1,
    candidate_sha=CHILD_SHA, phase=LatePhase.ADJUDICATING,
))

# What #57's split seeded #60 with, two levels below the root.
GRANDCHILD_ANCESTRY = _ancestry.LateAncestry(
    root_issue=ROOT,
    lineage_depth=2,
    parent_issue=CHILD,
    cycle_id=CHILD_CYCLE,
    generation=CHILD_GENERATION,
    snapshot_ref=CHILD_REF,
    snapshot_sha=CHILD_SHA,
    mirror_first=True,
)

# A generation a reader takes as a count and no ref can be minted from: it has
# more digits than a whole ref may have characters.
UNMINTABLE_GENERATION = 10 ** _namespace.MAX_SNAPSHOT_REF

# The root's adjudication cancelled in the middle of creating its children:
# the cancellation writes its own boundary and keeps the interrupted one.
CANCELLED_MID_SPLIT = replace(
    ADJUDICATING_ROOT,
    phase=LatePhase.CANCELLING,
    cancelled=True,
    cancelled_at="2026-09-29T00:00:00+00:00",
    cancelled_phase=LatePhase.SPLITTING,
)

# An edit that takes a field off the comment rather than setting one.
DROPPED = object()

# The two pinned keys most of the damage below lands on, spelled once.
CYCLE_KEY = "late_cycle_id"

DEPTH_KEY = "late_lineage_depth"


def root_split(ref_state: LateResourceState = LateResourceState.RETAINED, **overrides) -> LateGeneration:
    """The root's settled split, its snapshot entry at `ref_state`."""
    snapshot = LateResource(LateResourceKind.SNAPSHOT_REF, ROOT_REF, ref_state)
    fields = {"obligations": ROOT_SPLIT.obligations.with_resource(snapshot), **overrides}
    return LateGeneration(**{**ROOT_SPLIT.__dict__, **fields})


def child_ancestry(**overrides) -> _ancestry.LateAncestry:
    """What the root's split seeded #57 with, a field or two changed."""
    return _ancestry.LateAncestry(**{**CHILD_ANCESTRY.__dict__, **overrides})


def child_split(ref_state: LateResourceState = LateResourceState.RETAINED) -> LateGeneration:
    """#57's own settled split, minted off its ancestry's root and depth."""
    return root_split(
        cycle_id=CHILD_CYCLE,
        generation=CHILD_GENERATION,
        current_issue=CHILD,
        lineage_depth=1,
        candidate_sha=CHILD_SHA,
        obligations=LateObligations(
            resources=(LateResource(LateResourceKind.SNAPSHOT_REF, CHILD_REF, ref_state),),
            consumers=GRANDCHILDREN,
        ),
        split_children=GRANDCHILDREN,
    )


def read(
    issue: int, records: tuple = (), edits: tuple = (), body: str = "the issue as a human wrote it",
) -> _provenance.LateProvenance:
    """The provenance an issue's pinned comment and body decide on.

    Each record is written through its own owner's writer, so what is decided
    on is the wire shape a live issue carries; `edits` then lands on top of it
    as a hand edit or an older binary would, or takes a field off it.
    """
    state = PinnedState(data=dict(LEGACY_STATE))
    for record in records:
        if isinstance(record, LateGeneration):
            _late_state.write_late_generation(state, record)
        else:
            _lineage.write_late_ancestry(state, record)
    for key, edited in edits:
        if edited is DROPPED:
            state.data.pop(key)
        else:
            state.set(key, edited)
    return _provenance.read_provenance(state, issue, body)


# Issues no late split ever charged, by the records each carries. An accepted
# candidate's retirement keeps its ledgers and drops its identity, and a branch
# alone is no split.
ORDINARY = MappingProxyType({
    "legacy": (),
    "a cycle still adjudicating": (ADJUDICATING_ROOT,),
    "a restarted cycle": (LateGeneration(cycle_id=4, root_issue=ROOT, current_issue=ROOT, lineage_depth=0),),
    "an accepted cycle's leftovers": (LateGeneration(obligations=LateObligations(
        resources=(LateResource(LateResourceKind.BRANCH, BRANCH, LateResourceState.RECONCILED),),
    )),),
    # No phase proves a child: a cancelled cycle that created none is rebuilt
    # standing here.
    "cleaning up with no child": (replace(ADJUDICATING_ROOT, phase=LatePhase.CLEANING_UP),),
})

# Each thing that proves a split made children, standing alone on a live cycle
# that is otherwise the root's ordinary adjudication.
PROOFS = MappingProxyType({
    "the register": replace(ADJUDICATING_ROOT, phase=None, split_children=(CHILD,)),
    "a consumer": replace(ADJUDICATING_ROOT, phase=None, obligations=LateObligations(consumers=(CHILD,))),
    "a child entry": replace(ADJUDICATING_ROOT, phase=None, obligations=LateObligations(
        resources=(LateResource(LateResourceKind.CHILD, str(CHILD)),),
    )),
})

# Child evidence naming no other issue, by the record it stands on. Each would
# otherwise prove a split on its own.
INVALID_CHILDREN = MappingProxyType({
    "a child entry that is no issue": LateGeneration(obligations=LateObligations(
        resources=(LateResource(LateResourceKind.CHILD, "not-an-issue"),),
    )),
    "a child entry padded with zeros": LateGeneration(obligations=LateObligations(
        resources=(LateResource(LateResourceKind.CHILD, f"00{CHILD}"),),
    )),
    "the owner as its own consumer": LateGeneration(obligations=LateObligations(consumers=(ROOT,))),
    "the owner in its own register": replace(ADJUDICATING_ROOT, phase=None, split_children=(ROOT,)),
})

# A root whose split happened and whose snapshot entitles nothing, by its
# records and the edits over them: a ref never proved or already on its way
# out, one the ledger both holds and reconciles, a ledger nobody can add the
# next consumer to, and a split whose identity a retirement already dropped.
UNHELD_ROOT_SNAPSHOTS = MappingProxyType({
    **{
        f"snapshot {ref_state.value}": ((root_split(ref_state),), ())
        for ref_state in (
            LateResourceState.PENDING,
            LateResourceState.FAILED,
            LateResourceState.RECLAIMING,
            LateResourceState.RECONCILED,
        )
    },
    "held and reconciled at once": (ROOT_RECORDS, (("late_resources", [
        dict(SNAPSHOT_ENTRY), {**SNAPSHOT_ENTRY, "state": "reconciled"},
    ]),)),
    "opaque consumers": (ROOT_RECORDS, (("late_consumers", ["#57"]),)),
    "retired identity": (
        (LateGeneration(obligations=ROOT_SPLIT.obligations),),
        ((_endings.LATE_RETIRED_CYCLE_ID, ROOT_CYCLE),),
    ),
})

# An ancestry that cannot place #57: a fragment of the refusal, then the
# records, the edits over them, and the body.
UNPLACEABLE_ANCESTRIES = MappingProxyType({
    "unreadable parent": ("recorded but", (CHILD_ANCESTRY,), (("late_ancestry_parent", -1),)),
    "receipt, no ancestry": ("never recorded", (), (), f"the slice\n\n{RECEIPT}"),
    "claimed lineage only": ("no root", (CLAIMED_ANCESTRY,), (), RECEIPT),
    "unknown depth": ("depth None", (child_ancestry(lineage_depth=None),)),
    "depth of a root": ("depth 0", (child_ancestry(lineage_depth=0),)),
    "its own parent": ("own root or parent", (child_ancestry(parent_issue=CHILD),)),
    "depth 1 under another parent": ("#50 at depth 1", (child_ancestry(parent_issue=STRANGER),)),
    "depth 2 under the root": ("#41 at depth 2", (child_ancestry(lineage_depth=2),)),
    # A field its reader would answer with the empty value rather than refuse.
    "unreadable generation": (
        "`late_ancestry_generation`", (CHILD_ANCESTRY,), (("late_ancestry_generation", "bad"),),
    ),
    "a pointer outside the namespace": (
        "`late_ancestry_snapshot_ref`", (CHILD_ANCESTRY,), (("late_ancestry_snapshot_ref", "refs/heads/main"),),
    ),
    "a flag that is not true": (
        "`late_ancestry_mirror_first`", (CHILD_ANCESTRY,), (("late_ancestry_mirror_first", "true"),),
    ),
    # A `null` reads back as the field left out, and is not the same comment.
    **{
        f"a null {field}": (f"`{key}`", (CHILD_ANCESTRY,), ((key, None),))
        for field, key in (
            ("generation", "late_ancestry_generation"),
            ("snapshot commit", "late_ancestry_snapshot_sha"),
            ("flag", "late_ancestry_mirror_first"),
        )
    },
})

# A late record that disagrees with the lineage: a fragment of the refusal,
# then the issue, its records, and the edits over them. A record naming a
# lineage above an issue with no ancestry is one minted off an ancestry since
# lost, whether it split or not.
CONTRADICTING_RECORDS = MappingProxyType({
    "root mid-split": ("still creating", ROOT, (root_split(phase=LatePhase.SPLITTING),)),
    # Written before the first child is created, so it proves none and hides
    # whichever one the create may have landed.
    "splitting before any child": ("still creating", ROOT, (replace(ADJUDICATING_ROOT, phase=LatePhase.SPLITTING),)),
    "root record of another issue": ("for issue #57", ROOT, (root_split(current_issue=CHILD),)),
    # Its loop may have created a child before the write that records it.
    "cancelled mid-split": ("cancelled while it was creating", ROOT, (CANCELLED_MID_SPLIT,)),
    # Split nothing and charged nothing, and still minted off a root its
    # ancestry does not name.
    "an unsplit cycle rooted elsewhere": ("root #50, and its ancestry names root #41", CHILD, (
        CHILD_ANCESTRY, replace(ADJUDICATING_CHILD_RECORDS[1], root_issue=STRANGER),
    )),
    "a lost ancestry's lineage": ("root #41 at depth 1", CHILD, (LateGeneration(
        cycle_id=CHILD_CYCLE, generation=1, root_issue=ROOT, current_issue=CHILD, lineage_depth=1,
        candidate_sha=CHILD_SHA, phase=LatePhase.MEASURING,
    ),)),
    "split at another depth": (
        "depth 2", CHILD, (CHILD_ANCESTRY, child_split()), ((DEPTH_KEY, 2),),
    ),
})

# A late record whose identity is damaged or gone beside the fields it still
# names, keyed to a fragment of the refusal: the issue, its records, and the
# edits over them. Read typed, each would drop the record and with it a root
# and depth pointing elsewhere or a split contradicting the ancestry.
DAMAGED_RECORDS = MappingProxyType({
    "unreadable cycle, lineage elsewhere": ("`late_cycle_id`", CHILD, (
        root_split(current_issue=CHILD, lineage_depth=1, split_children=(), obligations=LateObligations()),
    ), ((CYCLE_KEY, "3"),)),
    "unreadable cycle, split deeper than its ancestry": ("`late_cycle_id`", CHILD, (
        CHILD_ANCESTRY, child_split(),
    ), ((CYCLE_KEY, -1), (DEPTH_KEY, 2))),
    "null cycle beside a register": ("`late_cycle_id`", ROOT, ROOT_RECORDS, ((CYCLE_KEY, None),)),
    "no cycle beside a register": ("beside no cycle", ROOT, ROOT_RECORDS, ((CYCLE_KEY, DROPPED),)),
    "unreadable counter": ("`late_generation`", ROOT, ROOT_RECORDS, (("late_generation", "1"),)),
    "unreadable root": ("`late_root_issue`", ROOT, ROOT_RECORDS, (("late_root_issue", 0),)),
    "unreadable current issue": ("`late_current_issue`", ROOT, ROOT_RECORDS, (("late_current_issue", True),)),
    "depth past the bound": ("`late_lineage_depth`", ROOT, ROOT_RECORDS, ((DEPTH_KEY, 9),)),
    # Split evidence the typed record would read as none: a phase that could
    # be the in-flight one, a register naming children, and a ledger that
    # could hold a consumer, each on a cycle that is otherwise ordinary.
    "unreadable phase": ("`late_phase`", ROOT, (ADJUDICATING_ROOT,), (("late_phase", "splitting!"),)),
    "unreadable register": (
        "`late_split_children`", ROOT, (ADJUDICATING_ROOT,), (("late_split_children", [CHILD, "58"]),),
    ),
    "null resources": ("`late_resources`", ROOT, (ADJUDICATING_ROOT,), (("late_resources", None),)),
    "null consumers": ("`late_consumers`", ROOT, (ADJUDICATING_ROOT,), (("late_consumers", None),)),
    "an announcement that is not true": (
        "`late_links_announced`", ROOT, (ADJUDICATING_ROOT,), (("late_links_announced", "yes"),),
    ),
    "an unreadable cancelled boundary": (
        "`late_cancelled_phase`", ROOT, (CANCELLED_MID_SPLIT,), (("late_cancelled_phase", "splitting!"),),
    ),
    # What a live cycle has to name, missing beside an ancestry that would
    # otherwise answer for the lineage on its own.
    "live cycle with no root": (
        "records no `late_root_issue`", CHILD, ADJUDICATING_CHILD_RECORDS, (("late_root_issue", DROPPED),),
    ),
    "live cycle with no issue": (
        "records no `late_current_issue`", CHILD, ADJUDICATING_CHILD_RECORDS, (("late_current_issue", DROPPED),),
    ),
    "live cycle with no depth": (
        "records no `late_lineage_depth`", CHILD, ADJUDICATING_CHILD_RECORDS, ((DEPTH_KEY, DROPPED),),
    ),
    "live root with no depth": ("records no `late_lineage_depth`", ROOT, (root_split(lineage_depth=None),)),
})

# Records that cannot say what a split made -- a snapshot is recorded before
# the first child, an unreadable entry may be one, and the announcement of the
# children's links is made after them and names none -- by the issue, its
# records, and the edits over them. An ancestry beside them settles the
# lineage, and still not which snapshot the split left.
AMBIGUOUS_SPLITS = MappingProxyType({
    "failed snapshot, retired": (ROOT, (LateGeneration(obligations=LateObligations(resources=(
        LateResource(LateResourceKind.SNAPSHOT_REF, ROOT_REF, LateResourceState.FAILED),
    ))),), ()),
    "held snapshot, no child": (ROOT, (root_split(split_children=(), obligations=LateObligations(resources=(
        LateResource(LateResourceKind.SNAPSHOT_REF, ROOT_REF, LateResourceState.RETAINED),
    )), phase=LatePhase.OWNER_CHECK),), ()),
    "opaque resources alone": (ROOT, (), (("late_resources", [{"kind": "tomorrow"}]),)),
    "opaque consumers alone": (ROOT, (), (("late_consumers", ["#57"]),)),
    "a descendant's failed snapshot": (CHILD, (CHILD_ANCESTRY, LateGeneration(obligations=LateObligations(
        resources=(LateResource(LateResourceKind.SNAPSHOT_REF, CHILD_REF, LateResourceState.FAILED),),
    ))), ()),
    "a root's announcement, no child record": (ROOT, (replace(
        ADJUDICATING_ROOT, phase=LatePhase.CLEANING_UP, links_announced=True,
    ),), ()),
    "a descendant's announcement, no child record": (CHILD, (CHILD_ANCESTRY, replace(
        ADJUDICATING_CHILD_RECORDS[1], phase=LatePhase.CLEANING_UP, links_announced=True,
    )), ()),
})


class OrdinaryProvenanceTest(unittest.TestCase):
    """An issue no late split ever charged inherits no lineage at all."""

    def test_an_issue_no_split_charged_is_ordinary(self) -> None:
        for label, records in ORDINARY.items():
            with self.subTest(label):
                decided = read(ROOT, records)

                self.assertEqual(decided, _provenance.LateProvenance())
                self.assertFalse(decided.is_inherited)
                self.assertFalse(decided.is_refused)


class InheritedProvenanceTest(unittest.TestCase):
    """A lineage a late split charged is named whole, snapshot and all."""

    def test_a_split_root_is_the_root_at_depth_zero(self) -> None:
        decided = read(ROOT, ROOT_RECORDS)

        self.assertEqual(decided, _provenance.LateProvenance(
            root_issue=ROOT,
            lineage_depth=0,
            snapshot=_entitlement.SnapshotEntitlement(
                owner_issue=ROOT,
                cycle_id=ROOT_CYCLE,
                generation=ROOT_GENERATION,
                snapshot_ref=ROOT_REF,
                snapshot_sha=ROOT_SHA,
                mirror_first=True,
            ),
        ))
        self.assertTrue(decided.is_inherited)
        self.assertFalse(decided.is_refused)

    def test_an_unheld_root_snapshot_still_charges(self) -> None:
        for label, case in UNHELD_ROOT_SNAPSHOTS.items():
            with self.subTest(label):
                self.assertEqual(
                    read(ROOT, *case), _provenance.LateProvenance(root_issue=ROOT, lineage_depth=0),
                )

    def test_a_descendant_inherits_its_ancestry(self) -> None:
        inherited = _entitlement.SnapshotEntitlement(
            owner_issue=ROOT,
            cycle_id=ROOT_CYCLE,
            generation=ROOT_GENERATION,
            snapshot_ref=ROOT_REF,
            snapshot_sha=ROOT_SHA,
            mirror_first=True,
        )
        # A restart hands the fresh cycle a depth of 0 whatever its ancestry
        # says; it split nothing, so it is no claim about the lineage.
        restarted = (CHILD_ANCESTRY, LateGeneration(cycle_id=2, root_issue=ROOT, current_issue=CHILD, lineage_depth=0))
        cases = (("unsplit", (CHILD_ANCESTRY,)), ("adjudicating", ADJUDICATING_CHILD_RECORDS), ("restarted", restarted))
        for label, records in cases:
            with self.subTest(label):
                self.assertEqual(
                    read(CHILD, records),
                    _provenance.LateProvenance(root_issue=ROOT, lineage_depth=1, snapshot=inherited),
                )

    def test_a_foreign_pointer_entitles_nothing(self) -> None:
        # A pointer at another split's ref is kept by a ledger nobody recorded
        # this lineage on.
        cases = (
            ("no pointer", child_ancestry(snapshot_ref="", snapshot_sha="")),
            ("another split's ref", child_ancestry(snapshot_ref=CHILD_REF)),
            # An identity no ref can be minted from names no ref, whatever
            # pointer stands beside it.
            ("an identity past the bound", child_ancestry(generation=UNMINTABLE_GENERATION)),
        )
        for label, recorded in cases:
            with self.subTest(label):
                self.assertEqual(
                    read(CHILD, (recorded,)), _provenance.LateProvenance(root_issue=ROOT, lineage_depth=1),
                )

    def test_each_child_proof_charges_the_root(self) -> None:
        for label, record in PROOFS.items():
            with self.subTest(label):
                self.assertEqual(
                    read(ROOT, (record,)), _provenance.LateProvenance(root_issue=ROOT, lineage_depth=0),
                )

    def test_a_grandchild_inherits_depth_two(self) -> None:
        self.assertEqual(read(GRANDCHILD, (GRANDCHILD_ANCESTRY,)), _provenance.LateProvenance(
            root_issue=ROOT,
            lineage_depth=2,
            snapshot=_entitlement.SnapshotEntitlement(
                owner_issue=CHILD,
                cycle_id=CHILD_CYCLE,
                generation=CHILD_GENERATION,
                snapshot_ref=CHILD_REF,
                snapshot_sha=CHILD_SHA,
                mirror_first=True,
            ),
        ))

    def test_a_split_descendant_offers_own_snapshot(self) -> None:
        # The replaced children were cut from #57's own candidate, so its
        # ancestry's older pointer is never the fallback.
        own = _entitlement.SnapshotEntitlement(
            owner_issue=CHILD,
            cycle_id=CHILD_CYCLE,
            generation=CHILD_GENERATION,
            snapshot_ref=CHILD_REF,
            snapshot_sha=CHILD_SHA,
            mirror_first=True,
        )
        for ref_state, snapshot in ((LateResourceState.RETAINED, own), (LateResourceState.RECONCILED, None)):
            with self.subTest(ref_state.value):
                self.assertEqual(
                    read(CHILD, (CHILD_ANCESTRY, child_split(ref_state))),
                    _provenance.LateProvenance(root_issue=ROOT, lineage_depth=1, snapshot=snapshot),
                )


class RefusedProvenanceTest(unittest.TestCase):
    """Late evidence that cannot place an issue is refused, never read as a root."""

    def test_an_unplaceable_ancestry_is_refused(self) -> None:
        for label, (reason, *case) in UNPLACEABLE_ANCESTRIES.items():
            with self.subTest(label):
                self._assert_refused(read(CHILD, *case), reason)

    def test_a_contradicting_late_record_is_refused(self) -> None:
        for label, (reason, *case) in CONTRADICTING_RECORDS.items():
            with self.subTest(label):
                self._assert_refused(read(*case), reason)

    def test_a_damaged_late_record_is_refused(self) -> None:
        for label, (reason, *case) in DAMAGED_RECORDS.items():
            with self.subTest(label):
                self._assert_refused(read(*case), reason)

    def test_an_ambiguous_split_is_refused(self) -> None:
        for label, case in AMBIGUOUS_SPLITS.items():
            with self.subTest(label):
                self._assert_refused(read(*case), "cannot be told")

    def test_invalid_child_evidence_is_refused(self) -> None:
        for label, record in INVALID_CHILDREN.items():
            with self.subTest(label):
                self._assert_refused(read(ROOT, (record,)), "not an issue, or that is this issue itself")

    def test_an_unparsed_comment_is_refused(self) -> None:
        # A comment that would not parse stands in as an empty payload, which
        # is exactly what an issue no split touched reads back as.
        unparsed = PinnedState(parsed=False)

        self._assert_refused(
            _provenance.read_provenance(unparsed, ROOT, "the issue as a human wrote it"), "could not be parsed",
        )

    def _assert_refused(self, decided: _provenance.LateProvenance, reason: str) -> None:
        self.assertTrue(decided.is_refused)
        self.assertFalse(decided.is_inherited)
        self.assertIsNone(decided.snapshot)
        self.assertIn(reason, decided.refusal or "")


if __name__ == "__main__":
    unittest.main()
