# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How a window's repositories are named, counted, worded, ranked, and tinted as bars."""
from __future__ import annotations

import unittest
from importlib.util import find_spec

from orchestrator.observability.analytics.query.cost_models import (
    RepoBreakdownRow,
)
from orchestrator.observability.dashboard import palette, spend_text
from orchestrator.observability.dashboard.charts import cost_horizontal, cost_repo
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases

_SKIP_REASON = "plotly not installed -- run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard`"

_DEARER_RUNS = "4 runs"

_CHEAPER_RUNS = "2 runs"

_DEARER_NAME = "widgets"

_CHEAPER_NAME = "gadgets"

_UNPRICED_NAME = "gizmos"

_OWNER_PREFIX = "acme/"

_DEARER_SLUG = f"{_OWNER_PREFIX}{_DEARER_NAME}"

_CHEAPER_SLUG = f"{_OWNER_PREFIX}{_CHEAPER_NAME}"

_DEARER_COST = cohort_cases.cohort(*cohort_cases.NAMED_COSTS["mixed providers"])

_CHEAPER_COST = cohort_cases.cohort(*cohort_cases.NAMED_COSTS["agy only"])

_UNPRICED_COST = cohort_cases.cohort(cases.UNPRICED)

# Three repositories under one owner, the unpriced one first and the dearest
# second, so the short name the bars are labelled by, the ranking under them,
# and a repository stating no amount are all visible in the figure.
_ROWS = (
    RepoBreakdownRow(
        repo=f"{_OWNER_PREFIX}{_UNPRICED_NAME}",
        issues=1,
        events=3,
        agent_exits=1,
        cost=_UNPRICED_COST,
    ),
    RepoBreakdownRow(
        repo=_DEARER_SLUG,
        issues=2,
        events=10,
        agent_exits=4,
        cost=_DEARER_COST,
    ),
    RepoBreakdownRow(
        repo=_CHEAPER_SLUG,
        issues=1,
        events=4,
        agent_exits=2,
        cost=_CHEAPER_COST,
    ),
)


def _repo_ticks() -> str:
    """The y-axis labels of the drawn ranking, joined for searching."""
    return " ".join(cost_repo.cost_by_repo(_ROWS).data[0].y)


class RepoNameTest(unittest.TestCase):
    """What an operator reads a bar by."""

    def test_the_owner_prefix_is_dropped(self) -> None:
        # The owner is the same across every bar being compared, so it spends
        # the gutter the amounts have to fit beside without telling them apart.
        self.assertEqual(cost_repo.repo_short_name(_DEARER_SLUG), _DEARER_NAME)

    def test_a_repo_naming_no_owner_is_left_alone(self) -> None:
        self.assertEqual(cost_repo.repo_short_name(_DEARER_NAME), _DEARER_NAME)


@unittest.skipUnless(find_spec("plotly"), _SKIP_REASON)
class RepoRankingFigureTest(unittest.TestCase):
    """What the adapter hands the ranking, and the window matching nothing."""

    def test_bars_are_labelled_by_short_name(self) -> None:
        # The prefix has to be gone from the drawn label rather than merely
        # contained in it: a bar still reading `acme/widgets` would satisfy a
        # search for `widgets`, so the normalization could be unwired and this
        # would still pass.
        ticks = _repo_ticks()
        self.assertIn(f"<b>{_DEARER_NAME}</b>", ticks)
        self.assertIn(f"<b>{_CHEAPER_NAME}</b>", ticks)
        self.assertNotIn(_OWNER_PREFIX, ticks)

    def test_the_sub_line_counts_runs_and_bases(self) -> None:
        # The amount beside it is what those agent runs came to, so counting
        # the cheap stage rows too would overstate a quiet repository; the
        # basis it is stated on follows, an AGY-only repository's a Gemini API
        # token estimate and a mixed one's blended.
        ticks = _repo_ticks()
        self.assertIn(f"{_DEARER_RUNS} · blended", ticks)
        self.assertIn(f"{_CHEAPER_RUNS} · Gemini API token estimate", ticks)
        self.assertNotIn("events", ticks)

    def test_repos_are_ranked_and_drawn_in_one_hue(self) -> None:
        # A repository is not a category the page tints by, so the ranking is
        # the accent throughout. A repository stating no amount ranks last and
        # reads as unpriced rather than as a zero, and the cheaper bar is drawn
        # before the dearer because a Plotly bar axis puts the first row at
        # the bottom.
        trace = cost_repo.cost_by_repo(_ROWS).data[0]
        cheaper = _CHEAPER_COST.evidence.total_usd
        dearer = _DEARER_COST.evidence.total_usd
        self.assertEqual(tuple(trace.x), (float(0), cheaper, dearer))
        self.assertEqual(tuple(trace.text), ("unpriced", "$0.32", "$0.69"))
        self.assertEqual(set(trace.marker.color), {palette.ACCENT})

    def test_each_bar_hovers_its_cost_worded_whole(self) -> None:
        # A blended repository's parts are read by their own amounts on hover.
        trace = cost_repo.cost_by_repo(_ROWS).data[0]
        self.assertEqual(trace.customdata[-1], spend_text.spend_line(_DEARER_COST))
        self.assertIn("CLI-reported $", trace.customdata[-1])

    def test_no_repos_is_one_bar_tall(self) -> None:
        # An operator who filtered the repositories away is told that, at the
        # height a single-row panel comes to, rather than meeting a card that
        # stands taller than the ones beside it.
        figure = cost_repo.cost_by_repo(())
        annotation = figure.layout.annotations[0]
        self.assertIn("repos", annotation.text)
        self.assertEqual(
            figure.layout.height, cost_horizontal.DEFAULT_CHART_HEIGHT,
        )


if __name__ == "__main__":
    unittest.main()
