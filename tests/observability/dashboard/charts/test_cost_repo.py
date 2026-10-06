# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How a window's repositories are named, counted, and tinted as bars."""
from __future__ import annotations

import unittest
from importlib.util import find_spec

from orchestrator.observability.analytics.query.cost_models import (
    RepoBreakdownRow,
)
from orchestrator.observability.dashboard import palette
from orchestrator.observability.dashboard.charts import cost_horizontal, cost_repo

_SKIP_REASON = "plotly not installed -- run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard`"

_DEARER_COST = 8.0

_CHEAPER_COST = 3.0

_DEARER_RUNS = "4 runs"

_CHEAPER_RUNS = "2 runs"

_DEARER_NAME = "widgets"

_CHEAPER_NAME = "gadgets"

_OWNER_PREFIX = "acme/"

_DEARER_SLUG = f"{_OWNER_PREFIX}{_DEARER_NAME}"

_CHEAPER_SLUG = f"{_OWNER_PREFIX}{_CHEAPER_NAME}"

# Two repositories under one owner, dearest first, so both the short name the
# bars are labelled by and the ranking under them are visible in the figure.
_ROWS = (
    RepoBreakdownRow(
        repo=_DEARER_SLUG,
        issues=2,
        events=10,
        agent_exits=4,
        total_cost_usd=_DEARER_COST,
    ),
    RepoBreakdownRow(
        repo=_CHEAPER_SLUG,
        issues=1,
        events=4,
        agent_exits=2,
        total_cost_usd=_CHEAPER_COST,
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

    def test_the_sub_line_counts_runs_not_events(self) -> None:
        # The amount beside it is what those agent runs came to, so counting
        # the cheap stage rows too would overstate a quiet repository.
        ticks = _repo_ticks()
        self.assertIn(_DEARER_RUNS, ticks)
        self.assertIn(_CHEAPER_RUNS, ticks)
        self.assertNotIn("events", ticks)

    def test_repos_are_ranked_and_drawn_in_one_hue(self) -> None:
        # A repository is not a category the page tints by, so the ranking is
        # the accent throughout; the cheaper bar is drawn first because a
        # Plotly bar axis puts the first row at the bottom.
        trace = cost_repo.cost_by_repo(_ROWS).data[0]
        self.assertEqual(tuple(trace.x), (_CHEAPER_COST, _DEARER_COST))
        self.assertEqual(
            tuple(trace.marker.color), (palette.ACCENT, palette.ACCENT),
        )

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
