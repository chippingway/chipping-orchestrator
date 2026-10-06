# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The frame the horizontal cost families share, and one series of bars."""
from __future__ import annotations

import unittest
from importlib.util import find_spec

from orchestrator.observability.dashboard.charts import cost_layout, primitives
from orchestrator.observability.dashboard.layout import base_layout

_SKIP_REASON = "plotly not installed -- run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard`"

_ROW_HEIGHT = primitives.HORIZONTAL_BAR_ROW_HEIGHT

_EXTRA_HEIGHT = primitives.HORIZONTAL_BAR_EXTRA_HEIGHT

_ROW_COUNT = 3

_PINNED_HEIGHT = 260

_STACKED = "stack"

_PANEL_TITLE = "Cost by stage"

_TRACE_NAME = "Cache"

_HOVER_LABEL = "Cached"

_Y_TICKS = ("<b>implementing</b>", "<b>validating</b>")

_AMOUNTS = (3.0, 9.0)

_TOTALS = (4.0, 12.0)


@unittest.skipUnless(find_spec("plotly"), _SKIP_REASON)
class PanelFrameTest(unittest.TestCase):
    """How a built figure is framed as one of the cost panels."""

    def test_labels_get_the_shared_left_gutter(self) -> None:
        # The gutter is what a two-line tick is drawn in and the right margin
        # what the outside value label needs, so every cost family reserves the
        # same room; the top margin stays the shared layout's, which is taller
        # when a title is drawn.
        gutter = cost_layout.HORIZONTAL_BAR_MARGIN
        margin = self._framed(title=_PANEL_TITLE).layout.margin
        self.assertEqual(margin.l, gutter["l"])
        self.assertEqual(margin.r, gutter["r"])
        self.assertEqual(margin.b, gutter["b"])
        titled_top = base_layout(title=_PANEL_TITLE)["margin"]["t"]
        self.assertEqual(margin.t, titled_top)
        self.assertEqual(
            self._framed().layout.margin.t, base_layout()["margin"]["t"],
        )

    def test_height_follows_the_rows_it_frames(self) -> None:
        self.assertEqual(
            self._framed().layout.height,
            _ROW_HEIGHT * _ROW_COUNT + _EXTRA_HEIGHT,
        )
        self.assertEqual(
            self._framed(height=_PINNED_HEIGHT).layout.height, _PINNED_HEIGHT,
        )

    def test_the_axis_is_read_in_dollars(self) -> None:
        # A cost panel's bars run along x, so that is the axis carrying the
        # unit; the y axis sizes itself to whatever the tick labels need.
        layout = self._framed().layout
        self.assertEqual(layout.xaxis.title.text, "USD")
        self.assertEqual(layout.xaxis.tickprefix, "$")
        self.assertTrue(layout.yaxis.automargin)

    def test_barmode_and_legend_are_opt_in(self) -> None:
        # A single-series ranking carries neither, so a family that splits its
        # bars asks for the stacking and the legend above the plot rather than
        # every panel paying for them.
        plain = self._framed().layout
        self.assertIsNone(plain.barmode)
        self.assertIsNone(plain.legend.traceorder)
        split = self._framed(
            barmode=_STACKED,
            legend=primitives.horizontal_legend(traceorder="reversed"),
        ).layout
        self.assertEqual(split.barmode, _STACKED)
        self.assertEqual(split.legend.traceorder, "reversed")

    def _framed(self, **options):
        from plotly import graph_objects as go

        figure = go.Figure()
        cost_layout.apply_horizontal_cost_layout(
            figure,
            cost_layout.HorizontalCostLayout(row_count=_ROW_COUNT, **options),
        )
        return figure


@unittest.skipUnless(find_spec("plotly"), _SKIP_REASON)
class CostBarTraceTest(unittest.TestCase):
    """What one requested series of bars comes back as."""

    def test_a_bar_is_horizontal_and_hover_labelled(self) -> None:
        # The hover label is what tells a reader which half of a split bar the
        # amount under the cursor belongs to, so it is spelled per series.
        trace = self._trace()
        self.assertEqual(trace.orientation, "h")
        self.assertEqual(trace.name, _TRACE_NAME)
        self.assertEqual(list(trace.x), list(_AMOUNTS))
        self.assertIn(f"{_HOVER_LABEL}: $", trace.hovertemplate)

    def test_offsetgroup_is_set_only_when_asked(self) -> None:
        # Two series sharing an offsetgroup stack at one y bucket, so a family
        # drawing roles side by side names one and a single-series panel does
        # not.
        self.assertIsNone(self._trace().offsetgroup)
        self.assertEqual(self._trace(offsetgroup="reviewer").offsetgroup, "reviewer")

    def test_only_a_totals_trace_is_labelled(self) -> None:
        # The amount lands once per bar rather than once per segment, so a
        # stack labels its outer series and leaves the base beneath it bare.
        self.assertIsNone(self._trace().text)
        labelled = self._trace(totals=_TOTALS)
        self.assertEqual(list(labelled.text), ["$4.00", "$12"])
        self.assertEqual(labelled.textposition, "outside")

    def _trace(self, **options):
        return cost_layout.cost_bar_trace(
            cost_layout.CostBarTrace(
                name=_TRACE_NAME,
                amounts=_AMOUNTS,
                y_ticks=_Y_TICKS,
                color="#5b54e0",
                hover_label=_HOVER_LABEL,
                **options,
            ),
        )


if __name__ == "__main__":
    unittest.main()
