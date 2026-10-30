# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a page's chrome and its four tiles look like once a browser reads them.

Every case reads the rendered string the way the stylesheet does: a class name
is what paints a tile's move, an arrow is what says which way it moved, and an
escaped label is what keeps a KPI's name off the page as markup rather than as
text. The band is read as one contract because it is drawn as one -- the pill
is written into the tile that carries it.

The formatters handed in are the page's own rather than stand-ins, so a figure
a banner reports here is the figure an operator reads.
"""

from __future__ import annotations

import inspect
import unittest
from typing import Any

from orchestrator.observability.analytics.query.overview_models import (
    DataExtent,
)
from orchestrator.observability.dashboard import (
    formatting,
    sparkline_html,
    spend_text,
    summary_html,
)
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases
from tests.observability.dashboard.dashboard_test_support import (
    MAY01,
    MAY07,
    data_extent,
)

# One move, read in both directions and under both mappings.
_MOVE = 0.25

_MOVE_TEXT = "25.0%"

_UP = "orch-delta up"

_DOWN = "orch-delta down"

_RISING_ARROW = "▲"

_FALLING_ARROW = "▼"

_ZERO = float(0)

# The window a banner and a filter line are drawn over, and what ran in it.
_REPOS = 3

_ONE = 1

_EVENTS = 12345

_EVENTS_TEXT = "12,345"

# A blended window: its figure, and the parts its note lists beside it.
_SPEND = cohort_cases.cohort(cases.REPORTED, cases.GEMINI_ESTIMATE)

_SPEND_TEXT = '<span class="value">$0.54</span>'

_SPEND_NOTE = (
    '<span class="note">blended: CLI-reported $0.42 + Gemini API token estimate $0.12</span>'
)

_DAYS = 7

_RUNS = 4200

_RUNS_TEXT = "4,200"

# The five readings the banner is called with.
_TOPBAR_KEYWORDS = (
    "extent",
    "distinct_repos",
    "total_events",
    "spend_in_range",
    "fmt_num",
)

# What a move and a tile are qualified by, carrying markup so the escape is
# read off the same string.
_UNSAFE_NOTE = "subtotal <i>here</i>"

_ESCAPED_NOTE = "subtotal &lt;i&gt;here&lt;/i&gt;"

# A KPI label carrying markup, so what a browser is asked to interpret is read
# off the same string the class names are.
_UNSAFE_LABEL = "Cost <b>by</b> repo"

_ESCAPED_LABEL = "Cost &lt;b&gt;by&lt;/b&gt; repo"

_FIGURE = "$1,235"

_SUB = "$176/day"

# One tile's line, the hue an entry names for it, and the hue a tile that names
# none is drawn in.
_SPARK = (1.0, 2.0, 3.0)

_SPARK_COLOR = "#111"

_DEFAULT_SPARK_COLOR = "#5b54e0"

_SVG_OPEN = "<svg"

_STRIP_OPEN = '<div class="orch-kpis">'

_TILE_OPEN = '<div class="orch-kpi">'

_TWO_TILES = 2

_LABEL_KEY = "label"

_VALUE_KEY = "value"

_SUB_KEY = "sub"

_DELTA_KEY = "delta"


def _topbar(extent: DataExtent, distinct_repos: int, spend=_SPEND) -> str:
    return summary_html.topbar_html(
        extent=extent,
        distinct_repos=distinct_repos,
        total_events=_EVENTS,
        spend_in_range=spend,
        fmt_num=formatting.fmt_num,
    )


def _tile(**sparkline: Any) -> dict:
    """One strip entry, given the line the case wants drawn under it."""
    return {
        _LABEL_KEY: _UNSAFE_LABEL,
        _VALUE_KEY: _FIGURE,
        _SUB_KEY: _SUB,
        _DELTA_KEY: _MOVE,
        **sparkline,
    }


class DeltaPillTest(unittest.TestCase):
    """A move is painted for a cost dashboard: a rise reads red and a drop
    green, and `invert` swaps that for the readings where up is the good
    direction without moving the arrow off the value's sign.
    """

    def test_a_move_is_painted_by_direction(self) -> None:
        for delta_value, invert, css_class, arrow in (
            (_MOVE, False, _UP, _RISING_ARROW),
            (-_MOVE, False, _DOWN, _FALLING_ARROW),
            (_MOVE, True, _DOWN, _RISING_ARROW),
            (-_MOVE, True, _UP, _FALLING_ARROW),
        ):
            with self.subTest(delta=delta_value, invert=invert):
                pill = summary_html.delta_pill(delta_value, invert=invert)
                self.assertIn(css_class, pill)
                self.assertIn(arrow, pill)
                self.assertIn(_MOVE_TEXT, pill)

    def test_nothing_to_report_renders_no_pill(self) -> None:
        # A window with no prior to compare against and one that did not move
        # both leave the slot empty rather than drawing a grey placeholder,
        # which read as a control that does nothing.
        for delta_value in (None, _ZERO):
            with self.subTest(delta=delta_value):
                self.assertEqual(summary_html.delta_pill(delta_value), "")

    def test_the_historical_keyword_still_binds(self) -> None:
        self.assertEqual(
            summary_html.delta_pill(value=_MOVE),
            summary_html.delta_pill(_MOVE),
        )

    def test_a_qualified_move_carries_its_note(self) -> None:
        # The note rides inside the pill, so the percentage cannot be read
        # without what it has to be read with.
        pill = summary_html.delta_pill(_MOVE, note=_UNSAFE_NOTE)
        self.assertIn(f"{_RISING_ARROW} {_MOVE_TEXT} · {_ESCAPED_NOTE}</span>", pill)
        self.assertNotIn(_UNSAFE_NOTE, pill)
        self.assertEqual(summary_html.delta_pill(None, note=_UNSAFE_NOTE), "")


class TopbarTest(unittest.TestCase):
    """The banner names the span the database holds, and says so plainly on
    the deployment where it holds nothing yet.
    """

    def test_a_populated_extent_names_its_span(self) -> None:
        banner = _topbar(data_extent(MAY01, MAY07), _REPOS)
        self.assertIn(
            f"{MAY01.isoformat()} → {MAY07.isoformat()} available", banner,
        )
        self.assertIn(f"{_REPOS} repos ·", banner)
        self.assertIn(f"{_EVENTS_TEXT} events", banner)
        self.assertIn(_SPEND_TEXT + _SPEND_NOTE, banner)

    def test_the_spend_is_never_bare(self) -> None:
        # An incomplete subtotal says so beside its figure, a complete amount
        # names its basis, and a window with no run reads as none rather than
        # as a spend of zero.
        for name, costs, figure, note in (
            ("incomplete", (cases.ANTHROPIC_ESTIMATE, cases.UNPRICED), "$0.30", "incomplete subtotal"),
            ("agy only", (cases.GEMINI_ESTIMATE,), "$0.12", "Gemini API token estimate"),
            ("empty", (), spend_text.NO_RUNS_FIGURE, spend_text.NO_RUNS_NOTE),
        ):
            banner = _topbar(data_extent(MAY01, MAY07), _REPOS, cohort_cases.cohort(*costs))
            with self.subTest(cohort=name):
                self.assertIn(f'<span class="value">{figure}</span><span class="note">', banner)
                self.assertIn(note, banner)

    def test_an_empty_extent_says_there_is_none(self) -> None:
        self.assertIn(
            "no data recorded yet", _topbar(DataExtent(), _REPOS),
        )

    def test_one_repo_is_counted_in_the_singular(self) -> None:
        self.assertIn(
            f"{_ONE} repo ·", _topbar(data_extent(MAY01, MAY07), _ONE),
        )

    def test_the_five_keywords_still_bind_by_name(self) -> None:
        self.assertEqual(
            tuple(inspect.signature(summary_html.topbar_html).parameters),
            _TOPBAR_KEYWORDS,
        )


class FilterMetaTest(unittest.TestCase):
    """The line under the filter bar restates the window a run selected."""

    def test_it_restates_the_window_and_its_runs(self) -> None:
        meta = summary_html.filter_meta_html(
            from_d=MAY01,
            to_d=MAY07,
            days=_DAYS,
            runs=_RUNS,
            fmt_num=formatting.fmt_num,
        )
        self.assertIn(f"{MAY01.isoformat()} → {MAY07.isoformat()}", meta)
        self.assertIn(f"{_DAYS} days ·", meta)
        self.assertIn(f"{_RUNS_TEXT} runs", meta)

    def test_one_day_is_counted_in_the_singular(self) -> None:
        meta = summary_html.filter_meta_html(
            from_d=MAY01,
            to_d=MAY01,
            days=_ONE,
            runs=_RUNS,
            fmt_num=formatting.fmt_num,
        )
        self.assertIn(f"{_ONE} day ·", meta)


class KpiStripTest(unittest.TestCase):
    """What a tile carries: its label and figure as text, the move beside
    them, and the line under them wherever the entry was given one.
    """

    def test_a_tile_reports_its_entry_as_text(self) -> None:
        strip = summary_html.kpi_strip_html((_tile(),))
        self.assertIn(_ESCAPED_LABEL, strip)
        self.assertNotIn(_UNSAFE_LABEL, strip)
        self.assertIn(_FIGURE, strip)
        self.assertIn(_SUB, strip)
        self.assertIn(_UP, strip)

    def test_a_note_sits_under_the_value_escaped(self) -> None:
        strip = summary_html.kpi_strip_html((_tile(note=_UNSAFE_NOTE, delta_note=_UNSAFE_NOTE),))
        self.assertIn(f'</div><div class="kpi-note">{_ESCAPED_NOTE}</div><div class="kpi-foot">', strip)
        self.assertIn(f"{_MOVE_TEXT} · {_ESCAPED_NOTE}</span>", strip)
        self.assertNotIn(_UNSAFE_NOTE, strip)
        self.assertNotIn("kpi-note", summary_html.kpi_strip_html((_tile(),)))

    def test_a_line_takes_the_hue_the_entry_named(self) -> None:
        # The SVG is the sparkline owner's own, so a tile and the line under
        # it cannot end up scaled or tinted two ways.
        for entry, color in (
            (_tile(spark=_SPARK, spark_color=_SPARK_COLOR), _SPARK_COLOR),
            (_tile(spark=_SPARK), _DEFAULT_SPARK_COLOR),
        ):
            with self.subTest(color=color):
                self.assertIn(
                    sparkline_html.sparkline_svg(_SPARK, color=color),
                    summary_html.kpi_strip_html((entry,)),
                )

    def test_a_tile_with_no_line_draws_none(self) -> None:
        self.assertNotIn(
            _SVG_OPEN, summary_html.kpi_strip_html((_tile(spark=None),)),
        )

    def test_the_tiles_are_assembled_into_one_strip(self) -> None:
        strip = summary_html.kpi_strip_html(
            (_tile(spark=_SPARK), _tile(spark=None)),
        )
        self.assertTrue(strip.startswith(_STRIP_OPEN))
        self.assertEqual(strip.count(_TILE_OPEN), _TWO_TILES)


if __name__ == "__main__":
    unittest.main()
