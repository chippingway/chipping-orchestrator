# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The lineage an ordinary split seeds its replacements with, decided off the parent's record.

A genuine edit hands the ordinary decomposer an issue a late split made, or one
whose own late split it is replacing. The children it cuts are still inside
that lineage, so each is born one level below its parent under the same root,
pointed at a snapshot only where the parent's own split holds it, and told that
snapshot by exactly the names its instructions give it. A record that cannot
prove the lineage, a bound with no room, and a snapshot neither held nor
released are refusals. The decision is driven directly here; what a split, its
recovery, and its release do with it is `test_replacement_split`'s subject and
the recovery and release tests beside it.
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass, replace
from types import MappingProxyType

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    ancestry as _ancestry,
    models as _late_models,
    obligations as _obligations,
)
from orchestrator.workflow.stages.decomposition import (
    late_child_content as _late_child_content,
    replacement_lineage as _replacement_lineage,
)
from tests.workflow.fixtures import _TEST_SPEC, _authorized_exemption
from tests.workflow.stages.decomposition import replacement_lineage_support as _support

# The replacements a split would record, the second never on the ledger.
PROTECTED_CHILD = 412

UNPROTECTED_CHILD = 413

# A ref no split of the parent made, and the one a descendant's ancestry points
# at -- its parent's, kept on that parent's ledger alone.
FOREIGN_REF = "refs/orchestrator/late-split/issue-4/cycle-2/gen-1"

ANCESTOR_REF = "refs/orchestrator/late-split/issue-40/cycle-2/gen-1"

# The two names a protected replacement's instructions give its snapshot.
TOLD = frozenset((_support.SNAPSHOT_REF, _support.OWN_MIRROR))

KEY_RESOURCES = "late_resources"

KEY_CONSUMERS = "late_consumers"

# A key of the ancestry group standing with none of the rest.
STRAY_ANCESTRY_KEY = "late_ancestry_depth"

# What an issue that reached this workflow another way carries.
LEGACY_STATE = MappingProxyType({"dev_agent": "codex", "parent_number": 12})

_RECONCILED = _obligations.LateResourceState.RECONCILED

# What a snapshot entry stands at once a reclamation has decided its ref goes.
_RELEASED = (_obligations.LateResourceState.RECLAIMING, _RECONCILED, _obligations.LateResourceState.FAILED)

# What every refusal of the snapshot says, the lineage beside it proved.
_SNAPSHOT_REFUSED = "lineage this issue's children inherit is proved, and the snapshot"

_LINEAGE_REFUSED = "would read as a fresh lineage at depth 0"

_UNPROTECTABLE = "no child can be recorded"

_UNSETTLED = "neither held nor released"

# A descendant that never split: its ancestry points at its own parent's ref.
_UNSPLIT_DESCENDANT = _support.cut_from_ancestor(depth=2, parent=_support.GRANDPARENT)

# Parents whose replacements are born into a lineage and pointed at nothing.
# The snapshot a descendant was itself cut from is its parent's ledger's to
# keep, so it is never handed down; a split's own ref, once a reclamation has
# taken it past `retained`, is owed to no new child.
_UNPOINTED = MappingProxyType({
    "a descendant that never split": (
        _support.record(ancestry=_UNSPLIT_DESCENDANT),
        replace(_support.ROOT_LINEAGE, root_issue=_support.ANCESTOR, lineage_depth=3, cycle_id=_support.ANCESTOR_CYCLE),
    ),
    **{
        f"a root whose ref is {ref_state.value}": (
            _support.record(_support.own_split(ref_state)), _support.ROOT_LINEAGE,
        )
        for ref_state in _RELEASED
    },
    # Correlated by the cycle the retirement says it dropped, and no ref can be
    # minted from an identity that is gone.
    "a root whose released split was retired": (
        _support.retired(_RECONCILED), replace(_support.ROOT_LINEAGE, generation=0),
    ),
})


@dataclass(frozen=True)
class _Refusal:
    """A parent whose replacements cannot be seeded, and a fragment of why.

    `proved` says the lineage itself is proved and the snapshot is what did
    not hold, which the refusal has to say: it asks for a different repair.
    """

    state: PinnedState
    said: str
    proved: bool = False
    body: str = _support.EDITED_BODY


_REFUSALS = MappingProxyType({
    "a parent already at the bound": _Refusal(
        _support.record(ancestry=_support.cut_from_ancestor(
            depth=_late_models.MAX_LINEAGE_DEPTH, parent=_support.GRANDPARENT,
        )),
        f"no split may create a child past depth {_late_models.MAX_LINEAGE_DEPTH}",
    ),
    "an ancestry that names no parent": _Refusal(
        _support.record(_support.own_split(), **{STRAY_ANCESTRY_KEY: 1}), _LINEAGE_REFUSED,
    ),
    "a comment that would not parse": _Refusal(PinnedState(parsed=False), _LINEAGE_REFUSED),
    "a child receipt with no ancestry": _Refusal(
        _support.record(),
        _LINEAGE_REFUSED,
        body="\n\n".join((
            _support.EDITED_BODY,
            _ancestry.child_marker(issue=_support.ANCESTOR, cycle=_support.ANCESTOR_CYCLE, generation=1, index=0),
        )),
    ),
    "a retired split naming no cycle": _Refusal(_support.retired(_RECONCILED, cycle=None), "keeps no cycle"),
    # Held and protectable, and its instructions would name the candidate's
    # change as a range from a base nobody recorded.
    "a held snapshot recorded with no base": _Refusal(
        _support.record(_support.own_split(base_sha="")), "recorded with no base", proved=True,
    ),
    # Damaged ledgers: none of them says whether the ref is still there for a
    # new consumer, which is not the same as saying it is gone.
    "a consumer ledger no child can be added to": _Refusal(
        _support.record(_support.own_split(), **{KEY_CONSUMERS: [_support.ORIGINAL, "#57"]}),
        _UNPROTECTABLE,
        proved=True,
    ),
    "a resource ledger with an entry it cannot read": _Refusal(
        _support.record(_support.own_split(), **{KEY_RESOURCES: [
            {"kind": "snapshot_ref", "target": _support.SNAPSHOT_REF, "state": "retained"},
            {"kind": "mystery", "target": "x", "state": "retained"},
        ]}),
        "cannot be told",
        proved=True,
    ),
    "a ref held and released at once": _Refusal(
        _support.record(_support.own_split(_support.HELD, _RECONCILED)), _UNSETTLED, proved=True,
    ),
    "a retired split still holding its ref": _Refusal(_support.retired(_support.HELD), _UNPROTECTABLE, proved=True),
})


class InheritedLineageTest(unittest.TestCase):
    """Replacements are born one level below their parent, never at depth 0."""

    def test_a_root_points_at_its_held_snapshot(self) -> None:
        # The parent carries the whole bypass an operator granted a commit of
        # its own, and the decision reads none of it.
        bypass = _authorized_exemption(_support.CANDIDATE_SHA, _support.BASE_SHA)
        for shape, state in (
            ("a root that split", _support.record(_support.own_split())),
            ("a root carrying its own bypass", _support.record(_support.own_split(), **bypass)),
        ):
            with self.subTest(shape=shape):
                lineage = _support.decide(state)

                self.assertIsNone(lineage.refusal)
                self.assertEqual(lineage.ancestry, _support.ROOT_LINEAGE)
                self.assertEqual(lineage.pointed(), _support.ROOT_REPLACEMENT)
                self.assertEqual(lineage.told, TOLD)

    def test_a_split_descendant_points_at_its_own(self) -> None:
        split = _support.own_split(root_issue=_support.ANCESTOR, lineage_depth=1)
        born = replace(_support.ROOT_REPLACEMENT, root_issue=_support.ANCESTOR, lineage_depth=2)

        lineage = _support.decide(_support.record(split, _support.cut_from_ancestor()))

        self.assertEqual(lineage.pointed(), born)
        self.assertEqual(lineage.told, TOLD)

    def test_an_unheld_snapshot_is_never_pointed_at(self) -> None:
        for shape, (state, born) in _UNPOINTED.items():
            with self.subTest(shape=shape):
                lineage = _support.decide(state)

                self.assertIsNone(lineage.refusal)
                self.assertEqual(lineage.ancestry, born)
                self.assertIsNone(lineage.snapshot)
                self.assertIsNone(lineage.pointed())
                self.assertEqual((lineage.instructions, lineage.told), ("", frozenset()))

    def test_an_issue_no_split_charged_seeds_nothing(self) -> None:
        lineage = _support.decide(_support.record(**LEGACY_STATE))

        self.assertEqual(lineage, _replacement_lineage.ReplacementLineage())


class RefusedLineageTest(unittest.TestCase):
    """A lineage or snapshot nobody can prove is a refusal, never an ordinary or unpointed seed."""

    def test_each_refusal_seeds_nothing(self) -> None:
        for shape, case in _REFUSALS.items():
            with self.subTest(shape=shape):
                lineage = _support.decide(case.state, case.body)

                refusal = lineage.refusal or ""
                self.assertIn(case.said, refusal)
                # A refused snapshot asks a human to repair that record, not
                # the lineage beside it.
                self.assertEqual(_SNAPSHOT_REFUSED in refusal, case.proved)
                self.assertEqual((lineage.ancestry, lineage.snapshot), (None, None))
                self.assertEqual(lineage.told, frozenset())


class ConsumerWriteTest(unittest.TestCase):
    """A child is pointed at the snapshot only once the parent's consumer ledger records it."""

    def test_a_protected_child_carries_the_pointer(self) -> None:
        state = _support.record(_support.own_split())
        lineage = _support.decide(state)
        untouched = _without_consumers(state)

        lineage.protect(state, PROTECTED_CHILD)

        self.assertEqual(state.get(KEY_CONSUMERS), [_support.ORIGINAL, PROTECTED_CHILD])
        self.assertEqual(_without_consumers(state), untouched)
        self.assertEqual(lineage.child_ancestry(state, PROTECTED_CHILD), _support.ROOT_REPLACEMENT)
        # One the ledger does not name carries the lineage alone.
        self.assertEqual(lineage.child_ancestry(state, UNPROTECTED_CHILD), _support.ROOT_LINEAGE)

    def test_nothing_is_written_without_a_pointer(self) -> None:
        for shape, state in (
            ("a released root", _support.record(_support.own_split(_RECONCILED))),
            ("a descendant that never split", _support.record(ancestry=_UNSPLIT_DESCENDANT)),
            ("an ordinary issue", _support.record()),
        ):
            with self.subTest(shape=shape):
                lineage = _support.decide(state)
                before = dict(state.data)

                lineage.protect(state, PROTECTED_CHILD)

                self.assertEqual(state.data, before)
                self.assertEqual(lineage.child_ancestry(state, PROTECTED_CHILD), lineage.ancestry)


def _without_consumers(state: PinnedState) -> dict:
    """Everything the parent's pinned comment carries but its consumer ledger."""
    return {key: written for key, written in state.data.items() if key != KEY_CONSUMERS}


# What a protected root replacement's instructions say: the pointer, the range
# its change is read as, the lineage, and the fetch quoted as every late child
# has been told it.
_INSTRUCTED = (
    f"## Reusing the work already committed for #{_support.PARENT}",
    f"exact snapshot commit: `{_support.CANDIDATE_SHA}`",
    f"the base it was cut against: `{_support.BASE_SHA}`",
    f"lineage: root #{_support.PARENT}, parent #{_support.PARENT}, depth 1 of at most {_late_models.MAX_LINEAGE_DEPTH}",
    f"adjudication: cycle {_support.CYCLE}, generation {_support.GENERATION}",
    f"git fetch {_TEST_SPEC.remote_name} '+{_support.SNAPSHOT_REF}:{_support.OWN_MIRROR}' ",
    f"git diff {_support.BASE_SHA}...{_support.CANDIDATE_SHA}",
)

# Every way a slice may spell its own snapshot: either name, however the text
# around it wraps it.
_OWN_SPELLINGS = (
    _support.SNAPSHOT_REF,
    _support.OWN_MIRROR,
    f"`{_support.SNAPSHOT_REF}`",
    f"[{_support.SNAPSHOT_REF}]",
    f"(`{_support.OWN_MIRROR}`).",
    f"<{_support.SNAPSHOT_REF}>",
    f"+{_support.SNAPSHOT_REF}:{_support.OWN_MIRROR}",
    f"'+{_support.SNAPSHOT_REF}:{_support.OWN_MIRROR}'",
    f"`\"+{_support.SNAPSHOT_REF}:{_support.OWN_MIRROR}\"`.",
    f"+{_support.SNAPSHOT_REF}:'{_support.OWN_MIRROR}'",
    f"{_support.SNAPSHOT_REF}/.",
)

_RUN_ON = f"{_support.SNAPSHOT_REF}@foreign"

_SPACED = f"{_support.SNAPSHOT_REF}\u00a0foreign"

_NESTED = f"refs/heads/{_support.SNAPSHOT_REF}"

# Spellings naming a ref nothing keeps for the child, each with the whole ref
# name it reads as.
_OTHER_SPELLINGS = MappingProxyType({
    "a foreign ref": (FOREIGN_REF, FOREIGN_REF),
    "the ancestor's ref": (f"`{ANCESTOR_REF}`", ANCESTOR_REF),
    "another repository's mirror": (_support.FOREIGN_MIRROR, _support.FOREIGN_MIRROR),
    # Whole names that contain its own ref, which git would fetch as the
    # different refs they are -- a non-breaking space is no break to git.
    "a ref running on past it": (_RUN_ON, _RUN_ON),
    "a ref running on inside backticks": (f"`{_support.SNAPSHOT_REF}!`", f"{_support.SNAPSHOT_REF}!"),
    "a ref running on through a non-breaking space": (_SPACED, _SPACED),
    "a ref nested under another": (_NESTED, _NESTED),
    # A pattern git fetches every generation it matches through.
    "a pattern spelling its own ref": (f"`{_support.SNAPSHOT_REF}*`", f"{_support.SNAPSHOT_REF}*"),
    # Wrapping that is not taken off: a second refspec `+`, and a quote or a
    # bracket never closed on the other side.
    "a refspec with a second `+`": (f"++{_support.SNAPSHOT_REF}", f"+{_support.SNAPSHOT_REF}"),
    "a quote never closed": (f"'{_support.SNAPSHOT_REF}", f"'{_support.SNAPSHOT_REF}"),
    "a bracket only closed": (f"{_support.SNAPSHOT_REF}]", f"{_support.SNAPSHOT_REF}]"),
})


# Refspecs, each with every name it reads as: wrapping is taken off a whole
# refspec only where it closes after the destination, and either side may be
# the one in the namespace.
_REFSPECS = MappingProxyType({
    "a quote never closed": (
        f"'+{_support.SNAPSHOT_REF}:{_support.OWN_MIRROR}",
        {f"'+{_support.SNAPSHOT_REF}", _support.OWN_MIRROR},
    ),
    "a second `+` inside the quotes": (
        f"'++{_support.SNAPSHOT_REF}:{_support.OWN_MIRROR}'",
        {f"+{_support.SNAPSHOT_REF}", _support.OWN_MIRROR},
    ),
    "a quote running on past its close": (
        f"'+{_support.SNAPSHOT_REF}:{_support.OWN_MIRROR}'!",
        {f"'+{_support.SNAPSHOT_REF}", f"{_support.OWN_MIRROR}'!"},
    ),
    "another repository's mirror as the destination": (
        f"'+{_support.SNAPSHOT_REF}:{_support.FOREIGN_MIRROR}'",
        {_support.SNAPSHOT_REF, _support.FOREIGN_MIRROR},
    ),
    "a branch fetched into the mirror": (f"'+refs/heads/main:{_support.OWN_MIRROR}'", {_support.OWN_MIRROR}),
    "the snapshot fetched into a branch": (f"'+{_support.SNAPSHOT_REF}:refs/heads/main'", {_support.SNAPSHOT_REF}),
})

_PATTERN = (f"{_support.SNAPSHOT_REF}*", f"{_support.OWN_MIRROR}*")

_PLUS_MIRROR = f"+{_support.OWN_MIRROR}"

# Refspecs spelled out of both told names that fetch refs past them: a pattern
# git expands to every generation it matches, and a destination whose `+` is
# the first character of a different ref, since only a whole refspec is forced.
_UNTOLD_REFSPECS = MappingProxyType({
    "a pattern": (f"+{_PATTERN[0]}:{_PATTERN[1]}", set(_PATTERN)),
    "a pattern quoted whole": (f"'+{_PATTERN[0]}:{_PATTERN[1]}'", set(_PATTERN)),
    "a destination opening on a `+`": (
        f"{_support.SNAPSHOT_REF}:{_PLUS_MIRROR}", {_support.SNAPSHOT_REF, _PLUS_MIRROR},
    ),
    "a forced refspec whose destination opens on a `+`": (
        f"+{_support.SNAPSHOT_REF}:{_PLUS_MIRROR}", {_support.SNAPSHOT_REF, _PLUS_MIRROR},
    ),
    "a destination quoted with its `+`": (
        f"{_support.SNAPSHOT_REF}:'{_PLUS_MIRROR}'", {_support.SNAPSHOT_REF, _PLUS_MIRROR},
    ),
    "a refspec quoted whole whose destination opens on a `+`": (
        f"'+{_support.SNAPSHOT_REF}:{_PLUS_MIRROR}'", {_support.SNAPSHOT_REF, _PLUS_MIRROR},
    ),
})


class ReuseInstructionsTest(unittest.TestCase):
    """What a protected replacement is told, and the names any issue text gives a snapshot."""

    def test_the_instructions_name_the_pointer(self) -> None:
        instructions = _support.decide(_support.record(_support.own_split())).instructions

        for said in _INSTRUCTED:
            with self.subTest(said=said):
                self.assertIn(said, instructions)

    def test_its_own_names_are_told(self) -> None:
        for spelled in _OWN_SPELLINGS:
            with self.subTest(spelled=spelled):
                named = _late_child_content._named_snapshots(f"reuse what {spelled} holds")

                self.assertTrue(named)
                self.assertLessEqual(named, TOLD)

    def test_any_other_name_is_its_own_ref(self) -> None:
        for shape, (spelled, read) in _OTHER_SPELLINGS.items():
            with self.subTest(shape=shape):
                named = _late_child_content._named_snapshots(f"reuse what {spelled} holds")

                self.assertEqual(named, {read})
                self.assertFalse(named <= TOLD)

    def test_a_refspec_names_each_side(self) -> None:
        for shape, (spelled, read) in _REFSPECS.items():
            with self.subTest(shape=shape):
                self.assertEqual(_late_child_content._named_snapshots(f"run git fetch origin {spelled} first"), read)

    def test_a_refspec_fetching_past_them_is_untold(self) -> None:
        told = _support.decide(_support.record(_support.own_split())).told

        for shape, (spelled, read) in _UNTOLD_REFSPECS.items():
            with self.subTest(shape=shape):
                named = _late_child_content._named_snapshots(f"run git fetch origin {spelled} first")

                self.assertEqual(named, read)
                self.assertFalse(named <= told)

    def test_a_published_fetch_names_what_is_told(self) -> None:
        # The fetch line as every late child created so far carries it, the
        # refspec quoted whole: its names are the two the lineage permits.
        published = (
            f"git fetch {_TEST_SPEC.remote_name} '+{_support.SNAPSHOT_REF}:{_support.OWN_MIRROR}'"
            "       # only if the ref is not here yet"
        )

        lineage = _support.decide(_support.record(_support.own_split()))

        self.assertEqual(_late_child_content._named_snapshots(published), lineage.told)

    def test_a_title_and_body_are_read_together(self) -> None:
        title = f"Reuse {_support.SNAPSHOT_REF}"
        body = f"and also {_support.FOREIGN_MIRROR}."

        named = _late_child_content._named_snapshots(title, None, body)

        self.assertEqual(named, {_support.SNAPSHOT_REF, _support.FOREIGN_MIRROR})
        self.assertEqual(_late_child_content._named_snapshots("refs/heads/main and refs/tags/v1"), frozenset())


if __name__ == "__main__":
    unittest.main()
