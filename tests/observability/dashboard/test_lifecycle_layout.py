# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where a browser lays the lifecycle pair's labels and legends out, at the widths the page draws them in.

The hermetic cases hold each split to the legend band it reserves and the pairing to the larger split's need; only a
browser says whether the two-line labels then stand apart, since Plotly decides where a legend ends and a tick label
lands as it lays the figure out. Each split of the most crowded window is drawn at the height the pairing pins it to,
across widths its column spans on the page -- the review column narrow, the stage column wider -- and every adjacent
pair of labels has to stand apart, with the legend ending above the plot.
"""
from __future__ import annotations

import unittest
from importlib.util import find_spec

from orchestrator.observability.dashboard import stage_cost_panel
from orchestrator.observability.dashboard.charts import cost_review, cost_stage
from tests.observability.dashboard import lifecycle_window_test_support as window
from tests.observability.dashboard.browser_layout_test_support import browser_from_environment, rendered_layout

_SKIP_REASON = "plotly not installed -- run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard`"

# The narrowest and widest each column is drawn at under the page's width cap.
_REVIEW_WIDTHS = (420, 600)

_STAGE_WIDTHS = (520, 840)


@unittest.skipUnless(find_spec("plotly"), _SKIP_REASON)
class LifecycleLabelLayoutTest(unittest.TestCase):
    """Opted into with `DASHBOARD_TEST_BROWSER=<headless Chrome or Chromium binary>`."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.browser = browser_from_environment()
        cls.height = stage_cost_panel.paired_bars_height(window.PARTLY_SPLIT_STAGES, window.PARTLY_SPLIT_ROUNDS)

    def test_review_labels_stand_apart(self) -> None:
        # Six legend lines over six two-bar rounds in the narrow column.
        figure = cost_review.cost_by_review_round(window.PARTLY_SPLIT_ROUNDS, height=self.height)
        self._assert_apart(figure, _REVIEW_WIDTHS, len(window.ALL_ROUNDS))

    def test_stage_labels_stand_apart(self) -> None:
        figure = cost_stage.cost_by_stage(window.PARTLY_SPLIT_STAGES, height=self.height)
        self._assert_apart(figure, _STAGE_WIDTHS, len(window.ALL_STAGES))

    def _assert_apart(self, figure, widths: tuple[int, ...], rows: int) -> None:
        for width in widths:
            drawn = rendered_layout(self.browser, figure, width=width, height=self.height)
            with self.subTest(width=width):
                self.assertEqual(len(drawn.ticks), rows)
                self.assertLess(drawn.label_overlap, 0)
                self.assertLessEqual(drawn.legend_bottom, drawn.plot_top)


if __name__ == "__main__":
    unittest.main()
