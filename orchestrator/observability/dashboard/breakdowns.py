# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The seven panel reads a page's comparison sections are drawn from.

Each one is a window already decided: the page hashed its filters into a cache
key, and what is left to say is which read that key is spent on. So the whole
of an adapter here is a query owner's read named beside the binding that issues
it, and everything under that -- the socket it runs on, the filters the key is
read back as, and the empty answer an unconfigured database yields -- is
decided by the owners it passes through rather than restated per panel.

Each names the query owner that defines it, so a patch aimed at a read lands
where the panel issues it. Which owner that is follows the column a
read groups by: a backend comparison, a per-repository tally, and a daily
resolved/rejected count are all day-bucketed, so they are the rollup's; a cost
source, why a run went unpriced, one run's own token split, and an hour of day
are what that bucket threw away, so they are the breakdown family's.

The activity heatmap is the one adapter carrying a filter of its own. A display
offset changes which weekday-and-hour cell a row is counted into rather than
which rows the window holds, so it travels beside the key instead of inside it
-- which is why it is also the one signature here that is not the key alone.
"""
from __future__ import annotations

from orchestrator.observability.analytics.query import breakdown_reads, rollup_reads
from orchestrator.observability.dashboard import filter_binding


def read_backend_efficiency(key: tuple):
    """Read per-backend agent-run efficiency across the window."""
    return filter_binding.read_filtered(
        rollup_reads.get_backend_efficiency,
        key,
    )


def read_repo_breakdown(key: tuple):
    """Read per-repository activity across the window."""
    return filter_binding.read_filtered(rollup_reads.get_repo_breakdown, key)


def read_cost_coverage(key: tuple):
    """Read token volume grouped by the source its cost was priced from."""
    return filter_binding.read_filtered(
        breakdown_reads.get_cost_coverage,
        key,
    )


def read_unpriced_reasons(key: tuple):
    """Read the window's unpriced runs counted per model and the reason each gave."""
    return filter_binding.read_filtered(
        breakdown_reads.get_unpriced_reasons,
        key,
    )


def read_hourly_heatmap(key: tuple, tz_offset_hours: int):
    """Read weekday-by-hour activity cells in the displayed timezone."""
    return filter_binding.read_filtered(
        breakdown_reads.get_hourly_heatmap,
        key,
        tz_offset_hours=tz_offset_hours,
    )


def read_throughput(key: tuple):
    """Read the daily resolved and rejected issue counts."""
    return filter_binding.read_filtered(
        rollup_reads.get_throughput_breakdown,
        key,
    )


def read_backend_daily_tokens(key: tuple):
    """Read daily token totals grouped by backend."""
    return filter_binding.read_filtered(
        breakdown_reads.get_backend_daily_tokens,
        key,
    )
