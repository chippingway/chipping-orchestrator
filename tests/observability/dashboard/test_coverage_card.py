# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What share of a window's spend the bar says was priced, and how it is sized.

The whole point of the bar is which denominator it divides by, so the cases
name a window where the two disagree: one source carrying most of the tokens
out of a small minority of the runs. Token share is what an operator is exposed
to when a pricing table has a gap, and run share only stands in for a window
that has not reported a token yet, or one holding a run whose token total is
unknown -- a window reporting neither divides by one rather than raising,
because a page is opened on an empty window precisely to find out that it is
empty.

The bar and the legend under it are read together, since a segment is built as
both at once: the same hue and the same percentage have to appear in each, the
hue comes off the theme the caller handed in, and the cost source naming a
segment is escaped into both, having arrived off the sink.
"""

from __future__ import annotations

import unittest

from orchestrator.observability.analytics.query.cost_models import (
    CostCoverageRow,
)
from orchestrator.observability.dashboard import coverage_card, palette
from tests.observability.dashboard.card_test_support import (
    COST_SOURCE_REPORTED,
    MONO_FONT,
    REPORTED_COLOR,
    TEXT,
    card_theme,
)

_UNPRICED = "unknown-price"

_PRICED_TOKENS = 750

_UNPRICED_TOKENS = 250

_PRICED_RUNS = 1

_UNPRICED_RUNS = 9

# The window the two denominators disagree on: the priced source is three
# quarters of the token volume out of a tenth of the runs.
_TOKEN_ROWS = (
    CostCoverageRow(
        cost_source=COST_SOURCE_REPORTED,
        runs=_PRICED_RUNS,
        total_tokens=_PRICED_TOKENS,
    ),
    CostCoverageRow(
        cost_source=_UNPRICED,
        runs=_UNPRICED_RUNS,
        total_tokens=_UNPRICED_TOKENS,
    ),
)

# The same three-quarter share reached the other way, by a window that has not
# reported a token yet.
_RUN_ONLY_ROWS = (
    CostCoverageRow(cost_source=COST_SOURCE_REPORTED, runs=3, total_tokens=0),
    CostCoverageRow(cost_source=_UNPRICED, runs=1, total_tokens=0),
)

# The token window again, with one unpriced run whose token total nothing
# settles: its source's known subtotal would understate it, so run share sizes
# the bar instead of a token share that hides the run nobody could measure.
_UNSETTLED_ROWS = (
    _TOKEN_ROWS[0],
    CostCoverageRow(
        cost_source=_UNPRICED,
        runs=_UNPRICED_RUNS,
        total_tokens=_UNPRICED_TOKENS,
        unknown_token_runs=1,
    ),
)

_MAJORITY_WIDTH = "width:75.0%"

_MINORITY_SHARE = "25.0%"

_UNSAFE_SOURCE = "src<&>"

_ESCAPED_SOURCE = "src&lt;&amp;&gt;"


def _rendered(rows) -> str:
    """The bar `rows` are drawn as, under the injected theme."""
    return coverage_card.cost_coverage_bar_html(rows, theme=card_theme())


class CostCoverageWeightsTest(unittest.TestCase):
    """Which denominator a window is divided by, and the one an empty window
    falls back to so the bar renders flat instead of raising.
    """

    def test_token_volume_wins_wherever_there_is_any(self) -> None:
        weights, total = coverage_card.cost_coverage_weights(_TOKEN_ROWS)
        self.assertEqual(weights, [_PRICED_TOKENS, _UNPRICED_TOKENS])
        self.assertEqual(total, _PRICED_TOKENS + _UNPRICED_TOKENS)

    def test_run_counts_stand_in_without_tokens(self) -> None:
        weights, total = coverage_card.cost_coverage_weights(_RUN_ONLY_ROWS)
        self.assertEqual(weights, [3, 1])
        self.assertEqual(total, 4)

    def test_an_unknown_total_falls_back_to_runs(self) -> None:
        weights, total = coverage_card.cost_coverage_weights(_UNSETTLED_ROWS)
        self.assertEqual(weights, [_PRICED_RUNS, _UNPRICED_RUNS])
        self.assertEqual(total, _PRICED_RUNS + _UNPRICED_RUNS)

    def test_a_window_with_neither_divides_by_one(self) -> None:
        for rows in ((), (CostCoverageRow(cost_source=_UNPRICED, runs=0),)):
            with self.subTest(rows=rows):
                _, total = coverage_card.cost_coverage_weights(rows)
                self.assertEqual(total, 1)


class CostCoverageBarHtmlTest(unittest.TestCase):
    """Every segment appears twice -- as a slice of the bar and as a line of
    the legend -- carrying one width, one percentage, and one hue.
    """

    def test_segments_are_sized_by_token_share(self) -> None:
        rendered = _rendered(_TOKEN_ROWS)
        self.assertIn("Cost attribution coverage", rendered)
        self.assertIn(_MAJORITY_WIDTH, rendered)
        self.assertIn(_MINORITY_SHARE, rendered)

    def test_run_share_sizes_a_window_with_no_tokens(self) -> None:
        self.assertIn(_MAJORITY_WIDTH, _rendered(_RUN_ONLY_ROWS))

    def test_an_empty_window_draws_an_empty_bar(self) -> None:
        rendered = _rendered(())
        self.assertIn('<div class="orch-cov-bar"></div>', rendered)
        self.assertIn('<div class="orch-cov-legend"></div>', rendered)

    def test_the_injected_theme_tints_and_types_it(self) -> None:
        # A source the caller mapped is painted the caller's way; one it did
        # not is positioned in this window's own source list, which is what
        # keeps a hue stable across the bar and the legend beside it.
        rendered = _rendered(_TOKEN_ROWS)
        self.assertIn(f"background:{REPORTED_COLOR}", rendered)
        self.assertIn(
            f"background:{palette.CATEGORICAL_PALETTE[1]}", rendered,
        )
        self.assertIn(f"color:{TEXT}", rendered)
        self.assertIn(f"font-family:{MONO_FONT}", rendered)

    def test_the_cost_source_is_escaped_into_both(self) -> None:
        rendered = _rendered(
            (CostCoverageRow(cost_source=_UNSAFE_SOURCE, runs=1, total_tokens=10),),
        )
        self.assertEqual(rendered.count(_ESCAPED_SOURCE), 2)
        self.assertNotIn(_UNSAFE_SOURCE, rendered)


if __name__ == "__main__":
    unittest.main()
