# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Analytics trajectory budget tests."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.observability.analytics.trajectories import models as trajectory_models
from orchestrator.observability.usage import trajectory as _usage_trajectory, trajectory_models as _usage_records
from tests.observability.analytics.analytics_codex_item_cases import (
    CODEX_ACCOUNTING_COUNTS,
    CODEX_ACCOUNTING_STEP_COUNT,
    codex_accounting_stdout as _codex_accounting_stdout,
)
from tests.observability.analytics.analytics_jsonl_helpers import (
    read_records as _read_records,
    read_text as _read_text,
)
from tests.observability.analytics.analytics_trajectory_cases import (
    claude_multistep_stdout as _claude_multistep_stdout,
)
from tests.observability.analytics.trajectories import (
    trajectories_test_support as _support,
)

_ANALYTICS_FILENAME_ALTERNATE = _support.ANALYTICS_FILENAME_ALTERNATE


_CLAUDE = _support.CLAUDE


_CLAUDE_MODEL = _support.CLAUDE_MODEL


_CODEX = _support.CODEX


_IDENTIFIED_ITEMS_KEY = _support.IDENTIFIED_ITEMS_KEY


_SOURCE_ITEM_COUNTS_KEY = _support.SOURCE_ITEM_COUNTS_KEY


_SOURCE_ITEMS_KEY = _support.SOURCE_ITEMS_KEY


_SOURCE_ITEMS_TRUNCATED_KEY = _support.SOURCE_ITEMS_TRUNCATED_KEY


_PROMPT_TEXT = _support.PROMPT_TEXT


_RUN_USAGE_KEY = _support.RUN_USAGE_KEY


_STEPS_KEY = _support.STEPS_KEY


_BASH_TOOL_NAME = _support.BASH_TOOL_NAME


_TOOL_CALL_KIND = _support.TOOL_CALL_KIND


_TOOL_RESULT_KIND = _support.TOOL_RESULT_KIND


_TRAJECTORY_FILENAME = _support.TRAJECTORY_FILENAME


_TRUNCATED_KEY = _support.TRUNCATED_KEY


_TURNS_KEY = _support.TURNS_KEY


_RECORD_BUDGET = "TRAJECTORY_RECORD_BUDGET"


_DROPS_EXCESS_STEPS_OBJECT_ARGUMENT = 3552


_DROPS_EXCESS_STEPS_RESULT_TEXT = 20


_BUDGET_TOOL_PAIR_COUNT = 5


_MANY_TURNS_COUNT = 5_000


_METADATA_ONLY_STEP_COUNT = 10_000


_STEP_TOOL_ID = "t0"


# A claude run of two small steps, which identifies no source items and so
# writes no counts summary.
_NO_ACCOUNTING_TRAJECTORY = _usage_records.AgentTrajectory(
    backend=_CLAUDE,
    steps=(
        _usage_records.TrajectoryStep(
            kind=_TOOL_CALL_KIND,
            name=_BASH_TOOL_NAME,
            tool_id=_STEP_TOOL_ID,
            turn=0,
            content="ls",
        ),
        _usage_records.TrajectoryStep(
            kind=_TOOL_RESULT_KIND,
            tool_id=_STEP_TOOL_ID,
            content="ok",
        ),
    ),
)


_NO_ACCOUNTING_STEP_COUNT = len(_NO_ACCOUNTING_TRAJECTORY.steps)


# Exactly what that run writes: its one prompt character, its `run_usage`
# summary, and both serialized steps. A summary the record leaves off is
# charged none of the budget, so this is the whole of what the record has to
# fit inside.
_NO_ACCOUNTING_BUDGET = 469


_IDENTIFIED_ITEM_COUNT = CODEX_ACCOUNTING_COUNTS[_IDENTIFIED_ITEMS_KEY]


# Three points in the draw-down of one accounting stream: a budget the six
# accounting rows fit inside but the steps behind them do not, one that stops
# partway through the rows, and one already spent before the first of them.
_STEPS_CUT_BUDGET = 1070


_ACCOUNTING_PREFIX_BUDGET = 670


_ACCOUNTING_SPENT_BUDGET = 470


# Each case names a point, the budget that reaches it, and whether the
# accounting's own truncation flag is written there.
_ACCOUNTING_BUDGET_CASES = (
    ("steps cut, accounting whole", _STEPS_CUT_BUDGET, False),
    ("accounting cut to a prefix", _ACCOUNTING_PREFIX_BUDGET, True),
    ("accounting cut away entirely", _ACCOUNTING_SPENT_BUDGET, True),
)


def _emit_stubbed_trajectory(test_case, trajectory) -> tuple[str, dict]:
    with tempfile.TemporaryDirectory() as temp_dir:
        trajectory_path = Path(temp_dir) / _TRAJECTORY_FILENAME
        with patch.object(
            _usage_trajectory,
            "parse_agent_trajectory",
            return_value=trajectory,
        ):
            test_case._emit(
                stdout="",
                prompt=_PROMPT_TEXT,
                traj_path=trajectory_path,
                analytics_path=Path(temp_dir) / _ANALYTICS_FILENAME_ALTERNATE,
            )
        raw_record = _read_text(trajectory_path)
    return raw_record, json.loads(raw_record)


class RecordAgentExitTrajectoryBudgetTest(_support.RecordAgentExitTrajectorySupport):
    def test_total_record_budget_drops_excess_steps(self) -> None:
        # When the cumulative redacted content crosses the record budget the
        # remaining steps are dropped and `truncated` is set, so one runaway
        # run cannot write an unbounded JSONL line.
        with (
            tempfile.TemporaryDirectory() as td,
            patch.object(trajectory_models, _RECORD_BUDGET, _DROPS_EXCESS_STEPS_OBJECT_ARGUMENT),
        ):
            t_path = Path(td) / _TRAJECTORY_FILENAME
            self._emit(
                stdout=_claude_multistep_stdout(
                    n_steps=_BUDGET_TOOL_PAIR_COUNT,
                    result_text="ten-chars!" * _DROPS_EXCESS_STEPS_RESULT_TEXT,
                ),
                traj_path=t_path,
                analytics_path=Path(td) / _ANALYTICS_FILENAME_ALTERNATE,
            )
            rec = _read_records(t_path)[0]
            self.assertTrue(rec[_TRUNCATED_KEY])
            # 5 pairs => 10 steps emitted; the budget dropped the tail but
            # kept a prefix.
            self.assertGreater(len(rec[_STEPS_KEY]), 0)
            self.assertLess(
                len(rec[_STEPS_KEY]),
                _BUDGET_TOOL_PAIR_COUNT * 2,
            )
            # The 5 small per-turn entries fit under the budget (they are drawn
            # down before the steps), so all are kept while the step tail is
            # dropped; a turns array that itself overflows is truncated too
            # (see test_turns_array_respects_total_budget).
            self.assertEqual(
                len(rec[_TURNS_KEY]),
                _BUDGET_TOOL_PAIR_COUNT,
            )
            self.assertIn(_RUN_USAGE_KEY, rec)

    def test_turns_array_respects_total_budget(self) -> None:
        # Regression: the per-turn `turns[]` array is charged AND truncated
        # under the record budget, not merely charged. A claude run with
        # thousands of turns but no steps would otherwise write the whole
        # array in full via `build_record` and overshoot the budget by its
        # size -- the reviewer reproduced ~914 KB with zero steps kept.
        many = _usage_records.AgentTrajectory(
            backend=_CLAUDE,
            turns=tuple(
                _usage_records.TurnUsage(
                    turn=index,
                    model=_CLAUDE_MODEL,
                    input_tokens=1,
                    output_tokens=1,
                )
                for index in range(_MANY_TURNS_COUNT)
            ),
        )
        raw, rec = _emit_stubbed_trajectory(self, many)
        self.assertTrue(rec[_TRUNCATED_KEY])
        self.assertLess(len(rec[_TURNS_KEY]), _MANY_TURNS_COUNT)
        # The on-disk line is bounded near the budget, not the ~914 KB an
        # uncapped turns array produced.
        self.assertLess(len(raw), getattr(trajectory_models, _RECORD_BUDGET) * 2)

    def test_metadata_only_steps_respect_total_budget(self) -> None:
        # Regression: the budget must count each step's serialized metadata,
        # not just `len(content)`. A run of 10,000 empty-content steps -- each
        # still ~80 bytes of `kind` / `name` / `tool_id` JSON -- would
        # otherwise produce a multi-hundred-KB record with NO `truncated`
        # flag, because the old content-length-only check never advanced.
        many = _usage_records.AgentTrajectory(
            backend=_CLAUDE,
            steps=tuple(
                _usage_records.TrajectoryStep(
                    kind=_TOOL_CALL_KIND,
                    name="command_execution",
                    tool_id=f"id{index}",
                    content=None,
                )
                for index in range(_METADATA_ONLY_STEP_COUNT)
            ),
        )
        raw, rec = _emit_stubbed_trajectory(self, many)
        self.assertTrue(rec[_TRUNCATED_KEY])
        self.assertLess(
            len(rec[_STEPS_KEY]),
            _METADATA_ONLY_STEP_COUNT,
        )
        # The on-disk line is bounded near the budget, not the ~749 KB an
        # uncapped run produced -- one step of overshoot plus the envelope.
        self.assertLess(len(raw), getattr(trajectory_models, _RECORD_BUDGET) * 2)

    def test_absent_accounting_costs_no_budget(self) -> None:
        # A run that identifies no source items is charged for none: at the
        # budget its own fields add up to, every step is kept and nothing is
        # flagged truncated, while one byte under it the last step goes.
        for budget, kept in (
            (_NO_ACCOUNTING_BUDGET, _NO_ACCOUNTING_STEP_COUNT),
            (_NO_ACCOUNTING_BUDGET - 1, _NO_ACCOUNTING_STEP_COUNT - 1),
        ):
            with self.subTest(budget=budget):
                self._assert_steps_kept(budget, kept)

    def _assert_steps_kept(self, budget: int, kept: int) -> None:
        with patch.object(trajectory_models, _RECORD_BUDGET, budget):
            record = _emit_stubbed_trajectory(self, _NO_ACCOUNTING_TRAJECTORY)[1]
        self.assertNotIn(_SOURCE_ITEM_COUNTS_KEY, record)
        self.assertEqual(len(record[_STEPS_KEY]), kept)
        self.assertEqual(
            record.get(_TRUNCATED_KEY, False),
            kept < _NO_ACCOUNTING_STEP_COUNT,
        )


class RecordAgentExitItemAccountingBudgetTest(_support.RecordAgentExitTrajectorySupport):
    """The source-item accounting is charged, and drawn ahead of the steps."""

    def test_accounting_outlasts_the_steps_it_covers(self) -> None:
        # The accounting is charged like every other variable array, but it is
        # drawn down before the steps: an id-by-id audit stays possible on the
        # very runs that overran the budget, where the timeline the ids account
        # for is what got cut. Once the budget reaches the rows themselves they
        # are cut to a prefix -- or to nothing -- and the flag beside them says
        # so, while the counts keep stating how many items the stream
        # identified either way.
        for case, budget, items_cut in _ACCOUNTING_BUDGET_CASES:
            with self.subTest(case=case):
                self._assert_bounded_accounting(budget, items_cut)

    def _assert_bounded_accounting(self, budget: int, items_cut: bool) -> None:
        record = self._emit_accounting_record(budget)
        kept = len(record.get(_SOURCE_ITEMS_KEY, ()))
        self.assertEqual(
            record[_SOURCE_ITEM_COUNTS_KEY],
            dict(CODEX_ACCOUNTING_COUNTS),
        )
        self.assertTrue(record[_TRUNCATED_KEY])
        self.assertEqual(
            record.get(_SOURCE_ITEMS_TRUNCATED_KEY, False),
            items_cut,
        )
        if items_cut:
            self.assertLess(kept, _IDENTIFIED_ITEM_COUNT)
            return
        self.assertEqual(kept, _IDENTIFIED_ITEM_COUNT)
        self.assertGreater(len(record[_STEPS_KEY]), 0)
        self.assertLess(len(record[_STEPS_KEY]), CODEX_ACCOUNTING_STEP_COUNT)

    def _emit_accounting_record(self, record_budget: int) -> dict:
        with (
            tempfile.TemporaryDirectory() as sink_dir,
            patch.object(trajectory_models, _RECORD_BUDGET, record_budget),
        ):
            trajectory_path = Path(sink_dir) / _TRAJECTORY_FILENAME
            self._emit(
                backend=_CODEX,
                stdout=_codex_accounting_stdout(),
                prompt=_PROMPT_TEXT,
                traj_path=trajectory_path,
                analytics_path=Path(sink_dir) / _ANALYTICS_FILENAME_ALTERNATE,
            )
            return _read_records(trajectory_path)[0]


if __name__ == "__main__":
    unittest.main()
