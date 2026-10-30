# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The page surface the hero card is drawn onto, faked.

Streamlit is in the optional `dashboard` group and the card is handed its `st`
rather than reaching for one, so the cases drive a whole render against a
stand-in that records what each call was given. Session state is a plain dict
because that is the whole of what the card asks of it -- read a remembered
mode, write the picked one -- and a rerun is modelled by seeding that dict
before the render rather than by driving two.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Self

from orchestrator.observability.analytics.query.activity_models import (
    BackendDailyTokensRow,
)
from orchestrator.observability.dashboard import usage_panel

_YEAR = 2026

_MAY = 5

MAY01 = date(_YEAR, _MAY, 1)

MAY07 = date(_YEAR, _MAY, 7)

CLAUDE = "claude"

CODEX = "codex"

# What the stubbed chart builder hands back, so a case can tell the figure the
# card forwarded from anything it built itself.
FIGURE = object()


class NullContext:
    """`with`-usable stand-in for `st.container(...)`."""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exception: object) -> bool:
        return False


class HeroStreamlit:
    """Fake `st` recording the toggle it drew and the chart it was handed."""

    def __init__(self, picks: str = usage_panel.TOKEN_TYPE_MODE) -> None:
        self.session_state: dict[str, str] = {}
        self.markdowns: list[str] = []
        self.radios: list[dict] = []
        self.charts: list[tuple] = []
        self.picks = picks

    def container(self, **options: Any) -> NullContext:
        return NullContext()

    def markdown(self, markup: str, **options: Any) -> None:
        self.markdowns.append(markup)

    def radio(self, label: str, **options: Any) -> str:
        self.radios.append({"label": label, **options})
        return self.picks

    def plotly_chart(self, figure: Any, **options: Any) -> None:
        self.charts.append((figure, options))


def backend_row(
    *,
    day: date = MAY01,
    backend: str = CLAUDE,
    total_tokens: int = 0,
    unknown_token_runs: int = 0,
) -> BackendDailyTokensRow:
    """One `(day, backend)` cell of the per-backend series: its known total and its runs of unknown total."""
    return BackendDailyTokensRow(
        day=day,
        backend=backend,
        total_tokens=total_tokens,
        unknown_token_runs=unknown_token_runs,
    )
