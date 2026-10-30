# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The markup a card, a banner, and a reliability tile are drawn as.

Every panel on the page is a card, and what makes one is written here rather
than by anything Streamlit draws: the hidden mark the stylesheet selects a
card's container by, together with the title and optional subtitle above it
and the muted notes a card can close on beneath its figure, the stack of
banners the page opens with, and the strip of tiles a window's run health is
read off. The three sit in one owner because each is a string
handed to `st.markdown(unsafe_allow_html=True)` whose class names are the ones
`css.py` writes rules for -- a header spelled in one module and a tile in
another are two places the chrome can stop agreeing with the stylesheet it is
painted by.

What a card is *told* stays elsewhere. A banner arrives as the `insights.py`
shape a crossing is raised as, so this owner decides only the glyph and the
class its severity paints through, and a severity nothing is mapped for falls
back to the neutral one rather than an empty box. A tile arrives already
reduced by `kpis.py`, and the number on it is rendered by the formatter the
caller hands in: the same strip is drawn beside counts and percentages, so a
value that already reads as text passes through untouched and only a numeric
one is formatted.

Every value a caller passes is escaped on the way in. A repo name, a skill, an
issue title, and a severity all reach a card off the sink rather than out of
this repository, and the whole surface here is markup a browser is asked to
interpret.
"""
from __future__ import annotations

import html
from collections.abc import Sequence

from orchestrator.observability.dashboard.insights import InsightBanner


def card_header_html(title: str, subtitle: str = "") -> str:
    """Build the title and optional subtitle for a dashboard card."""
    subtitle_html = (
        f'<p class="orch-card-sub">{html.escape(subtitle)}</p>'
        if subtitle
        else ""
    )
    return (
        '<span class="orch-cardmark"></span>'
        f'<p class="orch-card-title">{html.escape(title)}</p>{subtitle_html}'
    )


def card_note_html(*notes: str) -> str:
    """Build the muted lines a card closes on beneath its figure, leaving out an empty one."""
    return "".join(
        f'<p class="orch-card-note">{html.escape(note)}</p>' for note in notes if note
    )


def insights_html(banners: Sequence[InsightBanner]) -> str:
    """Render the computed-insight stack."""
    icon_for = {
        "error": "✕",
        "warning": "!",
        "info": "›",
        "success": "✓",
    }
    rows = []
    for banner in banners:
        icon = icon_for.get(banner.severity, "›")
        rows.append(
            f'<div class="orch-insight {html.escape(banner.severity)}">'
            f'<span class="icon">{icon}</span>'
            f'<span>{html.escape(banner.message)}</span>'
            "</div>"
        )
    rows_html = "".join(rows)
    return f'<div class="orch-insights">{rows_html}</div>'


def reliability_tiles_html(tiles: Sequence[tuple], *, fmt_num) -> str:
    """Render the reliability-tile strip to inline HTML."""
    tiles_html = "".join(
        f'<div class="orch-rel-tile {tone}">'
        '<div class="orch-rel-value">'
        f'{html.escape(tile_value if isinstance(tile_value, str) else fmt_num(tile_value))}'
        "</div>"
        f'<div class="orch-rel-label">{html.escape(label)}</div>'
        "</div>"
        for tile_value, label, tone in tiles
    )
    return f'<div class="orch-rel-tiles">{tiles_html}</div>'
