# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The placeholder, labels, and panel sizing every chart family draws with."""
from __future__ import annotations

import unittest
from importlib.util import find_spec
from types import MappingProxyType

from orchestrator.observability.dashboard import palette, tokens
from orchestrator.observability.dashboard.charts import primitives

_SKIP_REASON = "plotly not installed -- run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard`"

_NO_ROWS_MESSAGE = "No repos match the current filters."

_PLACEHOLDER_HEIGHT = 220

_PINNED_PANEL_HEIGHT = 320

_ROW_HEIGHT = primitives.HORIZONTAL_BAR_ROW_HEIGHT

_EXTRA_HEIGHT = primitives.HORIZONTAL_BAR_EXTRA_HEIGHT

# What a panel comes back sized to, per (row count, height the caller pinned).
# A panel with nothing in it is still one row tall, which is the height the
# empty-state card drawn in its place is pinned to.
_PANEL_HEIGHTS = (
    (3, None, _ROW_HEIGHT * 3 + _EXTRA_HEIGHT),
    (3, _PINNED_PANEL_HEIGHT, _PINNED_PANEL_HEIGHT),
    (0, None, _ROW_HEIGHT + _EXTRA_HEIGHT),
)


@unittest.skipUnless(find_spec("plotly"), _SKIP_REASON)
class EmptyFigureTest(unittest.TestCase):
    """A window with no rows is one annotated card, not a blank canvas."""

    def test_message_is_centered_over_hidden_axes(self) -> None:
        fig = primitives.empty_figure(
            _NO_ROWS_MESSAGE, height=_PLACEHOLDER_HEIGHT,
        )
        annotation = fig.layout.annotations[0]
        self.assertEqual(annotation.text, _NO_ROWS_MESSAGE)
        self.assertEqual((annotation.x, annotation.y), (0.5, 0.5))
        self.assertFalse(annotation.showarrow)
        self.assertFalse(fig.layout.xaxis.visible)
        self.assertFalse(fig.layout.yaxis.visible)

    def test_it_keeps_the_builder_s_height_and_theme(self) -> None:
        # The height the caller pinned is what stops an empty card from
        # snapping to Plotly's own default and dwarfing the cards beside it,
        # and the annotation is tinted off the theme so it reads as the same
        # page as the charts around it.
        fig = primitives.empty_figure(
            _NO_ROWS_MESSAGE, height=_PLACEHOLDER_HEIGHT,
        )
        annotation = fig.layout.annotations[0]
        self.assertEqual(fig.layout.height, _PLACEHOLDER_HEIGHT)
        self.assertEqual(annotation.font.color, palette.MUTED_TEXT)
        self.assertEqual(annotation.font.size, tokens.FONT_SIZE)
        self.assertEqual(fig.layout.paper_bgcolor, palette.CARD_BG)


class BarLabelTest(unittest.TestCase):
    """How a bar is annotated: its font and its tick."""

    def test_value_labels_are_set_in_the_mono_stack(self) -> None:
        # A column of amounts only lines up when every digit is the same
        # width, so the label font is the theme's mono stack rather than the
        # page font the rest of a figure is set in.
        textfont = primitives.monospace_textfont()
        self.assertEqual(textfont["family"], tokens.MONO_FONT_FAMILY)
        self.assertEqual(textfont["color"], palette.TEXT)

    def test_a_tick_carries_the_subtitle_it_has(self) -> None:
        ticks = primitives.two_line_y_ticks(("repo", "other"), ("10 runs", ""))
        self.assertEqual(
            ticks[0],
            "<b>repo</b><br>"
            f"<span style='color:{palette.MUTED_TEXT};font-size:11px'>"
            "10 runs</span>",
        )
        self.assertEqual(ticks[1], "<b>other</b>")


# Where a stacked legend is placed and how wide each entry is: the figure's
# top-left corner, one entry to a line.
_STACKED_PLACEMENT = MappingProxyType({
    "xref": "container",
    "yref": "container",
    "x": 0,
    "y": 1,
    "xanchor": "left",
    "yanchor": "top",
    "entrywidth": 1,
    "entrywidthmode": "fraction",
})


class PanelShapeTest(unittest.TestCase):
    """How a horizontal-bar panel is sized and where its legend sits."""

    def test_height_grows_with_the_rows_unless_pinned(self) -> None:
        for row_count, height, expected in _PANEL_HEIGHTS:
            with self.subTest(row_count=row_count, height=height):
                self.assertEqual(
                    primitives.horizontal_panel_height(
                        row_count, height=height,
                    ),
                    expected,
                )

    def test_the_legend_is_one_entry_a_line_on_top(self) -> None:
        # Anchored to the figure's top-left corner rather than the plot area,
        # and each entry as wide as the line, the legend takes as many lines
        # as it has entries at any panel width -- which is what lets a panel
        # reserve its band rather than lose rows to however far it wraps.
        legend = primitives.stacked_legend()
        placed = {key: legend[key] for key in _STACKED_PLACEMENT}
        self.assertEqual(placed, dict(_STACKED_PLACEMENT))
        self.assertNotIn("traceorder", legend)
        self.assertEqual(
            primitives.stacked_legend(traceorder="reversed")["traceorder"],
            "reversed",
        )

    def test_the_band_grows_by_one_line_per_entry(self) -> None:
        line = primitives.LEGEND_ENTRY_HEIGHT
        self.assertEqual(primitives.legend_band_height(3) - primitives.legend_band_height(2), line)
        self.assertEqual(primitives.legend_band_height(2), 2 * line + primitives.LEGEND_BAND_PAD)


if __name__ == "__main__":
    unittest.main()
