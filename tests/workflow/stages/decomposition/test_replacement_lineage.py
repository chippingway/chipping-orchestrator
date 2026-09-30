# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The lineage an ordinary split's children are born into, inside a late lineage.

A genuine edit hands the ordinary decomposer an issue a late split made, or one
whose own late split it is replacing. The children it answers with are still
cut inside that lineage, so each is seeded one level below its parent under
the same root, and pointed at a snapshot only where the parent's own consumer
ledger keeps that ref for it. A lineage the record cannot prove -- the
snapshot it may point at included -- creates nothing and starts nothing. What
a split a crash interrupted is repaired to is `test_recovery`'s subject.
"""
from __future__ import annotations

import json
import unittest
from dataclasses import dataclass, replace
from types import MappingProxyType

from orchestrator.workflow.late_split import (
    ancestry as _ancestry,
    lineage as _lineage,
    models as _late_models,
    obligations as _obligations,
)
from orchestrator.workflow.stages.decomposition import (
    blocked as _blocked,
    replacement_lineage as _replacement_lineage,
    umbrella as _umbrella,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.fixtures import (
    _TEST_SPEC,
    _agent,
    _authorized_exemption,
    _manifest,
    _PatchedWorkflowMixin,
    _reported,
)
from tests.workflow.stages.decomposition import replacement_lineage_support as _support

RUN_AGENT = "run_agent"

# The ref a descendant's own ancestry points it at -- its parent's, kept for it
# on that parent's ledger and for none of the children it creates -- and a ref
# no split of this lineage made.
_ANCESTOR_REF = "refs/orchestrator/late-split/issue-40/cycle-2/gen-1"

_FOREIGN_REF = "refs/orchestrator/late-split/issue-4/cycle-2/gen-1"

# The heading a child's reuse instructions open under, naming the parent whose
# own split preserved the snapshot.
_REUSE_HEADING = f"## Reusing the work already committed for #{_support.PARENT}"

# What a descendant that never split is cut from: two levels below the root,
# through an issue that is not the root.
_GRANDPARENT = 40

# A key of the ancestry group standing with none of the rest: a record that
# names no parent and cycle, so no lineage can be read off it.
_STRAY_ANCESTRY_KEY = "late_ancestry_depth"

# The seeding a case names the parent's own late record under.
_GENERATION = "generation"

# What every seed carries beside the lineage, and the group that lineage is.
_SEEDED_LINK = frozenset((_support.KEY_PARENT_NUMBER, _support.KEY_CREATED_AT))

_ANCESTRY_KEYS = frozenset(_lineage.LATE_ANCESTRY_KEYS)

# What the park says where the lineage itself could not be read.
_UNREAD_LINEAGE = "would read as a fresh lineage at depth 0"


@dataclass(frozen=True)
class _Lineage:
    """One parent's late record, and what its replacements are born with.

    `protected` says whether the parent's own ledger keeps a snapshot for
    them: it is what a pointer on the child and a consumer slot on the parent
    both follow from.
    """

    generation: _late_models.LateGeneration | None
    ancestry: _ancestry.LateAncestry | None
    born: _ancestry.LateAncestry
    protected: bool


def _born(root: int, depth: int, cycle: int = _support.CYCLE, *, pointer: bool) -> _ancestry.LateAncestry:
    """What a replacement of the parent is seeded with."""
    ancestry = _ancestry.LateAncestry(
        root_issue=root,
        lineage_depth=depth,
        parent_issue=_support.PARENT,
        cycle_id=cycle,
        generation=_support.GENERATION,
    )
    if not pointer:
        return ancestry
    return replace(
        ancestry, snapshot_ref=_support.SNAPSHOT_REF, snapshot_sha=_support.CANDIDATE_SHA, mirror_first=True,
    )


# Root and descendant replacements. The snapshot a descendant was itself cut
# from is its parent's ledger's to keep, so it is never handed down; the one a
# parent's own split holds is, while that ledger still holds it.
_LINEAGES = MappingProxyType({
    "a root that split": _Lineage(_support.own_split(), None, _support.ROOT_REPLACEMENT, protected=True),
    "a descendant that split": _Lineage(
        _support.own_split(root_issue=_support.ANCESTOR, lineage_depth=1),
        _support.cut_from_ancestor(),
        _born(_support.ANCESTOR, 2, pointer=True),
        protected=True,
    ),
    "a descendant that never split": _Lineage(
        None,
        _support.cut_from_ancestor(depth=2, parent=_GRANDPARENT),
        _born(_support.ANCESTOR, 3, _support.ANCESTOR_CYCLE, pointer=False),
        protected=False,
    ),
    "a root whose ref is gone": _Lineage(
        _support.own_split(_obligations.LateResourceState.RECONCILED), None, _support.ROOT_LINEAGE, protected=False,
    ),
})

# Parents whose children's lineage cannot be proved, as each is seeded.
_REFUSALS = MappingProxyType({
    "a parent already at the bound": (
        MappingProxyType({
            "ancestry": _support.cut_from_ancestor(depth=_late_models.MAX_LINEAGE_DEPTH, parent=_GRANDPARENT),
        }),
        "no split may create a child past depth",
    ),
    "an ancestry that names no parent": (
        MappingProxyType({_GENERATION: _support.own_split(), _STRAY_ANCESTRY_KEY: 1}),
        _UNREAD_LINEAGE,
    ),
    # The parent's own split holds its snapshot, and its consumer ledger is one
    # no replacement can be recorded on: not the same thing as a ref gone, and
    # nothing to do with the lineage, which is proved.
    "a held snapshot no consumer can be added to": (
        MappingProxyType({_GENERATION: _support.own_split(), _support.KEY_CONSUMERS: [_support.ORIGINAL, "#57"]}),
        "lineage this issue's children inherit is proved, and the snapshot",
    ),
    # Held and protectable, and its instructions would name the candidate's
    # change as a range from a base nobody recorded.
    "a held snapshot recorded with no base": (
        MappingProxyType({_GENERATION: _support.own_split(base_sha="")}),
        "recorded with no base its candidate was cut against",
    ),
    "a child receipt with no ancestry": (
        MappingProxyType({
            "body": "\n\n".join((
                _support.EDITED_BODY,
                _ancestry.child_marker(issue=_support.ANCESTOR, cycle=_support.ANCESTOR_CYCLE, generation=1, index=0),
            )),
        }),
        _UNREAD_LINEAGE,
    ),
})


def _seeded(github, number: int) -> _ancestry.LateAncestry:
    """The ancestry one child's pinned comment records."""
    return _lineage.read_late_ancestry(github.read_pinned_state(github.get_issue(number)))


class InheritedLineageTest(unittest.TestCase):
    """Replacements are born one level below their parent, never at depth 0."""

    def test_replacements_are_born_below_the_parent(self) -> None:
        for shape, lineage in _LINEAGES.items():
            with self.subTest(shape=shape):
                github, issue = _support.late_parent(lineage.generation, lineage.ancestry)
                recorded = _support.consumers(github)

                _support.redecompose(github, issue)

                self._assert_born(github, lineage, recorded)

    def test_a_slice_may_name_its_own_snapshot(self) -> None:
        # The one ref kept for the child is the one its instructions name, by
        # either name they give it, however the text around it wraps it.
        for named in (
            _support.SNAPSHOT_REF,
            _support.OWN_MIRROR,
            f"`{_support.SNAPSHOT_REF}`",
            f"(`{_support.OWN_MIRROR}`).",
            f"+{_support.SNAPSHOT_REF}:{_support.OWN_MIRROR}",
        ):
            with self.subTest(named=named):
                github, issue = _support.late_parent(_support.own_split())

                _support.redecompose(github, issue, _slice_naming(named))

                child = _support.replacements(github)[0]
                self.assertIn(child, _support.consumers(github))
                self.assertEqual(_seeded(github, child), _support.ROOT_REPLACEMENT)

    def test_a_seed_carries_nothing_of_the_gate(self) -> None:
        # The parent carries the whole bypass an operator granted a commit of
        # its own; what its children are seeded with is a parent link, a
        # stamp, and a lineage, written fresh.
        bypass = _authorized_exemption(_support.CANDIDATE_SHA, _support.BASE_SHA)
        github, issue = _support.late_parent(_support.own_split(), **bypass)

        _support.redecompose(github, issue)

        for number in _support.replacements(github):
            with self.subTest(child=number):
                seeded = set(github.pinned_data(number))
                self.assertEqual(seeded - _ANCESTRY_KEYS, _SEEDED_LINK)
                self.assertFalse(seeded & set(bypass))

    def _assert_born(self, github, lineage: _Lineage, recorded: list) -> None:
        """Every replacement is tracked, seeded with `lineage`, and protected by it."""
        created = _support.replacements(github)
        seeded = [_seeded(github, number) for number in created]
        protected = sorted([*recorded, *created]) if lineage.protected else recorded
        briefed = {_REUSE_HEADING in github.get_issue(number).body for number in created}
        self.assertEqual(len(created), _support.REPLACEMENT_COUNT)
        self.assertEqual(github.pinned_data(_support.PARENT)[_support.KEY_CHILDREN], created)
        self.assertEqual(github.workflow_label(github.get_issue(_support.PARENT)), WorkflowLabel.UMBRELLA)
        self.assertEqual(_support.consumers(github), protected)
        self.assertEqual(set(seeded), {lineage.born})
        # Told where the snapshot is exactly where it is pointed at one.
        self.assertEqual(briefed, {lineage.protected})


class ReuseInstructionsTest(_PatchedWorkflowMixin, unittest.TestCase):
    """What the implementer of a protected replacement is shown about its snapshot."""

    def test_the_implementer_reads_the_snapshot(self) -> None:
        # The slice first, then the reuse instructions for the one ref the
        # child's pointer names: the implementer reads the body, never the
        # pinned comment the pointer is recorded on.
        github, issue = _support.late_parent(_support.own_split())
        _support.redecompose(github, issue, _support.ONE_REPLACEMENT_MANIFEST)

        prompt = self._implementer_prompt(github)

        self.assertLess(prompt.index("the whole of it, as the edit now asks"), prompt.index(_REUSE_HEADING))
        for named in (_support.SNAPSHOT_REF, _support.CANDIDATE_SHA, _support.BASE_SHA):
            with self.subTest(named=named):
                self.assertIn(named, prompt)

    def _implementer_prompt(self, github) -> str:
        """Pick the replacement up, and hand back what its implementer is asked."""
        child = github.created_child_issues[0]
        mocks = self._run(
            lambda: _blocked._handle_ready(github, _TEST_SPEC, child),
            run_agent=_agent(last_message=_reported()),
        )
        return mocks[RUN_AGENT].call_args.args[1]


def _slice_naming(*refs: str) -> str:
    """A one-child umbrella manifest whose slice tells its child to reuse `refs`."""
    told = " and ".join(refs)
    return _manifest(json.dumps({
        "decision": "split",
        "umbrella": True,
        "rationale": "re-planned",
        "children": [{"title": "A", "body": f"the whole of it; reuse what {told} holds."}],
    }))


# A root whose own split holds the snapshot its replacements are pointed at.
_ROOT_SPLIT = MappingProxyType({_GENERATION: _support.own_split()})

# Slices whose own text tells a child to reuse a snapshot nothing keeps for it,
# by the parent's record and the ref the slice names.
_UNSUPPORTED = MappingProxyType({
    "a descendant told its ancestor's ref": (
        MappingProxyType({"ancestry": _support.cut_from_ancestor(depth=2, parent=_GRANDPARENT)}),
        _slice_naming(_ANCESTOR_REF),
        _ANCESTOR_REF,
    ),
    "a root replacement told a foreign ref beside its own": (
        _ROOT_SPLIT,
        _slice_naming(_support.SNAPSHOT_REF, _FOREIGN_REF),
        _FOREIGN_REF,
    ),
    # The same three numbers, fetched for another repository sharing the
    # clone: that repository's work, and on no ledger this parent writes.
    "a root replacement told another repository's mirror of its own ref": (
        _ROOT_SPLIT,
        _slice_naming(_support.FOREIGN_MIRROR),
        _support.FOREIGN_MIRROR,
    ),
    # Whole names that contain its own ref, which git would fetch as the
    # different refs they are.
    "a root replacement told a ref running on past its own": (
        _ROOT_SPLIT,
        _slice_naming(_support.EXTENDED_REF),
        _support.EXTENDED_REF,
    ),
    "a root replacement told a ref running on past its own inside backticks": (
        _ROOT_SPLIT,
        _slice_naming(f"`{_support.EXCLAIMED_REF}`"),
        _support.EXCLAIMED_REF,
    ),
    "a root replacement told a ref running on past its own through a non-breaking space": (
        _ROOT_SPLIT,
        _slice_naming(f"`{_support.SPACED_REF}`"),
        _support.SPACED_REF,
    ),
    "a root replacement told its own ref nested under another": (
        _ROOT_SPLIT,
        _slice_naming(_support.NESTED_REF),
        _support.NESTED_REF,
    ),
})


# What the parent's own snapshot entry reads as at the poll that would release
# a dependent replacement -- as its split left it, and no longer proved -- each
# beside the label that replacement ends on and the parks the parent takes.
_DEFERRED = MappingProxyType({
    "held": ("retained", WorkflowLabel.READY, []),
    "no longer proved": ("pending", WorkflowLabel.BLOCKED, [_replacement_lineage.PARK_LINEAGE_UNPROVED]),
})


class UnprovedLineageTest(unittest.TestCase):
    """A lineage that cannot be proved parks the split before any child exists, or before a later one starts."""

    def test_unsupported_reuse_creates_nothing(self) -> None:
        # The implementer reads the body, so a slice pointing at a ref the
        # child would not be recorded as a consumer of is refused as it
        # arrives -- not only when a crash is recovered.
        for shape, (seeded, answer, said) in _UNSUPPORTED.items():
            with self.subTest(shape=shape):
                github = self._refused(seeded, answer)

                self._assert_held(github, said)

    def test_nothing_is_created_or_started(self) -> None:
        for shape, (seeded, said) in _REFUSALS.items():
            with self.subTest(shape=shape):
                github, issue = _support.late_parent(**seeded)

                _support.redecompose(github, issue)[RUN_AGENT].assert_called_once()

                self._assert_held(github, said)

    def test_a_lapsed_proof_releases_no_dependent(self) -> None:
        # A dependent replacement is released polls after the split proved
        # its lineage, off the parent's record as it stands then -- so the
        # proof is asked again in front of that release, and the parent parks
        # once rather than on every poll that holds it.
        for shape, (entry_state, label, parked) in _DEFERRED.items():
            with self.subTest(shape=shape):
                self.assertEqual(self._released_after(entry_state), (label, parked))

    def _released_after(self, entry_state: str) -> tuple:
        """Where the dependent replacement and the parent's parks stand after two dependency polls.

        The split lands with the snapshot held, the first replacement then
        finishes, and the parent's own snapshot entry is put at `entry_state`
        before the polls that would release the second.
        """
        github, issue = _support.late_parent(_support.own_split())
        _support.redecompose(github, issue, _support.DEPENDENT_MANIFEST)
        first, second = _support.replacements(github)
        github.set_workflow_label(github.get_issue(first), WorkflowLabel.DONE, guarded=False)
        self._restate_snapshot(github, entry_state)
        for _ in range(2):
            _support.redecompose(github, issue, tick=_umbrella._handle_umbrella)
        return github.workflow_label(github.get_issue(second)), _support.parks(github)

    def _restate_snapshot(self, github, entry_state: str) -> None:
        """Put the parent's own snapshot entry at `entry_state`, every other entry as it stands."""
        pinned = github.pinned_data(_support.PARENT)
        restated = [
            {**entry, "state": entry_state} if entry.get("target") == _support.SNAPSHOT_REF else entry
            for entry in pinned["late_resources"]
        ]
        github.seed_state(_support.PARENT, **{**pinned, "late_resources": restated})

    def _refused(self, seeded, answer: str):
        """Seed the parent, run the decomposing tick it answers, and hand back its client."""
        github, issue = _support.late_parent(**seeded)
        _support.redecompose(github, issue, answer)[RUN_AGENT].assert_called_once()
        return github

    def _assert_held(self, github, said: str) -> None:
        """Nothing created or relabelled, and the park ahead of every marker.

        Ahead of the markers a recovery would read as a split, so the next
        answer is the decomposer's again -- and its notice says which of the
        things a split needs did not hold.
        """
        pinned = github.pinned_data(_support.PARENT)
        self.assertIn(said, github.posted_comments[-1][1])
        self.assertEqual(github.created_child_issues, [])
        self.assertEqual(github.label_history, [])
        self.assertTrue(pinned[_support.KEY_AWAITING_HUMAN])
        self.assertNotIn(_support.KEY_EXPECTED, pinned)
        self.assertEqual(_support.parks(github), [_replacement_lineage.PARK_LINEAGE_UNPROVED])


if __name__ == "__main__":
    unittest.main()
