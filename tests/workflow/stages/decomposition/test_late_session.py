# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The late run's pinned record: what it locks, and when it is believed."""
from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState
from orchestrator.workflow.late_split.events import LateVerdictCategory
from orchestrator.workflow.late_split.models import LateVerdict
from orchestrator.workflow.stages.decomposition import (
    late_models as _models,
    late_session as _session,
)
from orchestrator.workflow.stages.decomposition.late_budget import ESTIMATE
from tests.workflow.fixtures import BACKEND_CODEX
from tests.workflow.stages.decomposition import late_test_support as _support

DAMAGED_VERDICT = "probably fine"

ASKED = "which half of this is in scope?"

TITLE = "title"
BODY = "body"
DEPENDS_ON = "depends_on"
FIRST_TITLE = "A"
SECOND_TITLE = "B"
FIRST_BODY = "a"
SECOND_BODY = "b"

SPLIT_CHILDREN = (
    {TITLE: FIRST_TITLE, BODY: FIRST_BODY, ESTIMATE: _support.FIRST_ESTIMATE},
    {
        TITLE: SECOND_TITLE,
        BODY: SECOND_BODY,
        DEPENDS_ON: [0],
        ESTIMATE: _support.SECOND_ESTIMATE,
    },
)

# A budget nothing estimated: a numeric string is not a count, and a slice
# sized by one is a slice nobody sized.
UNESTIMATED = "400"

# What the comment has left over in the boundary case below: less than the
# sentence a `single` goes on to owe the thread, so a padded comment that
# takes every verdict is one that would refuse a `single` charged for it.
_ROOM_LEFT = 512


def recorded_child(
    title: str = FIRST_TITLE,
    body: str = FIRST_BODY,
    estimated: int | None = _support.FIRST_ESTIMATE,
) -> dict:
    """One child as the pinned comment records it, fields and all.

    `estimated` of None is the slice that declared no budget, which is what
    a manifest written before this domain kept them reads back as.
    """
    recorded = {TITLE: title, BODY: body, DEPENDS_ON: []}
    if estimated is not None:
        recorded[ESTIMATE] = estimated
    return recorded


def _completed_run(**overrides) -> _models._LateRun:
    return replace(
        _models._LateRun(
            role=_support.ROLE_DECOMPOSER,
            spec=_support.LATE_SPEC,
            backend=_support.LATE_BACKEND,
            extra_args=_support.LATE_ARGS,
            cycle_id=_support.CYCLE_ID,
            source_sha=_support.CANDIDATE_SHA,
            generation=_support.GENERATION_NUMBER,
            verdict=LateVerdict.SINGLE,
            split_blocker=_support.SPLIT_BLOCKER,
        ),
        **overrides,
    )


class LateRunRecordTest(unittest.TestCase):
    """What a fresh spawn records, and what a completed run adds to it."""

    def test_a_spawn_records_what_the_run_is(self) -> None:
        state = PinnedState()

        _session._record_late_spawn(state, _completed_run())

        self.assertEqual(state.get(_support.KEYS.role), _support.ROLE_DECOMPOSER)
        self.assertEqual(state.get(_support.KEYS.agent), _support.LATE_SPEC)
        self.assertEqual(state.get(_support.KEYS.run_cycle_id), _support.CYCLE_ID)
        self.assertEqual(state.get(_support.KEYS.source_sha), _support.CANDIDATE_SHA)
        self.assertEqual(state.get(_support.KEYS.run_generation), _support.GENERATION_NUMBER)

    def test_a_fresh_spawn_drops_the_previous_answer(self) -> None:
        # A tick that crashes mid-run must not read the last generation's
        # verdict back as this one's.
        state = PinnedState(data={
            _support.KEYS.session_id: "older-sess",
            _support.KEYS.verdict: str(LateVerdict.SINGLE),
            _support.KEYS.category: str(LateVerdictCategory.UNSAFE_SPLIT),
            _support.KEYS.split_blocker: _support.SPLIT_BLOCKER,
        })

        _session._record_late_spawn(state, _completed_run())

        for dropped in (
            _support.KEYS.session_id, _support.KEYS.verdict, _support.KEYS.category, _support.KEYS.split_blocker,
        ):
            with self.subTest(key=dropped):
                self.assertNotIn(dropped, state.data)

    def test_a_result_records_verdict_and_category(self) -> None:
        state = PinnedState()

        _session._record_late_result(state, _models._LateAdjudication(
            verdict=LateVerdict.QUESTION,
            category=LateVerdictCategory.SCOPE_AMBIGUOUS,
            question=ASKED,
        ))

        self.assertEqual(
            state.data,
            {
                _support.KEYS.verdict: str(LateVerdict.QUESTION),
                _support.KEYS.category: str(LateVerdictCategory.SCOPE_AMBIGUOUS),
                _support.KEYS.question: ASKED,
            },
        )

    def test_the_record_round_trips(self) -> None:
        state = PinnedState()
        _session._record_late_spawn(state, _completed_run())
        _session._record_late_result(
            state, _models._LateAdjudication(
                verdict=LateVerdict.SINGLE, split_blocker=_support.SPLIT_BLOCKER,
            ),
        )

        self.assertEqual(_session._read_late_run(state), _completed_run())


class LateResultRecordTest(unittest.TestCase):
    """What a completed outcome is written as, and what it refuses to be."""

    def test_a_split_records_its_manifest(self) -> None:
        # The manifest IS what a split decided, so a record without it would
        # refuse the re-run while the answer it stands for was gone.
        state = PinnedState()

        _session._record_late_result(state, _models._LateAdjudication(
            verdict=LateVerdict.SPLIT,
            rationale="two slices",
            children=SPLIT_CHILDREN,
        ))

        self.assertEqual(
            state.get(_support.KEYS.children),
            [
                recorded_child(),
                {
                    TITLE: SECOND_TITLE,
                    BODY: SECOND_BODY,
                    DEPENDS_ON: [0],
                    ESTIMATE: _support.SECOND_ESTIMATE,
                },
            ],
        )

    def test_a_manifest_carries_only_its_own_fields(self) -> None:
        # Rewritten from the fields a child issue is created out of, so
        # nothing an agent put beside them lands in the comment humans read
        # -- and the budget that issue states is one of them.
        state = PinnedState()

        _session._record_late_result(state, _models._LateAdjudication(
            verdict=LateVerdict.SPLIT,
            children=({
                TITLE: FIRST_TITLE,
                BODY: FIRST_BODY,
                ESTIMATE: _support.FIRST_ESTIMATE,
                "notes": "x",
            },),
        ))

        self.assertEqual(state.get(_support.KEYS.children), [recorded_child()])

    def test_a_slice_nobody_sized_records_no_budget(self) -> None:
        # A value that is not a count is one nothing estimated, and writing it
        # back would put a size in the comment as though an agent had given
        # it. A manifest recorded before this domain kept budgets is the same
        # record, so both read back the same way.
        state = PinnedState()

        _session._record_late_result(state, _models._LateAdjudication(
            verdict=LateVerdict.SPLIT,
            children=(
                {TITLE: FIRST_TITLE, BODY: FIRST_BODY},
                {
                    TITLE: SECOND_TITLE,
                    BODY: SECOND_BODY,
                    ESTIMATE: UNESTIMATED,
                },
            ),
        ))

        self.assertEqual(
            state.get(_support.KEYS.children),
            [
                recorded_child(estimated=None),
                recorded_child(SECOND_TITLE, SECOND_BODY, estimated=None),
            ],
        )

    def test_a_single_records_what_stopped_a_split(self) -> None:
        # The one thing a human deciding about an oversized candidate cannot
        # get from anywhere else once the run is over.
        state = PinnedState()

        _session._record_late_result(state, _models._LateAdjudication(
            verdict=LateVerdict.SINGLE,
            rationale="one coherent change",
            split_blocker=_support.SPLIT_BLOCKER,
        ))

        self.assertEqual(
            state.data,
            {
                _support.KEYS.verdict: str(LateVerdict.SINGLE),
                _support.KEYS.split_blocker: _support.SPLIT_BLOCKER,
            },
        )

    def test_a_recovered_outcome_is_whole(self) -> None:
        state = PinnedState()
        _session._record_late_result(state, _models._LateAdjudication(
            verdict=LateVerdict.SPLIT, children=SPLIT_CHILDREN,
        ))

        recovered = _session._recovered_adjudication(
            _session._read_late_run(state),
        )

        self.assertEqual(recovered.verdict, LateVerdict.SPLIT)
        self.assertEqual(
            [child[TITLE] for child in recovered.children],
            [FIRST_TITLE, SECOND_TITLE],
        )
        self.assertEqual(recovered.children[1][DEPENDS_ON], [0])
        self.assertEqual(
            [child[ESTIMATE] for child in recovered.children],
            [_support.FIRST_ESTIMATE, _support.SECOND_ESTIMATE],
        )

    def test_a_recovered_single_reports_a_reason(self) -> None:
        # A result recorded before this domain kept an explanation is still
        # this candidate's answer, and reports the stand-in: re-running the
        # adjudicator to recover prose would pay for a second run that is
        # free to decide something else.
        cases = (
            ("recorded", {_support.KEYS.split_blocker: _support.SPLIT_BLOCKER}, _support.SPLIT_BLOCKER),
            ("legacy", {}, _models.UNRECORDED_SPLIT_BLOCKER),
        )
        for name, recorded, expected in cases:
            with self.subTest(case=name):
                run = _session._read_late_run(PinnedState(data={
                    _support.KEYS.run_cycle_id: _support.CYCLE_ID,
                    _support.KEYS.source_sha: _support.CANDIDATE_SHA,
                    _support.KEYS.run_generation: _support.GENERATION_NUMBER,
                    _support.KEYS.verdict: str(LateVerdict.SINGLE),
                    **recorded,
                }))

                self.assertTrue(run.answers(_support.late_generation()))
                self.assertEqual(
                    _session._recovered_adjudication(
                        run,
                    ).split_blocker_explanation,
                    expected,
                )


class LateResultBudgetTest(unittest.TestCase):
    """What an outcome may take of the comment it is written into.

    The comment is shared and bounded, so what is measured is the whole of
    what the write would produce -- and what it leaves behind matters as much,
    since the sentence the outcome earns has to be recorded there too.
    """

    def test_an_outcome_past_the_budget_is_refused(self) -> None:
        # Shortening it would record a question nobody asked or an
        # explanation nobody wrote; the caller is told it did not fit rather
        # than handed half an outcome.
        oversized = "x" * _session.MAX_RECORDED_BODY
        cases = (
            _models._LateAdjudication(
                verdict=LateVerdict.QUESTION,
                category=LateVerdictCategory.UNKNOWN,
                question=oversized,
            ),
            _models._LateAdjudication(
                verdict=LateVerdict.SINGLE, split_blocker=oversized,
            ),
        )
        for adjudication in cases:
            with self.subTest(verdict=adjudication.verdict):
                state = PinnedState()

                kept = _session._record_late_result(state, adjudication)

                self.assertFalse(kept)
                self.assertEqual(state.data, {})

    def test_what_the_comment_already_holds_counts(self) -> None:
        # A result small on its own can still be the one that pushes the
        # comment past what GitHub accepts, and finding that out from the
        # failed write means the agent has already been paid for.
        held = PinnedState(data={
            _support.KEYS.plan_pr_body: "p" * (_session.MAX_RECORDED_BODY - 100),
        })
        modest = _models._LateAdjudication(
            verdict=LateVerdict.SPLIT, children=SPLIT_CHILDREN,
        )

        self.assertTrue(
            _session._record_late_result(PinnedState(), modest),
        )
        self.assertFalse(_session._record_late_result(held, modest))
        self.assertNotIn(_support.KEYS.verdict, held.data)

    def test_no_verdict_pays_for_the_sentence_it_owes(self) -> None:
        # One budget, and every verdict is held to it. The park a `single`
        # earns is one nothing supersedes, while the refusal a smaller budget
        # would produce IS superseded -- so charging it for the sentence it
        # owes would buy another decomposer run against a candidate already
        # adjudicated and leave that `single` short of the park a human's
        # decision is owed on.
        crowded = {
            _support.KEYS.plan_pr_body: "p" * (_session.MAX_RECORDED_BODY - _ROOM_LEFT),
        }
        verdicts = (
            ("single", _models._LateAdjudication(verdict=LateVerdict.SINGLE)),
            ("split", _models._LateAdjudication(
                verdict=LateVerdict.SPLIT, children=SPLIT_CHILDREN,
            )),
        )

        for named, adjudication in verdicts:
            with self.subTest(verdict=named):
                self.assertTrue(_session._record_late_result(
                    PinnedState(data=dict(crowded)), adjudication,
                ))

    def test_a_park_sentence_has_room_left_over(self) -> None:
        # What that costs nothing, because it is written into the headroom the
        # outcome budget leaves under GitHub's own limit rather than out of
        # the budget itself.
        self.assertLessEqual(
            _session.MAX_RECORDED_BODY + _session.MAX_NOTICE_BODY,
            MAX_PINNED_BODY,
        )


class LateSessionLockTest(unittest.TestCase):
    """Which backend a later run lands on, and what it falls back to."""

    def test_an_unlocked_issue_uses_the_config(self) -> None:
        run = _session._read_late_run(PinnedState())

        self.assertEqual(run.spec, config.DECOMPOSE_AGENT_SPEC)
        self.assertEqual(run.backend, config.DECOMPOSE_AGENT)
        self.assertEqual(run.extra_args, config.DECOMPOSE_AGENT_ARGS)
        self.assertEqual(run.role, _support.ROLE_DECOMPOSER)

    def test_a_locked_spec_outranks_the_config(self) -> None:
        state = PinnedState(data={_support.KEYS.agent: _support.LATE_SPEC})

        with patch.object(config, "DECOMPOSE_AGENT_SPEC", BACKEND_CODEX):
            run = _session._read_late_run(state)

        self.assertEqual(run.spec, _support.LATE_SPEC)
        self.assertEqual(run.backend, _support.LATE_BACKEND)
        self.assertEqual(run.extra_args, _support.LATE_ARGS)

    def test_a_legacy_bare_backend_round_trips(self) -> None:
        run = _session._read_late_run(
            PinnedState(data={_support.KEYS.agent: BACKEND_CODEX}),
        )

        self.assertEqual(run.backend, BACKEND_CODEX)
        self.assertEqual(run.extra_args, ())


class LateRunAnswersTest(unittest.TestCase):
    """When a recorded result is read instead of paying for another run."""

    def test_only_this_generation_and_commit(self) -> None:
        cases = (
            ("the recorded answer", _completed_run(), True),
            # A restart mints a fresh cycle and puts the generation counter
            # back where it started, so the counter alone would read one
            # cycle's verdict as the next one's.
            ("another cycle", _completed_run(cycle_id=_support.CYCLE_ID + 1), False),
            ("another generation", _completed_run(generation=2), False),
            ("another commit", _completed_run(source_sha=_support.OTHER_SHA), False),
            ("no commit at all", _completed_run(source_sha=""), False),
            ("no result yet", _completed_run(verdict=None), False),
        )
        for name, run, answered in cases:
            with self.subTest(case=name):
                self.assertEqual(run.answers(_support.late_generation()), answered)

    def test_an_incomplete_record_reads_unanswered(self) -> None:
        # A half-written outcome is worse than none: it would suppress the
        # next spawn and then have nothing to announce or create.
        cases = (
            ("a damaged verdict", {_support.KEYS.verdict: DAMAGED_VERDICT}),
            ("a question with no question", {
                _support.KEYS.verdict: str(LateVerdict.QUESTION),
                _support.KEYS.category: str(LateVerdictCategory.UNSAFE_SPLIT),
            }),
            ("a question with no category", {
                _support.KEYS.verdict: str(LateVerdict.QUESTION),
                _support.KEYS.question: ASKED,
            }),
            ("a split with no manifest", {
                _support.KEYS.verdict: str(LateVerdict.SPLIT),
            }),
            ("a split whose manifest is not one", {
                _support.KEYS.verdict: str(LateVerdict.SPLIT),
                _support.KEYS.children: [{TITLE: FIRST_TITLE}],
            }),
        )
        for name, recorded in cases:
            with self.subTest(case=name):
                run = _session._read_late_run(PinnedState(data={
                    _support.KEYS.run_cycle_id: _support.CYCLE_ID,
                    _support.KEYS.source_sha: _support.CANDIDATE_SHA,
                    _support.KEYS.run_generation: _support.GENERATION_NUMBER,
                    **recorded,
                }))

                self.assertFalse(run.answers(_support.late_generation()))

    def test_a_split_with_no_budgets_reads_answered(self) -> None:
        # A live issue's split was recorded before this domain kept budgets,
        # and the rules a record is read through ask for none. Reading such a
        # manifest as no manifest at all would send a candidate that has
        # already been adjudicated round again, for a run free to decide
        # something else entirely.
        unsized = recorded_child(estimated=None)
        run = _session._read_late_run(PinnedState(data={
            _support.KEYS.run_cycle_id: _support.CYCLE_ID,
            _support.KEYS.source_sha: _support.CANDIDATE_SHA,
            _support.KEYS.run_generation: _support.GENERATION_NUMBER,
            _support.KEYS.verdict: str(LateVerdict.SPLIT),
            _support.KEYS.children: [unsized],
        }))

        self.assertTrue(run.answers(_support.late_generation()))
        self.assertEqual(run.children, (unsized,))

    def test_a_budgeted_split_reads_back_whole(self) -> None:
        # The manifest the transaction creates children from, so the budget
        # each child issue states has to survive the record it is read out of.
        run = _session._read_late_run(PinnedState(data={
            _support.KEYS.run_cycle_id: _support.CYCLE_ID,
            _support.KEYS.source_sha: _support.CANDIDATE_SHA,
            _support.KEYS.run_generation: _support.GENERATION_NUMBER,
            _support.KEYS.verdict: str(LateVerdict.SPLIT),
            _support.KEYS.children: [recorded_child()],
        }))

        self.assertTrue(run.answers(_support.late_generation()))
        self.assertEqual(run.children, (recorded_child(),))
        self.assertEqual(run.children[0][ESTIMATE], _support.FIRST_ESTIMATE)


if __name__ == "__main__":
    unittest.main()
