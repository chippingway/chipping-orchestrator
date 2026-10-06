# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The weekday-by-hour grid: its cells, its axes, and its empty window."""
from __future__ import annotations

import unittest
from importlib.util import find_spec

from orchestrator.observability.analytics.query.activity_models import (
    HourlyHeatmapPoint,
)
from orchestrator.observability.dashboard import palette
from orchestrator.observability.dashboard.charts import heatmap

_SKIP_REASON = "plotly not installed -- run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard`"

_WEEKDAYS = 7

_SUNDAY_HOUR = 9

_SUNDAY_TOKENS = 1_500

_WEDNESDAY = 3

_WEDNESDAY_HOUR = 14

_WEDNESDAY_TOKENS = 12_000

# The two cells every volume assertion is read off. Their event counts are
# deliberately at a different scale from their token totals, so a grid drawn
# from `count` cannot pass for one drawn from `total_tokens`.
_POINTS = (
    HourlyHeatmapPoint(
        weekday=0,
        hour=_SUNDAY_HOUR,
        count=1,
        total_tokens=_SUNDAY_TOKENS,
    ),
    HourlyHeatmapPoint(
        weekday=_WEDNESDAY,
        hour=_WEDNESDAY_HOUR,
        count=5,
        total_tokens=_WEDNESDAY_TOKENS,
    ),
)

# A weekday past the last row and an hour past the last column. Either would
# raise on the way into the matrix if the grid indexed what it was handed.
_OUT_OF_RANGE = (
    HourlyHeatmapPoint(
        weekday=_WEEKDAYS, hour=0, count=1, total_tokens=_SUNDAY_TOKENS,
    ),
    HourlyHeatmapPoint(
        weekday=0,
        hour=heatmap.HOURS_PER_DAY,
        count=1,
        total_tokens=_SUNDAY_TOKENS,
    ),
)

# What the grid is pinned to (px): 7 rows x 24 columns read as compact squares
# at this height and as tall rectangles at Plotly's own default.
_HEATMAP_HEIGHT = 240

_EMPTY_MESSAGE = "No events match the current filters."

_TZ_LABELS = (("UTC", "hour (UTC)"), ("UTC+7", "hour (UTC+7)"))


def _cell_grid(fig) -> list[list[int]]:
    """The single heatmap trace's cells as a plain weekday x hour list."""
    return [list(row) for row in fig.data[0].z]


class HeatmapMatrixTest(unittest.TestCase):
    """What lands in a cell, and what is refused a cell at all."""

    def test_cells_carry_token_volume_not_event_count(self) -> None:
        grid = heatmap.heatmap_matrix(_POINTS)
        self.assertEqual(len(grid), _WEEKDAYS)
        self.assertEqual(len(grid[0]), heatmap.HOURS_PER_DAY)
        self.assertEqual(grid[0][_SUNDAY_HOUR], _SUNDAY_TOKENS)
        self.assertEqual(
            grid[_WEDNESDAY][_WEDNESDAY_HOUR], _WEDNESDAY_TOKENS,
        )

    def test_unplaceable_points_leave_zeroes(self) -> None:
        # A window with nothing in it and a point naming a cell the grid does
        # not have come back the same way: the whole grid, all zero. Dropping
        # the stray point is what keeps one out-of-range weekday from being a
        # page that fails to load.
        for point in _OUT_OF_RANGE:
            with self.subTest(weekday=point.weekday, hour=point.hour):
                self.assertFalse(
                    heatmap.valid_heatmap_point(point, _WEEKDAYS),
                )
        for points in ((), _OUT_OF_RANGE):
            with self.subTest(points=len(points)):
                grid = heatmap.heatmap_matrix(points)
                self.assertEqual(len(grid), _WEEKDAYS)
                self.assertTrue(
                    all(cell == 0 for row in grid for cell in row),
                )


@unittest.skipUnless(find_spec("plotly"), _SKIP_REASON)
class HeatmapFigureTest(unittest.TestCase):
    """The figure those cells are drawn as: its grid, axes, and height."""

    def test_the_figure_is_drawn_from_the_matrix(self) -> None:
        grid = _cell_grid(heatmap.hour_weekday_heatmap(_POINTS))
        self.assertEqual(grid, heatmap.heatmap_matrix(_POINTS))

    def test_rows_are_labelled_in_the_order_given(self) -> None:
        # Postgres `EXTRACT(DOW FROM ts)` numbers Sunday 0, so a point's
        # weekday indexes its row directly. Re-mapping to a Monday-first week
        # would shift every cell against the label an operator reads it off.
        fig = heatmap.hour_weekday_heatmap(_POINTS)
        self.assertEqual(tuple(fig.data[0].y), heatmap.WEEKDAY_LABELS)
        self.assertEqual(fig.data[0].y[0], "Sun")
        self.assertEqual(_cell_grid(fig)[0][_SUNDAY_HOUR], _SUNDAY_TOKENS)

    def test_the_plot_background_paints_the_cell_grid(self) -> None:
        # The inter-cell gaps show the plot background, so painting it the
        # border colour turns them into a visible weekday x hour grid --
        # otherwise zero-volume (white) cells vanish against a white backdrop
        # and the sparse hours read as missing data.
        fig = heatmap.hour_weekday_heatmap(())
        self.assertEqual(fig.layout.plot_bgcolor, palette.BORDER)
        self.assertGreater(fig.data[0].xgap, 0)
        self.assertGreater(fig.data[0].ygap, 0)

    def test_the_hour_axis_carries_the_zone_given(self) -> None:
        # Nothing here shifts a timestamp, so the label is the caller's claim
        # about the offset the cells were already read under.
        for tz_label, expected in _TZ_LABELS:
            with self.subTest(tz_label=tz_label):
                fig = heatmap.hour_weekday_heatmap((), tz_label=tz_label)
                self.assertEqual(fig.layout.xaxis.title.text, expected)

    def test_an_empty_window_is_annotated_in_place(self) -> None:
        # The grid is still drawn under the sentence: an empty heatmap reads
        # as a window with no activity, where an empty bar series would not.
        fig = heatmap.hour_weekday_heatmap(())
        annotation = fig.layout.annotations[0]
        self.assertEqual(annotation.text, _EMPTY_MESSAGE)
        self.assertEqual(annotation.font.color, palette.MUTED_TEXT)
        self.assertEqual(len(_cell_grid(fig)), _WEEKDAYS)

    def test_the_height_is_pinned_to_compact_squares(self) -> None:
        fig = heatmap.hour_weekday_heatmap(())
        self.assertEqual(fig.layout.height, _HEATMAP_HEIGHT)
        self.assertEqual(
            heatmap.heatmap_layout(None)["height"], _HEATMAP_HEIGHT,
        )


if __name__ == "__main__":
    unittest.main()
