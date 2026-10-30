# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The days a usage figure spans and the height each stack over them reaches."""
from __future__ import annotations

import unittest
from datetime import date

from orchestrator.observability.dashboard.charts import usage_bands, usage_series

_YEAR = 2026

_DAY = date(_YEAR, 5, 1)

_NEXT_DAY = date(_YEAR, 5, 2)

_CLAUDE = "claude"

_CODEX = "codex"

_CLAUDE_TOKENS = 1_200.0

_CODEX_TOKENS = 600.0

_INPUT_TOKENS = 1_000.0

_OUTPUT_TOKENS = 500.0

_CACHE_TOKENS = 400.0

_COST_USD = 1.5


def _rolled_up_day() -> usage_bands.DailyTokenValues:
    """One day's buckets, as the roll-up would hand them over."""
    return {
        _DAY: {
            usage_bands.INPUT_BAND: _INPUT_TOKENS,
            usage_bands.OUTPUT_BAND: _OUTPUT_TOKENS,
            usage_bands.CACHE_BAND: _CACHE_TOKENS,
            usage_bands.COST_BAND: _COST_USD,
        },
    }


class DayAxisTest(unittest.TestCase):
    """Every day a band is drawn for is a day the axis carries."""

    def test_the_axis_is_the_day_span_as_a_list(self) -> None:
        self.assertEqual(usage_series.date_axis((_DAY, _NEXT_DAY)), [_DAY, _NEXT_DAY])

    def test_a_backend_only_day_gets_a_bucket(self) -> None:
        # The two reads are windowed alike but grouped differently, so a day
        # the per-backend one holds alone would otherwise have its stack drawn
        # past the end of the axis rather than at its own date.
        daily = _rolled_up_day()
        usage_series.ensure_backend_days(
            daily, usage_bands.BackendDailyTokens({_NEXT_DAY: {_CLAUDE: _CLAUDE_TOKENS}}, {_NEXT_DAY: 0}),
        )
        self.assertEqual(sorted(daily), [_DAY, _NEXT_DAY])
        self.assertEqual(daily[_NEXT_DAY], usage_bands.empty_token_bucket())

    def test_a_day_already_rolled_up_keeps_its_bands(self) -> None:
        daily = _rolled_up_day()
        usage_series.ensure_backend_days(
            daily, usage_bands.BackendDailyTokens({_DAY: {_CLAUDE: _CLAUDE_TOKENS}}, {_DAY: 0}),
        )
        self.assertEqual(daily, _rolled_up_day())

    def test_backends_are_named_in_a_stable_order(self) -> None:
        # The order is the legend's order and the color each backend is drawn
        # in is picked off its position, so the same window has to come back
        # the same way however the days it spans are keyed.
        names = usage_series.backend_names(usage_bands.BackendDailyTokens(
            {
                _NEXT_DAY: {_CODEX: _CODEX_TOKENS},
                _DAY: {_CLAUDE: _CLAUDE_TOKENS, _CODEX: _CODEX_TOKENS},
            },
            {},
        ))
        self.assertEqual(names, [_CLAUDE, _CODEX])


class StackTotalTest(unittest.TestCase):
    """A day's stack is as tall as the mode that drew it says."""

    def test_a_backend_stack_adds_up_its_backends(self) -> None:
        totals = usage_series.usage_stack_totals(
            (_DAY,),
            _rolled_up_day(),
            backend_rows_by_day=usage_bands.BackendDailyTokens(
                {_DAY: {_CLAUDE: _CLAUDE_TOKENS, _CODEX: _CODEX_TOKENS}},
                {_DAY: 0},
            ),
            mode=usage_bands.BACKEND_MODE,
        )
        self.assertEqual(totals, [_CLAUDE_TOKENS + _CODEX_TOKENS])

    def test_a_token_type_stack_adds_up_its_bands(self) -> None:
        totals = usage_series.usage_stack_totals(
            (_DAY,),
            _rolled_up_day(),
            backend_rows_by_day=None,
            mode="type",
        )
        self.assertEqual(
            totals, [_INPUT_TOKENS + _OUTPUT_TOKENS + _CACHE_TOKENS],
        )

    def test_backend_mode_with_no_rows_uses_bands(self) -> None:
        # A window the per-backend read came back empty for still draws the
        # token-type stack, so the axis has to be scaled to what is on it.
        totals = usage_series.usage_stack_totals(
            (_DAY,),
            _rolled_up_day(),
            backend_rows_by_day=usage_bands.BackendDailyTokens({}, {}),
            mode=usage_bands.BACKEND_MODE,
        )
        self.assertEqual(
            totals, [_INPUT_TOKENS + _OUTPUT_TOKENS + _CACHE_TOKENS],
        )


if __name__ == "__main__":
    unittest.main()
