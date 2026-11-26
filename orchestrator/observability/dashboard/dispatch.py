# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How one page load's two waves are driven, and what a failed one says.

The plan owner says what a load reads and the fan-out says how a wave of it
runs; what is decided here is the order a page paints in around the two. Both
waves are dispatched inside a single spinner, with the first-wave render
between them, so an operator watches one loading indicator over the whole load
rather than one per wave -- and the chrome that render draws is on screen
before the ten panel reads beneath it are issued.

That render is also where a load can end early. A window holding no rows has
nothing for those panels to draw, so a first-wave render reporting nothing back
short-circuits the second wave entirely and the load is left unlogged here: the
caller that drew the empty-window banner is the one that measures it, because
the reads it spent are the seven already issued rather than all seventeen.

A read that cannot reach the database is answered rather than reported. The
first failing reader arrives as the connection owner's error and becomes one
banner naming what to check, followed by the stop that ends the script -- a
page whose window, tiles, and every panel below them each raised their own
trace would say the same thing seventeen times.

Every load that does complete emits one line, because the fan-out is an
operator's switch rather than a setting: the wall clock it took, how many reads
were behind it, and which way those were issued are what make the two branches
comparable from a single grep of the Streamlit log.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from time import perf_counter
from typing import Any

from orchestrator.observability.analytics.query import connections
from orchestrator.observability.dashboard import fanout, read_plan

LOADING_INDICATOR_MESSAGE = "Loading analytics…"
ReadResults = dict[str, Any]
# Named as a literal rather than taken from `__name__`: an operator's level and
# handler selection over the Streamlit log picks the load line out by logger, so
# the name has to stay put while the module holding it moves.
log = logging.getLogger("orchestrator._dashboard_read_dispatch")


def dispatch_reads(readers, *, st: Any, parallel: bool):
    """Run one wave and answer a failed read with a single banner."""
    try:
        return fanout.fan_out_reads(readers, parallel=parallel)
    except connections.AnalyticsReadError as error:
        st.error(
            f"Analytics query failed: {error}. The dashboard cannot render "
            "without database access; check Postgres connectivity and reload."
        )
        st.stop()


def log_dashboard_load(
    *,
    load_start: float,
    reads: int,
    parallel: bool,
) -> None:
    """Emit the one line a completed load is measured by."""
    log.info(
        "dashboard.load: total=%.1fs reads=%d parallel=%s",
        perf_counter() - load_start,
        reads,
        "true" if parallel else "false",
    )


def run_read_waves(
    reads: read_plan.DashboardReadPlan,
    *,
    st: Any,
    render_first_wave: Callable[[ReadResults], Any],
) -> tuple[ReadResults, Any] | None:
    """Dispatch both read waves and merge their data."""
    with st.spinner(LOADING_INDICATOR_MESSAGE):
        read_results = dispatch_reads(
            reads.first_wave,
            st=st,
            parallel=reads.parallel,
        )
        first_wave = render_first_wave(read_results)
        if first_wave is None:
            return None
        read_results.update(
            dispatch_reads(
                reads.second_wave,
                st=st,
                parallel=reads.parallel,
            )
        )
    log_dashboard_load(
        load_start=reads.started_at,
        reads=reads.total_reads,
        parallel=reads.parallel,
    )
    return read_results, first_wave
