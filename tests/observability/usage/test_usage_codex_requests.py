# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Each Codex usage record priced on what it establishes: a write at a reported lifetime, a tier under its bound.

A record with no price states every reason that applies, each beside the model it was priced as, and a run keeps them
only where its cost is unpriced: a CLI-reported amount, a zero included, outranks the estimate and leaves none.
"""

import json
import unittest
from datetime import date
from types import MappingProxyType

from orchestrator.observability.usage import (
    codex_requests,
    cost_evidence as _cost,
    event_stream as _event_stream,
    metrics as _metrics,
    protocol as _protocol,
    unpriced as _unpriced,
)
from tests.observability.usage import (
    usage_codex_events as _codex,
    usage_codex_tool_events as _tool_events,
    usage_codex_usage_capture as _capture,
    usage_jsonl_helpers as _jsonl,
    usage_test_values as _usage_cases,
)

_INPUT = _protocol.INPUT
_CACHED = _protocol.CACHED
_OUTPUT = _protocol.OUTPUT
_THIRTY_MIN = _protocol.CACHE_WRITE_THIRTY_MIN
_TWELVE_HOUR = _protocol.CACHE_WRITE_TWELVE_HOUR
_UNKNOWN_LIFETIME = _protocol.CACHE_WRITE_UNKNOWN_LIFETIME
# The CLI's own spellings of the counts a usage block carries.
_INPUT_FIELD = _usage_cases.INPUT_TOKENS_FIELD
_CACHED_FIELD = "cached_input_tokens"
_WRITES_FIELD = "cache_write_input_tokens"
_PROVIDER_DETAILS = "input_tokens_details"

_GPT_FIVE_FIVE = _capture.GPT_FIVE_FIVE
_GPT_FIVE_SIX_SOL = _capture.GPT_FIVE_SIX_SOL
_GPT_FIVE_ONE_CODEX = "gpt-5.1-codex"
_GPT_FIVE_FOUR_MINI = "gpt-5.4-mini"
_UNKNOWN_MODEL = "gpt-5.7"
_GPT_SIX_ASTRA = "gpt-6-astra"
_GPT_FIVE_FIVE_PRO = "gpt-5.5-pro"
_THRESHOLD = 272_000
_PAST_THRESHOLD = _THRESHOLD + 1
_PLACES = 9
_UsageRow = codex_requests.CodexUsageRow
_VERIFIED_ON = (date.fromisoformat("2026-10-29"),)
_CAPTURED_INPUT = 12000

# GPT-5.6 Sol's page rates, its writes OpenAI's 1.25x and 2.5x of its input rate.
_SOL_INPUT_RATE = 4
_SOL_CACHED_RATE = 0.4
_SOL_OUTPUT_RATE = 20
_THIRTY_MIN_MULTIPLE = 1.25
_TWELVE_HOUR_MULTIPLE = 2.5
# Per-million rates by the class a token is billed as; the models before GPT-5.6 charge no write.
_RATES = MappingProxyType({
    _GPT_FIVE_FIVE: {_INPUT: 5, _CACHED: 0.5, _OUTPUT: 30},
    _GPT_FIVE_SIX_SOL: {
        _INPUT: _SOL_INPUT_RATE,
        _CACHED: _SOL_CACHED_RATE,
        _THIRTY_MIN: _SOL_INPUT_RATE * _THIRTY_MIN_MULTIPLE,
        _TWELVE_HOUR: _SOL_INPUT_RATE * _TWELVE_HOUR_MULTIPLE,
        _OUTPUT: _SOL_OUTPUT_RATE,
    },
    _GPT_FIVE_ONE_CODEX: {_INPUT: 1.25, _CACHED: 0.125, _OUTPUT: 10},
    _GPT_FIVE_FOUR_MINI: {_INPUT: 0.75, _CACHED: 0.075, _OUTPUT: 4.5},
})

# OpenAI's own example: 12,000 input tokens holding 4,000 cache reads and 7,000 writes split 3,000 / 4,000 by
# lifetime, so 1,000 ordinary.
_EXAMPLE = MappingProxyType({
    _INPUT: _CAPTURED_INPUT,
    _CACHED: 4000,
    _THIRTY_MIN: 3000,
    _TWELVE_HOUR: 4000,
    _UNKNOWN_LIFETIME: 0,
    _OUTPUT: 500,
})
# OpenAI's worked example prices that input at $0.01515 where input costs $1 and cached input $0.10 per million;
# GPT-5.6 Sol's $4 and $0.40 are four times those, and its 500 output tokens cost $0.01.
_GUIDE_INPUT_COST_USD = 0.01515
_EXAMPLE_OUTPUT_COST_USD = 0.01
_LIFETIMES_ALONE = MappingProxyType({
    token_class: count for token_class, count in _EXAMPLE.items() if token_class != _UNKNOWN_LIFETIME
})

# The resumed capture's block also counts the request of the invocation it resumed.
_RESUMED_PROVIDER_USAGE = (*_capture.ONE_REQUEST_PROVIDER_USAGE, *_capture.RESUMED_PROVIDER_USAGE)
_CAPTURES = (
    (_capture.ONE_REQUEST_STDOUT, _capture.ONE_REQUEST_PROVIDER_USAGE),
    (_capture.TWO_REQUEST_STDOUT, _capture.TWO_REQUEST_PROVIDER_USAGE),
    (_capture.RESUMED_STDOUT, _RESUMED_PROVIDER_USAGE),
    (_capture.UNREPORTED_WRITES_STDOUT, _capture.UNREPORTED_WRITES_PROVIDER_USAGE),
)

# Why a record has no price, as the reasons it names.
_MISSING_PRICE = (_unpriced.MISSING_MODEL_PRICE,)
_INDETERMINATE_TIER = (_unpriced.INDETERMINATE_REQUEST_TIER,)
_MISSING_COUNT = (_unpriced.MISSING_CACHE_WRITE_COUNT,)
_MISSING_LIFETIME = (_unpriced.MISSING_CACHE_WRITE_LIFETIME,)
_INVALID = (_unpriced.INVALID_TOKEN_COUNTS,)

# A captured stream, the model it is priced as, and the tokens it bills by class, or the reasons it has no price.
_CAPTURED_PRICES = (
    (
        "a single request's writes are ordinary input before GPT-5.6",
        _capture.ONE_REQUEST_STDOUT,
        _GPT_FIVE_FIVE,
        {_INPUT: 8000, _CACHED: 4000, _OUTPUT: 500},
    ),
    ("a write of no lifetime on GPT-5.6", _capture.ONE_REQUEST_STDOUT, _GPT_FIVE_SIX_SOL, _MISSING_LIFETIME),
    (
        "two requests under the threshold that sum past it",
        _capture.TWO_REQUEST_STDOUT,
        _GPT_FIVE_FIVE,
        _INDETERMINATE_TIER,
    ),
    (
        "the same two requests on a flat-rate model",
        _capture.TWO_REQUEST_STDOUT,
        _GPT_FIVE_ONE_CODEX,
        {_INPUT: 71000, _CACHED: 330000, _OUTPUT: 100},
    ),
    (
        "a resumed thread whose whole input bounds every request",
        _capture.RESUMED_STDOUT,
        _GPT_FIVE_FIVE,
        {_INPUT: 10000, _CACHED: 15000, _OUTPUT: 570},
    ),
    (
        "the zero the CLI prints for a write count it was not given",
        _capture.UNREPORTED_WRITES_STDOUT,
        _GPT_FIVE_SIX_SOL,
        _MISSING_COUNT,
    ),
    (
        "the same zero before GPT-5.6",
        _capture.UNREPORTED_WRITES_STDOUT,
        _GPT_FIVE_FIVE,
        {_INPUT: 6952, _CACHED: 2048, _OUTPUT: 300},
    ),
    (
        "codex-cli 0.148.0's zero write count on GPT-5.6",
        _tool_events.TOOL_RUN_STDOUT,
        _GPT_FIVE_SIX_SOL,
        _MISSING_COUNT,
    ),
    (
        "codex-cli 0.148.0's run before GPT-5.6",
        _tool_events.TOOL_RUN_STDOUT,
        _GPT_FIVE_FIVE,
        {_INPUT: 11657, _CACHED: 94464, _OUTPUT: 634},
    ),
)


def _frame(model: str, usage: dict[str, int], output: int = 1000) -> dict:
    return {
        _usage_cases.TYPE_FIELD: "turn_complete",
        _usage_cases.MODEL_FIELD: model,
        _usage_cases.USAGE_FIELD: {**usage, _usage_cases.OUTPUT_TOKENS_FIELD: output},
    }


_SMALL_FRAME = _frame(_GPT_FIVE_FIVE, {_INPUT_FIELD: 100000, _CACHED_FIELD: 50000})
# What the observed GPT-6 Astra runs printed: a cumulative input past the tier, and the CLI's zero write count.
_ASTRA_FRAME = _frame(_GPT_SIX_ASTRA, {_INPUT_FIELD: _PAST_THRESHOLD, _CACHED_FIELD: 200000, _WRITES_FIELD: 0})
_ASTRA_REASONS = (_unpriced.INDETERMINATE_REQUEST_TIER, _unpriced.MISSING_CACHE_WRITE_COUNT)
# The frames a stream printed, priced as the model the last one names, and the tokens the run bills, or the reasons
# it has no price.
_FRAME_PRICES = (
    ("a frame printed twice", (_SMALL_FRAME, _SMALL_FRAME), {_INPUT: 50000, _CACHED: 50000, _OUTPUT: 1000}),
    (
        "cumulative frames whose difference stays under the threshold",
        (_frame(_GPT_FIVE_FIVE, {_INPUT_FIELD: 150000}), _frame(_GPT_FIVE_FIVE, {_INPUT_FIELD: 300000})),
        _INDETERMINATE_TIER,
    ),
    (
        "the same frames on a flat-rate model",
        (_frame(_GPT_FIVE_FOUR_MINI, {_INPUT_FIELD: 150000}), _frame(_GPT_FIVE_FOUR_MINI, {_INPUT_FIELD: 300000})),
        {_INPUT: 300000, _OUTPUT: 1000},
    ),
    (
        "a run at the threshold",
        (_frame(_GPT_FIVE_FIVE, {_INPUT_FIELD: _THRESHOLD}),),
        {_INPUT: _THRESHOLD, _OUTPUT: 1000},
    ),
    ("a run past the threshold", (_frame(_GPT_FIVE_FIVE, {_INPUT_FIELD: _PAST_THRESHOLD}),), _INDETERMINATE_TIER),
    (
        "a pro run past the threshold",
        (_frame(_GPT_FIVE_FIVE_PRO, {_INPUT_FIELD: _PAST_THRESHOLD}),),
        _INDETERMINATE_TIER,
    ),
    ("a GPT-5.4 run past the threshold", (_frame("gpt-5.4", {_INPUT_FIELD: _PAST_THRESHOLD}),), _INDETERMINATE_TIER),
    ("the observed GPT-6 Astra run", (_ASTRA_FRAME,), _ASTRA_REASONS),
    (
        "positive writes past the threshold on GPT-5.6",
        (_frame(_GPT_FIVE_SIX_SOL, {_INPUT_FIELD: _PAST_THRESHOLD, _WRITES_FIELD: 3000}),),
        (_unpriced.INDETERMINATE_REQUEST_TIER, _unpriced.MISSING_CACHE_WRITE_LIFETIME),
    ),
    (
        "cached input on a model publishing no cached rate",
        (_frame(_GPT_FIVE_FIVE_PRO, {_INPUT_FIELD: 10000, _CACHED_FIELD: 4000}),),
        (_unpriced.UNRATED_TOKEN_CLASS,),
    ),
    (
        "positive writes before GPT-5.6",
        (_frame(_GPT_FIVE_FIVE, {_INPUT_FIELD: 10000, _CACHED_FIELD: 4000, _WRITES_FIELD: 3000}),),
        {_INPUT: 6000, _CACHED: 4000, _OUTPUT: 1000},
    ),
    (
        "positive writes on GPT-5.6",
        (_frame(_GPT_FIVE_SIX_SOL, {_INPUT_FIELD: 10000, _CACHED_FIELD: 4000, _WRITES_FIELD: 3000}),),
        _MISSING_LIFETIME,
    ),
    (
        "no write field on GPT-5.6",
        (_frame(_GPT_FIVE_SIX_SOL, {_INPUT_FIELD: 10000, _CACHED_FIELD: 4000}),),
        _MISSING_COUNT,
    ),
    (
        "reads and writes past the input",
        (_frame(_GPT_FIVE_FIVE, {_INPUT_FIELD: 10000, _CACHED_FIELD: 8000, _WRITES_FIELD: 3000}),),
        _INVALID,
    ),
    (
        "a negative write count before GPT-5.6",
        (_frame(_GPT_FIVE_FIVE, {_INPUT_FIELD: 10000, _CACHED_FIELD: 4000, _WRITES_FIELD: -1}),),
        _INVALID,
    ),
    (
        "a negative write count on a flat-rate model",
        (_frame(_GPT_FIVE_ONE_CODEX, {_INPUT_FIELD: 10000, _CACHED_FIELD: 4000, _WRITES_FIELD: -1}),),
        _INVALID,
    ),
    ("an unknown model", (_frame(_UNKNOWN_MODEL, {_INPUT_FIELD: 10000}),), _MISSING_PRICE),
)

# A record, and the tokens it bills by class, or the reasons it has no price.
_ROW_PRICES = (
    (
        "both lifetimes",
        _UsageRow(_GPT_FIVE_SIX_SOL, dict(_EXAMPLE)),
        {_INPUT: 1000, _CACHED: 4000, _THIRTY_MIN: 3000, _TWELVE_HOUR: 4000, _OUTPUT: 500},
    ),
    (
        "30-minute writes alone",
        _UsageRow(
            _GPT_FIVE_SIX_SOL,
            {_INPUT: _CAPTURED_INPUT, _CACHED: 4000, _THIRTY_MIN: 7000, _UNKNOWN_LIFETIME: 0, _OUTPUT: 500},
        ),
        {_INPUT: 1000, _CACHED: 4000, _THIRTY_MIN: 7000, _OUTPUT: 500},
    ),
    (
        "12-hour writes alone",
        _UsageRow(_GPT_FIVE_SIX_SOL, {_INPUT: _CAPTURED_INPUT, _TWELVE_HOUR: 7000, _UNKNOWN_LIFETIME: 0, _OUTPUT: 500}),
        {_INPUT: 5000, _TWELVE_HOUR: 7000, _OUTPUT: 500},
    ),
    (
        "nothing written",
        _UsageRow(_GPT_FIVE_SIX_SOL, {_INPUT: _CAPTURED_INPUT, _CACHED: 4000, _UNKNOWN_LIFETIME: 0, _OUTPUT: 500}),
        {_INPUT: 8000, _CACHED: 4000, _OUTPUT: 500},
    ),
    (
        "both lifetimes before GPT-5.6",
        _UsageRow(_GPT_FIVE_FIVE, dict(_EXAMPLE)),
        {_INPUT: 8000, _CACHED: 4000, _OUTPUT: 500},
    ),
    (
        "lifetimes short of a whole write count",
        _UsageRow(_GPT_FIVE_SIX_SOL, dict(_LIFETIMES_ALONE)),
        _MISSING_COUNT,
    ),
    (
        "a write of unknown lifetime",
        _UsageRow(_GPT_FIVE_SIX_SOL, {**_EXAMPLE, _UNKNOWN_LIFETIME: 1000}),
        _MISSING_LIFETIME,
    ),
    ("lifetimes past the input", _UsageRow(_GPT_FIVE_SIX_SOL, {**_EXAMPLE, _INPUT: 10000}), _INVALID),
    ("lifetimes past the input before GPT-5.6", _UsageRow(_GPT_FIVE_FIVE, {**_EXAMPLE, _INPUT: 10000}), _INVALID),
    (
        "a negative count",
        _UsageRow(_GPT_FIVE_FIVE, {_INPUT: _CAPTURED_INPUT, _CACHED: -4000, _OUTPUT: 500}),
        _INVALID,
    ),
    (
        "a record at the threshold",
        _UsageRow(_GPT_FIVE_SIX_SOL, {_INPUT: _THRESHOLD, _UNKNOWN_LIFETIME: 0, _OUTPUT: 500}),
        {_INPUT: _THRESHOLD, _OUTPUT: 500},
    ),
    (
        "a record past the threshold",
        _UsageRow(_GPT_FIVE_SIX_SOL, {_INPUT: _PAST_THRESHOLD, _UNKNOWN_LIFETIME: 0}),
        _INDETERMINATE_TIER,
    ),
    (
        "a record past the threshold short of a whole write count",
        _UsageRow(_GPT_FIVE_SIX_SOL, {_INPUT: _PAST_THRESHOLD, _OUTPUT: 500}),
        (_unpriced.INDETERMINATE_REQUEST_TIER, _unpriced.MISSING_CACHE_WRITE_COUNT),
    ),
    ("a tiered record reporting no input", _UsageRow(_GPT_FIVE_FIVE, {_OUTPUT: 500}), _INDETERMINATE_TIER),
    ("an unknown model", _UsageRow(_UNKNOWN_MODEL, {_INPUT: _CAPTURED_INPUT, _OUTPUT: 500}), _MISSING_PRICE),
)


def _amount(model: str, billed: dict[str, int]) -> float:
    rates = _RATES[model]
    charges = (rates[token_class] * count for token_class, count in billed.items())
    return sum(charges) / _usage_cases.TOKENS_PER_MILLION


def _provider_totals(provider_usage: tuple[dict, ...]) -> tuple[int, int, int]:
    """The input, cached, and output tokens the provider reported over every request, summed."""
    return (
        sum(usage[_INPUT_FIELD] for usage in provider_usage),
        sum(usage[_PROVIDER_DETAILS]["cached_tokens"] for usage in provider_usage),
        sum(usage[_usage_cases.OUTPUT_TOKENS_FIELD] for usage in provider_usage),
    )


def _assert_priced(
    test_case: unittest.TestCase,
    metrics: _metrics.UsageMetrics,
    model: str,
    answer: dict[str, int] | tuple[str, ...],
) -> None:
    """`metrics` is an estimate of what `answer` bills on OpenAI's basis, or unpriced for each reason it names."""
    cost = metrics.cost_evidence
    if isinstance(answer, tuple):
        observed = (cost.cost_source, cost.complete_usd, cost.contributions)
        test_case.assertEqual(observed, (_usage_cases.UNKNOWN_COST_SOURCE, None, ()))
        named = tuple(sorted(_unpriced.UnpricedReason(model, reason) for reason in answer))
        test_case.assertEqual(metrics.unpriced_reasons, named)
        return
    test_case.assertEqual(
        (cost.cost_source, cost.basis, cost.contributions[0].rates_verified_on),
        (_usage_cases.ESTIMATED_COST_SOURCE, _cost.OPENAI_API_ESTIMATE, _VERIFIED_ON),
    )
    test_case.assertAlmostEqual(cost.complete_usd, _amount(model, answer), places=_PLACES)
    test_case.assertEqual(metrics.unpriced_reasons, ())


class CodexCapturedUsageTest(unittest.TestCase):
    """Captured `codex exec --json` streams: what each usage block sums, and what that lets an estimate price."""

    def test_counters_sum_the_requests_a_block_covers(self) -> None:
        for stdout, provider_usage in _CAPTURES:
            with self.subTest(stdout=stdout.splitlines()[0]):
                metrics = _metrics.parse_codex_usage(stdout, fallback_model=_GPT_FIVE_FIVE)
                counted = (metrics.input_tokens, metrics.cached_tokens, metrics.output_tokens)
                self.assertEqual(counted, _provider_totals(provider_usage))
                self.assertEqual(
                    (metrics.cache_read_tokens, metrics.cache_write_tokens, metrics.models),
                    (0, 0, (_GPT_FIVE_FIVE,)),
                )
                self.assertEqual(
                    metrics.token_evidence.to_dict(),
                    {"observed": ["input_tokens", "output_tokens", "cached_tokens"], "cache_overlap": "within-input"},
                )

    def test_runs_price_what_their_block_establishes(self) -> None:
        for description, stdout, model, billed in _CAPTURED_PRICES:
            with self.subTest(description):
                metrics = _metrics.parse_codex_usage(stdout, fallback_model=model)
                _assert_priced(self, metrics, model, billed)

    def test_reported_cost_outranks_an_unpriced_block(self) -> None:
        # The block would be unpriced on its own -- a write of no lifetime on
        # GPT-5.6, and the observed GPT-6 Astra run -- but the CLI's amount, a
        # zero included, is the run's cost, so no reason stands beside it.
        for stdout, model in (
            (_capture.ONE_REQUEST_STDOUT, _GPT_FIVE_SIX_SOL),
            (_jsonl.jsonl(_ASTRA_FRAME), _GPT_SIX_ASTRA),
        ):
            for reported in (0, _usage_cases.CODEX_REPORTED_COST_USD):
                with self.subTest(model=model, reported=reported):
                    report = json.dumps(_codex.task_complete(total_cost_usd=reported))
                    metrics = _metrics.parse_codex_usage(_jsonl.stdout_lines(stdout, report), fallback_model=model)
                    self.assertEqual(
                        (metrics.cost_source, metrics.cost_usd, metrics.cost_evidence.basis),
                        (_usage_cases.REPORTED_COST_SOURCE, reported, _cost.CLI_REPORTED),
                    )
                    self.assertEqual(metrics.unpriced_reasons, ())
                    self.assertNotIn(_unpriced.UNPRICED_REASONS, metrics.to_dict())


class CodexUsageFramesTest(unittest.TestCase):
    """A run is priced on its last record alone, so no frame difference or repetition sizes or charges a request."""

    def test_frames_price_their_last_record_once(self) -> None:
        for description, frames, billed in _FRAME_PRICES:
            with self.subTest(description):
                metrics = _metrics.parse_codex_usage(_jsonl.jsonl(*frames))
                last = frames[-1]
                self.assertEqual(metrics.input_tokens, last[_usage_cases.USAGE_FIELD][_INPUT_FIELD])
                _assert_priced(self, metrics, last[_usage_cases.MODEL_FIELD], billed)

    def test_a_run_counting_no_tokens_has_no_usage(self) -> None:
        for stdout in ("", _jsonl.jsonl(_codex.turn_complete(model=_GPT_FIVE_SIX_SOL, cache_write=0))):
            with self.subTest(stdout=stdout):
                metrics = _metrics.parse_codex_usage(stdout)
                self.assertEqual(
                    (metrics.cost_source, metrics.cost_usd, metrics.cost_evidence.completeness),
                    (_cost.NO_USAGE_SOURCE, None, _cost.NO_USAGE),
                )


class CodexUsageRowTest(unittest.TestCase):
    """The estimate one record's counts establish, each cache write at its lifetime's rate and charged once."""

    def test_records_price_each_write_at_its_lifetime(self) -> None:
        for description, row, billed in _ROW_PRICES:
            with self.subTest(description):
                _assert_priced(self, self._row_metrics(row), row.model, billed)

    def test_lifetimes_match_openai_worked_example(self) -> None:
        # The 7,000-token aggregate is never charged beside its two parts.
        estimate = _UsageRow(_GPT_FIVE_SIX_SOL, dict(_EXAMPLE)).price().estimate
        assert estimate is not None
        expected = _GUIDE_INPUT_COST_USD * _SOL_INPUT_RATE + _EXAMPLE_OUTPUT_COST_USD
        self.assertAlmostEqual(estimate.amount_usd, expected, places=_PLACES)

    def _row_metrics(self, row: codex_requests.CodexUsageRow) -> _metrics.UsageMetrics:
        """A run whose one record is `row`, its cost selected with no CLI-reported amount beside the estimate."""
        pricing = row.price()
        metrics = _metrics.UsageMetrics(backend=_protocol.CODEX)
        metrics.apply_cost(_event_stream.select_cost(None, pricing.estimate, has_usage=True), pricing.unpriced)
        return metrics
