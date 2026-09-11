# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one theme object a page hands every panel it draws.

The panel owners take the theme as a parameter rather than importing one, so
that a section can be rendered against a marking stand-in and so that no owner
under this package binds a page's chrome at import. Something still has to
compose the object they are handed, and this is it: the five style owners --
the palette, the geometry and type tokens, the Plotly layout assembled from
both, the page stylesheet, and the compact formatters -- read back through one
name, so `theme.ACCENT` and the palette's own `ACCENT` are the same value and a
card tinted through either lands on the same hue.

Every name here is the owner's own object, re-exported rather than rebuilt.
This module implements nothing and imports neither Plotly nor Streamlit, so a
caller may name it at module load in an install carrying none of the optional
`dashboard` group.
"""
from __future__ import annotations

from orchestrator.observability.dashboard import palette as _palette, tokens as _tokens
from orchestrator.observability.dashboard.css import PAGE_CSS as PAGE_CSS
from orchestrator.observability.dashboard.formatting import (
    fmt_money as fmt_money,
    fmt_money_exact as fmt_money_exact,
    fmt_num as fmt_num,
    fmt_tokens as fmt_tokens,
)
from orchestrator.observability.dashboard.layout import base_layout as base_layout
from orchestrator.observability.dashboard.palette import color_for as color_for

ACCENT = _palette.ACCENT
AGENT_ROLE_COLORS = _palette.AGENT_ROLE_COLORS
BACKEND_COLORS = _palette.BACKEND_COLORS
BACKGROUND = _palette.BACKGROUND
BORDER = _palette.BORDER
CARD_BG = _palette.CARD_BG
CATEGORICAL_PALETTE = _palette.CATEGORICAL_PALETTE
COST_SOURCE_COLORS = _palette.COST_SOURCE_COLORS
DANGER = _palette.DANGER
EVENT_COLORS = _palette.EVENT_COLORS
GRID = _palette.GRID
INK = _palette.INK
MUTED_TEXT = _palette.MUTED_TEXT
MUTED_TEXT_SOFT = _palette.MUTED_TEXT_SOFT
NEUTRAL = _palette.NEUTRAL
PRIMARY = _palette.PRIMARY
REVIEW_ROUND_COLORS = _palette.REVIEW_ROUND_COLORS
SECONDARY = _palette.SECONDARY
STAGE_COLORS = _palette.STAGE_COLORS
SUCCESS = _palette.SUCCESS
SURFACE = _palette.SURFACE
TEXT = _palette.TEXT
TOKEN_TYPE_COLORS = _palette.TOKEN_TYPE_COLORS
WARNING = _palette.WARNING
CARD_PADDING = _tokens.CARD_PADDING
CONTENT_MAX_WIDTH = _tokens.CONTENT_MAX_WIDTH
FONT_FAMILY = _tokens.FONT_FAMILY
FONT_SIZE = _tokens.FONT_SIZE
GRID_GAP = _tokens.GRID_GAP
MONO_FONT_FAMILY = _tokens.MONO_FONT_FAMILY
RADIUS = _tokens.RADIUS
TITLE_FONT_SIZE = _tokens.TITLE_FONT_SIZE
TOPBAR_STICKY_HEIGHT = _tokens.TOPBAR_STICKY_HEIGHT
