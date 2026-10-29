# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a run's tallies and its money read as, off the record it was parsed from."""
from __future__ import annotations

import unittest

from orchestrator.observability.trajectory_viewer import models
from orchestrator.observability.usage import cost_evidence as usage_cost
from tests.observability.trajectory_viewer.trajectory_viewer_test_support import (
    ASSISTANT_MESSAGE,
    CLAUDE_TOKENS,
    TOOL_BASH,
    TOOL_CALL,
    TOOL_RESULT,
    cost,
    run,
    step,
)

_MODEL_CLAUDE = "claude-opus-4-8"

_RUN_COST = 0.83

_TURN_COST = 0.0123

_INPUT_TOKENS = 12

_OUTPUT_TOKENS = 340

_CACHE_READ_TOKENS = 900

_REPORTED_RUN = cost(usage_cost.COMPLETE, (usage_cost.CLI_REPORTED, _RUN_COST))

_TURN_ESTIMATE = cost(
    usage_cost.COMPLETE, (usage_cost.ANTHROPIC_API_ESTIMATE, _TURN_COST),
)

_UNPRICED = cost(usage_cost.INCOMPLETE)


def _priced_run_usage() -> models.RunUsageView:
    """The run summary a claude record whose CLI reported its cost carries."""
    return models.RunUsageView(
        models=(_MODEL_CLAUDE,),
        turns=2,
        input_tokens=_INPUT_TOKENS,
        output_tokens=_OUTPUT_TOKENS,
        cache_read_tokens=_CACHE_READ_TOKENS,
        cost_evidence=_REPORTED_RUN,
        token_evidence=CLAUDE_TOKENS,
    )


class RunTallyTest(unittest.TestCase):
    """Steps are counted whole; only the calls among them are tool calls."""

    def test_message_turns_are_steps_but_not_calls(self) -> None:
        # The text turns a newer record interleaves must not inflate the tool
        # tally the overview table ranks runs by.
        counted = run(steps=(
            step(ASSISTANT_MESSAGE, content="thinking"),
            step(TOOL_CALL, name=TOOL_BASH),
            step(TOOL_RESULT, tool_id="t1"),
            step("user_message", content="go on"),
            step(TOOL_CALL, name="Edit"),
        ))
        self.assertEqual((counted.step_count, counted.tool_calls), (5, 2))

    def test_a_stepless_run_counts_nothing(self) -> None:
        self.assertEqual((run().step_count, run().tool_calls), (0, 0))


class RunUsageProjectionTest(unittest.TestCase):
    """The money and the token total come from the summary, not the turns."""

    def test_the_summary_is_what_a_run_reports(self) -> None:
        # The first model named is the one the run is attributed to, and the
        # cost is the run's own CLI-reported amount rather than the turns'
        # estimates re-added.
        metered = run(
            run_usage=_priced_run_usage(),
            turns=(models.TurnUsageView(turn=0, cost_evidence=_TURN_ESTIMATE),),
        )
        self.assertEqual(
            (metered.model, metered.cost_evidence),
            (_MODEL_CLAUDE, _REPORTED_RUN),
        )
        self.assertEqual(
            metered.total_tokens,
            _INPUT_TOKENS + _OUTPUT_TOKENS + _CACHE_READ_TOKENS,
        )

    def test_a_pre_usage_record_degrades_cleanly(self) -> None:
        # No summary at all: nothing states what the run used or cost, so each
        # projection answers unknown for its own type rather than raising or
        # reading as free work.
        unmetered = run()
        self.assertEqual(unmetered.model, "")
        self.assertEqual(unmetered.cost_evidence, cost(usage_cost.UNKNOWN))
        self.assertIsNone(unmetered.total_tokens)

    def test_an_unnamed_model_and_unpriced_cost(self) -> None:
        # A summary is present but says less than usual: no model list, and a
        # cost the price catalogue could not resolve.
        partial = run(run_usage=models.RunUsageView(cost_evidence=_UNPRICED))
        self.assertEqual(partial.model, "")
        self.assertEqual(partial.cost_evidence, _UNPRICED)


class TurnLookupTest(unittest.TestCase):
    """A timeline entry finds its own turn's usage while it is walked."""

    def test_a_recorded_turn_is_found_by_index(self) -> None:
        metered = run(turns=(
            models.TurnUsageView(turn=0, cost_evidence=_TURN_ESTIMATE),
            models.TurnUsageView(turn=1, cost_evidence=_UNPRICED),
        ))
        self.assertEqual(metered.usage_for_turn(0).cost_evidence, _TURN_ESTIMATE)
        self.assertEqual(metered.usage_for_turn(1).cost_evidence, _UNPRICED)

    def test_an_unbilled_entry_has_no_turn_usage(self) -> None:
        # A bracket and a tool result carry no turn index, and a codex record
        # carries no per-turn detail at all, so both ask with nothing to find.
        metered = run(turns=(models.TurnUsageView(turn=0),))
        self.assertIsNone(metered.usage_for_turn(None))
        self.assertIsNone(metered.usage_for_turn(9))
        self.assertIsNone(run().usage_for_turn(0))

    def test_an_unindexed_turn_is_unreachable(self) -> None:
        # A malformed record whose turn index would not coerce is kept in the
        # tuple the detail card lists, but is not addressable by index.
        metered = run(turns=(
            models.TurnUsageView(turn=None, cost_evidence=_TURN_ESTIMATE),
        ))
        self.assertIsNone(metered.usage_for_turn(0))
        self.assertEqual(len(metered.turns), 1)


if __name__ == "__main__":
    unittest.main()
