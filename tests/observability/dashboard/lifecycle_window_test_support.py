# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The window the lifecycle pair is most crowded by.

Every stage and review round the page draws, each leaving part of its amount unsplit, so the review split's legend
lists all six of its lines and the stage split all three of its own -- the window a narrow review panel used to lose
label room on once its legend grew. The pairing's height cases and the browser layout check both draw it.
"""
from __future__ import annotations

from orchestrator.observability.analytics.query.cache_shares import TokenShareBands
from orchestrator.observability.analytics.query.cost_models import ReviewRoundBucketRow
from orchestrator.observability.analytics.query.run_models import StageBreakdown
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases

# The cache share, the rest, and the amount no declared total split.
_SHARES = (0.4, 0.19, 0.1)

_PARTLY_SPLIT = TokenShareBands(*_SHARES)

_DEVELOPMENT = cohort_cases.cohort(cases.REPORTED)

_REVIEW = cohort_cases.cohort(cases.GEMINI_ESTIMATE)

ALL_STAGES = ("decomposing", "implementing", "validating", "fixing", "documenting", "resolving_conflict", "done")

ALL_ROUNDS = ("0", "1", "2", "3", "4", "5")

PARTLY_SPLIT_STAGES = tuple(
    StageBreakdown(stage=stage, count=1, runs=1, cost=_DEVELOPMENT, bands=_PARTLY_SPLIT)
    for stage in ALL_STAGES
)

PARTLY_SPLIT_ROUNDS = tuple(
    ReviewRoundBucketRow(
        bucket=bucket,
        runs=2,
        developer_cost=_DEVELOPMENT,
        reviewer_cost=_REVIEW,
        developer_bands=_PARTLY_SPLIT,
        reviewer_bands=_PARTLY_SPLIT,
    )
    for bucket in ALL_ROUNDS
)
