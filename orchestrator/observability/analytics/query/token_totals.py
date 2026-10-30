# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How many tokens a set of agent runs spent, each counted once, and how many runs' totals stay unknown.

Adding a run's raw counters up is wrong for some providers: Codex's `cached_tokens` is part of its input count, so
input plus the cache counters counts those tokens twice, while Claude's cache reads and writes sit beside its input and
belong in the sum. The sync stores each `agent_exit` row's `total_tokens` as `usage.token_evidence` defines it -- every
observed counter once, a cache counter already inside input not added again -- and NULL where the evidence leaves it
unknown: an Antigravity run's cache reads beside its input, whose overlap nothing establishes yet, a record written
before token evidence existed with a nonzero cache counter, and a row stored before the column did.

A sum over those totals is therefore only ever a known subtotal, so each fragment selects two cells: the summed known
totals, and the runs whose total is unknown. A reader that shows the first keeps the second beside it, so a subtotal
never reads as the whole. The fragment is spelled once per scan target: the agent-run view holds only runs, the events
table holds other events whose NULL total states nothing, and the rollup carries the unknown runs pre-counted.
"""

from __future__ import annotations

RUN_TOKEN_TOTAL_SQL = (
    "COALESCE(SUM(total_tokens), 0), "
    "COALESCE(SUM(CASE WHEN total_tokens IS NULL THEN 1 ELSE 0 END), 0)"
)

EVENT_TOKEN_TOTAL_SQL = (
    "COALESCE(SUM(total_tokens), 0), "
    "COALESCE(SUM(CASE WHEN event = 'agent_exit' AND total_tokens IS NULL THEN 1 ELSE 0 END), 0)"
)

ROLLUP_TOKEN_TOTAL_SQL = (
    "COALESCE(SUM(total_tokens), 0), "
    "COALESCE(SUM(total_tokens_unknown_runs), 0)"
)
