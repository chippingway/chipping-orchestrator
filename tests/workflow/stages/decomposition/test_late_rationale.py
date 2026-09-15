# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The rationale beside a late verdict: which records keep it, and how much of it."""
from __future__ import annotations

import itertools
import unittest
from types import MappingProxyType

from orchestrator.github.pinned_state import (
    PinnedState,
    pinned_state_body,
    pinned_state_from_comment,
)
from orchestrator.workflow.late_split.events import LateVerdictCategory
from orchestrator.workflow.late_split.models import LateVerdict
from orchestrator.workflow.stages.decomposition import (
    late_run_reading as _late_run_reading,
    late_session as _session,
)
from orchestrator.workflow.stages.decomposition.late_budget import ESTIMATE
from orchestrator.workflow.stages.decomposition.late_result_models import (
    MAX_RATIONALE,
    RATIONALE_TRUNCATION_MARKER,
    _LateAdjudication,
)
from tests.support.fakes import FakeComment
from tests.workflow.stages.decomposition import late_test_support as _support

# What ends the HTML comment the pinned state is written in, so a case can say
# where the rendered comment closes.
_COMMENT_CLOSE = "-->"

_STATE_COMMENT_ID = 900

_FILLER = "r"

_BACKSLASH = "\N{REVERSE SOLIDUS}"

# One stretch of a rationale every piece of which a thread would obey or the
# rendered comment pays more than a character for: a fence, an HTML-comment
# opener and the wrapper's own terminator, the two characters JSON escapes, a
# line separator, control characters, and characters past the Basic
# Multilingual Plane, which JSON spells as surrogate pairs.
_ADVERSARIAL_STRETCH = "".join((
    '```\n<!-- "said" ',
    _BACKSLASH,
    " -->  ",
    "\N{GRINNING FACE}" * 8,
    "\x00" * 4,
))

# Long enough to be cut, so what is measured includes the marker.
_ADVERSARIAL_RATIONALE = _ADVERSARIAL_STRETCH * (
    MAX_RATIONALE // len(_ADVERSARIAL_STRETCH) + 1
)


def _cut(rationale: str) -> str:
    """What a rationale past the bound is recorded as: a prefix and the marker."""
    prefix = rationale[:MAX_RATIONALE - len(RATIONALE_TRUNCATION_MARKER)]
    return f"{prefix}{RATIONALE_TRUNCATION_MARKER}"


def _answered_state(**recorded) -> dict:
    """A result recorded against the standard candidate, and these fields."""
    return {
        _support.KEYS.run_cycle_id: _support.CYCLE_ID,
        _support.KEYS.source_sha: _support.CANDIDATE_SHA,
        _support.KEYS.run_generation: _support.GENERATION_NUMBER,
        **recorded,
    }


# What each verdict that keeps a rationale is recorded as, beside the field it
# is acted on through.
_ANSWERED_RECORDS = (
    ("single", {
        _support.KEYS.verdict: str(LateVerdict.SINGLE),
        _support.KEYS.split_blocker: _support.SPLIT_BLOCKER,
    }),
    ("split", {
        _support.KEYS.verdict: str(LateVerdict.SPLIT),
        _support.KEYS.children: [
            {"title": "A", "body": "a", "depends_on": [], ESTIMATE: _support.FIRST_ESTIMATE},
        ],
    }),
)

# A rationale nobody can be shown. A key never written is the record every
# live issue carries from before this key existed; the rest are values a hand
# edit or another binary could leave under it.
_UNUSABLE_RATIONALES = (
    ("never recorded", {}),
    ("empty", {_support.KEYS.rationale: ""}),
    ("blank", {_support.KEYS.rationale: " \n\t "}),
    ("not a string", {_support.KEYS.rationale: ["one", "coherent", "change"]}),
    ("a number", {_support.KEYS.rationale: 7}),
    ("null", {_support.KEYS.rationale: None}),
    ("past the bound", {_support.KEYS.rationale: _FILLER * (MAX_RATIONALE + 1)}),
)

_UNUSABLE_RECORDS = tuple(
    (f"{verdict}: {named}", _answered_state(**answered, **unusable))
    for (verdict, answered), (named, unusable) in itertools.product(
        _ANSWERED_RECORDS, _UNUSABLE_RATIONALES,
    )
)

_AT_THE_BOUND = _FILLER * MAX_RATIONALE

_PAST_THE_BOUND = _FILLER * (MAX_RATIONALE + 1)

_CUT_FILLER = _cut(_PAST_THE_BOUND)

# Past the whole outcome budget is the length that, refused, would park the
# verdict it argued for.
_LONG_RATIONALES = (
    ("at the bound", _AT_THE_BOUND, _AT_THE_BOUND),
    ("one past it", _PAST_THE_BOUND, _CUT_FILLER),
    ("past the whole outcome budget", _FILLER * _session.MAX_RECORDED_BODY, _CUT_FILLER),
)

_LONG_PROSE = "w" * (3 * MAX_RATIONALE)

# Each field a verdict is acted on through, at a length a rationale is cut at,
# and what it has to be recorded as: exactly what the agent wrote.
_WHOLE_BESIDE_A_CUT = (
    (
        _LateAdjudication(
            verdict=LateVerdict.SINGLE,
            rationale=_LONG_PROSE,
            split_blocker=_LONG_PROSE,
        ),
        _support.KEYS.split_blocker,
        _LONG_PROSE,
    ),
    (
        _LateAdjudication(
            verdict=LateVerdict.SPLIT,
            rationale=_LONG_PROSE,
            children=(
                {"title": "A", "body": _LONG_PROSE, ESTIMATE: _support.FIRST_ESTIMATE},
            ),
        ),
        _support.KEYS.children,
        [{"title": "A", "body": _LONG_PROSE, "depends_on": [], ESTIMATE: _support.FIRST_ESTIMATE}],
    ),
)

_ADVERSARIAL_SINGLE = _LateAdjudication(
    verdict=LateVerdict.SINGLE,
    rationale=_ADVERSARIAL_RATIONALE,
    split_blocker=_support.SPLIT_BLOCKER,
)

_ADVERSARIAL_RECORD = MappingProxyType({
    _support.KEYS.verdict: str(LateVerdict.SINGLE),
    _support.KEYS.split_blocker: _support.SPLIT_BLOCKER,
    _support.KEYS.rationale: _cut(_ADVERSARIAL_RATIONALE),
})

# How much a held pull-request body has to take for the comment holding it
# and that record to land exactly on the outcome budget.
_CEILING_PADDING = _session.MAX_RECORDED_BODY - len(
    pinned_state_body({_support.KEYS.plan_pr_body: "", **_ADVERSARIAL_RECORD}),
)


class RecordedRationaleTest(unittest.TestCase):
    """Which records keep a rationale, and what a reader makes of one."""

    def test_a_question_keeps_no_rationale(self) -> None:
        # A question asks rather than argues, and a split refused at the
        # lineage bound is recorded as the question it became -- so nothing is
        # written beside one, and what a hand edit put there is not read back,
        # while the question itself still answers.
        state = PinnedState()
        _session._record_late_result(state, _LateAdjudication(
            verdict=LateVerdict.QUESTION,
            category=LateVerdictCategory.SCOPE_AMBIGUOUS,
            question=_support.QUESTION_ASKED,
            rationale=_support.SPLIT_RATIONALE,
        ))
        edited = _late_run_reading._read_late_run(PinnedState(data=_answered_state(
            **state.data, **{_support.KEYS.rationale: _support.SPLIT_RATIONALE},
        )))

        self.assertNotIn(_support.KEYS.rationale, state.data)
        self.assertTrue(edited.answers(_support.late_generation()))
        self.assertEqual(edited.rationale, "")

    def test_an_unusable_rationale_reads_absent(self) -> None:
        # A rationale decides nothing, so a record carrying none a reader can
        # use is still this candidate's answer rather than a reason to pay for
        # another run. Reading it rewrites nothing, so a key never written and
        # one holding a value nobody can show stay two different records.
        for named, held in _UNUSABLE_RECORDS:
            with self.subTest(case=named):
                state = PinnedState(data=dict(held))

                run = _late_run_reading._read_late_run(state)

                self.assertTrue(run.answers(_support.late_generation()))
                self.assertEqual(run.rationale, "")
                self.assertEqual(
                    _late_run_reading._recovered_adjudication(run).rationale, "",
                )
                self.assertEqual(state.data, held)


class RationaleBoundTest(unittest.TestCase):
    """What a rationale may take of the record, and what it may never cost.

    The bound is on the rationale alone and is applied before the comment is
    measured, so a long argument is cut rather than refused -- while every
    field a verdict is acted on through still goes in whole or not at all.
    """

    def test_a_long_rationale_is_cut_visibly(self) -> None:
        self.assertEqual(len(_CUT_FILLER), MAX_RATIONALE)
        self.assertTrue(_CUT_FILLER.endswith(RATIONALE_TRUNCATION_MARKER))
        for named, written, kept in _LONG_RATIONALES:
            with self.subTest(case=named):
                state = PinnedState()

                self.assertTrue(_session._record_late_result(state, _LateAdjudication(
                    verdict=LateVerdict.SINGLE,
                    rationale=written,
                    split_blocker=_support.SPLIT_BLOCKER,
                )))
                self.assertEqual(state.get(_support.KEYS.rationale), kept)
                self.assertEqual(
                    _late_run_reading._read_late_run(state).rationale, kept,
                )

    def test_only_the_rationale_is_cut(self) -> None:
        # A shortened explanation gives a reason nobody wrote and a shortened
        # manifest names a child nobody proposed, so beside a cut rationale
        # both go in exactly as the agent wrote them.
        for adjudication, whole_key, whole in _WHOLE_BESIDE_A_CUT:
            with self.subTest(verdict=adjudication.verdict):
                state = PinnedState()

                self.assertTrue(_session._record_late_result(state, adjudication))
                self.assertEqual(state.get(whole_key), whole)
                self.assertEqual(
                    state.get(_support.KEYS.rationale), _cut(_LONG_PROSE),
                )

    def test_the_cut_is_measured_as_it_renders(self) -> None:
        # Escaping is most of what this rationale costs, so a check counting
        # its characters rather than rendering the write would accept it past
        # the ceiling. At the ceiling the whole record goes in; one character
        # past it nothing does -- not the verdict, not the explanation, and
        # not the argument.
        self.assertGreater(
            len(pinned_state_body(dict(_ADVERSARIAL_RECORD)))
            - len(pinned_state_body({**_ADVERSARIAL_RECORD, _support.KEYS.rationale: ""})),
            2 * MAX_RATIONALE,
        )
        for named, padding, fits in (
            ("at the ceiling", _CEILING_PADDING, True),
            ("one past it", _CEILING_PADDING + 1, False),
        ):
            with self.subTest(case=named):
                crowded = {_support.KEYS.plan_pr_body: "p" * padding}
                state = PinnedState(data=dict(crowded))

                self.assertEqual(
                    _session._record_late_result(state, _ADVERSARIAL_SINGLE), fits,
                )
                self.assertEqual(
                    state.data,
                    {**crowded, **_ADVERSARIAL_RECORD} if fits else crowded,
                )

    def test_a_cut_rationale_survives_the_comment(self) -> None:
        # Rendered by the owner that writes the comment and read back by the
        # one that parses it: the wrapper closes where it should, and the
        # value a reader rebuilds is the bounded one the record kept.
        state = PinnedState()
        _session._record_late_result(state, _ADVERSARIAL_SINGLE)
        body = pinned_state_body(state.data)

        parsed = pinned_state_from_comment(
            FakeComment(id=_STATE_COMMENT_ID, body=body),
            trusted_login=None,
            issue_number=_support.LATE_ISSUE_NUMBER,
        )

        self.assertEqual(
            body.index(_COMMENT_CLOSE), len(body) - len(_COMMENT_CLOSE),
        )
        self.assertEqual(
            _late_run_reading._read_late_run(parsed).rationale,
            _ADVERSARIAL_RECORD[_support.KEYS.rationale],
        )


if __name__ == "__main__":
    unittest.main()
