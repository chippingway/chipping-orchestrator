# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How a group's stated cost is split by token share, and the three bands the split is read back as.

Nothing the sink holds says what a run's cached tokens cost: a CLI reports one total and an estimate stores one amount
per basis, never a cache charge. The cache and no-cache bands a spend panel stacks are therefore an allocation rather
than a measurement. Each row's stated amount -- `cost_cohorts.STATED_USD_SQL`, every basis added -- is weighted by the
share of its declared non-overlapping token total that its cache counters hold, and the rest of the amount is the
no-cache band. The share is read off the declared total rather than the raw counters, so a Codex run's cached input,
which its provider counts inside its input, sits in the cache share once rather than being added to the input that
holds it.

A share exists only where the declared total does. A run whose total the evidence leaves unknown -- an Antigravity
run's cache reads beside its input, a record an earlier build wrote with a nonzero cache counter, a row stored before
the column -- has no share to split by, and neither does a total of zero. Its amount lands whole in a third band,
unsplit, rather than in no-cache, where it would read as spend no cache touched. The three bands add back up to the
amount the group's runs state, so a panel stacks them to the length its cohort states, a subtotal at its known part.

The fragment is spelled once per scan target. On the agent-run view a row is one run, with `total_cache_tokens` its
cache counters. On the rollup a row is a day's bucket of runs, split only where every run in it has a declared total
(`total_tokens_unknown_runs` is zero), with `cache_tokens_in_total` the cache counters inside those totals. Both select
`TOKEN_SHARE_WIDTH` cells in the order `token_share_bands` reads them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from orchestrator.observability.analytics.query.cost_cohorts import STATED_USD_SQL

TOKEN_SHARE_WIDTH = 3

_STATED = f"({STATED_USD_SQL})"

_DECLARED_TOTAL = "total_tokens::numeric"


def _token_share_sql(shared: str, cache_tokens: str) -> str:
    """The band cells over rows where `shared` holds, whose declared `total_tokens` holds `cache_tokens`."""
    return ", ".join((
        f"SUM(CASE WHEN {shared} THEN {_STATED} * {cache_tokens} / {_DECLARED_TOTAL} END)",
        f"SUM(CASE WHEN {shared} THEN {_STATED} * (total_tokens - {cache_tokens}) / {_DECLARED_TOTAL} END)",
        f"SUM(CASE WHEN {shared} THEN NULL ELSE {_STATED} END)",
    ))


RUN_TOKEN_SHARE_SQL = _token_share_sql("total_tokens > 0", "total_cache_tokens")

ROLLUP_TOKEN_SHARE_SQL = _token_share_sql(
    "COALESCE(total_tokens_unknown_runs, 0) = 0 AND total_tokens > 0",
    "COALESCE(cache_tokens_in_total, 0)",
)


@dataclass(frozen=True)
class TokenShareBands:
    """A group's stated amount allocated by its runs' token share: never what any cache was charged.

    `cache_usd` and `no_cache_usd` split the amounts whose runs declared a token total, by the cache counters' share of
    it; `unsplit_usd` is the amount of the runs whose total is unknown or zero, which no share divides.
    """

    cache_usd: float = field(default_factory=float)
    no_cache_usd: float = field(default_factory=float)
    unsplit_usd: float = field(default_factory=float)


def token_share_bands(row: Sequence[Any], start: int = 0) -> TokenShareBands:
    """Read the cells a token-share fragment selected, from `start` on; a row too narrow to hold them raises.

    A band no row contributed to sums to NULL, which is an empty band: the amount it would hold is in another one, or
    the group states none, which its cost cohort says.
    """
    cells = tuple(row[start:start + TOKEN_SHARE_WIDTH])
    if len(cells) != TOKEN_SHARE_WIDTH:
        raise ValueError(f"a token share is {TOKEN_SHARE_WIDTH} cells; the row holds {len(cells)} from {start}")
    return TokenShareBands(*(float(cell or 0) for cell in cells))


NO_TOKEN_SHARE = TokenShareBands()
