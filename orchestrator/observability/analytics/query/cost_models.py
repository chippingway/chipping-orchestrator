# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The rows one window's spend is broken down into.

Each row here answers "where did the money go" along one axis -- review round,
backend, repo, or the pricing source the parser could attach -- so the NULL
bucketing under `"unknown"` and the token totals a ratio divides by are
declared once per axis rather than re-derived by every chart that plots one.

Money is carried as the evidence the sync filed rather than as one summed
amount. A group's cost is the `CostCohort` its runs fold to -- each basis's
amount, an estimate's rate dates, and the runs counted by the completeness
each states -- so a breakdown words a CLI-reported amount, one provider's
estimate, a blended total with its parts, an unpriced group, and an amount
with no basis apart, and never shows a subtotal as the whole. Tokens are the
runs' declared non-overlapping totals with the runs whose total is unknown
counted beside them. The cache and no-cache bands a review round is stacked
into are `TokenShareBands`: the stated amount allocated by token share, never
a measured cache charge.
"""

from __future__ import annotations

from dataclasses import dataclass

from orchestrator.observability.analytics.query.cache_shares import NO_TOKEN_SHARE, TokenShareBands
from orchestrator.observability.analytics.query.cost_cohorts import EMPTY_COST_COHORT, CostCohort, fold_cohorts


@dataclass(frozen=True)
class ReviewRoundBucketRow:
    """Per-review-round development and review cost of agent runs.

    `bucket` is the categorical round string
    (`0`/`1`/`2`/`3`/`4`/`5`/`6+`, plus `unknown` for NULL rounds);
    `get_review_round_breakdown` derives it from the raw
    `review_round` so rounds 3-5 stay separate and only 6+ is grouped.
    It is exposed verbatim so the dashboard chart's labels can map
    each bucket directly. Every development and review run records its
    round, a fresh implementation as `0`, so a row with
    `review_round IS NULL` surfaces under the `"unknown"` bucket rather
    than in a round it never named.

    `developer_cost` and `reviewer_cost` are the cohorts the round's
    implementation / fix runs and its automated review runs fold to,
    each counting its own runs; `cost` is the two folded together, the
    round's whole cohort. Each role's stated amount is further split
    into `TokenShareBands` -- its cache tokens' share, the rest, and
    the amount of runs whose token total is unknown -- prorated per
    run by token share, so the three add back up to what the role's
    runs state and a chart can stack them without presenting an
    allocation as a cache charge.
    """

    bucket: str
    runs: int
    failed: int = 0
    developer_cost: CostCohort = EMPTY_COST_COHORT
    reviewer_cost: CostCohort = EMPTY_COST_COHORT
    developer_bands: TokenShareBands = NO_TOKEN_SHARE
    reviewer_bands: TokenShareBands = NO_TOKEN_SHARE

    @property
    def developer_runs(self) -> int:
        return self.developer_cost.runs

    @property
    def reviewer_runs(self) -> int:
        return self.reviewer_cost.runs

    @property
    def cost(self) -> CostCohort:
        """The round's two roles folded into one cohort."""
        return fold_cohorts((self.developer_cost, self.reviewer_cost))


@dataclass(frozen=True)
class BackendEfficiencyRow:
    """Per-`backend` aggregate of agent runs.

    Powers the dashboard's "backend efficiency" panel: total runs,
    how many failed, the average wall-clock duration (None when no
    row in the window carried a duration), and what the runs cost as
    a cohort. `total_tokens` is the runs' declared non-overlapping
    totals and `unknown_token_runs` the runs whose total the evidence
    leaves unknown; `cache_tokens` and `output_tokens` are the cache
    and output counters inside those known totals, so the cost per
    token and the cache share divide by tokens each counted once -- a
    Codex run's cached input is not added again beside the input that
    holds it. Rows whose `backend` is NULL bucket under `"unknown"` so
    the chart still surfaces them rather than silently dropping a
    category.
    """

    backend: str
    runs: int
    failed: int = 0
    avg_duration_s: float | None = None
    cost: CostCohort = EMPTY_COST_COHORT
    total_tokens: int = 0
    unknown_token_runs: int = 0
    cache_tokens: int = 0
    output_tokens: int = 0

    @property
    def input_side_tokens(self) -> int:
        """The known totals less their output: the uncached input and the cache tokens, each counted once."""
        return max(self.total_tokens - self.output_tokens, 0)


@dataclass(frozen=True)
class RepoBreakdownRow:
    """Per-`repo` rollup over the filter window.

    The dashboard's "activity by repo" chart plots issue and event
    counts side-by-side; `agent_exits` and `cost` -- the cohort the
    repository's runs fold to -- are the cost-focused companions.
    Distinct issue counts use `COUNT(DISTINCT issue)` because rows are
    already scoped to one repo per bucket, so the `(repo, issue)`
    row-constructor used by `get_summary` is unnecessary here.
    """

    repo: str
    issues: int
    events: int
    agent_exits: int = 0
    cost: CostCohort = EMPTY_COST_COHORT


@dataclass(frozen=True)
class CostCoverageRow:
    """Per-`cost_source` count and token rollup of agent runs.

    Powers the dashboard's "cost attribution coverage" bar.
    `total_tokens` rolls up the per-`cost_source` token volume so
    the redesigned bar can be sized by token share -- matching the
    standalone mock, which treats coverage as "what fraction of
    token volume the parser could attribute a price to" rather than
    "what fraction of runs". A small number of high-token runs can
    dominate the cost picture, so a run-count share would
    misrepresent how exposed an operator is to pricing-table gaps.
    The `unknown-price` cohort is the maintenance signal for the
    price tables in `observability/usage/prices.py` -- it is NEVER
    collapsed into a generic "unknown" bucket here so an operator
    can see at a glance how much volume the parser could not price.
    Rows whose `cost_source` is NULL surface under `"unknown"` so
    they remain visible (this is distinct from the `unknown-price`
    string the parser writes -- a NULL is "field absent", not
    "field present with the value 'unknown-price'").
    `total_tokens` sums the runs' non-overlapping totals and
    `unknown_token_runs` counts the runs whose total the evidence
    leaves unknown, so a bucket whose totals nothing settles is not
    mistaken for one that spent no tokens.
    """

    cost_source: str
    runs: int
    total_tokens: int = 0
    unknown_token_runs: int = 0
