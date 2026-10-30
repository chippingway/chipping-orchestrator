# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the hero card stacks, and what the toggle above it remembers.

The chart builder is stubbed out, so what a case reads back is the rows, mode,
and title the card asked for rather than a figure. That request is the boundary
worth pinning here: the figure itself belongs to the chart owner, and this card
is what decides which stack that owner is asked to draw.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.observability.dashboard import card_html, usage_panel
from tests.observability.dashboard.usage_panel_test_support import (
    CLAUDE,
    CODEX,
    FIGURE,
    MAY01,
    MAY07,
    HeroStreamlit,
    backend_row,
)

# One backend day read back twice, so a case can tell a summed cell from the
# last one written.
_FIRST_HALF = 10

_SECOND_HALF = 5

_CODEX_TOKENS = 3

_LATER_DAY_TOKENS = 8

_UNKNOWN_RUNS = 2

_CHART_BUILDER = "usage_over_time"


def _render(
    *,
    picks: str = usage_panel.TOKEN_TYPE_MODE,
    backend_daily_rows=(),
    ts_points=(),
) -> tuple:
    """Drive one render, returning the fake page and the chart request."""
    st = HeroStreamlit(picks)
    with patch.object(
        usage_panel, _CHART_BUILDER, return_value=FIGURE,
    ) as chart:
        usage_panel.render_hero_usage(
            st=st,
            ts_points=ts_points,
            backend_daily_rows=backend_daily_rows,
        )
        request = chart.call_args
    return st, request


class BackendTokensByDayTest(unittest.TestCase):
    """A window's backend rows are totalled per day before they are stacked."""

    def test_repeated_cells_are_summed(self) -> None:
        # The same `(day, backend)` pair can arrive more than once, so a band
        # drawn off the raw rows would report the last cell, not the day. The
        # runs of unknown total are summed per day beside the tokens, since
        # they are this read's own count of what its stack leaves out.
        totals = usage_panel.backend_tokens_by_day([
            backend_row(total_tokens=_FIRST_HALF, unknown_token_runs=1),
            backend_row(total_tokens=_SECOND_HALF, unknown_token_runs=_UNKNOWN_RUNS),
            backend_row(backend=CODEX, total_tokens=_CODEX_TOKENS),
            backend_row(day=MAY07, total_tokens=_LATER_DAY_TOKENS),
        ])
        self.assertEqual(
            totals.tokens,
            {
                MAY01: {
                    CLAUDE: float(_FIRST_HALF + _SECOND_HALF),
                    CODEX: float(_CODEX_TOKENS),
                },
                MAY07: {CLAUDE: float(_LATER_DAY_TOKENS)},
            },
        )
        self.assertEqual(totals.unknown_runs, {MAY01: 1 + _UNKNOWN_RUNS, MAY07: 0})
        # The stack walks the totals as a mapping of day to backend tokens.
        self.assertEqual(dict(totals), totals.tokens)

    def test_a_missing_total_counts_as_nothing(self) -> None:
        totals = usage_panel.backend_tokens_by_day([
            backend_row(total_tokens=None, unknown_token_runs=None),
        ])
        self.assertEqual(totals.tokens, {MAY01: {CLAUDE: float(0)}})
        self.assertEqual(totals.unknown_runs, {MAY01: 0})


class StackModeOptionTest(unittest.TestCase):
    """Each mode is named and placed the same way the toggle offers it."""

    def test_each_mode_is_named_and_placed_alike(self) -> None:
        # The label and the index are one choice read from two ends: what the
        # option says, and where the radio opens on it.
        for mode, label, index in (
            (usage_panel.TOKEN_TYPE_MODE, "By token type", 0),
            (usage_panel.BACKEND_MODE, "By backend", 1),
        ):
            with self.subTest(mode=mode):
                self.assertEqual(usage_panel.stack_mode_label(mode), label)
                self.assertEqual(usage_panel.stack_mode_index(mode), index)


class SelectStackModeTest(unittest.TestCase):
    """The toggle opens on the remembered mode and keeps what was picked."""

    def test_a_first_render_defaults_to_token_type(self) -> None:
        st = HeroStreamlit()
        usage_panel.select_stack_mode(st)
        self.assertEqual(
            st.session_state[usage_panel.STACK_MODE_STATE_KEY],
            usage_panel.TOKEN_TYPE_MODE,
        )
        self.assertEqual(st.radios[0]["index"], 0)

    def test_the_radio_opens_on_the_remembered_mode(self) -> None:
        # Streamlit reruns the whole script on every interaction, so a radio
        # seeded from anything but the remembered mode would snap the card
        # back to the default stack whenever a filter beside it moved.
        st = HeroStreamlit()
        st.session_state[usage_panel.STACK_MODE_STATE_KEY] = (
            usage_panel.BACKEND_MODE
        )
        usage_panel.select_stack_mode(st)
        self.assertEqual(st.radios[0]["index"], 1)

    def test_the_picked_mode_survives_the_next_rerun(self) -> None:
        st = HeroStreamlit(usage_panel.BACKEND_MODE)
        picked = usage_panel.select_stack_mode(st)
        self.assertEqual(picked, usage_panel.BACKEND_MODE)
        self.assertEqual(
            st.session_state[usage_panel.STACK_MODE_STATE_KEY],
            usage_panel.BACKEND_MODE,
        )

    def test_the_toggle_is_a_collapsed_inline_radio(self) -> None:
        # The card header already names the panel, so the radio's own label is
        # collapsed rather than repeated above the two options. The widget key
        # is Streamlit's and stays apart from the one the mode is remembered
        # under, which the widget's own reset must not take with it.
        st = HeroStreamlit()
        usage_panel.select_stack_mode(st)
        drawn = st.radios[0]
        self.assertEqual(drawn["label"], usage_panel.STACK_MODE_LABEL)
        self.assertEqual(
            drawn["options"],
            (usage_panel.TOKEN_TYPE_MODE, usage_panel.BACKEND_MODE),
        )
        self.assertIs(drawn["format_func"], usage_panel.stack_mode_label)
        self.assertIs(drawn["horizontal"], True)
        self.assertEqual(drawn["label_visibility"], "collapsed")
        self.assertEqual(drawn["key"], usage_panel.STACK_MODE_WIDGET_KEY)
        self.assertNotEqual(
            usage_panel.STACK_MODE_WIDGET_KEY,
            usage_panel.STACK_MODE_STATE_KEY,
        )


class RenderHeroUsageTest(unittest.TestCase):
    """The card titles itself, and hands the chart the stack that was picked."""

    def test_the_card_is_headed_by_the_shared_markup(self) -> None:
        # Every panel on the page is headed by the one markup owner, so this
        # card is titled the way the ones under it are rather than by markup of
        # its own the stylesheet would have to be taught about.
        st, _ = _render()
        self.assertEqual(
            st.markdowns,
            [card_html.card_header_html(
                usage_panel.CARD_TITLE, usage_panel.CARD_SUBTITLE,
            )],
        )

    def test_the_type_stack_asks_for_no_backend_rows(self) -> None:
        # The time-series points already carry the per-type bands, so totalling
        # a window's backend rows for this stack is work no trace reads.
        _, request = _render(backend_daily_rows=[backend_row()])
        self.assertIsNone(request.kwargs["backend_rows_by_day"])
        self.assertEqual(request.kwargs["mode"], usage_panel.TOKEN_TYPE_MODE)

    def test_the_backend_stack_gets_per_day_totals(self) -> None:
        _, request = _render(
            picks=usage_panel.BACKEND_MODE,
            backend_daily_rows=[
                backend_row(total_tokens=_FIRST_HALF),
                backend_row(total_tokens=_SECOND_HALF),
            ],
        )
        backend_rows = request.kwargs["backend_rows_by_day"]
        day_tokens = float(_FIRST_HALF + _SECOND_HALF)
        self.assertEqual(backend_rows.tokens, {MAY01: {CLAUDE: day_tokens}})
        self.assertEqual(backend_rows.unknown_runs, {MAY01: 0})
        self.assertEqual(request.kwargs["mode"], usage_panel.BACKEND_MODE)

    def test_the_figure_carries_no_title_of_its_own(self) -> None:
        # The card header above it already names the panel, so a figure title
        # would print the same line twice.
        points = object()
        _, request = _render(ts_points=points)
        self.assertEqual(request.args, (points,))
        self.assertIsNone(request.kwargs["title"])

    def test_plotly_is_handed_a_plain_config_copy(self) -> None:
        # The shared defaults are a read-only proxy, which is not
        # JSON-serializable, and one call site mutating a copy must not reach
        # the panel drawn after it.
        st, _ = _render()
        figure, options = st.charts[0]
        self.assertIs(figure, FIGURE)
        self.assertIs(options["use_container_width"], True)
        handed = options["config"]
        self.assertEqual(handed, dict(usage_panel.PLOTLY_CONFIG))
        self.assertIsInstance(handed, dict)
        self.assertIsNot(handed, usage_panel.PLOTLY_CONFIG)


if __name__ == "__main__":
    unittest.main()
