# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one backend's row is worth by the time it is a card.

The readings the card exists for are read off the rendered string, since that
is where an operator reads them: the spend with its basis and shortfall
beneath it, what a million tokens cost, how much of the input side of the
declared token totals went through the cache, and what one run cost. A spend
is a cohort, so the cases name the backends a card has to keep apart -- a
CLI-reported one, an AGY-only one whose amount is a Gemini API token estimate
and whose token totals are partly unknown, a mixed one blended with its parts,
an incomplete one, one stating no basis, and one stating no amount -- and a
Codex backend whose cached input sits inside its input, which the cache share
counts once. A ratio is checked against a row whose numbers make the
arithmetic visible, and against a row a backend barely ran in, because every
one of them divides by something a thin window can leave at zero.

The tint, the type, and the token formatter are read back as the ones the
caller handed in rather than any this package holds, and a backend name and
every worded figure are read back escaped.
"""

from __future__ import annotations

import unittest

from orchestrator.observability.analytics.query.cost_models import (
    BackendEfficiencyRow,
)
from orchestrator.observability.dashboard import backend_card
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases
from tests.observability.dashboard.card_test_support import (
    BACKEND_CLAUDE,
    BACKEND_CODEX,
    BODY_FONT,
    BORDER,
    CLAUDE_COLOR,
    MONO_FONT,
    card_theme,
)

_ONE_MILLION = 1_000_000

_TWO_MILLION = 2 * _ONE_MILLION

_RUNS = 2

_PER_MILLION = "/ 1M tok"

_PER_RUN = "/ run"

_VIA_CACHE = "input via cache"

_UNAVAILABLE = "—"

_HALF_PCT = 50

# Codex's 400 cached tokens of its 1,000 input.
_CODEX_CACHE_PCT = 40

# Two CLI-reported runs of $0.42 over two million declared tokens, half of
# them cache inside the input side and none output: $0.84 of spend, a 50%
# cache share, $0.42 a million, and $0.42 a run.
_REPORTED_ROW = BackendEfficiencyRow(
    backend=BACKEND_CLAUDE,
    runs=_RUNS,
    cost=cohort_cases.cohort(*cohort_cases.NAMED_COSTS["reported only"]),
    total_tokens=_TWO_MILLION,
    cache_tokens=_ONE_MILLION,
)

# A Codex run whose cached tokens are part of its input: the declared total is
# input plus output, so the cache share is the cached tokens over the input
# alone rather than over the input and the cache again.
_CODEX_ROW = BackendEfficiencyRow(
    backend=BACKEND_CODEX,
    runs=1,
    cost=cohort_cases.cohort(cases.OPENAI_ESTIMATE),
    total_tokens=cases.CODEX_TOTAL,
    cache_tokens=cases.CODEX_CACHED,
    output_tokens=cases.CODEX_OUTPUT,
)

# Antigravity runs whose token totals the evidence leaves unknown: the amount
# they state is in the spend while their tokens are in no total, so no cost
# per token is taken.
_AGY_ROW = BackendEfficiencyRow(
    backend="agy",
    runs=_RUNS,
    cost=cohort_cases.cohort(*cohort_cases.NAMED_COSTS["agy only"]),
    total_tokens=0,
    unknown_token_runs=_RUNS,
)

# A backend the window carries no work for, so every ratio behind the card
# divides by zero unless the guard answers first.
_EMPTY_ROW = BackendEfficiencyRow(backend=BACKEND_CODEX, runs=0)

_UNSAFE_BACKEND = "ba<ck>"

_ESCAPED_BACKEND = "ba&lt;ck&gt;"


def _rendered(row: BackendEfficiencyRow) -> str:
    """The card `row` is drawn as, under the injected theme."""
    return backend_card.backend_efficiency_card_html(row, theme=card_theme())


def _priced(name: str) -> BackendEfficiencyRow:
    """A backend whose two runs state cohort `name`, over a million declared tokens."""
    return BackendEfficiencyRow(
        backend=BACKEND_CLAUDE,
        runs=_RUNS,
        cost=cohort_cases.cohort(*cohort_cases.NAMED_COSTS[name]),
        total_tokens=_ONE_MILLION,
    )


class BackendEfficiencyMetricsTest(unittest.TestCase):
    """The three readings a card reports, and the guard under each."""

    def test_each_reading_has_its_own_denominator(self) -> None:
        metrics = backend_card.backend_efficiency_metrics(_REPORTED_ROW)
        spend = _REPORTED_ROW.cost.evidence.total_usd
        self.assertEqual(metrics.tokens, _TWO_MILLION)
        self.assertAlmostEqual(metrics.cost_per_million, spend / 2)
        self.assertAlmostEqual(metrics.cost_per_run, spend / _RUNS)
        self.assertEqual(metrics.cache_share_pct, _HALF_PCT)

    def test_cached_input_is_counted_once(self) -> None:
        # Codex's cached tokens are inside its input, so the input side of the
        # declared total is the input alone and the share is 400 of 1,000.
        metrics = backend_card.backend_efficiency_metrics(_CODEX_ROW)
        self.assertAlmostEqual(metrics.cache_share_pct, _CODEX_CACHE_PCT)

    def test_a_token_subtotal_takes_no_cost_per_token(self) -> None:
        # The amount covers runs whose tokens the total leaves out, so a cost
        # per token over it would overstate every token it does count.
        metrics = backend_card.backend_efficiency_metrics(_AGY_ROW)
        self.assertIsNone(metrics.cost_per_million)
        self.assertIsNone(metrics.cache_share_pct)
        self.assertAlmostEqual(metrics.cost_per_run, _AGY_ROW.cost.evidence.total_usd / _RUNS)

    def test_an_empty_window_reports_none_of_them(self) -> None:
        metrics = backend_card.backend_efficiency_metrics(_EMPTY_ROW)
        self.assertEqual(metrics.tokens, 0)
        self.assertIsNone(metrics.cost_per_million)
        self.assertIsNone(metrics.cost_per_run)
        self.assertIsNone(metrics.cache_share_pct)


class BackendRatioTextTest(unittest.TestCase):
    """How each ratio is worded: taken, qualified, or unavailable."""

    def test_complete_ratios_read_plain(self) -> None:
        self.assertEqual(
            backend_card.backend_ratio_texts(_REPORTED_ROW),
            (f"$0.42 {_PER_MILLION}", f"50% {_VIA_CACHE}", f"$0.42 {_PER_RUN}"),
        )

    def test_a_ratio_of_a_short_amount_is_qualified(self) -> None:
        # A ratio of a subtotal or of an amount of unknown completeness says so,
        # like the amount it divides.
        for name, qualifier in (("incomplete", "incomplete subtotal"), ("missing basis", "completeness unknown")):
            with self.subTest(cohort=name):
                per_million, _, per_run = backend_card.backend_ratio_texts(_priced(name))
                self.assertTrue(per_million.endswith(f"{_PER_MILLION} ({qualifier})"))
                self.assertTrue(per_run.endswith(f"{_PER_RUN} ({qualifier})"))

    def test_a_ratio_with_nothing_to_divide_is_a_dash(self) -> None:
        unpriced = BackendEfficiencyRow(backend=BACKEND_CLAUDE, runs=1, cost=cohort_cases.cohort(cases.UNPRICED))
        self.assertEqual(
            backend_card.backend_ratio_texts(unpriced),
            (f"{_UNAVAILABLE} {_PER_MILLION}", f"{_UNAVAILABLE} {_VIA_CACHE}", f"{_UNAVAILABLE} {_PER_RUN}"),
        )

    def test_a_share_of_known_totals_says_so(self) -> None:
        partly_known = BackendEfficiencyRow(
            backend=BACKEND_CLAUDE,
            runs=_RUNS,
            total_tokens=_TWO_MILLION,
            unknown_token_runs=1,
            cache_tokens=_ONE_MILLION,
        )
        _, share, _ = backend_card.backend_ratio_texts(partly_known)
        self.assertEqual(share, f"50% {_VIA_CACHE} (known totals)")


class BackendEfficiencyCardHtmlTest(unittest.TestCase):
    """The card is hand-rolled markup so the caller can render one
    `st.markdown` per backend, and every figure on it is the reading beside
    its own unit and its basis.
    """

    def test_the_readings_reach_the_card(self) -> None:
        rendered = _rendered(_REPORTED_ROW)
        self.assertIn(f"{_RUNS} runs", rendered)
        self.assertIn("$0.84<span", rendered)
        self.assertIn("CLI-reported", rendered)
        for reading in backend_card.backend_ratio_texts(_REPORTED_ROW):
            with self.subTest(reading=reading):
                self.assertIn(reading, rendered)

    def test_agy_spend_reads_as_a_gemini_estimate(self) -> None:
        # Its amount is a Gemini API token estimate, never an Antigravity
        # charge, and the runs whose token total is unknown are counted.
        rendered = _rendered(_AGY_ROW)
        self.assertIn("Gemini API token estimate", rendered)
        self.assertIn(f"{_UNAVAILABLE} {_PER_MILLION}", rendered)
        self.assertIn("token total unknown for 2 runs", rendered)

    def test_a_blended_backend_lists_its_parts(self) -> None:
        rendered = _rendered(_priced("mixed providers"))
        self.assertIn("blended: CLI-reported $0.52 + Gemini API token estimate $0.12", rendered)

    def test_a_short_amount_never_reads_as_complete(self) -> None:
        incomplete = _rendered(_priced("incomplete"))
        self.assertIn("2 of 3 runs unpriced or partly priced", incomplete)
        unpriced = BackendEfficiencyRow(backend=BACKEND_CLAUDE, runs=1, cost=cohort_cases.cohort(cases.UNPRICED))
        self.assertIn("unpriced<span", _rendered(unpriced))

    def test_an_empty_window_still_draws_a_card(self) -> None:
        rendered = _rendered(_EMPTY_ROW)
        self.assertIn("—<span", rendered)
        self.assertIn("no agent runs", rendered)
        self.assertIn(f"{_UNAVAILABLE} {_PER_RUN}", rendered)

    def test_the_injected_theme_paints_it(self) -> None:
        # The page hands one theme object to every builder, so a card that
        # resolved a hue or a font of its own would be a panel painted off a
        # palette the chrome around it was not.
        rendered = _rendered(_REPORTED_ROW)
        self.assertIn(f"border:1px solid {BORDER}", rendered)
        self.assertIn(f"background:{CLAUDE_COLOR}", rendered)
        self.assertIn(f"font-family:{MONO_FONT}", rendered)
        self.assertIn(f"font-family:{BODY_FONT}", rendered)
        self.assertIn(f"~{_TWO_MILLION} tok", rendered)

    def test_the_backend_name_is_escaped(self) -> None:
        rendered = _rendered(
            BackendEfficiencyRow(backend=_UNSAFE_BACKEND, runs=1),
        )
        self.assertIn(_ESCAPED_BACKEND, rendered)
        self.assertNotIn(_UNSAFE_BACKEND, rendered)


if __name__ == "__main__":
    unittest.main()
