# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a run on one backend is worth, and the card it is read off.

One card per backend answers a single question -- what work on this agent
costs -- so the readings behind it sit beside the markup rather than in the
page drawing it. The spend is the backend's cost cohort, worded the way the
overview words a window: the amount its runs state, or the word standing where
they state none, with the basis beneath it -- an Antigravity backend's amount
a Gemini API token estimate, a mixed one blended with each basis's amount --
and why it falls short of complete spend.

Three ratios follow: what a million tokens cost, what one run cost, and how
much of the input side of the declared token totals went through the cache.
The tokens are the runs' declared non-overlapping totals, so a Codex run's
cached input is counted once, inside its input, and the cache share divides
the cache counters inside those totals by the totals less their output. A
ratio is never shown as though both of its sides were whole. One whose
denominator is zero, whose numerator states no amount, or whose tokens are a
subtotal -- the cost per token then divides the cost of runs whose tokens it
does not count -- is unavailable and reads as a dash. A money ratio over an
amount short of complete spend is qualified the way the amount is, and a cache
share over known totals leaving some run out says so; the count of those runs
closes the card.

The theme is a parameter rather than an import, the way every card builder on
this page is handed one: a page resolves a single theme object and passes it
down, so the border, the type, the token formatter, and the per-backend hue a
card is drawn in are the ones the chrome and charts around it were drawn from.
The backend name reaches this owner off the sink rather than out of this
repository, so it is escaped into the markup a browser is asked to interpret,
as is every worded figure and note.
"""
from __future__ import annotations

import html
from dataclasses import dataclass

from orchestrator.observability.analytics.query.cost_models import (
    BackendEfficiencyRow,
)
from orchestrator.observability.dashboard import cost_text, spend_text

_TOKENS_PER_MILLION = 1_000_000

_PERCENT = 100

# What a ratio reads as where one of its sides leaves nothing to divide.
_UNAVAILABLE = "—"


@dataclass(frozen=True)
class BackendEfficiencyMetrics:
    """The card's three ratios, each None where it is unavailable."""

    tokens: int
    cost_per_million: float | None
    cost_per_run: float | None
    cache_share_pct: float | None


def safe_ratio(numerator: float | None, denominator: float) -> float | None:
    """Divide, or answer None where either side leaves nothing to divide."""
    if numerator is None or denominator <= 0:
        return None
    return numerator / denominator


def backend_efficiency_metrics(
    row: BackendEfficiencyRow,
) -> BackendEfficiencyMetrics:
    """The ratios one backend's row is reported by, over its stated amount and declared token totals."""
    spend = row.cost.evidence.total_usd
    # A token subtotal leaves out tokens the amount was stated for, so no cost per token divides by it.
    priced_tokens = 0 if row.unknown_token_runs else row.total_tokens
    cache_share = safe_ratio(row.cache_tokens, row.input_side_tokens)
    return BackendEfficiencyMetrics(
        tokens=row.total_tokens,
        cost_per_million=safe_ratio(spend, priced_tokens / _TOKENS_PER_MILLION),
        cost_per_run=safe_ratio(spend, row.runs),
        cache_share_pct=None if cache_share is None else cache_share * _PERCENT,
    )


def backend_ratio_texts(row: BackendEfficiencyRow) -> tuple[str, str, str]:
    """The three ratios as a card words them: a dash where unavailable, each qualified where its sides fall short."""
    metrics = backend_efficiency_metrics(row)
    shortfall = cost_text.completeness_text(row.cost.evidence)
    share = metrics.cache_share_pct
    return (
        _ratio_text(_money(metrics.cost_per_million), "/ 1M tok", shortfall),
        _ratio_text(
            None if share is None else f"{share:.0f}%",
            "input via cache",
            "known totals" if row.unknown_token_runs else "",
        ),
        _ratio_text(_money(metrics.cost_per_run), "/ run", shortfall),
    )


def backend_efficiency_card_html(row: BackendEfficiencyRow, *, theme) -> str:
    """Render one backend-efficiency card to inline HTML."""
    color = theme.color_for(row.backend, explicit=theme.BACKEND_COLORS)
    note_style = f"color:{theme.MUTED_TEXT};font-size:11px;font-family:{theme.FONT_FAMILY}"
    ratios = "</span><span>".join(map(html.escape, backend_ratio_texts(row)))
    token_note = html.escape(spend_text.token_note(row.unknown_token_runs))
    token_line = f'<div style="{note_style};margin-top:4px">{token_note}</div>' if token_note else ""
    return (
        f'<div style="border:1px solid {theme.BORDER};'
        "border-radius:8px;padding:10px 12px;"
        'margin-bottom:8px">'
        '<div style="display:flex;align-items:center;'
        'gap:8px;margin-bottom:4px">'
        '<span style="display:inline-block;width:10px;'
        f'height:10px;border-radius:50%;background:{color}">'
        "</span>"
        f'<b style="color:{theme.TEXT}">{html.escape(row.backend)}</b>'
        f'<span style="color:{theme.MUTED_TEXT};'
        'font-size:12px;margin-left:auto">'
        f'{row.runs} runs · {html.escape(theme.fmt_tokens(row.total_tokens))} tok'
        "</span></div>"
        f'<div style="color:{theme.TEXT};font-size:20px;'
        "font-weight:600;"
        f'font-family:{theme.MONO_FONT_FAMILY}">'
        f"{html.escape(spend_text.spend_figure(row.cost))}"
        f'<span style="color:{theme.MUTED_TEXT};'
        "font-size:11px;margin-left:8px;"
        f'font-family:{theme.FONT_FAMILY}">spend</span></div>'
        f'<div style="{note_style};margin-bottom:6px">'
        f"{html.escape(spend_text.spend_note(row.cost))}</div>"
        '<div style="display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;'
        f'color:{theme.MUTED_TEXT}"><span>{ratios}</span></div>'
        f"{token_line}</div>"
    )


def _money(amount: float | None) -> str | None:
    return None if amount is None else cost_text.fmt_cost_usd(amount)


def _ratio_text(spelled: str | None, unit: str, note: str) -> str:
    """One ratio as the card words it: a dash where it was not taken, and its qualifier beside it where it was."""
    if spelled is None:
        return f"{_UNAVAILABLE} {unit}"
    return f"{spelled} {unit} ({note})" if note else f"{spelled} {unit}"
