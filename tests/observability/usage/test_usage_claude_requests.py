# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Each Claude API message priced on its own: its writes at their reported lifetimes, its tier on its own prompt."""

import math
import unittest
from types import MappingProxyType

from orchestrator.observability.usage import (
    metrics as _metrics,
    protocol as _protocol,
    trajectory as _trajectory,
)
from tests.observability.usage import (
    usage_claude_events as _claude,
    usage_claude_request_events as _requests,
    usage_jsonl_helpers as _jsonl,
    usage_test_values as _usage_cases,
)

_HAIKU_FIVE_FIVE = "claude-haiku-5-5"
_PLACES = 9
# Per-million rates in Claude's page columns -- input, 5m writes, 1h writes, cache reads, output -- for Opus 4.7,
# Sonnet 4.6, and Haiku 5.5 up to and over its 100,000-token prompt threshold.
_OPUS_RATES = (5, 6.25, 10, 0.5, 25)
_SONNET_RATES = (3, 3.75, 6, 0.3, 15)
_HAIKU_RATES = (0.1, 0.125, 0.2, 0.01, 0.5)
_HAIKU_TIER_RATES = (0.5, 0.625, 1, 0.05, 2.5)

_AGGREGATE = "cache_creation_input_tokens"
_SPLIT = "cache_creation"
_FIVE_MINUTE = "ephemeral_5m_input_tokens"
_ONE_HOUR = "ephemeral_1h_input_tokens"
_INPUT_TOKENS = 100
_OUTPUT_TOKENS = 50
_ORDINARY = MappingProxyType({
    _usage_cases.INPUT_TOKENS_FIELD: _INPUT_TOKENS,
    "cache_read_input_tokens": 0,
    _usage_cases.OUTPUT_TOKENS_FIELD: _OUTPUT_TOKENS,
})
_EVERY_COUNTER = (
    _protocol.INPUT_TOKENS,
    _protocol.OUTPUT_TOKENS,
    _protocol.CACHE_READ_TOKENS,
    _protocol.CACHE_WRITE_TOKENS,
)

# A block's cache-write fields, the five-minute and one-hour writes it prices (None where it prices nothing), and the
# cache-write count it records.
_LIFETIME_CASES = (
    (
        "an aggregate beside its split",
        {_AGGREGATE: 1000, _SPLIT: {_FIVE_MINUTE: 600, _ONE_HOUR: 400}},
        (600, 400),
        1000,
    ),
    (
        "explicit zeros",
        {_AGGREGATE: 0, _SPLIT: {_FIVE_MINUTE: 0, _ONE_HOUR: 0}},
        (0, 0),
        0,
    ),
    ("a split naming one lifetime", {_AGGREGATE: 1000, _SPLIT: {_ONE_HOUR: 1000}}, (0, 1000), 1000),
    (
        "a negative lifetime",
        {_AGGREGATE: 1000, _SPLIT: {_FIVE_MINUTE: -600, _ONE_HOUR: 1000}},
        (0, 1000),
        1000,
    ),
    ("a split without its aggregate", {_SPLIT: {_FIVE_MINUTE: 600, _ONE_HOUR: 400}}, (600, 400), 1000),
    ("one lifetime without an aggregate", {_SPLIT: {_FIVE_MINUTE: 600}}, (600, 0), 600),
    ("a zero aggregate alone", {_AGGREGATE: 0}, (0, 0), 0),
    ("an aggregate alone", {_AGGREGATE: 1000}, None, 1000),
    ("a split short of its aggregate", {_AGGREGATE: 1000, _SPLIT: {_FIVE_MINUTE: 600}}, None, 1000),
    (
        "a split beyond its aggregate",
        {_AGGREGATE: 500, _SPLIT: {_FIVE_MINUTE: 400, _ONE_HOUR: 400}},
        None,
        500,
    ),
    (
        "a lifetime that is no count",
        {_AGGREGATE: 1000, _SPLIT: {_FIVE_MINUTE: "many", _ONE_HOUR: 400}},
        None,
        1000,
    ),
    ("a split that is no object", {_AGGREGATE: 1000, _SPLIT: [600, 400]}, None, 1000),
    (
        "a whole-number float",
        {_AGGREGATE: 1000, _SPLIT: {_FIVE_MINUTE: 600.0, _ONE_HOUR: 400}},
        (600, 400),
        1000,
    ),
    (
        "a fractional lifetime",
        {_AGGREGATE: 1000, _SPLIT: {_FIVE_MINUTE: 600.9, _ONE_HOUR: 400}},
        None,
        1000,
    ),
    (
        "an infinite lifetime",
        {_AGGREGATE: 1000, _SPLIT: {_FIVE_MINUTE: 0, _ONE_HOUR: math.inf}},
        None,
        1000,
    ),
    (
        "a lifetime spelled as a string",
        {_AGGREGATE: 1000, _SPLIT: {_FIVE_MINUTE: "600", _ONE_HOUR: 400}},
        None,
        1000,
    ),
    (
        "a split beside a zero aggregate",
        {_AGGREGATE: 0, _SPLIT: {_FIVE_MINUTE: 0, _ONE_HOUR: 1000}},
        None,
        0,
    ),
)

# Blocks holding a count no number can be -- named for it -- and the input and cache-write counts the run keeps.
_NON_FINITE_BLOCKS = (
    (
        "a lifetime spelled Infinity",
        {_AGGREGATE: 1000, _SPLIT: {_FIVE_MINUTE: 0, _ONE_HOUR: "Infinity"}},
        (100, 1000),
    ),
    (
        "an infinite aggregate",
        {_AGGREGATE: math.inf, _SPLIT: {_FIVE_MINUTE: 600, _ONE_HOUR: 400}},
        (100, 1000),
    ),
    ("an input count of NaN", {_usage_cases.INPUT_TOKENS_FIELD: math.nan, _AGGREGATE: 0}, (0, 0)),
)
_REPORTED_USD = 0.75

# Haiku 5.5 requests and the rates each pays: exactly 100,000 prompt tokens, one more with all but one of them cache
# traffic, and two small requests whose prompts add up past the threshold.
_HAIKU_REQUESTS = (
    ((1000, 0, 0, 99_000, 200), _HAIKU_RATES),
    ((1, 10_000, 0, 90_000, 200), _HAIKU_TIER_RATES),
    ((60_000, 0, 0, 0, 100), _HAIKU_RATES),
    ((60_000, 0, 0, 0, 100), _HAIKU_RATES),
)
_HAIKU_RUN = _jsonl.jsonl(*(
    _requests.request(f"msg_{position}", _HAIKU_FIVE_FIVE, request[0])
    for position, request in enumerate(_HAIKU_REQUESTS)
))
_LEAD_COUNTS = (*_requests.LEAD_COUNTS[:-1], _requests.LEAD_OUTPUT_TOKENS)
_HANDBACK_COUNTS = (0, 0, 0, 0, _requests.HANDBACK_OUTPUT_TOKENS)


def _priced(rates: tuple[float, ...], counts: tuple[int, ...]) -> float:
    charges = zip(rates, counts, strict=True)
    amount = sum(rate * count for rate, count in charges)
    return round(amount / _usage_cases.TOKENS_PER_MILLION, _PLACES)


def _costs(stdout: str) -> tuple[float | None, ...]:
    """The run's cost, then each turn's, each parsed on its own and rounded; None where one states no amount."""
    run_usage = _metrics.parse_claude_usage(stdout)
    trajectory = _trajectory.parse_claude_trajectory(stdout)
    return tuple(_rounded(usage.cost_usd) for usage in (run_usage, *trajectory.turns))


def _rounded(cost: float | None) -> float | None:
    return None if cost is None else round(cost, _PLACES)


# A hand-back run's cost, then its lead turn's and its hand-back turn's, on Haiku 5.5 and on Sonnet 4.6.
_HANDBACK_COSTS = (
    (_HAIKU_FIVE_FIVE, (None, _priced(_HAIKU_RATES, _LEAD_COUNTS), None)),
    (
        _usage_cases.SONNET,
        (
            _rounded(_priced(_SONNET_RATES, _LEAD_COUNTS) + _priced(_SONNET_RATES, _HANDBACK_COUNTS)),
            _priced(_SONNET_RATES, _LEAD_COUNTS),
            _priced(_SONNET_RATES, _HANDBACK_COUNTS),
        ),
    ),
)


class CacheWriteLifetimeTest(unittest.TestCase):
    """Every cache write is charged once, at the lifetime its usage block reports for it."""

    def test_writes_price_at_their_reported_lifetime(self) -> None:
        # The run and its one turn read a block alike, recording its aggregate
        # as the cache-write count wherever it reports one. A write the block
        # gives no lifetime -- a lone nonzero aggregate, what a short split
        # leaves over, or all of one its split exceeds or cannot be read --
        # leaves the estimate without an amount rather than priced at either
        # lifetime's rate; an explicit zero is priced like any other count.
        for label, writes, priced, written in _LIFETIME_CASES:
            with self.subTest(label):
                self.assertEqual(self._reading(writes), self._expected(priced, written))

    def test_non_finite_counts_keep_the_reported_cost(self) -> None:
        # A count no number can be reads as unreported rather than stopping the
        # parse, so the run keeps every count its block does state and the
        # cost the CLI reported beside them.
        for label, fields, kept in _NON_FINITE_BLOCKS:
            with self.subTest(label):
                self.assertEqual(
                    self._reported_reading(fields),
                    (kept, _usage_cases.REPORTED_COST_SOURCE, _REPORTED_USD),
                )

    def _reported_reading(self, fields: dict) -> tuple[object, ...]:
        stdout = _jsonl.jsonl(
            _claude.assistant(model=_usage_cases.SONNET, usage={**_ORDINARY, **fields}),
            _claude.terminal_result(total_cost_usd=_REPORTED_USD),
        )
        run_usage = _metrics.parse_claude_usage(stdout)
        counts = (run_usage.input_tokens, run_usage.cache_write_tokens)
        return counts, run_usage.cost_source, run_usage.cost_usd

    def _reading(self, writes: dict) -> tuple[object, ...]:
        frame = _claude.assistant(model=_usage_cases.OPUS_FOUR_SEVEN, usage={**_ORDINARY, **writes})
        stdout = _jsonl.jsonl(frame)
        run_usage = _metrics.parse_claude_usage(stdout)
        turn = _trajectory.parse_claude_trajectory(stdout).turns[0]
        return (
            (run_usage.cache_write_tokens, turn.cache_write_tokens),
            run_usage.token_evidence.observed,
            _costs(stdout),
        )

    def _expected(
        self,
        priced: tuple[int, int] | None,
        written: int,
    ) -> tuple[object, ...]:
        counts = None if priced is None else (_INPUT_TOKENS, *priced, 0, _OUTPUT_TOKENS)
        cost = None if counts is None else _priced(_OPUS_RATES, counts)
        return (written, written), _EVERY_COUNTER, (cost, cost)


class RequestTierTest(unittest.TestCase):
    """Haiku 5.5's rates follow each request's own prompt: its input, cache reads, and cache writes together."""

    def test_each_request_pays_its_own_tier(self) -> None:
        # A request of exactly 100,000 prompt tokens pays the base rates, and
        # one of 100,001 the higher ones on every class, its output included,
        # though all but one of its tokens are cache traffic. Small requests
        # whose prompts add up past the threshold each pay base rates, and the
        # run's estimate is its turns' estimates summed.
        expected = [_priced(rates, counts) for counts, rates in _HAIKU_REQUESTS]
        run_cost = round(sum(expected), _PLACES)
        self.assertEqual(_costs(_HAIKU_RUN), (run_cost, *expected))
        self.assertEqual(_metrics.parse_claude_usage(_HAIKU_RUN).cost_source, _usage_cases.ESTIMATED_COST_SOURCE)

    def test_conflicting_writes_size_no_prompt(self) -> None:
        # A one-hour split of 100,001 writes beside a zero aggregate cannot be
        # right on both counts, so the message's prompt is unknown and neither
        # of Haiku 5.5's tiers prices the run or its turn.
        usage = {
            _usage_cases.INPUT_TOKENS_FIELD: 1,
            "cache_read_input_tokens": 0,
            _usage_cases.OUTPUT_TOKENS_FIELD: 1,
            _AGGREGATE: 0,
            _SPLIT: {_FIVE_MINUTE: 0, _ONE_HOUR: 100_001},
        }
        stdout = _jsonl.jsonl(_claude.assistant(model=_HAIKU_FIVE_FIVE, usage=usage))
        self.assertEqual(_costs(stdout), (None, None))

    def test_unestablished_prompts_price_flat_rates(self) -> None:
        # A `result` total sums many requests, and a message reporting no
        # cache-read count or only one lifetime's writes has no known prompt:
        # on Haiku 5.5 each leaves the run with no amount, while Sonnet 4.6's
        # flat rates still price every count such a row holds.
        for model, source in (
            (_HAIKU_FIVE_FIVE, _usage_cases.UNKNOWN_COST_SOURCE),
            (_usage_cases.SONNET, _usage_cases.ESTIMATED_COST_SOURCE),
        ):
            for label, stdout in _requests.unestablished_runs(model):
                with self.subTest(label, model=model):
                    run_usage = _metrics.parse_claude_usage(stdout)
                    self.assertEqual(
                        (run_usage.cost_source, run_usage.cost_usd is None),
                        (source, model == _HAIKU_FIVE_FIVE),
                    )

    def test_handback_turn_prices_on_flat_rates(self) -> None:
        # The lead message is a request of known prompt, priced on either
        # model. The hand-back's turn observes its output count alone: Sonnet
        # 4.6 prices it at the output rate and the run sums both turns, while
        # Haiku 5.5 cannot tell which tier that output paid, so the turn and
        # the run state no amount.
        for model, costs in _HANDBACK_COSTS:
            with self.subTest(model=model):
                stdout = _requests.handback_run(model)
                handback_turn = _trajectory.parse_claude_trajectory(stdout).turns[-1]
                self.assertEqual(
                    (_costs(stdout), handback_turn.token_evidence.observed),
                    (costs, (_protocol.OUTPUT_TOKENS,)),
                )
