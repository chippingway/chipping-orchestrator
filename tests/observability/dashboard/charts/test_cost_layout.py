# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The frame the horizontal cost families share, one series of bars, and a token-share split's three segments."""
from __future__ import annotations

import unittest
from importlib.util import find_spec

from orchestrator.observability.dashboard import palette
from orchestrator.observability.dashboard.charts import cost_layout, primitives
from orchestrator.observability.dashboard.layout import base_layout

_SKIP_REASON = "plotly not installed -- run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard`"

_ROW_HEIGHT = primitives.HORIZONTAL_BAR_ROW_HEIGHT

_EXTRA_HEIGHT = primitives.HORIZONTAL_BAR_EXTRA_HEIGHT

_ROW_COUNT = 3

_PINNED_HEIGHT = 260

_LEGEND_ENTRIES = 3

_STACKED = "stack"

_PANEL_TITLE = "Cost by stage"

_TRACE_NAME = "Cache"

_HOVER_LABEL = "Cached"

_Y_TICKS = ("<b>implementing</b>", "<b>validating</b>")

_AMOUNTS = (3.0, 9.0)

_FIGURES = ("$4.00", "unpriced")

_NOTES = ("$4.00 (CLI-reported)", "unpriced (incomplete: 1 of 1 runs unpriced or partly priced)")

# One series of two groups split by token share: the first all declared, the
# second with an amount no declared total could split.
_SPLIT = cost_layout.TokenShareBars(
    no_cache=(1.0, 0),
    cache=(3.0, 0),
    unsplit=(0, 0.5),
    figures=_FIGURES,
    notes=_NOTES,
)

_SPLIT_COLORS = ("#5b54e0", "rgba(91,84,224,0.45)")

# One group whose whole amount a declared total split, leaving nothing unknown.
_WHOLE = cost_layout.TokenShareBars(
    no_cache=(1.0,),
    cache=(3.0,),
    unsplit=(0,),
    figures=_FIGURES[:1],
    notes=_NOTES[:1],
)

_REVIEWER = "reviewer"


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
            legend_entries=_LEGEND_ENTRIES,
            legend_order="reversed",
        ).layout
        self.assertEqual(split.barmode, _STACKED)
        self.assertEqual(split.legend.traceorder, "reversed")
        self.assertEqual((split.legend.xref, split.legend.entrywidth), ("container", 1))

    def test_the_legend_band_is_reserved_and_counted(self) -> None:
        # The band is reserved above the plot and added to the height a panel
        # sizes itself to, so the rows keep their full height beneath it; a
        # pinned height is the caller's, the band coming out of it.
        band = primitives.legend_band_height(_LEGEND_ENTRIES)
        split = self._framed(legend_entries=_LEGEND_ENTRIES).layout
        self.assertEqual(split.margin.t, band)
        self.assertEqual(split.height, _ROW_HEIGHT * _ROW_COUNT + _EXTRA_HEIGHT + band)
        pinned = self._framed(legend_entries=_LEGEND_ENTRIES, height=_PINNED_HEIGHT).layout
        self.assertEqual((pinned.margin.t, pinned.height), (band, _PINNED_HEIGHT))

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
        self.assertEqual(self._trace(offsetgroup=_REVIEWER).offsetgroup, _REVIEWER)

    def test_only_a_labelled_trace_carries_text(self) -> None:
        # The figure lands once per bar rather than once per segment, so a
        # stack labels its outer series and leaves the base beneath it bare --
        # and the figure is the caller's words, so an unpriced bar reads so.
        self.assertIsNone(self._trace().text)
        labelled = self._trace(labels=_FIGURES)
        self.assertEqual(list(labelled.text), list(_FIGURES))
        self.assertEqual(labelled.textposition, "outside")

    def test_a_noted_trace_hovers_the_whole_cost(self) -> None:
        # A segment's own amount alone would read as the group's spend, so its
        # hover adds the cost the caller worded for the whole group.
        self.assertIsNone(self._trace().customdata)
        noted = self._trace(notes=_NOTES)
        self.assertEqual(tuple(noted.customdata), _NOTES)
        self.assertIn("Total: %{customdata}", noted.hovertemplate)
        self.assertFalse(self._trace(show_legend=False).showlegend)

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


class TokenShareTracesTest(unittest.TestCase):
    """The three segments a token-share split is stacked into."""

    def test_the_segments_are_named_as_shares(self) -> None:
        # Neither split segment may read as a measured cache charge, and the
        # amount nothing split is outermost, in the shared muted tint, carrying
        # the figure past the bar.
        traces = cost_layout.token_share_traces(_SPLIT, _Y_TICKS, colors=_SPLIT_COLORS)
        self.assertEqual(
            tuple(trace.name for trace in traces),
            ("Non-cache token share", "Cache token share", "Token share unknown"),
        )
        tints = tuple(trace.color for trace in traces)
        self.assertEqual(tints, (*_SPLIT_COLORS, palette.MUTED_TEXT_SOFT))
        labels = tuple(trace.labels for trace in traces)
        self.assertEqual(labels, (None, None, _FIGURES))
        self.assertEqual({trace.notes for trace in traces}, {_NOTES})

    def test_a_role_names_and_offsets_segments(self) -> None:
        traces = cost_layout.token_share_traces(
            _SPLIT, _Y_TICKS, role="Review", colors=_SPLIT_COLORS, offsetgroup=_REVIEWER,
        )
        self.assertEqual(traces[1].name, "Review (cache token share)")
        self.assertEqual({trace.offsetgroup for trace in traces}, {_REVIEWER})

    def test_a_series_counts_the_lines_it_lists(self) -> None:
        # The count a panel reserves its legend band by is the count of
        # entries the series shows: the unsplit one only where it holds some.
        self.assertEqual((_SPLIT.legend_entries, _WHOLE.legend_entries), (3, 2))

    def test_an_empty_unsplit_stays_off_the_legend(self) -> None:
        split = cost_layout.token_share_traces(_SPLIT, _Y_TICKS, colors=_SPLIT_COLORS)
        self.assertTrue(split[-1].show_legend)
        whole = cost_layout.token_share_traces(_WHOLE, _Y_TICKS[:1], colors=_SPLIT_COLORS)
        self.assertFalse(whole[-1].show_legend)


if __name__ == "__main__":
    unittest.main()
