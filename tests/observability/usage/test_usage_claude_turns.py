# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Focused provider usage parsing tests."""

import json
import unittest

from orchestrator.observability.usage import (
    metrics as _metrics,
    trajectory as _trajectory,
    trajectory_models as _records,
)
from tests.observability.usage import (
    usage_assertions as _assertions,
    usage_claude_events as _claude,
    usage_claude_stream_capture as _capture,
    usage_claude_subagent_events as _subagent,
    usage_jsonl_helpers as _jsonl,
    usage_pricing_cases as _pricing,
    usage_test_values as _usage_cases,
)

# The subagent capture's messages in the order their first frames print.
_SUBAGENT_RUN_PRINTED = (
    _capture.SUBAGENT_RUN_LEAD_MESSAGES[0],
    *_capture.SUBAGENT_RUN_SUBAGENT_MESSAGES,
    *_capture.SUBAGENT_RUN_LEAD_MESSAGES[1:],
)


def _settled_turn(turn: _records.TurnUsage) -> tuple[object, ...]:
    return turn.turn, turn.model, _capture.TokenCounts.parsed(turn), turn.cost_source


def _turn_counts(trajectory: _records.AgentTrajectory) -> list[_capture.TokenCounts]:
    return [_capture.TokenCounts.parsed(turn) for turn in trajectory.turns]


def _parsed(run_stdout: str) -> tuple[_metrics.UsageMetrics, _records.AgentTrajectory]:
    """The run's usage and its trajectory, each parsed from the stream on its own."""
    return _metrics.parse_claude_usage(run_stdout), _trajectory.parse_claude_trajectory(run_stdout)


class ClaudeTurnUsageTest(unittest.TestCase):
    """Per-turn token usage from ``_trajectory.parse_claude_trajectory``.

    Tokens are billed per assistant turn (one ``message.id``), not per timeline
    step: a turn's ``text`` and ``tool_use`` blocks share one ``usage`` record,
    so usage rides on ``_records.AgentTrajectory.turns`` -- one ``_records.TurnUsage`` per turn --
    while every ``assistant_message`` / ``tool_call`` step carries the same
    ``turn`` index. Per-turn cost is always an estimate from the shared price
    path; ``tool_result`` / ``user_message`` steps are turn inputs (``turn``
    ``None``).
    """

    def test_indexes_span_tool_turns_and_models(
        self,
    ) -> None:
        # A single assistant message with a text block and two tool_use blocks
        # is one turn: all three steps share turn 0 and there is one _records.TurnUsage
        # for it, with the cache read/write split and a per-turn estimated cost
        # priced from that turn's own model. A second message is turn 1, priced
        # from its own (different) model; the interleaved tool_result steps are
        # turn inputs and carry no index.
        stdout = _jsonl.jsonl(
            _claude.system_init(tools=[_usage_cases.BASH_TOOL, "Edit"]),
            _claude.assistant(
                id=_usage_cases.CLAUDE_TURN_ID,
                model=_usage_cases.SONNET,
                content_blocks=[
                    _jsonl.text("working"),
                    _jsonl.tool_use(
                        _usage_cases.BASH_TOOL,
                        {_usage_cases.COMMAND_FIELD: _usage_cases.LIST_COMMAND},
                        id=_usage_cases.TASK_ONE_ID,
                    ),
                    _jsonl.tool_use("Edit", {_usage_cases.FILE_PATH_FIELD: "a.py"}, id="t2"),
                ],
                usage=_claude.usage(
                    input=_usage_cases.CLAUDE_TURN_INPUT_TOKENS,
                    cache_write=_usage_cases.CLAUDE_TURN_CACHE_WRITE_TOKENS,
                    cache_read=_usage_cases.CLAUDE_TURN_CACHE_READ_TOKENS,
                    output=_usage_cases.CLAUDE_TURN_OUTPUT_TOKENS,
                ),
            ),
            _jsonl.user(
                [
                    _jsonl.tool_result(_usage_cases.TASK_ONE_ID, "o1"),
                    _jsonl.tool_result("t2", "o2"),
                ]
            ),
            _claude.assistant(
                id="msg_1",
                model=_usage_cases.HAIKU,
                content_blocks=[_jsonl.text(_usage_cases.FINAL_OUTPUT)],
                usage=_claude.usage(
                    input=_usage_cases.HAIKU_TURN_INPUT_TOKENS,
                    output=_usage_cases.HAIKU_TURN_OUTPUT_TOKENS,
                ),
            ),
            _claude.terminal_result(result="ok", num_turns=2),
        )
        trajectory = _trajectory.parse_claude_trajectory(stdout)
        self.assertEqual(
            [(step.kind, step.turn) for step in trajectory.steps],
            [
                (_usage_cases.ASSISTANT_MESSAGE_STEP, 0),
                (_usage_cases.TOOL_CALL_STEP, 0),
                (_usage_cases.TOOL_CALL_STEP, 0),
                (_usage_cases.TOOL_RESULT_STEP, None),
                (_usage_cases.TOOL_RESULT_STEP, None),
                (_usage_cases.ASSISTANT_MESSAGE_STEP, 1),
            ],
        )
        self.assertEqual(len(trajectory.turns), 2)
        turn0, turn1 = trajectory.turns
        # sonnet: input=3, cw5m=3.75, cr=0.30, output=15 (per 1M).
        self.assertEqual(
            turn0,
            _records.TurnUsage(
                turn=0,
                model=_usage_cases.SONNET,
                input_tokens=_usage_cases.CLAUDE_TURN_INPUT_TOKENS,
                output_tokens=_usage_cases.CLAUDE_TURN_OUTPUT_TOKENS,
                cache_read_tokens=_usage_cases.CLAUDE_TURN_CACHE_READ_TOKENS,
                cache_write_tokens=_usage_cases.CLAUDE_TURN_CACHE_WRITE_TOKENS,
                cost_usd=turn0.cost_usd,
                cost_source=_usage_cases.ESTIMATED_COST_SOURCE,
            ),
        )
        _assertions.assert_cost(
            self,
            turn0,
            _pricing.sonnet_turn_cost(),
            places=_usage_cases.COST_ASSERT_PLACES,
        )
        # haiku-3-5: input=0.80, output=4 (per 1M).
        self.assertEqual(turn1.turn, 1)
        self.assertEqual(turn1.model, _usage_cases.HAIKU)
        self.assertEqual(turn1.cache_read_tokens, 0)
        self.assertEqual(turn1.cache_write_tokens, 0)
        _assertions.assert_cost(
            self,
            turn1,
            _pricing.haiku_turn_cost(),
            places=_usage_cases.COST_ASSERT_PLACES,
        )

    def test_cache_creation_adds_to_cache_write(self) -> None:
        # The structured 5m/1h cache-creation form sums into a single per-turn
        # cache_write_tokens while both still price at their own rate.
        stdout = _jsonl.jsonl(
            _claude.assistant(
                id=_usage_cases.CLAUDE_TURN_ID,
                model=_usage_cases.OPUS_FOUR_SEVEN,
                content_blocks=[_jsonl.text(_usage_cases.GREETING_TEXT)],
                usage=_claude.usage(
                    input=0,
                    cache_five_minute=_usage_cases.CLAUDE_FIVE_MINUTE_CACHE_TOKENS,
                    cache_one_hour=_usage_cases.CLAUDE_ONE_HOUR_CACHE_TOKENS,
                    output=100,
                ),
            ),
        )
        turn0 = _trajectory.parse_claude_trajectory(stdout).turns[0]
        self.assertEqual(
            turn0.cache_write_tokens,
            _usage_cases.CLAUDE_COMBINED_CACHE_WRITE_TOKENS,
        )
        # opus-4-7: input=5, cw5m=6.25, cw1h=10, cr=0.50, output=25.
        expected = (
            _usage_cases.CLAUDE_FIVE_MINUTE_CACHE_TOKENS * _usage_cases.PRICE_RATE_SIX_AND_QUARTER
            + _usage_cases.CLAUDE_ONE_HOUR_CACHE_TOKENS * 10
            + 100 * _usage_cases.PRICE_RATE_TWENTY_FIVE
        ) / _usage_cases.TOKENS_PER_MILLION
        assert turn0.cost_usd is not None
        self.assertAlmostEqual(
            turn0.cost_usd,
            expected,
            places=_usage_cases.COST_ASSERT_PLACES,
        )

    def test_partial_frames_use_last_record_per_turn(self) -> None:
        # Two frames sharing a message.id are one turn, and with no
        # message_delta closing it the last frame's usage record is the
        # turn's. Both frames' steps carry the single turn 0.
        stdout = _jsonl.jsonl(
            _claude.assistant(
                id=_usage_cases.CLAUDE_TURN_ID,
                model=_usage_cases.OPUS_FOUR_SEVEN,
                content_blocks=[_jsonl.text("partial")],
                usage=_claude.usage(input=5, output=10, cache_read=100),
            ),
            _claude.assistant(
                id=_usage_cases.CLAUDE_TURN_ID,
                model=_usage_cases.OPUS_FOUR_SEVEN,
                content_blocks=[
                    _jsonl.tool_use(
                        _usage_cases.BASH_TOOL,
                        {_usage_cases.COMMAND_FIELD: _usage_cases.LIST_COMMAND},
                        id=_usage_cases.TASK_ONE_ID,
                    ),
                ],
                usage=_claude.usage(
                    input=8,
                    output=_usage_cases.PARTIAL_TURN_OUTPUT_TOKENS,
                    cache_read=_usage_cases.PARTIAL_TURN_CACHE_READ_TOKENS,
                ),
            ),
        )
        trajectory = _trajectory.parse_claude_trajectory(stdout)
        self.assertEqual([step.turn for step in trajectory.steps], [0, 0])
        self.assertEqual(len(trajectory.turns), 1)
        self.assertEqual(trajectory.turns[0].input_tokens, 8)
        self.assertEqual(
            trajectory.turns[0].output_tokens,
            _usage_cases.PARTIAL_TURN_OUTPUT_TOKENS,
        )
        self.assertEqual(
            trajectory.turns[0].cache_read_tokens,
            _usage_cases.PARTIAL_TURN_CACHE_READ_TOKENS,
        )

    def test_unpriced_model_turn_is_unknown_price(self) -> None:
        # A turn whose model has no first-party rate is unknown-price with a
        # None cost -- never a silent zero -- while its token counts still land.
        stdout = _jsonl.jsonl(
            _claude.assistant(
                id=_usage_cases.CLAUDE_TURN_ID,
                model=_usage_cases.UNKNOWN_MODEL,
                content_blocks=[_jsonl.text(_usage_cases.GREETING_TEXT)],
                usage=_claude.usage(input=100, output=_usage_cases.TOKEN_COUNT_TWO_HUNDRED),
            ),
        )
        turn0 = _trajectory.parse_claude_trajectory(stdout).turns[0]
        self.assertEqual(turn0.cost_source, _usage_cases.UNKNOWN_COST_SOURCE)
        self.assertIsNone(turn0.cost_usd)
        self.assertEqual(turn0.model, _usage_cases.UNKNOWN_MODEL)
        self.assertEqual(turn0.input_tokens, 100)
        self.assertEqual(turn0.output_tokens, _usage_cases.TOKEN_COUNT_TWO_HUNDRED)

    def test_turn_cost_estimated_when_run_has_cost(
        self,
    ) -> None:
        # total_cost_usd is a run-level terminal figure; per-turn cost is always
        # an estimate and never inherits the reported source or value, even
        # though the run aggregate still surfaces the authoritative total.
        stdout = _jsonl.jsonl(
            _claude.assistant(
                id=_usage_cases.CLAUDE_TURN_ID,
                model=_usage_cases.SONNET,
                content_blocks=[_jsonl.text(_usage_cases.GREETING_TEXT)],
                usage=_claude.usage(input=100, output=_usage_cases.TOKEN_COUNT_TWO_HUNDRED),
            ),
            _claude.terminal_result(
                total_cost_usd=_usage_cases.TRAJECTORY_REPORTED_COST_USD,
                num_turns=1,
            ),
        )
        turn0 = _trajectory.parse_claude_trajectory(stdout).turns[0]
        self.assertEqual(turn0.cost_source, _usage_cases.ESTIMATED_COST_SOURCE)
        self.assertNotEqual(turn0.cost_usd, _usage_cases.TRAJECTORY_REPORTED_COST_USD)
        self.assertEqual(
            _metrics.parse_claude_usage(stdout).cost_usd,
            _usage_cases.TRAJECTORY_REPORTED_COST_USD,
        )

    def test_per_turn_estimates_sum_to_run_estimate(self) -> None:
        # The per-turn builder and the run aggregate share one estimator,
        # `claude_estimate_cost` on the `prices` owner, and pricing is linear
        # in token counts -- so the per-turn estimates must sum to the
        # run-level estimated cost.
        stdout = _jsonl.jsonl(
            _claude.assistant(
                id=_usage_cases.CLAUDE_TURN_ID,
                model=_usage_cases.SONNET,
                content_blocks=[_jsonl.text("a")],
                usage=_claude.usage(
                    input=100,
                    cache_write=_usage_cases.TOKEN_COUNT_TWO_HUNDRED,
                    cache_read=_usage_cases.TOKEN_COUNT_THREE_HUNDRED,
                    output=_usage_cases.TOKEN_COUNT_FIFTY,
                ),
            ),
            _claude.assistant(
                id="msg_1",
                model=_usage_cases.HAIKU,
                content_blocks=[_jsonl.text("b")],
                usage=_claude.usage(
                    input=_usage_cases.TOKEN_COUNT_FOUR_HUNDRED, output=_usage_cases.TOKEN_COUNT_TWENTY
                ),
            ),
        )
        run = _metrics.parse_claude_usage(stdout)
        turns = _trajectory.parse_claude_trajectory(stdout).turns
        self.assertEqual(run.cost_source, _usage_cases.ESTIMATED_COST_SOURCE)
        self.assertEqual(len(turns), 2)
        total = sum(turn.cost_usd for turn in turns)
        assert run.cost_usd is not None
        self.assertAlmostEqual(
            run.cost_usd,
            total,
            places=_usage_cases.COST_ASSERT_PLACES,
        )

    def test_no_usage_frames_yield_no_turns(self) -> None:
        # A stream whose assistant frames carry no usage block produces no
        # _records.TurnUsage, and the steps it does emit fall back to turn 0 by
        # first-seen message.id -- no exception.
        stdout = _jsonl.jsonl(
            _claude.assistant(id=_usage_cases.CLAUDE_TURN_ID, content_blocks=[_jsonl.text(_usage_cases.GREETING_TEXT)]),
        )
        trajectory = _trajectory.parse_claude_trajectory(stdout)
        self.assertEqual(trajectory.turns, ())
        self.assertEqual([step.turn for step in trajectory.steps], [0])


class ClaudeSettledTurnUsageTest(unittest.TestCase):
    """Per-turn output counts settled by the ``message_delta`` closing each message.

    A message's ``assistant`` frames repeat the usage it opened with; the
    ``message_delta`` its stream events close it with, named through the
    wrapper's ``api_message_id``, carries its final output count. Turn
    indices, models, and input and cache counts stay the ones the frames give.
    """

    def test_captured_turns_carry_final_counts(self) -> None:
        run, trajectory = _parsed(_capture.MAIN_RUN_STDOUT)
        self.assertEqual(
            [step.turn for step in trajectory.steps],
            [0, 0, 0, None, None, 1, None, 2],
        )
        self.assertEqual(
            [_settled_turn(turn) for turn in trajectory.turns],
            [
                (turn, _capture.MODEL, message.final, _usage_cases.UNKNOWN_COST_SOURCE)
                for turn, message in enumerate(_capture.MAIN_RUN_MESSAGES)
            ],
        )
        self.assertEqual(
            _capture.summed(_turn_counts(trajectory)),
            _capture.TokenCounts.parsed(run),
        )

    def test_captured_subagent_turns_settle(self) -> None:
        # What `modelUsage` reports beyond every printed count settles the
        # subagent's first message. The message closing it, printed only on
        # the hand-back, becomes a turn numbered after every stepped one and
        # carries its output count alone; the steps keep their indices.
        expected = [message.final for message in _SUBAGENT_RUN_PRINTED]
        expected.append(_capture.TokenCounts(0, 0, 0, _capture.SUBAGENT_RUN_HANDBACK.output_tokens))
        run, trajectory = _parsed(_capture.SUBAGENT_RUN_STDOUT)
        self.assertEqual(
            [step.turn for step in trajectory.steps],
            [0, None, 1, None, None, 2, None, 3],
        )
        self.assertEqual(
            [(turn.turn, turn.model, _capture.TokenCounts.parsed(turn)) for turn in trajectory.turns],
            [(index, _capture.MODEL, counted) for index, counted in enumerate(expected)],
        )
        self.assertEqual(_capture.TokenCounts.parsed(run), _capture.summed(expected))

    def test_each_turn_settles_under_its_own_model(self) -> None:
        # Each message_delta settles only the turn it names, priced from that
        # turn's own model, so the per-turn estimates still sum to the run's.
        stdout = _jsonl.jsonl(
            _claude.assistant(
                id=_usage_cases.CLAUDE_TURN_ID,
                model=_usage_cases.SONNET,
                content_blocks=[_jsonl.text("a")],
                usage=_claude.usage(
                    input=_usage_cases.CLAUDE_TURN_INPUT_TOKENS,
                    cache_write=_usage_cases.CLAUDE_TURN_CACHE_WRITE_TOKENS,
                    cache_read=_usage_cases.CLAUDE_TURN_CACHE_READ_TOKENS,
                    output=1,
                ),
            ),
            _claude.message_delta(_usage_cases.CLAUDE_TURN_ID, output_tokens=_usage_cases.CLAUDE_TURN_OUTPUT_TOKENS),
            _claude.assistant(
                id=_usage_cases.MESSAGE_FIXTURE_ID,
                model=_usage_cases.HAIKU,
                content_blocks=[_jsonl.text(_usage_cases.FINAL_OUTPUT)],
                usage=_claude.usage(input=_usage_cases.HAIKU_TURN_INPUT_TOKENS, output=1),
            ),
            _claude.message_delta(_usage_cases.MESSAGE_FIXTURE_ID, output_tokens=_usage_cases.HAIKU_TURN_OUTPUT_TOKENS),
        )
        run, trajectory = _parsed(stdout)
        self.assertEqual(
            [(turn.model, turn.output_tokens) for turn in trajectory.turns],
            [
                (_usage_cases.SONNET, _usage_cases.CLAUDE_TURN_OUTPUT_TOKENS),
                (_usage_cases.HAIKU, _usage_cases.HAIKU_TURN_OUTPUT_TOKENS),
            ],
        )
        sonnet_turn, haiku_turn = trajectory.turns
        _assertions.assert_cost(self, sonnet_turn, _pricing.sonnet_turn_cost(), places=_usage_cases.COST_ASSERT_PLACES)
        _assertions.assert_cost(self, haiku_turn, _pricing.haiku_turn_cost(), places=_usage_cases.COST_ASSERT_PLACES)
        self.assertEqual(
            (run.models, run.output_tokens, run.cost_source),
            (
                (_usage_cases.SONNET, _usage_cases.HAIKU),
                _usage_cases.CLAUDE_TURN_OUTPUT_TOKENS + _usage_cases.HAIKU_TURN_OUTPUT_TOKENS,
                _usage_cases.ESTIMATED_COST_SOURCE,
            ),
        )
        _assertions.assert_cost(
            self,
            run,
            _pricing.sonnet_turn_cost() + _pricing.haiku_turn_cost(),
            places=_usage_cases.COST_ASSERT_PLACES,
        )

    def test_several_open_messages_keep_starts(self) -> None:
        # `modelUsage` gives two open subagent messages a single total no
        # frame divides between them, so each keeps its start count; the
        # hand-back's output still counts, in a turn after every stepped one.
        stdout = _jsonl.jsonl(
            _subagent.lead_assistant(_usage_cases.SONNET),
            _claude.message_delta(_usage_cases.CLAUDE_TURN_ID, output_tokens=_usage_cases.TOKEN_COUNT_FIFTY),
            _subagent.subagent_assistant("msg_sub_a", _usage_cases.SONNET),
            _subagent.subagent_assistant("msg_sub_b", _usage_cases.SONNET),
            _subagent.handback(_usage_cases.TOOL_USE_A_ID, _usage_cases.SONNET, output=_usage_cases.TOKEN_COUNT_TWENTY),
            _claude.terminal_result(modelUsage={
                _usage_cases.SONNET: _subagent.model_totals(
                    input_tokens=_subagent.LEAD_INPUT_TOKENS + _subagent.SUBAGENT_INPUT_TOKENS * 3,
                    output_tokens=_usage_cases.TOKEN_COUNT_FIFTY + _usage_cases.TOKEN_COUNT_TWENTY + 7,
                ),
            }),
        )
        run, trajectory = _parsed(stdout)
        self.assertEqual(
            [(turn.turn, turn.output_tokens) for turn in trajectory.turns],
            [
                (0, _usage_cases.TOKEN_COUNT_FIFTY),
                (1, 1),
                (2, 1),
                (3, _usage_cases.TOKEN_COUNT_TWENTY),
            ],
        )
        self.assertEqual(
            run.output_tokens,
            _usage_cases.TOKEN_COUNT_FIFTY + _usage_cases.TOKEN_COUNT_TWENTY + 2,
        )

    def test_handbacks_count_once_per_invocation(self) -> None:
        # A resumed subagent returns under the agent id it had before, so a
        # hand-back counts once per call it answers: a second call's return
        # counts again, while a frame repeating a return does not.
        first_return = _subagent.handback(
            _usage_cases.TOOL_USE_A_ID,
            _usage_cases.SONNET,
            output=_usage_cases.TOKEN_COUNT_TWENTY,
        )
        stdout = _jsonl.jsonl(
            _subagent.lead_assistant(_usage_cases.SONNET),
            _claude.message_delta(_usage_cases.CLAUDE_TURN_ID, output_tokens=_usage_cases.TOKEN_COUNT_FIFTY),
            first_return,
            first_return,
            _subagent.handback(_usage_cases.TOOL_USE_B_ID, _usage_cases.SONNET, output=10),
        )
        run, trajectory = _parsed(stdout)
        self.assertEqual(
            [(turn.turn, turn.output_tokens) for turn in trajectory.turns],
            [(0, _usage_cases.TOKEN_COUNT_FIFTY), (1, _usage_cases.TOKEN_COUNT_TWENTY), (2, 10)],
        )
        self.assertEqual(run.output_tokens, _usage_cases.TOKEN_COUNT_FIFTY + _usage_cases.TOKEN_COUNT_TWENTY + 10)

    def test_streams_without_deltas_keep_frame_counts(self) -> None:
        # A stream printed without partial messages closes no message, so
        # every message keeps the count its last frame carries and neither a
        # hand-back nor `modelUsage` is read -- not even for a subagent on a
        # model of its own, whose `modelUsage` would otherwise settle it.
        cases = (
            (
                _jsonl.without_frames(_capture.SUBAGENT_RUN_STDOUT, _claude.STREAM_EVENT),
                [message.start for message in _SUBAGENT_RUN_PRINTED],
            ),
            (
                _jsonl.jsonl(
                    _subagent.lead_assistant(_usage_cases.SONNET),
                    _subagent.subagent_assistant("msg_sub_a", _usage_cases.HAIKU),
                    _subagent.handback(
                        _usage_cases.TOOL_USE_A_ID,
                        _usage_cases.HAIKU,
                        output=_usage_cases.TOKEN_COUNT_TWENTY,
                    ),
                    _claude.terminal_result(modelUsage={
                        _usage_cases.HAIKU: _subagent.model_totals(
                            input_tokens=_subagent.SUBAGENT_INPUT_TOKENS * 2,
                            output_tokens=_usage_cases.TOKEN_COUNT_TWENTY + 7,
                        ),
                    }),
                ),
                [
                    _capture.TokenCounts(_subagent.LEAD_INPUT_TOKENS, 0, 0, 1),
                    _capture.TokenCounts(_subagent.SUBAGENT_INPUT_TOKENS, 0, 0, 1),
                ],
            ),
        )
        for stdout, expected in cases:
            with self.subTest(expected=expected):
                run, trajectory = _parsed(stdout)
                self.assertEqual(_turn_counts(trajectory), expected)
                self.assertEqual(_capture.TokenCounts.parsed(run), _capture.summed(expected))

    def test_unattributable_frames_settle_nothing(self) -> None:
        # A message_delta settles a turn only when it names the turn's message
        # and carries an output count, and a tool result counts as a hand-back
        # only with a subagent's id and usage: a truncated delta, one naming no
        # message, one without an output count, one naming a message no
        # `assistant` frame printed, and tool results short of a hand-back
        # leave the run and its one turn as the frame counts them.
        stdout = _jsonl.stdout_lines(
            json.dumps(
                _claude.assistant(
                    id=_usage_cases.CLAUDE_TURN_ID,
                    model=_usage_cases.SONNET,
                    content_blocks=[_jsonl.text(_usage_cases.GREETING_TEXT)],
                    usage=_claude.usage(input=100, output=_usage_cases.TOKEN_COUNT_TWENTY),
                ),
            ),
            '{"type":"stream_event","event":{"type":"message_delta"',
            json.dumps(_claude.message_delta(output_tokens=_usage_cases.TOKEN_COUNT_TWO_HUNDRED)),
            json.dumps(_claude.message_delta(_usage_cases.CLAUDE_TURN_ID)),
            json.dumps(
                _claude.message_delta(
                    _usage_cases.MESSAGE_FIXTURE_ID,
                    output_tokens=_usage_cases.TOKEN_COUNT_TWO_HUNDRED,
                ),
            ),
            json.dumps(_subagent.tool_result_frame({"stdout": "ok"}, _usage_cases.TOOL_USE_A_ID)),
            json.dumps(
                _subagent.tool_result_frame(
                    {_usage_cases.USAGE_FIELD: _claude.usage(output=_usage_cases.TOKEN_COUNT_TWO_HUNDRED)},
                    _usage_cases.TOOL_USE_B_ID,
                ),
            ),
        )
        run, trajectory = _parsed(stdout)
        self.assertEqual(
            (run.input_tokens, run.output_tokens, run.turns),
            (100, _usage_cases.TOKEN_COUNT_TWENTY, 1),
        )
        self.assertEqual(
            [(turn.turn, turn.output_tokens) for turn in trajectory.turns],
            [(0, _usage_cases.TOKEN_COUNT_TWENTY)],
        )
