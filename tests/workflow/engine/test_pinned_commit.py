# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The guarded commit of an issue's pinned state.

What a commit lands, over a record other roads keep writing: its own staged
fields and the transformations a domain supplies, with every other field taken
from a fresh reading. What it refuses, and that a refusal leaves the record, the
pinned writes sent, and the caller's state exactly as they were. That the whole
candidate is measured as it would be written before anything goes out, and that
an edit nobody confirmed is reported as neither answer. And that the fresh
reading taken alone is refused as a commit's would be, and names the
prerequisites that moved rather than refusing over them.
"""
from __future__ import annotations

import json
import unittest
from dataclasses import replace
from types import MappingProxyType
from typing import Any

from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState, pinned_state_body
from orchestrator.workflow.engine import pinned_commit as _commit, pinned_commit_models as _models
from tests.workflow.engine import pinned_commit_test_support as support

_ABSENT = _models.ABSENT
_REFUSAL = _models.CommitRefusal
_STATUS = _models.CommitStatus
_COUNTER = "rounds_seen"
_ANOTHER_TOTAL = 2000
_OWN_TOTAL = 1500
_IDS = "ids"

# A domain check's cap on the total, a total past it, and the check's answer.
_CAP = 3000
_PAST_THE_CAP = 5000
_OVER_THE_CAP = "the total is past the cap"

# The settled record every case reads.
_SETTLED_READ = support.RECORD[support.SETTLED]

# Another road moving nothing but a total.
_MOVED_TOTAL = MappingProxyType({support.TOTAL: _ANOTHER_TOTAL})

# Another road's write while the caller decided: a total moved, a marker
# retired, a field no binary here knows recorded, and a watermark the caller
# owns but stages nothing for moved on.
_ANOTHER_ROAD = MappingProxyType({
    support.TOTAL: _ANOTHER_TOTAL,
    support.RETIRED: _ABSENT,
    support.UNKNOWN: {"n": [1, None, True]},
    support.WATERMARK: 60,
})

# The fields each transformation below decides over the fresh value.
_DERIVED = (support.TOTAL, support.LEDGER, support.RETIRED, _COUNTER)


def _added(fresh: Any, read: Any, staged: Any) -> Any:
    """A total both roads add to: the fresh value, plus what this caller added."""
    return fresh + staged - read


def _merged(fresh: Any, read: Any, staged: Any) -> Any:
    """A ledger every road appends to; `staged` is extended in place, which only its copy sees."""
    staged.extend(entry for entry in fresh if entry not in staged)
    return sorted(staged)


_TRANSFORMS = MappingProxyType({
    support.TOTAL: _added,
    support.LEDGER: _merged,
    support.RETIRED: lambda fresh, read, staged: _ABSENT,
    _COUNTER: lambda fresh, read, staged: 1 if fresh is _ABSENT else fresh + 1,
})

# What those transformations leave the record carrying.
_TRANSFORMED = MappingProxyType({
    support.TOTAL: _ANOTHER_TOTAL + _OWN_TOTAL - support.RECORD[support.TOTAL],
    support.LEDGER: [11, 12, 13, 14],
    support.RETIRED: _ABSENT,
    _COUNTER: 1,
})

# A prerequisite as the caller read it and as another road left it: every pair
# Python calls equal and a reader does not, at any depth.
_PREREQUISITE_MOVES = MappingProxyType({
    "null written where it was absent": (_ABSENT, None),
    "dropped where it was null": (None, _ABSENT),
    "true where it was 1": (1, True),
    "1.0 where it was 1": (1, 1.0),
    "nested true where it was 1": ({_IDS: [7, 1]}, {_IDS: [7, True]}),
    "nested null where it was absent": ({"at": {}}, {"at": {"comment": None}}),
})

# What spoils the comment between the caller's reading and its commit.
_SPOILED = MappingProxyType({
    "unreadable": (lambda world: world.github.pinned_failures.unreadable.add(support.ISSUE), _REFUSAL.UNREADABLE),
    "unparsed": (support.unparse, _REFUSAL.MALFORMED),
    "replaced": (support.repin, _REFUSAL.REPLACED),
    "deleted": (support.unpin, _REFUSAL.REPLACED),
})

# What lands between the commit's own fresh reading and its edit.
_UNDER_THE_EDIT = MappingProxyType({
    "moved": (lambda world: world.another_road(**_MOVED_TOTAL), _REFUSAL.MOVED),
    "replaced": (support.repin, _REFUSAL.REPLACED),
    "unreadable": (lambda world: world.github.pinned_failures.unreadable.add(support.ISSUE), _REFUSAL.UNREADABLE),
})

# A filler of one unit -- empty for plain characters -- bringing the candidate to
# the limit plus an excess; what the commit comes to, what it measured, and the
# settled record the comment is left carrying.
_MEASURED = MappingProxyType({
    "at the limit": (("", 0), (_STATUS.COMMITTED, None, dict(support.SETTLED_ANEW))),
    "one past the limit": (("", 1), (_STATUS.REFUSED, MAX_PINNED_BODY + 1, _SETTLED_READ)),
    "terminators, written unescaped": (("-->", 0), (_STATUS.COMMITTED, None, dict(support.SETTLED_ANEW))),
})


def _filler(unit: str, excess: int) -> str:
    """A value bringing the settled candidate's rendered body to `MAX_PINNED_BODY + excess`, of `unit` where it fits."""
    unfilled = pinned_state_body(support.recorded(settled=True, **{support.UNKNOWN: ""}))
    room = MAX_PINNED_BODY + excess - len(unfilled)
    units = room // len(unit) if unit else 0
    return unit * units + "x" * (room - len(unit) * units)


class CommitLandingTest(unittest.TestCase):
    """What a commit lands, and what it leaves the record carrying beside it."""

    def test_own_fields_land_over_every_other_write(self) -> None:
        # Each of another road's moves is the fresh reading's to keep, and
        # the caller's settled record is the one field it replaces.
        world = support.seeded()
        world.settle()
        world.another_road(**_ANOTHER_ROAD)

        outcome = world.commit()

        self.assertIs(outcome.status, _STATUS.COMMITTED)
        self.assertEqual(world.record(), support.recorded(settled=True, **_ANOTHER_ROAD))
        self.assertEqual(world.github.write_state_calls, 2, "one write for the other road, one for the commit")
        self.assertEqual(outcome.reading.data, world.record(), "the committed reading is what reads back")
        self.assertEqual(outcome.reading.comment_id, world.state.comment_id)
        self.assertEqual(world.state.data, support.recorded(settled=True), "the caller's state is its own")

    def test_agreeing_owned_edits_send_nothing(self) -> None:
        # Another road settled exactly what this caller staged: the record
        # already reads as the candidate, so there is nothing to send.
        world = support.seeded()
        world.settle()
        world.another_road(**support.recorded(settled=True))
        before = world.snapshot()

        outcome = world.commit()

        self.assertIs(outcome.status, _STATUS.COMMITTED)
        self.assertEqual(world.snapshot(), before)
        self.assertEqual(outcome.reading.data, world.record())

    def test_transformations_decide_over_fresh_values(self) -> None:
        # A total and a ledger both roads moved keep both moves; a field the
        # transformation drops is dropped; a field the record never carried is
        # handed over as absent. The transformations get copies, so the one
        # that extends what it was handed leaves the caller's state alone.
        world = support.seeded(owned=_DERIVED)
        world.state.set(support.TOTAL, _OWN_TOTAL)
        world.state.set(support.LEDGER, [11, 12, 13])
        world.another_road(**{
            support.TOTAL: _ANOTHER_TOTAL,
            support.LEDGER: [11, 12, 14],
        })

        outcome = world.commit(_TRANSFORMS)

        self.assertIs(outcome.status, _STATUS.COMMITTED)
        self.assertEqual(world.record(), support.recorded(**_TRANSFORMED))
        self.assertEqual(world.state.get(support.LEDGER), [11, 12, 13])

    def test_prepare_measures_and_commit_reads_again(self) -> None:
        # The measured candidate is handed back and nothing is written for
        # it. A request made behind it -- another road's write landing -- is
        # what the commit is laid over, rather than the candidate prepared.
        world = support.seeded()
        world.settle()

        prepared = _commit.prepare(world.github, world.issue, world.guard, world.state.data)
        sent = world.github.write_state_calls
        world.another_road(**_MOVED_TOTAL)
        committed = world.commit()

        self.assertIs(prepared.status, _STATUS.PREPARED)
        self.assertEqual(prepared.reading.data, support.recorded(settled=True))
        self.assertEqual(sent, 0)
        self.assertIs(committed.status, _STATUS.COMMITTED)
        self.assertEqual(world.record(), support.recorded(settled=True, **_MOVED_TOTAL))

    def test_a_transformation_may_refuse_to_join(self) -> None:
        # A transformation that cannot keep both moves of its field answers
        # CONFLICT, and the commit refuses as it refuses a field that has none:
        # the field named, nothing written, and nothing the caller holds moved.
        world = support.seeded(owned=(support.SETTLED, support.TOTAL))
        world.settle()
        world.state.set(support.TOTAL, _OWN_TOTAL)
        world.another_road(**_MOVED_TOTAL)
        found = world.snapshot()

        outcome = world.commit({support.TOTAL: lambda *_moves: _models.CONFLICT})

        self.assertEqual(
            (outcome.status, outcome.refusal, outcome.fields, world.snapshot()),
            (_STATUS.REFUSED, _REFUSAL.OWNED_CONFLICT, (support.TOTAL,), found),
        )

    def test_reordered_keys_spell_the_same(self) -> None:
        # A prerequisite rewritten with its keys in another order is the same
        # record, spelled the same.
        record = support.recorded(**{support.PR: {"a": 1, "b": 2}})
        world = support.seeded(record)
        world.settle()
        world.another_road(**{support.PR: {"b": 2, "a": 1}})

        self.assertIs(world.commit().status, _STATUS.COMMITTED)


class CommitRefusalTest(unittest.TestCase):
    """What a commit refuses, with the record, its writes, and the caller's state left exactly as they were."""

    def assert_refused(
        self, world: support.CommitWorld, expected: _models.CommitRefusal, **commit: Any,
    ) -> _models.CommitOutcome:
        """Commit and hold it to `expected`, with nothing written and nothing the caller holds moved."""
        before = world.snapshot()
        outcome = world.commit(**commit)
        self.assertIs(outcome.status, _STATUS.REFUSED)
        self.assertIs(outcome.refusal, expected)
        self.assertIsNone(outcome.reading)
        self.assertEqual(world.snapshot(), before)
        return outcome

    def test_prerequisites_hold_their_exact_spelling(self) -> None:
        for case, (read, moved) in _PREREQUISITE_MOVES.items():
            with self.subTest(case=case):
                world = support.seeded(support.recorded(**{support.PR: read}))
                world.settle()
                world.another_road(**{support.PR: moved})

                outcome = self.assert_refused(world, _REFUSAL.PREREQUISITE_CHANGED)

                self.assertEqual(outcome.fields, (support.PR,))

    def test_an_owned_field_moved_elsewhere_conflicts(self) -> None:
        # Rewritten or dropped by another road while this caller staged its
        # own value: taking either back would put the older reading's choice
        # over the newer one.
        for case, moved in (("rewritten", {"revision": 5}), ("dropped", _ABSENT)):
            with self.subTest(case=case):
                world = support.seeded()
                world.settle()
                world.another_road(**{support.SETTLED: moved})

                outcome = self.assert_refused(world, _REFUSAL.OWNED_CONFLICT)

                self.assertEqual(outcome.fields, (support.SETTLED,))

    def test_undeclared_writes_are_refused_unread(self) -> None:
        # Staged on a field the caller never declared, or transformed: either
        # is refused before the comment is read, which a thread nobody can
        # read shows -- a read would have answered UNREADABLE.
        for case, derived in (("staged", {}), ("transformed", {support.TOTAL: _added})):
            with self.subTest(case=case):
                world = support.seeded()
                if not derived:
                    world.state.set(support.TOTAL, _OWN_TOTAL)
                world.github.pinned_failures.unreadable.add(support.ISSUE)

                outcome = self.assert_refused(world, _REFUSAL.UNDECLARED_WRITE, derived=derived)

                self.assertEqual(outcome.fields, (support.TOTAL,))

    def test_a_comment_spoiled_since_its_reading(self) -> None:
        for case, (spoil, refusal) in _SPOILED.items():
            with self.subTest(case=case):
                world = support.seeded()
                world.settle()
                spoil(world)

                self.assert_refused(world, refusal)

    def test_a_reading_with_nothing_to_commit_over(self) -> None:
        # A reading that would not parse is a record nobody read, and an issue
        # that pinned nothing has no comment the strict edit may rewrite --
        # it never creates one.
        unparsed = support.seeded()
        support.unparse(unparsed)
        unparsed = support.CommitWorld.of(unparsed.github, unparsed.issue)
        unpinned = support.seeded({})
        for world, refusal in ((unparsed, _REFUSAL.MALFORMED), (unpinned, _REFUSAL.REPLACED)):
            with self.subTest(refusal=refusal):
                world.settle()

                self.assert_refused(world, refusal)
        self.assertEqual(unpinned.record(), {})

    def test_a_comment_moving_under_the_edit(self) -> None:
        # Behind the commit's own fresh reading and ahead of its edit: the
        # strict edit's walk is the last reading, and it sends nothing over a
        # record that is no longer the one the candidate was derived over.
        for case, (move, refusal) in _UNDER_THE_EDIT.items():
            with self.subTest(case=case):
                world = support.seeded()
                world.settle()
                with world.interfering(move):
                    outcome = world.commit()

                self.assertEqual((outcome.status, outcome.refusal), (_STATUS.REFUSED, refusal))
                self.assertEqual(world.record()[support.SETTLED], _SETTLED_READ)
                self.assertEqual(world.state.data, support.recorded(settled=True))


class CommitBoundaryTest(unittest.TestCase):
    """What is measured before anything goes out, and what an unanswered edit is reported as."""

    def test_the_whole_rendered_candidate_is_measured(self) -> None:
        # Another road's field fills the comment, so the record it wrote still
        # fits and the candidate -- that field, and this caller's longer
        # settled record -- is measured as rendered: at the limit it lands,
        # one past it is refused with the record intact. A payload of
        # terminators is measured as written, which past the limit escaped is
        # the unescaped rendering.
        for case, (filler, measured) in _MEASURED.items():
            with self.subTest(case=case):
                world = support.seeded()
                world.settle()
                world.another_road(**{support.UNKNOWN: _filler(*filler)})

                outcome = world.commit()

                self.assertEqual(
                    (outcome.status, outcome.length, world.record()[support.SETTLED]),
                    measured,
                )
                self.assertLessEqual(len(pinned_state_body(world.record())), MAX_PINNED_BODY)

    def test_the_check_judges_the_candidate_sent(self) -> None:
        # The guard's own domain check is asked of the very candidate a commit
        # sends, over the reading it would land on: another road's total past
        # the cap, written after the caller read the record, is refused with
        # the check's answer and nothing sent; one inside the cap lands.
        for total, landed in (
            (_PAST_THE_CAP, (_STATUS.REFUSED, _OVER_THE_CAP, _SETTLED_READ)),
            (_ANOTHER_TOTAL, (_STATUS.COMMITTED, None, dict(support.SETTLED_ANEW))),
        ):
            with self.subTest(total=total):
                world = support.seeded()
                world.guard = replace(world.guard, admits=self._caps_the_total)
                world.settle()
                world.another_road(**{support.TOTAL: total})

                outcome = world.commit()

                self.assertEqual(
                    (outcome.status, outcome.inadmissible, world.record()[support.SETTLED]),
                    landed,
                )

    def test_unanswered_edits_are_unconfirmed(self) -> None:
        # A lost response and a refused edit are one answer to the caller,
        # who cannot tell which it got; only the first changed the record,
        # and the domain's own receipts are what settle it later.
        for how, lands in (("lost", True), ("refused", False)):
            with self.subTest(how=how):
                world = support.seeded()
                world.settle()
                getattr(world.github.pinned_failures, how).add(support.ISSUE)

                outcome = world.commit()

                self.assertIs(outcome.status, _STATUS.UNCONFIRMED)
                self.assertEqual(outcome.reading.data, support.recorded(settled=True))
                self.assertEqual(world.record(), support.recorded(settled=lands))
                self.assertEqual(world.github.write_state_calls, 1)


    def _caps_the_total(self, candidate: PinnedState) -> str | None:
        """A domain check refusing a candidate whose total is past the cap."""
        return _OVER_THE_CAP if candidate.get(support.TOTAL) > _CAP else None


class CommitCaptureTest(unittest.TestCase):
    """What a capture holds a commit, or a reading taken alone, to is fixed when it is taken."""

    def test_a_capture_is_not_moved_by_its_caller(self) -> None:
        # The caller's state is mutable and mutated in place; what the
        # commit was captured over is not.
        state = PinnedState(comment_id=1, data={support.PR: {_IDS: [1]}})
        guard = _models.PinnedCommit.capture(state, prerequisites=(support.PR,))

        state.get(support.PR)[_IDS].append(2)

        self.assertEqual(guard.read[support.PR], '{"ids": [1]}')
        with self.assertRaises(TypeError):
            guard.read[support.PR] = "{}"

    def test_a_reading_taken_in_moves_the_sync(self) -> None:
        # A state remembers the reading it last synced with. A road laying
        # some fields of a fresh reading over it advances that memory for those
        # fields alone; one replacing the state with what a commit landed
        # advances it to that reading whole. A state that read nothing is left
        # without one unless it now holds a whole reading.
        world = support.seeded()
        fresh = support.recorded(**{support.TOTAL: _ANOTHER_TOTAL, support.WATERMARK: 60})

        _commit.takes_in(world.state, fresh, (support.TOTAL,))
        partly = json.loads(world.state.synced)
        _commit.takes_in(world.state, fresh)
        unread = PinnedState(data=dict(fresh))
        _commit.takes_in(unread, fresh, (support.TOTAL,))

        self.assertEqual(
            (partly, json.loads(world.state.synced), unread.synced),
            (support.recorded(**{support.TOTAL: _ANOTHER_TOTAL}), fresh, None),
        )

    def test_a_reread_refuses_a_spoiled_comment(self) -> None:
        # The comment read afresh alone, with nothing staged: refused as a
        # commit refuses that reading, with nothing written and nothing the
        # caller holds moved.
        for case, spoiled in _SPOILED.items():
            with self.subTest(case=case):
                world = support.seeded()
                spoiled[0](world)
                before = world.snapshot()

                outcome = _commit.reread(world.github, world.issue, world.guard)

                self.assertEqual(
                    (outcome.status, outcome.refusal, world.snapshot()),
                    (_STATUS.REFUSED, spoiled[1], before),
                )

    def test_a_reread_names_what_moved(self) -> None:
        # A prerequisite spelled otherwise on the comment read afresh -- null
        # for absent, true for 1, at any depth -- is named by the capture
        # rather than refused over, and the reading handed back, since the
        # caller may still lay a write of its own over it; nothing is written.
        for case, spellings in {**_PREREQUISITE_MOVES, "nothing moved": (1, 1)}.items():
            with self.subTest(case=case):
                world = self.moved_under(*spellings)
                before = world.snapshot()

                fresh = _commit.reread(world.github, world.issue, world.guard)

                self.assertEqual(
                    (fresh.data, world.guard.moved(fresh.data), world.snapshot()),
                    (world.record(), () if case == "nothing moved" else (support.PR,), before),
                )

    def moved_under(self, read: Any, moved: Any) -> support.CommitWorld:
        """A caller's reading of `pr_number` spelled `read`, and the comment since rewritten to spell it `moved`."""
        world = support.seeded(support.recorded(**{support.PR: read}))
        world.another_road(**{support.PR: moved})
        return world
