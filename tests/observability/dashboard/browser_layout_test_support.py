# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where a real browser lays a figure's tick labels, legend, and plot area out.

Plotly decides how far a legend wraps, the margin it pushes, and where each tick label lands only when a page lays the
figure out, so a check that two-line labels stay apart reads the geometry a browser computed rather than the layout
dict handed to it. The browser is the headless Chrome or Chromium `DASHBOARD_TEST_BROWSER` names, and a case skips
when it names none that runs, the way the live analytics cases skip without a database.
"""
from __future__ import annotations

import html
import itertools
import json
import os
import re
import subprocess
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

BROWSER_ENV = "DASHBOARD_TEST_BROWSER"

# The element the dumped page is read back from, holding the JSON the script writes.
_LAYOUT_TEXT = re.compile(r'<pre id="layout">(.*?)</pre>', re.DOTALL)

# Draws the figure, then writes each y tick label's top and bottom, the legend's bottom, and the plot area's top --
# all in page coordinates -- into the element the dumped page is read back from.
_MEASURE = (
    "Plotly.newPlot('chart', figure.data, figure.layout, {displayModeBar: false}).then(chart => {"
    "const ticks = Array.from(chart.querySelectorAll('.ytick'), tick => {"
    "const box = tick.getBoundingClientRect(); return [box.top, box.bottom];});"
    "const legend = chart.querySelector('.legend').getBoundingClientRect().bottom;"
    "const plotTop = chart.getBoundingClientRect().top + chart._fullLayout._size.t;"
    "document.getElementById('layout').textContent = JSON.stringify({ticks, legend, plotTop});});"
)

_BROWSER_FLAGS = ("--headless", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=5000", "--dump-dom")

_RENDER_SECONDS = 60


@dataclass(frozen=True)
class RenderedLayout:
    """Where a drawn figure's y tick labels, legend, and plot area landed."""

    ticks: tuple[tuple[float, float], ...]
    legend_bottom: float
    plot_top: float

    @classmethod
    def from_dumped_page(cls, dumped: str) -> RenderedLayout:
        """Read back what the measuring script wrote into the page the browser dumped."""
        layout_text = html.unescape(_LAYOUT_TEXT.search(dumped).group(1))
        measured = json.loads(layout_text)
        ticks = tuple(map(tuple, measured["ticks"]))
        return cls(ticks, measured["legend"], measured["plotTop"])

    @property
    def label_overlap(self) -> float:
        """How far the closest two adjacent tick labels run into each other; negative where all stand apart."""
        neighbours = itertools.pairwise(sorted(self.ticks))
        return max(
            upper_bottom - lower_top
            for (_, upper_bottom), (lower_top, _) in neighbours
        )


def browser_from_environment() -> str:
    """The headless browser `DASHBOARD_TEST_BROWSER` names, or a skip when it names none that runs."""
    browser = os.environ.get(BROWSER_ENV, "").strip()
    if not browser or not os.access(browser, os.X_OK):
        raise unittest.SkipTest(f"{BROWSER_ENV} names no headless Chrome or Chromium; browser layout check skipped.")
    return browser


def rendered_layout(browser: str, figure, *, width: int, height: int) -> RenderedLayout:
    """Draw `figure` at `width` by `height` in the browser and read back where its labels and legend landed."""
    with tempfile.TemporaryDirectory() as scratch:
        page = Path(scratch) / "figure.html"
        page.write_text(_page(figure, width, height), encoding="utf-8")
        command = [browser, *_BROWSER_FLAGS, page.as_uri()]
        drawn = subprocess.run(command, capture_output=True, text=True, check=True, timeout=_RENDER_SECONDS)
    return RenderedLayout.from_dumped_page(drawn.stdout)


def _page(figure, width: int, height: int) -> str:
    """A page holding Plotly, the figure in a box of the given size, and the measuring script."""
    from plotly.offline import get_plotlyjs

    return (
        f'<meta charset="utf-8"><div id="chart" style="width:{width}px;height:{height}px"></div>'
        f'<pre id="layout"></pre><script>{get_plotlyjs()}</script>'
        f"<script>const figure = {figure.to_json()};{_MEASURE}</script>"
    )
