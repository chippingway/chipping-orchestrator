# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a page frames one window with, before any breakdown of it.

These four answer for the window as a whole rather than for a slice of it: the
values its filters can be set to, how far the data behind them reaches, what it
totals, and how those totals move day by day. The first three construct bare,
because "no database configured" and "no rows in the window" are answers a page
renders rather than errors it raises. The series cell is the exception: it is
one row of a `GROUP BY`, so it requires the `(day, event, count)` key it was
grouped on and defaults only the cost and token aggregates hung off that key.

Spend and tokens are carried as the evidence reductions say them, never as one
summed number. A cost is a `CostCohort` -- the runs counted by the completeness
each states beside their amounts by basis -- so a window with no run, a complete
zero, an incomplete subtotal, and an amount nothing states the basis of stay four
answers. A token count is the runs' non-overlapping totals with the runs whose
total is unknown counted beside it, so a known subtotal never reads as the whole;
the series cell also splits its known total into cache, output, and the uncached
input left over, the bands a stack draws without counting a cache token twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from orchestrator.observability.analytics.query.cost_cohorts import EMPTY_COST_COHORT, CostCohort


@dataclass(frozen=True)
class FilterOptions:
    """Distinct values for the dashboard filter dropdowns.

    Tuples (not lists) so the result is hashable and obviously
    immutable to callers that cache it. Empty tuples are the
    documented "DB unset" and "empty table" result -- the dashboard
    should render a disabled filter rather than crash.
    """

    repos: tuple[str, ...] = ()
    events: tuple[str, ...] = ()
    stages: tuple[str, ...] = ()
    backends: tuple[str, ...] = ()
    agent_roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class DataExtent:
    """Earliest and latest event timestamps in the table.

    The dashboard uses this to default the sidebar date picker to a
    window that actually contains data -- a freshly-deployed database
    has no rows, so picking today's date returns nothing. Both fields
    are `None` when the table is empty or when `ANALYTICS_DB_URL` is
    unset; the dashboard branches on that to render a "no data yet"
    state.
    """

    min_ts: datetime | None = None
    max_ts: datetime | None = None


@dataclass(frozen=True)
class Summary:
    """Aggregate counts for a date-bounded window.

    Zero-valued by default so the "DB unset" path can return
    ``Summary()`` and the dashboard renders a still-meaningful page.
    `by_event` and `by_stage` use plain dicts because Streamlit-style
    rendering iterates them; ordering follows the SQL `GROUP BY` so
    the dashboard sees stable counts even if the rows reshuffle
    between queries. `total_agent_runs` / `failed_agent_runs` count
    `event = 'agent_exit'` rows (and the failing subset where
    `exit_code <> 0`) inside the same filtered window so the
    dashboard's "agent success rate" reads off the same query as the
    rest of the overview. `cost` is the window's runs reduced as a
    cost cohort -- an empty one where no run ran -- and
    `total_tokens` the runs' summed non-overlapping totals, with
    `unknown_token_runs` the runs whose total the evidence leaves
    unknown, so where it is nonzero `total_tokens` is a subtotal.
    """

    total_events: int = 0
    distinct_issues: int = 0
    distinct_repos: int = 0
    by_event: dict[str, int] = field(default_factory=dict)
    by_stage: dict[str, int] = field(default_factory=dict)
    total_agent_runs: int = 0
    failed_agent_runs: int = 0
    # Window-wide timeout count -- agent_exit rows whose `timed_out`
    # flag is true. Sourced from the totals query so the redesigned
    # reliability "Timeouts" tile sees every timed-out run in the
    # window, not just the latest N from `get_recent_agent_exits`.
    timed_out_agent_runs: int = 0
    cost: CostCohort = EMPTY_COST_COHORT
    total_tokens: int = 0
    unknown_token_runs: int = 0


@dataclass(frozen=True)
class TimeSeriesPoint:
    """One (day, event, count) cell of the daily time-series.

    `day` is a `date`, not a `datetime`, because the SQL aggregates
    over `date_trunc('day', ts)` and a date matches a Plotly chart's
    axis directly. The cell carries the per-event cost cohort and
    token totals as well so a "spend over time" chart can pivot off
    the same query the activity chart uses -- avoids a second round
    trip for what is already grouped by `(day, event)`. The known
    `total_tokens` is split into `cache_tokens` and `output_tokens`
    -- the cache and output counters inside those totals -- and the
    uncached input left over, so the hero chart's `mode="type"` stack
    draws an Input / Output / Cache stack whose height is the known
    total: a Codex run's cached tokens move from its input band to
    the cache band rather than sitting in both. A run whose total is
    unknown is in none of the bands and is counted in
    `unknown_token_runs` instead. Fields default to zero so a
    fake-cursor fixture that returns just `(day, event, count)` rows
    still validates the no-aggregate path.
    """

    day: date
    event: str
    count: int
    cost: CostCohort = EMPTY_COST_COHORT
    total_tokens: int = 0
    unknown_token_runs: int = 0
    cache_tokens: int = 0
    output_tokens: int = 0

    @property
    def uncached_input_tokens(self) -> int:
        """The known total less its cache and output counters: the input no cache answered."""
        return max(self.total_tokens - self.cache_tokens - self.output_tokens, 0)
