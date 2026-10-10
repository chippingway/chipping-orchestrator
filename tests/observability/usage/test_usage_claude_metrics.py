# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Focused provider usage parsing tests."""

import json
import unittest
from dataclasses import replace

from orchestrator.observability.usage import metrics as _metrics
from tests.observability.usage import (
    usage_assertions as _assertions,
    usage_claude_events as _claude,
    usage_claude_stream_capture as _capture,
    usage_jsonl_helpers as _jsonl,
    usage_test_values as _usage_cases,
)

_ASSISTANT_FRAME = "assistant"
_RESULT_FRAME = "result"


class ClaudeUsageAggregationTest(unittest.TestCase):
    """Synthetic ``claude -p --output-format stream-json`` runs.

    Frames sharing a ``message.id`` are one message, and with no
    ``message_delta`` closing it the last frame's usage is the message's;
    per-model totals roll up into the flattened ``_metrics.UsageMetrics``
    shape.
    """

    def test_extracts_tokens_model_and_estimates_cost(self) -> None:
        stdout = _jsonl.jsonl(
            _claude.system_init(session_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
            _claude.assistant(
                model=_usage_cases.SONNET,
                usage=_claude.usage(
                    input=100,
                    cache_write=1000,
                    cache_read=_usage_cases.TOKEN_COUNT_FIVE_THOUSAND,
                    output=_usage_cases.TOKEN_COUNT_TWO_HUNDRED,
                ),
            ),
            _claude.assistant(
                model=_usage_cases.SONNET,
                usage=_claude.usage(
                    input=_usage_cases.CLAUDE_FINAL_INPUT_TOKENS,
                    cache_write=_usage_cases.CLAUDE_FINAL_CACHE_WRITE_TOKENS,
                    cache_read=_usage_cases.CLAUDE_FINAL_CACHE_READ_TOKENS,
                    output=_usage_cases.CLAUDE_FINAL_OUTPUT_TOKENS,
                ),
            ),
            _claude.terminal_result(num_turns=3),
        )
        metrics = _metrics.parse_claude_usage(stdout)
        self.assertEqual(
            (
                metrics.backend,
                metrics.models,
                (
                    metrics.input_tokens,
                    metrics.output_tokens,
                    metrics.cache_read_tokens,
                    metrics.cache_write_tokens,
                ),
                metrics.cached_tokens,
                metrics.turns,
            ),
            (
                _usage_cases.CLAUDE,
                (_usage_cases.SONNET,),
                (
                    _usage_cases.CLAUDE_FINAL_INPUT_TOKENS,
                    _usage_cases.CLAUDE_FINAL_OUTPUT_TOKENS,
                    _usage_cases.CLAUDE_FINAL_CACHE_READ_TOKENS,
                    _usage_cases.CLAUDE_FINAL_CACHE_WRITE_TOKENS,
                ),
                0,
                3,
            ),
        )
        # sonnet rates: input=3, cw5m=3.75, cr=0.30, output=15 (per 1M)
        expected = (
            _usage_cases.CLAUDE_FINAL_INPUT_TOKENS * 3
            + _usage_cases.CLAUDE_FINAL_CACHE_WRITE_TOKENS * _usage_cases.PRICE_RATE_THREE_AND_THREE_QUARTERS
            + _usage_cases.CLAUDE_FINAL_CACHE_READ_TOKENS * _usage_cases.PRICE_RATE_THREE_TENTHS
            + _usage_cases.CLAUDE_FINAL_OUTPUT_TOKENS * _usage_cases.PRICE_RATE_FIFTEEN
        ) / _usage_cases.TOKENS_PER_MILLION
        self.assertEqual(metrics.cost_source, _usage_cases.ESTIMATED_COST_SOURCE)
        _assertions.assert_cost(self, metrics, expected, places=9)

    def test_cache_creation_keeps_ttl_buckets(self) -> None:
        # The structured form (``cache_creation.ephemeral_*_input_tokens``)
        # bills 5m and 1h cache writes at different rates; the parser must
        # keep them separate rather than collapse both onto the 5m bucket.
        stdout = _jsonl.jsonl(
            _claude.assistant(
                model=_usage_cases.OPUS_FOUR_SEVEN,
                usage=_claude.usage(
                    input=0,
                    cache_five_minute=_usage_cases.CLAUDE_FIVE_MINUTE_CACHE_TOKENS,
                    cache_one_hour=_usage_cases.CLAUDE_ONE_HOUR_CACHE_TOKENS,
                    output=100,
                ),
            ),
        )
        metrics = _metrics.parse_claude_usage(stdout)
        # opus-4-7 rates: input=5, cw5m=6.25, cw1h=10, cr=0.50, output=25
        expected = (
            _usage_cases.CLAUDE_FIVE_MINUTE_CACHE_TOKENS * _usage_cases.PRICE_RATE_SIX_AND_QUARTER
            + _usage_cases.CLAUDE_ONE_HOUR_CACHE_TOKENS * 10
            + 100 * _usage_cases.PRICE_RATE_TWENTY_FIVE
        ) / _usage_cases.TOKENS_PER_MILLION
        self.assertEqual(
            metrics.cache_write_tokens,
            _usage_cases.CLAUDE_COMBINED_CACHE_WRITE_TOKENS,
        )
        self.assertEqual(metrics.cost_source, _usage_cases.ESTIMATED_COST_SOURCE)
        assert metrics.cost_usd is not None
        self.assertAlmostEqual(metrics.cost_usd, expected, places=9)

    def test_reported_total_cost_overrides_estimate(self) -> None:
        # Even when we *could* compute an estimate, the agent's own
        # ``total_cost_usd`` on the result frame is authoritative -- it
        # already accounts for any pricing nuance we may have missed.
        stdout = _jsonl.jsonl(
            _claude.assistant(
                model=_usage_cases.SONNET, usage=_claude.usage(input=100, output=_usage_cases.TOKEN_COUNT_TWO_HUNDRED)
            ),
            _claude.terminal_result(
                total_cost_usd=_usage_cases.CLAUDE_REPORTED_COST_USD,
                num_turns=1,
            ),
        )
        metrics = _metrics.parse_claude_usage(stdout)
        self.assertEqual(metrics.cost_source, _usage_cases.REPORTED_COST_SOURCE)
        self.assertEqual(metrics.cost_usd, _usage_cases.CLAUDE_REPORTED_COST_USD)

    def test_multiple_models_sum_when_all_priced(self) -> None:
        stdout = _jsonl.jsonl(
            _claude.assistant(
                id="msg_a",
                model=_usage_cases.SONNET,
                usage=_claude.usage(input=100, output=_usage_cases.TOKEN_COUNT_FIFTY),
            ),
            _claude.assistant(
                id="msg_b",
                model=_usage_cases.HAIKU,
                usage=_claude.usage(input=_usage_cases.TOKEN_COUNT_TWO_HUNDRED, output=100),
            ),
        )
        metrics = _metrics.parse_claude_usage(stdout)
        self.assertEqual(set(metrics.models), {_usage_cases.SONNET, _usage_cases.HAIKU})
        self.assertEqual(metrics.input_tokens, _usage_cases.TOKEN_COUNT_THREE_HUNDRED)
        self.assertEqual(metrics.output_tokens, _usage_cases.COMBINED_OUTPUT_TOKENS)
        self.assertEqual(metrics.cost_source, _usage_cases.ESTIMATED_COST_SOURCE)
        # sonnet: input=3, output=15; haiku-3-5: input=0.80, output=4
        sonnet_cost = 100 * 3 + _usage_cases.TOKEN_COUNT_FIFTY * _usage_cases.PRICE_RATE_FIFTEEN
        haiku_cost = _usage_cases.TOKEN_COUNT_TWO_HUNDRED * _usage_cases.PRICE_RATE_FOUR_FIFTHS + 100 * 4
        expected = (sonnet_cost + haiku_cost) / _usage_cases.TOKENS_PER_MILLION
        assert metrics.cost_usd is not None
        self.assertAlmostEqual(metrics.cost_usd, expected, places=9)


class ClaudeCapturedUsageTest(unittest.TestCase):
    """Run totals parsed from the captured streams in ``usage_claude_stream_capture``.

    Every ``assistant`` frame repeats the usage its message opened with, so a
    message's output count is the one the ``message_delta`` closing it
    carries, joined through the wrapper's ``api_message_id``; its input and
    cache counts stay the ones its frames carry.
    """

    def test_run_output_is_the_cli_reported_total(self) -> None:
        metrics = _metrics.parse_claude_usage(_capture.MAIN_RUN_STDOUT)
        self.assertEqual(
            (
                _capture.TokenCounts.parsed(metrics),
                metrics.models,
                metrics.turns,
                metrics.cost_usd,
                metrics.cost_source,
            ),
            (
                _capture.MAIN_RUN_TOTALS,
                (_capture.MODEL,),
                _capture.MAIN_RUN_NUM_TURNS,
                _capture.MAIN_RUN_COST_USD,
                _usage_cases.REPORTED_COST_SOURCE,
            ),
        )

    def test_subagent_run_output_is_the_cli_total(self) -> None:
        # The hand-back's usage is that of the subagent's closing message,
        # which printed no frame, and what `modelUsage` reports beyond every
        # printed count is its first message's final output. Input and cache
        # counts stay the ones the `assistant` frames carry.
        frames = _capture.summed(
            message.start
            for message in (*_capture.SUBAGENT_RUN_LEAD_MESSAGES, *_capture.SUBAGENT_RUN_SUBAGENT_MESSAGES)
        )
        metrics = _metrics.parse_claude_usage(_capture.SUBAGENT_RUN_STDOUT)
        self.assertEqual(
            (_capture.TokenCounts.parsed(metrics), metrics.cost_usd, metrics.cost_source),
            (
                replace(frames, output_tokens=_capture.SUBAGENT_RUN_MODEL_TOTALS.output_tokens),
                _capture.SUBAGENT_RUN_COST_USD,
                _usage_cases.REPORTED_COST_SOURCE,
            ),
        )

    def test_unmatched_model_usage_keeps_starts(self) -> None:
        # Without `modelUsage`, or with input and cache counts showing it
        # covers usage the stream never printed, the subagent's first message
        # keeps its start count; the hand-back's output still counts.
        unmatched = (
            ("no result frame", _jsonl.without_frames(_capture.SUBAGENT_RUN_STDOUT, _RESULT_FRAME)),
            ("wider modelUsage", _capture.SUBAGENT_RUN_STDOUT.replace('"inputTokens":10,', '"inputTokens":12,')),
        )
        printed = _capture.summed([
            *(message.final for message in _capture.SUBAGENT_RUN_LEAD_MESSAGES),
            *(message.start for message in _capture.SUBAGENT_RUN_SUBAGENT_MESSAGES),
        ])
        expected = replace(printed, output_tokens=printed.output_tokens + _capture.SUBAGENT_RUN_HANDBACK.output_tokens)
        for label, unmatched_stdout in unmatched:
            with self.subTest(label):
                self.assertEqual(_capture.TokenCounts.parsed(_metrics.parse_claude_usage(unmatched_stdout)), expected)

    def test_estimate_prices_the_final_output_counts(self) -> None:
        # Repriced under a model with first-party rates, and cut of the
        # `result` frame whose reported cost would take precedence.
        repriced = _capture.MAIN_RUN_STDOUT.replace(_capture.MODEL, _usage_cases.OPUS_FOUR_SEVEN)
        metrics = _metrics.parse_claude_usage(_jsonl.without_frames(repriced, _RESULT_FRAME))
        totals = _capture.MAIN_RUN_TOTALS
        # opus-4-7 rates: input=5, cw5m=6.25, cr=0.50, output=25 (per 1M);
        # the flat cache-write count bills at the 5m rate.
        expected = (
            totals.input_tokens * 5
            + totals.cache_write_tokens * _usage_cases.PRICE_RATE_SIX_AND_QUARTER
            + totals.cache_read_tokens * 0.5
            + totals.output_tokens * _usage_cases.PRICE_RATE_TWENTY_FIVE
        ) / _usage_cases.TOKENS_PER_MILLION
        self.assertEqual(
            (_capture.TokenCounts.parsed(metrics), metrics.models, metrics.cost_source),
            (totals, (_usage_cases.OPUS_FOUR_SEVEN,), _usage_cases.ESTIMATED_COST_SOURCE),
        )
        _assertions.assert_cost(self, metrics, expected, places=_usage_cases.COST_ASSERT_PLACES)

    def test_streams_without_deltas_keep_fallbacks(self) -> None:
        # Without stream events, the start counts on a message's `assistant`
        # frames are all the run counts of it -- a subagent's hand-back and
        # `modelUsage` go unread -- and with the `result` frame alone left, its
        # `usage` is the run's.
        cases = (
            (
                _capture.MAIN_RUN_STDOUT,
                (_claude.STREAM_EVENT,),
                _capture.summed(message.start for message in _capture.MAIN_RUN_MESSAGES),
            ),
            (
                _capture.SUBAGENT_RUN_STDOUT,
                (_claude.STREAM_EVENT,),
                _capture.summed(
                    message.start
                    for message in (*_capture.SUBAGENT_RUN_LEAD_MESSAGES, *_capture.SUBAGENT_RUN_SUBAGENT_MESSAGES)
                ),
            ),
            (_capture.MAIN_RUN_STDOUT, (_claude.STREAM_EVENT, _ASSISTANT_FRAME), _capture.MAIN_RUN_TOTALS),
        )
        for captured, cut_frames, expected in cases:
            with self.subTest(expected=expected):
                metrics = _metrics.parse_claude_usage(_jsonl.without_frames(captured, *cut_frames))
                self.assertEqual(
                    (_capture.TokenCounts.parsed(metrics), metrics.cost_source),
                    (expected, _usage_cases.REPORTED_COST_SOURCE),
                )


class ClaudeUsageErrorTest(unittest.TestCase):
    """Synthetic ``claude -p --output-format stream-json`` runs.

    Frames sharing a ``message.id`` are one message, and with no
    ``message_delta`` closing it the last frame's usage is the message's;
    per-model totals roll up into the flattened ``_metrics.UsageMetrics``
    shape.
    """

    def test_unknown_model_yields_unknown_price(self) -> None:
        # Usage is present but no first-party rates match the SKU; we must
        # report unknown-price rather than guess at zero cost.
        stdout = _jsonl.jsonl(
            _claude.assistant(
                model=_usage_cases.UNKNOWN_MODEL,
                usage=_claude.usage(input=100, output=_usage_cases.TOKEN_COUNT_TWO_HUNDRED),
            ),
        )
        metrics = _metrics.parse_claude_usage(stdout)
        self.assertEqual(metrics.cost_source, _usage_cases.UNKNOWN_COST_SOURCE)
        self.assertIsNone(metrics.cost_usd)
        self.assertEqual(metrics.input_tokens, 100)
        self.assertEqual(metrics.output_tokens, _usage_cases.TOKEN_COUNT_TWO_HUNDRED)

    def test_no_usage_events_returns_no_usage(self) -> None:
        stdout = _jsonl.jsonl(
            _claude.system_init(),
            _claude.terminal_result(num_turns=0),
        )
        metrics = _metrics.parse_claude_usage(stdout)
        self.assertEqual(metrics.cost_source, "no-usage")
        self.assertIsNone(metrics.cost_usd)
        self.assertEqual(metrics.input_tokens, 0)
        self.assertEqual(metrics.output_tokens, 0)
        self.assertEqual(metrics.models, ())

    def test_malformed_lines_are_skipped(self) -> None:
        # A banner line, a partial flush, and an outright truncated JSON
        # frame must not poison the rest of the stream. Real claude runs
        # do occasionally splice progress text into stdout.
        good = json.dumps(
            _claude.assistant(
                model=_usage_cases.SONNET, usage=_claude.usage(input=10, output=_usage_cases.TOKEN_COUNT_TWENTY)
            )
        )
        stdout = _jsonl.stdout_lines(
            "starting claude...",
            '{"type":"assistant","message"',
            good,
            "",
            "  ",
            "not json either",
        )
        metrics = _metrics.parse_claude_usage(stdout)
        self.assertEqual(metrics.input_tokens, 10)
        self.assertEqual(metrics.output_tokens, _usage_cases.TOKEN_COUNT_TWENTY)
        self.assertEqual(metrics.cost_source, _usage_cases.ESTIMATED_COST_SOURCE)

    def test_empty_stdout(self) -> None:
        metrics = _metrics.parse_claude_usage("")
        self.assertEqual(metrics, _metrics.UsageMetrics(backend=_usage_cases.CLAUDE))
