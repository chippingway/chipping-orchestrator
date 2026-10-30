# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The rows a read hands back bucketed by when the work happened.

Each row here is one time cell -- a day, or an hour of a weekday -- and carries
the volume measured in it rather than a rate derived from it. Keeping the cell
raw is what lets the page above choose the presentation: a Monday-first
heatmap, a stacked throughput bar, a per-backend token series.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class BackendDailyTokensRow:
    """One `(day, backend, total_tokens)` cell of the per-backend daily
    token series.

    Powers the redesigned dashboard's "By backend" toggle on the hero
    spend & token usage chart. Reading off `analytics_agent_runs` (a
    view over `event = 'agent_exit'` rows) means the chart never
    silently caps at the `get_recent_agent_exits` `LIMIT` -- every
    backend's tokens get counted across the full window, in lockstep
    with the cost line and KPI aggregates. `total_tokens` sums the
    runs' non-overlapping totals; `unknown_token_runs` counts the runs
    whose total the evidence leaves unknown, so where it is nonzero
    `total_tokens` is a subtotal of the others.
    """

    day: date
    backend: str
    total_tokens: int
    unknown_token_runs: int = 0


@dataclass(frozen=True)
class HourlyHeatmapPoint:
    """One (weekday, hour, count, total_tokens) cell of the 7x24
    activity matrix.

    `weekday` follows Postgres `EXTRACT(DOW)` which is 0=Sunday;
    the dashboard chart re-orders to a Monday-first layout if the
    operator prefers (we expose the raw value so the chart layer
    owns the presentation choice). `hour` is the hour of day in
    the same timezone the database stores `ts` in (the orchestrator
    writes UTC). `count` is the per-cell event count; `total_tokens`
    is the matching token volume -- the agent runs' non-overlapping
    totals -- so the redesigned dashboard's "When agents run"
    heatmap can render token intensity (matching the standalone
    mock) rather than event intensity, which would over-weight the
    cheap `stage_enter` / `stage_evaluation` cells against the
    `agent_exit` rows that actually drive spend. `unknown_token_runs`
    counts the cell's agent runs whose total the evidence leaves
    unknown; where it is nonzero `total_tokens` is a subtotal.
    """

    weekday: int
    hour: int
    count: int
    total_tokens: int = 0
    unknown_token_runs: int = 0


@dataclass(frozen=True)
class ThroughputDayRow:
    """One day's resolved / rejected throughput count.

    Powers the dashboard's "issues resolved per day" chart: counts
    `stage_enter` rows whose `stage` is `done` (resolved) or
    `rejected` (closed without merge), grouped by day. The two
    columns are reported side by side so the chart can stack /
    group them without a second query.
    """

    day: date
    resolved: int = 0
    rejected: int = 0
