# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The late reply's fenced block, and what the initial parser still means."""
from __future__ import annotations

import unittest

from orchestrator.workflow.late_split.events import LateVerdictCategory
from orchestrator.workflow.late_split.models import LateVerdict
from orchestrator.workflow.stages.decomposition import (
    late_reply as _late_reply,
    manifest as _manifest,
)
from orchestrator.workflow.stages.decomposition.late_budget import ESTIMATE
from orchestrator.workflow.stages.decomposition.late_reply import _SPLIT_BLOCKER
from tests.workflow.fixtures import _manifest as _initial_block
from tests.workflow.stages.decomposition import late_test_support as _support

SINGLE_PAYLOAD = '{"decision": "single", "rationale": "fits"}'

# The same outcome as a LATE reply carries it: the explanation the late
# contract requires and the initial one has no field for.
LATE_SINGLE_PAYLOAD = (
    '{"decision": "single", "rationale": "fits", '
    f'"{_SPLIT_BLOCKER}": "{_support.SPLIT_BLOCKER}"}}'
)


# One reply per way a late block fails to be an answer, each with the fragment
# the park message has to carry.
_REFUSED_REPLIES = (
    ("no block at all", "the late decomposer decided single", "no outcome"),
    ("two blocks", f"{_support.SINGLE_REPLY}\n{_support.SINGLE_REPLY}", "exactly one"),
    ("prose after", f"{_support.SINGLE_REPLY}\nand one more thought", "final block"),
    ("not json", _support.late_block("{decision: single}"), "invalid JSON"),
    ("not an object", _support.late_block('["single"]'), "not a JSON object"),
    ("no decision", _support.late_block("{}"), "decision must be"),
    ("unknown decision", _support.late_block('{"decision": "maybe"}'), "decision must"),
    (
        "split with no children",
        _support.late_block('{"decision": "split", "children": []}'),
        "non-empty children",
    ),
    (
        "split with a cycle",
        _support.late_block(
            '{"decision": "split", "children": ['
            '{"title": "A", "body": "a", "depends_on": [1]},'
            '{"title": "B", "body": "b", "depends_on": [0]}]}'
        ),
        "cycle",
    ),
    (
        "question with nothing asked",
        _support.late_block('{"decision": "question", "category": "unsafe_split"}'),
        "non-empty question",
    ),
    (
        "a single with no explanation",
        _support.late_block(SINGLE_PAYLOAD),
        f"requires a non-empty {_SPLIT_BLOCKER}",
    ),
    (
        "a single explained with whitespace",
        _support.late_block(f'{{"decision": "single", "{_SPLIT_BLOCKER}": "  "}}'),
        f"requires a non-empty {_SPLIT_BLOCKER}",
    ),
    (
        "a single explained with something that is not text",
        _support.late_block(f'{{"decision": "single", "{_SPLIT_BLOCKER}": [1, 2]}}'),
        "no safe split of this work is available",
    ),
    (
        "a child with no budget",
        _support.split_reply_of(None),
        f"child 0 needs an `{ESTIMATE}`",
    ),
    (
        "a budget that is a string",
        _support.split_reply_of("300"),
        f"child 0 needs an `{ESTIMATE}`",
    ),
    ("a budget that is a bool", _support.split_reply_of(True), "child 0 needs"),
    ("a budget of nothing", _support.split_reply_of(_support.FIRST_ESTIMATE, 0), "child 1 needs"),
    (
        "a budget at the ceiling",
        _support.split_reply_of(_support.THRESHOLD),
        f"is not below the {_support.THRESHOLD}-line ceiling",
    ),
)


# What each outcome says stopped a split: the reply, and the pair of what the
# adjudication carries and what a reader of the verdict is told. Only a
# `single` is an answer about a split that did not happen, and one that named
# no obstacle is refused above rather than parsed into a verdict with nothing
# under it.
_SPLIT_BLOCKERS = (
    ("explained", _support.SINGLE_REPLY, (_support.SPLIT_BLOCKER, _support.SPLIT_BLOCKER)),
    ("split", _support.SPLIT_REPLY, ("", "")),
    ("question", _support.QUESTION_REPLY, ("", "")),
)


class LateReplyTest(unittest.TestCase):
    """What each of the three structured outcomes parses to."""

    def test_single_carries_rationale_and_category(self) -> None:
        adjudication, error = _late_reply._parse_late_reply(
            _support.SINGLE_REPLY, _support.THRESHOLD,
        )

        self.assertIsNone(error)
        self.assertEqual(adjudication.verdict, LateVerdict.SINGLE)
        self.assertEqual(
            adjudication.category, LateVerdictCategory.GENERATED_ARTIFACTS,
        )
        self.assertEqual(adjudication.rationale, "one coherent change")
        self.assertEqual(adjudication.children, ())
        self.assertIsNone(adjudication.child_count)

    def test_what_each_verdict_says_stopped_a_split(self) -> None:
        # A `single` carries the reason as a field rather than as prose around
        # the block, which nothing keeps, and it is the only verdict that
        # answers about a split that did not happen: the other two carry
        # nothing under it and tell a reader nothing.
        for name, reply, expected in _SPLIT_BLOCKERS:
            with self.subTest(case=name):
                adjudication, refusal = _late_reply._parse_late_reply(
                    reply, _support.THRESHOLD,
                )

                self.assertIsNone(refusal)
                self.assertEqual(
                    (
                        adjudication.split_blocker,
                        adjudication.split_blocker_explanation,
                    ),
                    expected,
                )

    def test_split_carries_the_children_it_proposed(self) -> None:
        adjudication, error = _late_reply._parse_late_reply(
            _support.SPLIT_REPLY, _support.THRESHOLD,
        )

        self.assertIsNone(error)
        self.assertEqual(adjudication.verdict, LateVerdict.SPLIT)
        self.assertEqual(adjudication.child_count, 2)
        self.assertEqual(
            [child["title"] for child in adjudication.children], ["A", "B"],
        )
        self.assertEqual(adjudication.children[1]["depends_on"], [0])

    def test_question_carries_what_it_asks(self) -> None:
        adjudication, error = _late_reply._parse_late_reply(
            _support.QUESTION_REPLY, _support.THRESHOLD,
        )

        self.assertIsNone(error)
        self.assertEqual(adjudication.verdict, LateVerdict.QUESTION)
        self.assertEqual(
            adjudication.category, LateVerdictCategory.SCOPE_AMBIGUOUS,
        )
        self.assertEqual(
            adjudication.question, "which half of this is in scope?",
        )

    def test_an_unknown_category_records_as_such(self) -> None:
        # The vocabulary is widened in review, never by what an agent wrote,
        # and a question with no category still has to have one.
        cases = (
            ('"category": "the diff smells", ', LateVerdictCategory.UNKNOWN),
            ("", LateVerdictCategory.UNKNOWN),
        )
        for declared, expected in cases:
            with self.subTest(declared=declared):
                adjudication, error = _late_reply._parse_late_reply(
                    _support.late_block(
                        '{"decision": "question", '
                        f'{declared}"question": "which half?"}}'
                    ),
                    _support.THRESHOLD,
                )
                self.assertIsNone(error)
                self.assertEqual(adjudication.category, expected)

    def test_an_absent_category_stays_absent(self) -> None:
        adjudication, error = _late_reply._parse_late_reply(
            _support.late_block(LATE_SINGLE_PAYLOAD), _support.THRESHOLD,
        )

        self.assertIsNone(error)
        self.assertIsNone(adjudication.category)

    def test_every_refusal_names_why(self) -> None:
        for name, reply, fragment in _REFUSED_REPLIES:
            with self.subTest(case=name):
                adjudication, error = _late_reply._parse_late_reply(
                    reply, _support.THRESHOLD,
                )
                self.assertIsNone(adjudication)
                self.assertIn(fragment, error)


class LateBudgetTest(unittest.TestCase):
    """The addition budget every proposed child has to declare."""

    def test_a_split_keeps_the_budgets_declared(self) -> None:
        # What each child said it would add across all of its paths travels
        # with the manifest that proposed it, so what was judged is what the
        # agent wrote rather than a number read back off something else.
        proposed, refusal = _late_reply._parse_late_reply(
            _support.SPLIT_REPLY, _support.THRESHOLD,
        )

        self.assertIsNone(refusal)
        self.assertEqual(
            [child[ESTIMATE] for child in proposed.children],
            [_support.FIRST_ESTIMATE, _support.SECOND_ESTIMATE],
        )

    def test_an_unknown_ceiling_still_requires_one(self) -> None:
        # A generation that cannot say what it was measured against refuses
        # nothing on size -- there is no number to be past -- and still
        # refuses a child that declared no budget at all, since a missing one
        # is a protocol failure whatever the bound is.
        oversized, refusal = _late_reply._parse_late_reply(
            _support.split_reply_of(_support.THRESHOLD * 2), None,
        )

        self.assertIsNone(refusal)
        self.assertEqual(oversized.child_count, 1)

        unsized, error = _late_reply._parse_late_reply(
            _support.split_reply_of(None), None,
        )

        self.assertIsNone(unsized)
        self.assertIn(ESTIMATE, error)


class ModeSeparationTest(unittest.TestCase):
    """Neither parser reads the other's block, and neither changed."""

    def test_an_initial_manifest_is_not_a_late_reply(self) -> None:
        adjudication, error = _late_reply._parse_late_reply(
            _initial_block(SINGLE_PAYLOAD), _support.THRESHOLD,
        )

        self.assertIsNone(adjudication)
        self.assertIn("no outcome", error)

    def test_a_late_reply_is_not_an_initial_manifest(self) -> None:
        # `(None, None)` is the initial contract's "the decomposer asked a
        # question", which a late block must not turn into.
        parsed, error = _manifest._parse_manifest(_support.SINGLE_REPLY)

        self.assertIsNone(parsed)
        self.assertIsNone(error)

    def test_the_initial_envelope_is_unchanged(self) -> None:
        cases = (
            (
                _initial_block(SINGLE_PAYLOAD) * 2,
                "expected exactly one orchestrator-manifest block, found 2",
            ),
            (
                f"{_initial_block(SINGLE_PAYLOAD)}\ntrailing",
                (
                    "orchestrator-manifest must be the final block; "
                    "found content after the closing fence"
                ),
            ),
        )
        for reply, expected in cases:
            with self.subTest(expected=expected):
                parsed, error = _manifest._parse_manifest(reply)
                self.assertIsNone(parsed)
                self.assertEqual(error, expected)


if __name__ == "__main__":
    unittest.main()
