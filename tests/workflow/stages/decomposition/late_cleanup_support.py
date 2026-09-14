# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One umbrella made by a split, and what it still owes a remote.

Shared by the three modules that ask about it, because they ask about the same
issue from three ends: what a branch obligation costs the terminal, when the
snapshot it is holding may finally go, and what is left to settle once a human
has closed the owner mid-cycle. Every one of them drives the real handler,
since what is under test is exactly the routing -- an issue that has become an
umbrella never reaches the transaction again, and a closed one is never
dispatched to the stage its label names.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from orchestrator.workflow.late_split import ancestry as _ancestry, lineage as _lineage, state as _late_state
from orchestrator.workflow.late_split.obligations import (
    LateObligations,
    LateResource,
    LateResourceKind,
    LateResourceState,
)
from orchestrator.workflow.late_split.phases import LatePhase
from orchestrator.workflow.stages.decomposition import late_sweep as _late_sweep, umbrella as _umbrella
from orchestrator.workflow.stages.decomposition.models import _ChildScan
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import _TEST_SPEC, _agent
from tests.workflow.stages.decomposition.late_seam_support import (
    LocalTeardown,
    RecordedDelete,
    SnapshotOutcome,
    local_teardown,
)
from tests.workflow.stages.decomposition.late_test_support import (
    CANDIDATE_SHA,
    CYCLE_ID,
    GENERATION_NUMBER,
    LINEAGE_DEPTH,
    ROOT_ISSUE,
    late_generation,
)

UMBRELLA = "workflow:umbrella"

DECOMPOSING = "workflow:decomposing"

LABEL_DONE = "done"

LABEL_REJECTED = "rejected"

LABEL_IN_REVIEW = "workflow:in_review"

LABEL_READY = "workflow:ready"

LABEL_BLOCKED = "workflow:blocked"

PARENT_NUMBER = 41

CHILD_NUMBER = 411

# The second slice's child: created on GitHub and never recorded, which is
# what the crash between the two writes leaves behind.
UNRECORDED_CHILD = 412

SUPERSEDED_BRANCH = "orchestrator/chippingway__orchestrator/issue-41"

SNAPSHOT_REF = "refs/orchestrator/late-split/issue-41/cycle-3/gen-1"

# The issue a NESTED owner was itself cut from, and the moment either
# observer marks a cycle over. Both are fixed so a case can assert on them.
ANCESTOR_NUMBER = 4

CANCELLED_AT = "2026-08-22T10:00:00+00:00"

# The stage key the split transaction writes before its first create, and
# the one piece of evidence a rewound phase cannot erase.
EXPECTED_CHILDREN = "expected_children_count"

# The ledger entry kinds a reclamation acts on, and the one beside them
# that is a receipt rather than an obligation: a child is a live issue,
# not an object on the remote.
RECLAIMABLE_KINDS = ("branch", "snapshot_ref", "plan_pr")

CHILD_KIND = "child"

# The phases a record only reaches past the forward-links announcement,
# which is written in the same step as the first of them.
_PAST_ANNOUNCEMENT = (LatePhase.SUPERSEDING, LatePhase.CLEANING_UP)

STATE_RECONCILED = "reconciled"

STATE_FAILED = "failed"

STATE_RETAINED = "retained"

STATE_RECLAIMING = "reclaiming"

EVENT_LATE_CLEANUP = "late_cleanup"

RESOLVED_STAMP = "umbrella_resolved_at"

WORKFLOW_LOG = "orchestrator.workflow"


@dataclass(frozen=True)
class OwnerSeed:
    """Which owner a case is about, and how its one consumer stands.

    The defaults are the umbrella the terminal reaches: open, on `umbrella`,
    with a child that ended -- which means closed, because every disposition
    that ends a child closes it as it fires. A case says otherwise when it is
    about a closed owner (swept under either cleanup label) or about a
    consumer a human reopened, which is the state no label records and the one
    the reclamation rule reads.

    `child_ref` is the snapshot the consumer's own ancestry names, which is
    what decides whether this owner may speak for it: a child pointed at a
    sibling generation's ref belongs to that generation. `child_ancestry` is
    False for the crash window the split leaves when it records a child and
    then cannot seed it: the body still carries the marker the create stamped
    into it, and the pinned comment carries nothing.

    `child` is False for the interval BEFORE that: the ref is preserved and
    proved ahead of the first child issue, so an owner closed in there records
    a snapshot and no consumers at all.

    `recorded` is False for the issue that never entered the late gate at all,
    which is every umbrella the initial decomposer ever made: it carries one
    of the two swept labels and no generation, so nothing about a late cycle
    is its to end.

    `cancelled` is the mark either observer leaves -- the flag, the stamp, and
    the boundary it interrupted -- which is what a case about the ending
    starts from rather than reaching through the observer that writes it.

    `announced` is the forward-links receipt the transaction writes in the
    same step as `superseding`, and it is derived from the phase for every
    seed at or past that boundary. A case says it explicitly for the one
    shape where the two disagree: a supersession retried after a park, which
    rewrites the earlier phases over the boundary while stepping over the
    announcement it already made.

    `ancestor_ref` makes this owner somebody else's child as well as its own
    split's owner, which every late owner below the root of a lineage is. It
    is what a case needs to reach the reuse guard that shares the dispatcher's
    one pinned read with the cancellation guard.

    `child_mirror_first` is the ordering claim the split stamps onto every
    pointer it writes -- that the reclamation which can take this ref drops
    this host's copy of it first. False is a pointer written by an
    orchestrator that took the remote first and the mirror afterwards, which
    is what a repository upgraded mid-lineage still carries.

    `phase` defaults to what a finished split leaves, which is what every
    umbrella and every closed owner past its transaction really carries: the
    children are all created and all recorded, so the consumer ledger is the
    whole account of who was cut from the ref. A case about a split still IN
    its loop says `splitting` -- there the list may be short by a child that
    already exists, and nothing on the ref may be reclaimed.
    """

    label: str = UMBRELLA
    closed: bool = False
    recorded: bool = True
    cancelled: bool = False
    announced: bool = False
    ancestor_ref: str = ""
    child: bool = True
    child_closed: bool = True
    child_ref: str = SNAPSHOT_REF
    child_ancestry: bool = True
    child_mirror_first: bool = True
    phase: LatePhase = LatePhase.CLEANING_UP

    def seed_ancestry(self, github: FakeGitHubClient, parent) -> None:
        """Give the OWNER an ancestry of its own, for a nested split.

        Written after the generation rather than before it, because the two
        are separate key groups and only the order of the seeding says which
        write is the one the fake keeps.
        """
        if not self.ancestor_ref:
            return
        recorded = github.read_pinned_state(parent)
        _lineage.write_late_ancestry(recorded, _ancestry.LateAncestry(
            root_issue=ANCESTOR_NUMBER,
            lineage_depth=LINEAGE_DEPTH,
            parent_issue=ANCESTOR_NUMBER,
            cycle_id=CYCLE_ID,
            generation=GENERATION_NUMBER,
            snapshot_ref=self.ancestor_ref,
            snapshot_sha=CANDIDATE_SHA,
            mirror_first=True,
            scope="the slice this owner was cut for",
        ))
        github.seed_state(PARENT_NUMBER, **recorded.data)

    def seed_child(self, github: FakeGitHubClient, child_label: str) -> None:
        """Add the one consumer, with the ancestry a split writes on it.

        Always an ancestry, because a split always writes one: it is the
        record that says which generation this child was cut from and which
        ref it may reuse, and a reclamation reads it to decide whom it may
        speak for.
        """
        if not self.child:
            return
        child = make_issue(
            CHILD_NUMBER,
            label=child_label,
            closed=self.child_closed,
            body="\n\n".join((
                "the slice this child owns",
                _ancestry.child_marker(
                    issue=PARENT_NUMBER,
                    cycle=CYCLE_ID,
                    generation=GENERATION_NUMBER,
                    index=0,
                ),
            )),
        )
        github.add_issue(child)
        if not self.child_ancestry:
            return
        recorded = github.read_pinned_state(child)
        _lineage.write_late_ancestry(recorded, _ancestry.LateAncestry(
            root_issue=ROOT_ISSUE,
            lineage_depth=LINEAGE_DEPTH + 1,
            parent_issue=PARENT_NUMBER,
            cycle_id=CYCLE_ID,
            generation=GENERATION_NUMBER,
            snapshot_ref=self.child_ref,
            snapshot_sha=CANDIDATE_SHA,
            mirror_first=self.child_mirror_first,
            scope="the slice this child owns",
        ))
        github.seed_state(CHILD_NUMBER, **recorded.data)


@dataclass(frozen=True)
class SeededUmbrella:
    """The parent one case walks, and the client it lives on."""

    github: FakeGitHubClient
    parent: object

    def swept(
        self, case, outcome=SnapshotOutcome.DELETED, **answers,
    ) -> RecordedDelete:
        """Sweep this owner as closed, the remote answering `outcome`."""
        return self.swept_by(case, RecordedDelete(outcome, **answers))

    def swept_by(self, case, remote: RecordedDelete) -> RecordedDelete:
        """Sweep this owner as closed, with a prepared remote answering.

        The real handler, because half of what a closed owner's cases ask
        about is the routing: its ledger is reached through the cleanup sweep
        and never through the stage handler its label names. A case hands its
        own recorder in where what it is about is WHEN the remote was asked
        rather than what it answered.
        """
        with remote.answering():
            walk_owner(case, self, _late_sweep._handle_closed_owner_cleanup)
        return remote


def split_umbrella(
    owed: LateResourceState | None,
    *,
    snapshot: LateResourceState | None = None,
    child_label: str = LABEL_DONE,
    branch: str = SUPERSEDED_BRANCH,
    owner: OwnerSeed | None = None,
) -> SeededUmbrella:
    """An umbrella whose children are done and whose remote is still owed.

    `owed=None` is the cycle that never got as far as superseding anything,
    so its ledger records no branch at all.
    """
    seed = owner or OwnerSeed()
    github = FakeGitHubClient()
    parent = make_issue(PARENT_NUMBER, label=seed.label, closed=seed.closed)
    github.add_issue(parent)
    seed.seed_child(github, child_label)
    if not seed.recorded:
        github.seed_state(PARENT_NUMBER, umbrella=True)
        return SeededUmbrella(github=github, parent=parent)
    settled = late_generation(
        threshold=None, additions=None, phase=seed.phase,
        obligations=LateObligations().with_consumers(
            (CHILD_NUMBER,) if seed.child else (),
        ),
    )
    if seed.child:
        # What the split writes for a child in ONE step: the consumer, the
        # positional register, and the obligation entry. A fixture recording
        # fewer of the three describes no record production can produce.
        settled = replace(
            settled.with_split_children((CHILD_NUMBER,)),
            obligations=settled.obligations.with_resource(LateResource(
                kind=LateResourceKind.CHILD,
                target=str(CHILD_NUMBER),
                resource_state=LateResourceState.PENDING,
            )),
        )
    if owed is not None:
        settled = replace(
            settled, obligations=settled.obligations.with_resource(LateResource(
                kind=LateResourceKind.BRANCH,
                target=branch,
                resource_state=owed,
            )),
        )
    if snapshot is not None:
        settled = replace(
            settled, obligations=settled.obligations.with_resource(LateResource(
                kind=LateResourceKind.SNAPSHOT_REF,
                target=SNAPSHOT_REF,
                resource_state=snapshot,
            )),
        )
    if seed.announced or seed.phase in _PAST_ANNOUNCEMENT:
        settled = replace(settled, links_announced=True)
    if seed.cancelled:
        settled = replace(
            settled.cancel(CANCELLED_AT), phase=LatePhase.CANCELLING,
        )
    recorded = github.read_pinned_state(parent)
    _late_state.write_late_generation(recorded, settled)
    github.seed_state(
        PARENT_NUMBER,
        children=[CHILD_NUMBER] if seed.child else [],
        umbrella=True,
        **recorded.data,
    )
    seed.seed_ancestry(github, parent)
    return SeededUmbrella(github=github, parent=parent)


def walk_owner(
    case,
    seeded: SeededUmbrella,
    tick=_umbrella._handle_umbrella,
    *,
    local_gone: bool = True,
) -> LocalTeardown:
    """Run one tick over this owner through the real handler that answers it.

    The umbrella's own poll by default, and the cleanup sweep where a case is
    about a closed owner -- the two entries into the same reclamation.

    The local teardown it held is handed back, because what a reclamation
    asked of the checkout is not something the ledger records: an entry reads
    `failed` whether the local half ran and did not finish or was never
    attempted at all.
    """
    with local_teardown(local_gone=local_gone) as teardown:
        case._run(
            lambda: tick(seeded.github, _TEST_SPEC, seeded.parent),
            run_agent=_agent(),
        )
        return teardown


def resource_states(
    github: FakeGitHubClient, kind: str | None = None,
) -> dict:
    """What the parent's ledger records, by target, for one kind of entry.

    Defaulted to the RECLAIMABLE kinds -- the branch, the ref, and the held
    plan PR -- because that is the ledger every reclamation case is about, and
    the child receipts beside them are neither asked about nor acted on there.
    A case about the receipts themselves names `child` and gets those.
    """
    recorded = github.pinned_data(PARENT_NUMBER).get("late_resources") or []
    wanted = (kind,) if kind else RECLAIMABLE_KINDS
    return {
        entry["target"]: entry["state"]
        for entry in recorded
        if entry["kind"] in wanted
    }


def seed_unrecorded_child(github: FakeGitHubClient) -> None:
    """Add a child of this split that its parent's ledger never took.

    The split opens a child issue and records it in two writes -- it must,
    since a child on GitHub the parent does not record is a child nothing
    would come back to -- so a tick that died between them leaves exactly
    this: an issue carrying the marker the create stamped into its body, and
    a parent whose consumer list stops one short of it.
    """
    github.add_issue(make_issue(
        UNRECORDED_CHILD,
        label=LABEL_BLOCKED,
        body="\n\n".join((
            "the slice nobody recorded",
            _ancestry.child_marker(
                issue=PARENT_NUMBER,
                cycle=CYCLE_ID,
                generation=GENERATION_NUMBER,
                index=1,
            ),
        )),
    ))


def scan_of(label, *, closed: bool = False) -> _ChildScan:
    """The umbrella's own child scan, reporting one child this way."""
    child = make_issue(CHILD_NUMBER, label=label)
    child.closed = closed
    return _ChildScan(
        children=[CHILD_NUMBER],
        issues={CHILD_NUMBER: child},
        labels={CHILD_NUMBER: label},
    )
