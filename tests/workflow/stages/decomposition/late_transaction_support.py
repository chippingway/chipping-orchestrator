# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One guarded split, driven straight into the transaction that runs it.

The transaction is entered from exactly one shape -- a `split` a fresh owner
read cleared -- so these tests build that shape and call the owner, rather than
paying for an agent run and an owner read to reach the same place. What the
coordinator does to GET here has its own modules; what happens once it has is
this one's subject.

The remote is the seam every case pins. Creating and proving a snapshot is a
push and a fetch against a real host, and the whole transaction turns on what
those two answer, so a case says which answers it is about with a seed and the
`late_seam_support` owner holds the rest.
"""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from types import MappingProxyType

from orchestrator.workflow.late_split import lineage as _lineage, state as _late_state
from orchestrator.workflow.stages.decomposition import (
    late_children as _late_children,
    late_hold as _late_hold,
    late_transaction as _late_transaction,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _GuardedSplit,
    _LateAdjudicationRun,
    _LateContext,
    _LateDisposition,
    _LateRun,
)
from tests.support.fakes import FakeGitHubClient
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.stages.decomposition import late_test_support as _support
from tests.workflow.stages.decomposition.late_seam_support import (
    SnapshotSeed,
    snapshot_seams,
)

# The manifest every case splits into, and the dependency between its two
# children -- so activation has one child to release and one to hold. Each
# slice declares the budget the reply contract requires of it, since that is
# the manifest the transaction is handed on every road that reaches it.
CHILDREN = (
    _support.proposed_slice("A", "the first slice", _support.FIRST_ESTIMATE),
    _support.proposed_slice("B", "the second slice", _support.SECOND_ESTIMATE, depends_on=(0,)),
)

# What the slice at the bottom of the chain below says it will add.
THIRD_ESTIMATE = 300

# A plan whose dependencies run two levels deep: the prerequisite that may
# land dormant, the consumer that waits on it, and the slice that waits on
# that one. A single level cannot show a graph recorded for a child that is
# neither the root nor a leaf of it.
MULTI_LEVEL_CHILDREN = (
    _support.proposed_slice("A", "the dormant prerequisite", _support.FIRST_ESTIMATE),
    _support.proposed_slice(
        "B", "the slice that consumes it", _support.SECOND_ESTIMATE, depends_on=(0,),
    ),
    _support.proposed_slice(
        "C", "the slice that activates the pair", THIRD_ESTIMATE,
        depends_on=(1,),
    ),
)

# The graph that plan records: one entry per child that waits on another, and
# none for the prerequisite nothing gates.
MULTI_LEVEL_GRAPH = MappingProxyType({"1": [0], "2": [1]})

SNAPSHOT_REF = (
    f"refs/orchestrator/late-split/issue-{_support.LATE_ISSUE_NUMBER}"
    f"/cycle-{_support.CYCLE_ID}/gen-{_support.GENERATION_NUMBER}"
)

KEY_CHILDREN = "children"
KEY_CONSUMERS = "late_consumers"
KEY_DEP_GRAPH = "dep_graph"
KEY_DECOMPOSED_AT = "decomposed_at"
KEY_LINKS_ANNOUNCED = "late_links_announced"
KEY_SPLIT_CHILDREN = "late_split_children"
KEY_EXPECTED_CHILDREN = "expected_children_count"
KEY_PARENT_NUMBER = "parent_number"
KEY_PR_NUMBER = "pr_number"
KEY_UMBRELLA = "umbrella"

# The terminal a cancelled cycle earns once it owes the remote nothing.
LABEL_REJECTED = "rejected"
KEY_RESOURCES = "late_resources"

KEY_ANCESTRY_REF = "late_ancestry_snapshot_ref"
KEY_ANCESTRY_SHA = "late_ancestry_snapshot_sha"
KEY_ANCESTRY_DEPTH = "late_ancestry_depth"
KEY_ANCESTRY_ROOT = "late_ancestry_root_issue"
KEY_ANCESTRY_PARENT = "late_ancestry_parent"
KEY_ANCESTRY_CYCLE = "late_ancestry_cycle_id"
KEY_ANCESTRY_GENERATION = "late_ancestry_generation"
KEY_ANCESTRY_BASE = "late_ancestry_base_branch"
KEY_DECLARED_SCOPE = "late_declared_scope"

# The two receipts this transaction stamps, spelled for the exact adjudication
# every case runs: a marker scoped to another one is a receipt for another
# episode, which is the whole reason they carry an identity at all.
SUPERSESSION_MARKER = (
    f"<!--orchestrator-late-supersession:issue={_support.LATE_ISSUE_NUMBER}"
    f":cycle={_support.CYCLE_ID}:generation={_support.GENERATION_NUMBER}-->"
)

FORWARD_LINK_MARKER = (
    f"<!--orchestrator-late-split:cycle={_support.CYCLE_ID}"
    f":generation={_support.GENERATION_NUMBER}-->"
)

EVENT_LATE_SNAPSHOT = "late_snapshot"
EVENT_LATE_CLEANUP = "late_cleanup"
EVENT_LATE_FAILURE = "late_failure"

PARK_SNAPSHOT_FAILED = "late_snapshot_failed"
PARK_CHILDREN_FAILED = "late_children_failed"
PARK_SUPERSESSION_FAILED = "late_supersession_failed"

WORKFLOW_LOG = "orchestrator.workflow"

ERROR = "ERROR"


class LateSplitCase:
    """One oversized issue whose adjudication decided to split it."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.generation = _support.late_generation()
        self.issue = _support.seed_late_issue(self.github, self.generation)
        # What the run's local teardown was asked to do, which no record
        # carries: a branch entry reads `failed` whether the local half ran
        # and did not finish or was never attempted at all.
        self.teardown = None

    def _transact(
        self,
        *,
        children=CHILDREN,
        snapshot=None,
        generation=None,
        killed=None,
        **state,
    ) -> _LateAdjudicationRun:
        """Run the transaction once over a guarded split, and report it."""
        if state:
            self.github.seed_state(
                self.issue.number, **{**self._pinned(), **state},
            )
        recorded = generation or self.generation
        context = _LateContext(
            gh=self.github,
            spec=_TEST_SPEC,
            issue=self.issue,
            state=self.github.read_pinned_state(self.issue),
            generation=recorded,
        )
        finished = _LateAdjudicationRun(
            disposition=_LateDisposition.DECIDED,
            generation=recorded,
            run=_LateRun(),
            guarded_split=_GuardedSplit(
                generation=recorded, children=tuple(children),
            ),
        )
        with snapshot_seams(snapshot or SnapshotSeed()) as teardown:
            self.teardown = teardown
            with killed or nullcontext():
                return _late_transaction._run_late_split(context, finished)

    def _resume(self, **run_fields) -> _LateAdjudicationRun:
        """Run the transaction again from the record it left behind.

        What the next eligible tick does: the recorded verdict is reused, the
        owner is read again, and the same guarded split reaches this owner
        with whatever the parked attempt made durable.
        """
        return self._transact(
            generation=_late_state.read_late_generation(
                self.github.read_pinned_state(self.issue),
            ),
            **run_fields,
        )

    def _pinned(self) -> dict:
        return self.github.pinned_data(self.issue.number)

    def _child_state(self, child_number: int) -> dict:
        return self.github.pinned_data(child_number)

    def _resources(self) -> dict:
        """The obligation ledger as {(kind, target): state}."""
        return {
            (entry["kind"], entry["target"]): entry["state"]
            for entry in self._pinned().get(KEY_RESOURCES) or []
        }

    def _events_named(self, family: str) -> list[dict]:
        return [
            record for record in self.github.recorded_events
            if record.get("event") == family
        ]


class HeldPlanPrSplitCase(LateSplitCase):
    """A split whose plan PR already wears this generation's hold.

    Seeded held rather than held by a first tick, because the subject is what
    the supersession does to it: reaching that state through an adjudication
    would cost a recorded verdict, and a recorded verdict is what stops the
    next tick spawning the run under test.
    """

    def setUp(self) -> None:
        super().setUp()
        self.generation = replace(
            self.generation,
            plan_pr_number=_support.PLAN_PR_NUMBER,
            plan_pr_body=_support.PLAN_PR_BODY,
        )
        self.github.seed_state(
            self.issue.number, **self._pinned(), pr_number=_support.PLAN_PR_NUMBER,
        )
        self.plan_pr = _support.seed_plan_pr(
            self.github, body=_late_hold._hold_body(self.generation),
        )


def label_of(github: FakeGitHubClient, issue_number: int) -> str:
    """The one workflow label an issue currently carries."""
    return next(
        label.name for label in github.get_issue(issue_number).labels
    )


def first_child(github: FakeGitHubClient):
    """The child a split created for the first slice of its manifest."""
    return github.created_child_issues[0]


def child_marker(generation, index: int) -> str:
    """The receipt this generation's slice `index` is stamped with.

    Through the production builder, so a test that plants one plants exactly
    what the lookup searches for.
    """
    return _late_children._child_marker(generation, index)


def sibling_marker(generation, parent_issue: int) -> str:
    """The child marker ANOTHER parent's first slice would carry.

    Built through the production builder rather than spelled out, so the day
    that identity stops naming the issue this reads as the same marker and the
    cross-parent adoption it guards against actually happens.
    """
    return _late_children._child_marker(
        replace(generation, current_issue=parent_issue), 0,
    )


def ancestry_of(github: FakeGitHubClient, issue_number: int):
    """What one child reads back as the lineage it was created under.

    Read through the domain's own reader rather than off the raw keys, so a
    test asserts on what a descendant's size gate will actually inherit
    rather than on the spelling it happens to be stored under.
    """
    return _lineage.read_late_ancestry(
        github.read_pinned_state(github.get_issue(issue_number)),
    )
