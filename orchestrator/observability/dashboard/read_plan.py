# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one page load reads, split into the two waves it is drawn in.

A wave is the list of named readers `fanout` runs, so the whole of this owner
is which adapter each entry spends its key on and which of the two waves it
belongs to. The split is what lets the page paint before the load finishes:
the first wave is exactly the reads the chrome above the fold is reduced from,
so the topbar, the KPI strip, and the window banner can render while the ten
panels beneath them are still being read. Keeping both registries here rather
than beside the sections that draw them is what makes that boundary readable
-- a read moved between waves changes what renders early, which is a decision
about the page rather than about the panel it feeds.

Nothing is read while a wave is built. Each entry is a name and the adapter
with its key already bound, because a parallel load runs those callables on
worker threads, and a thread that is not the one Streamlit renders on may not
write to the page. The heatmap is the single entry carrying a second bound
argument: a display offset changes which cell a row is counted into rather
than which rows the window holds, so it travels beside the key instead of
inside it.

Every entry is cached rather than issued directly, and the TTL is the one
number that decision carries. Streamlit reruns the whole script on every
widget interaction, so an uncached wave would put seventeen queries on Postgres
for each nudge of the filter bar. A minute bounds the other direction: a window
nobody changes goes back to Postgres on the first rerun after that minute is
up, so newly synced events reach a page left open on it within one, and every
rerun until then is answered out of the cache.

The keys those entries are bound to are hashed as a pair, because the delta
pills and the cost-trend banner report this window against the one before it.
Both are hashed by the filter owner off the same repo, event, stage, and issue
selections, and the earlier span is measured by the window owner's own
arithmetic, so the two windows a page compares cannot end up narrowed
differently.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any

from orchestrator.observability.dashboard import (
    breakdowns,
    fanout,
    filters,
    rollups,
    skills,
    windows,
)

WIDGET_CACHE_TTL_SECONDS = 60


@dataclass(frozen=True)
class DashboardReadPlan:
    first_wave: Sequence[fanout.NamedReader]
    second_wave: Sequence[fanout.NamedReader]
    parallel: bool
    started_at: float

    @property
    def total_reads(self) -> int:
        return len(self.first_wave) + len(self.second_wave)


def widget_task(
    st: Any,
    name: str,
    reader: Callable[..., Any],
    *args: Any,
) -> fanout.NamedReader:
    """Name one cached read and bind what it is issued under."""
    cached_reader = st.cache_data(
        show_spinner=False,
        ttl=WIDGET_CACHE_TTL_SECONDS,
    )(reader)
    return name, partial(cached_reader, *args)


def first_wave_readers(
    st: Any,
    key: tuple,
    prev_key: tuple,
) -> list[fanout.NamedReader]:
    """The seven reads the chrome above the fold, the Cost details section among it, is drawn from."""
    return [
        widget_task(st, "summary", rollups.read_summary, key),
        widget_task(st, "prev_summary", rollups.read_prev_kpi, prev_key),
        widget_task(st, "ts_points", rollups.read_time_series, key),
        widget_task(st, "review_round_rows", rollups.read_review_round, key),
        widget_task(st, "throughput_rows", breakdowns.read_throughput, key),
        widget_task(
            st,
            "cost_coverage_rows",
            breakdowns.read_cost_coverage,
            key,
        ),
        widget_task(
            st,
            "unpriced_reason_rows",
            breakdowns.read_unpriced_reasons,
            key,
        ),
    ]


def second_wave_readers(
    st: Any,
    key: tuple,
    tz_offset_choice: int,
) -> list[fanout.NamedReader]:
    """The ten reads the panels beneath that chrome are drawn from."""
    return [
        widget_task(st, "stage_rows", rollups.read_stage_breakdown, key),
        widget_task(st, "agent_exits", rollups.read_recent_agent_exits, key),
        widget_task(st, "issues_rows", rollups.read_top_cost_issues, key),
        widget_task(st, "backend_rows", breakdowns.read_backend_efficiency, key),
        widget_task(st, "repo_rows", breakdowns.read_repo_breakdown, key),
        widget_task(
            st,
            "heatmap_rows",
            breakdowns.read_hourly_heatmap,
            key,
            int(tz_offset_choice),
        ),
        widget_task(
            st,
            "backend_daily_rows",
            breakdowns.read_backend_daily_tokens,
            key,
        ),
        widget_task(st, "skill_adoption_rows", skills.read_skill_adoption, key),
        widget_task(st, "skill_rows", skills.read_skill_trigger_rates, key),
        widget_task(
            st,
            "skill_matrix_rows",
            skills.read_skill_trigger_matrix,
            key,
        ),
    ]


def widget_readers(*, st: Any, key, prev_key, tz_offset_choice: int):
    """Return the first and second cached read waves."""
    return (
        first_wave_readers(st, key, prev_key),
        second_wave_readers(st, key, tz_offset_choice),
    )


def build_read_keys(
    *,
    window: windows.DateWindow,
    repo_filter: str | None,
    event_filter: Sequence[str] | None,
    stage_filter: Sequence[str] | None,
    issue_filter: int | None,
):
    """Build current and previous-window cache keys."""
    key = filters.cache_key(
        window,
        repo_filter,
        event_filter,
        stage_filter,
        issue_filter,
    )
    prev_key = filters.cache_key(
        windows.previous_window(window),
        repo_filter,
        event_filter,
        stage_filter,
        issue_filter,
    )
    return key, prev_key
