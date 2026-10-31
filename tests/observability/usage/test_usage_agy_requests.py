# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Each Antigravity run priced on what it establishes: one mapped slug, its own steps, and one row's dates."""

import operator
import unittest
from datetime import date, datetime
from types import MappingProxyType

from orchestrator.observability.usage import (
    agy_events,
    agy_requests,
    cost_evidence as _cost,
    metrics as _metrics,
    price_catalogue,
)
from tests.observability.usage import usage_agy_stream_capture as _capture, usage_test_values as _usage_cases
from tests.support import agy_stream as _stream

# Input, cached input, and output tokens; and a page row's input, output, and cached-input rates.
_Counts = tuple[int, int, int]
_PageRow = tuple[float, float, float]

_TOKENS_PER_MILLION = 1_000_000
_VERIFIED_ON = (date.fromisoformat("2026-10-29"),)
_INPUT_FIELD = "input_tokens"

_ARGON_HIGH = "gemini-4-argon-high"
_FLASH_HIGH = "gemini-3.8-flash-high"
_ARGON = "gemini-4-argon"
_FLASH = "gemini-3.8-flash"
_EARLIER_FLASH = "gemini-3.6-flash"
# Each slug the CLI's documentation or its 1.4.10 model listing names for a
# Gemini API model, and that model.
_MAPPED = MappingProxyType({
    _ARGON_HIGH: _ARGON,
    "gemini-4-argon-medium": _ARGON,
    _FLASH_HIGH: _FLASH,
    _capture.MODEL: _FLASH,
    "gemini-3.8-flash-low": _FLASH,
    "gemini-3.6-flash-high": _EARLIER_FLASH,
    "gemini-3.6-flash-medium": _EARLIER_FLASH,
})
# Each model's page rows before its scheduled change and after it.
_ARGON_PAGE_ROWS = ((2, 10, 0.1), (4, 20, 0.2))
_FLASH_PAGE_ROWS = ((0.75, 3.75, 0.075), (1.5, 7.5, 0.15))
_PAGE_ROWS = MappingProxyType({_ARGON: _ARGON_PAGE_ROWS, _FLASH: _FLASH_PAGE_ROWS, _EARLIER_FLASH: _FLASH_PAGE_ROWS})
# Slugs the CLI lists for a deployment no Gemini API row is established for,
# models Antigravity serves from other providers, bare API IDs, and spellings
# near a mapped slug.
_UNMAPPED = (
    "gemini-3.7-flash-high",
    "gemini-3.7-flash-medium",
    "gemini-3.1-pro-high",
    "gemini-3.1-pro-low",
    "gemini-4-argon-low",
    "gemini-3.6-flash-low",
    _FLASH,
    _ARGON,
    _usage_cases.SONNET,
    "claude-opus-4-6-thinking",
    "gpt-oss-120b-medium",
    "gemini-3.8-flash-high[1m]",
    "GEMINI-3.8-FLASH-HIGH",
)
# Instants long before either scheduled change, and long after both.
_EARLIER = "2026-10-31T12:00:00+00:00"
_LATER = "2027-02-01T12:00:00+00:00"
# One step's counts, and the usage block reporting them.
_COUNTS = (1000, 200, 100)
_STEP_USAGE = MappingProxyType({
    _INPUT_FIELD: _COUNTS[0],
    "cache_read_tokens": _COUNTS[1],
    "output_tokens": _COUNTS[2],
})
_PRICED_STEP = _stream.step(1, usage=dict(_STEP_USAGE))
_ACTIVE_STEP = _stream.step(1, state=agy_events.ACTIVE, usage=dict(_STEP_USAGE))
_SUBAGENT = MappingProxyType({"subagents": [{"type_name": "research", "conversation_id": _stream.SESSION_ID}]})
_DELEGATING_STEP = _stream.step(2, kind=agy_events.TOOL, subagent_info=dict(_SUBAGENT))

# Each captured run, its completed response, and the counts that response reports.
_CAPTURED_RUNS = (
    (_capture.FRESH_RUN, _capture.FRESH_DONE, (6827, 0, 32)),
    (_capture.RESUMED_RUN, _capture.RESUMED_DONE, (7072, 0, 37)),
)
# The guide's run with a checkpoint, and its cached second turn: each with the
# slug it is priced as, its counts, and the page row they pay.
_GUIDE_RUNS = (
    ("\n".join(_capture.GUIDE_RUN), _ARGON_HIGH, (10418, 8113, 589), _ARGON_PAGE_ROWS[0]),
    (_capture.GUIDE_CACHED_STEP, _FLASH_HIGH, (278, 30214, 4), _FLASH_PAGE_ROWS[0]),
)
_ARGON_INIT = _stream.event(agy_events.INIT, model=_ARGON_HIGH)
_MIXED_LINES = (_ARGON_INIT, _stream.init_event(), _PRICED_STEP)
_MIXED_MODELS = (_ARGON_HIGH, _stream.MODEL)
# Spans around Gemini 4 Argon's change, each with the page row it pays, if any.
_ARGON_SPANS = (
    (("2026-11-30T09:59:59+00:00",), 0),
    (("2026-11-30T10:00:00+00:00",), None),
    (("2026-11-29T00:00:00+00:00", "2026-12-02T00:00:00+00:00"), None),
    (("2026-12-01T11:59:59+00:00",), None),
    (("2026-12-01T12:00:00+00:00",), 1),
    (("2026-12-01T21:00:00+09:00",), 1),
)
# Usage nothing prices: a subagent's handoff beside priced usage, a negative
# count, and a usage block reporting no count.
_UNSETTLED = (
    (_PRICED_STEP, _DELEGATING_STEP),
    (_stream.step(1, usage={**_STEP_USAGE, _INPUT_FIELD: -1}),),
    (_stream.step(1, usage={}),),
)


def _span(started: str = _EARLIER, ended: str | None = None) -> price_catalogue.UsageSpan:
    return price_catalogue.UsageSpan(datetime.fromisoformat(started), datetime.fromisoformat(ended or started))


def _usd(counts: _Counts, page_row: _PageRow) -> float:
    rates = (page_row[0], page_row[2], page_row[1])
    return sum(map(operator.mul, counts, rates)) / _TOKENS_PER_MILLION


def _run_on(slug: str, *lines: str) -> str:
    """A stream whose `init` names `slug`, followed by `lines`."""
    return "\n".join((_stream.event(agy_events.INIT, model=slug), *lines))


def _parse(
    stdout: str,
    span: price_catalogue.UsageSpan | None,
    fallback_model: str | None = None,
) -> _metrics.UsageMetrics:
    return _metrics.parse_agent_usage(_stream.BACKEND, stdout, fallback_model=fallback_model, span=span)


def _tokens(usage: _metrics.UsageMetrics) -> tuple[_Counts, int | None]:
    """The run's input, cache-read, and output counters, and the total its token evidence settles."""
    counters = (usage.input_tokens, usage.cache_read_tokens, usage.output_tokens)
    return counters, usage.token_evidence.total(usage.to_dict())


class AntigravityEstimateTest(unittest.TestCase):
    """A run on one mapped slug is priced at its Gemini API model's rates; anything less established stays unpriced."""

    def test_captured_runs_price_their_own_steps(self) -> None:
        # Each captured run's completed response, its frame repeated, is priced
        # once, its output already holding its thinking; the resume prices its
        # own step and none of the conversation total its `result` reports.
        for lines, done, counts in _CAPTURED_RUNS:
            with self.subTest(done=done):
                usage = _parse("\n".join((*lines, done)), _span())
                self.assertEqual((usage.models, usage.turns), ((_capture.MODEL,), 1))
                self.assertEqual(_tokens(usage), (counts, sum(counts)))
                self.assertEqual(usage.cost_source, _usage_cases.ESTIMATED_COST_SOURCE)
                self.assertAlmostEqual(usage.cost_usd, _usd(counts, _FLASH_PAGE_ROWS[0]))
                estimate = _cost.CostContribution(_cost.GEMINI_API_ESTIMATE, usage.cost_usd, _VERIFIED_ON)
                self.assertEqual(usage.cost_evidence, _cost.CostEvidence(_cost.COMPLETE, (estimate,)))

    def test_checkpoint_and_cache_reads_price(self) -> None:
        # The guide's run prices its checkpoint step beside its response, and
        # every cached token at the cached-input rate, apart from the input.
        for stdout, slug, counts, page_row in _GUIDE_RUNS:
            with self.subTest(slug=slug):
                usage = _parse(stdout, _span(), fallback_model=slug)
                self.assertEqual(_tokens(usage), (counts, sum(counts)))
                self.assertAlmostEqual(usage.cost_usd, _usd(counts, page_row))

    def test_mapped_slugs_price_at_model_rates(self) -> None:
        self.assertEqual(dict(agy_requests.API_MODELS), dict(_MAPPED))
        for slug, model in _MAPPED.items():
            for period, instant in enumerate((_EARLIER, _LATER)):
                with self.subTest(slug=slug, instant=instant):
                    usage = _parse(_run_on(slug, _PRICED_STEP), _span(instant))
                    self.assertAlmostEqual(usage.cost_usd, _usd(_COUNTS, _PAGE_ROWS[model][period]))

    def test_unestablished_attribution_stays_unpriced(self) -> None:
        runs = [(_run_on(slug, _PRICED_STEP), (slug,)) for slug in _UNMAPPED]
        runs.extend((("\n".join(_MIXED_LINES), _MIXED_MODELS), (_PRICED_STEP, ())))
        for stdout, models in runs:
            with self.subTest(models=models):
                usage = _parse(stdout, _span())
                self.assertEqual(usage.models, models)
                self._assert_unpriced(usage)

    def test_span_has_to_settle_one_row(self) -> None:
        # Gemini 4 Argon's rates change on 2026-12-01 in a time zone its page
        # does not name, so a span touching both dates in any zone -- UTC-12
        # through UTC+14 -- is unpriced, as is a run given no span at all.
        stdout = _run_on(_ARGON_HIGH, _PRICED_STEP)
        self._assert_unpriced(_parse(stdout, None))
        for instants, period in _ARGON_SPANS:
            with self.subTest(instants=instants):
                usage = _parse(stdout, _span(*instants))
                if period is None:
                    self._assert_unpriced(usage)
                else:
                    self.assertAlmostEqual(usage.cost_usd, _usd(_COUNTS, _ARGON_PAGE_ROWS[period]))

    def test_unsettled_usage_has_no_estimate(self) -> None:
        # No completed usage is no usage, however priceable the model, while
        # usage nothing settles a price for is unpriced.
        for stdout in ("", _run_on(_ARGON_HIGH), _run_on(_ARGON_HIGH, _ACTIVE_STEP)):
            with self.subTest(stdout=stdout):
                usage = _parse(stdout, _span(), fallback_model=_ARGON_HIGH)
                self.assertEqual((usage.cost_source, usage.cost_usd), (_cost.NO_USAGE_SOURCE, None))
        for lines in _UNSETTLED:
            with self.subTest(lines=lines):
                self._assert_unpriced(_parse(_run_on(_ARGON_HIGH, *lines), _span()))

    def _assert_unpriced(self, usage: _metrics.UsageMetrics) -> None:
        self.assertEqual((usage.cost_source, usage.cost_usd), (_usage_cases.UNKNOWN_COST_SOURCE, None))
        self.assertEqual(usage.cost_evidence, _cost.CostEvidence(_cost.INCOMPLETE))
