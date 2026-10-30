# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The runs the live grouped-read test replays, and what each group of them folds to in Python.

Each named cohort is one repository's runs -- reported-only, AGY-only, mixed-provider, incomplete, and missing-basis --
spread across stages, backends, roles, and review rounds so that every grouped read folds runs of several cohorts into
one group somewhere. Every run is its own issue, so the rollup files each in a bucket of its own and a token-share
split per bucket is the per-run split computed here. The expected answer for a group is what the Python readers fold
its records to, so a grouped read that agrees with it agrees with every other usage surface.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from typing import Any

from orchestrator.observability.analytics.query import cost_cohorts
from orchestrator.observability.usage import cost_evidence as usage_cost, token_evidence as usage_tokens
from tests.observability.analytics import analytics_usage_cases as cases

_CLAUDE = "claude"

_CODEX = "codex"

_AGY = "agy"

DEVELOPER = "developer"

REVIEWER = "reviewer"

STAGE = "stage"

IMPLEMENTING = "implementing"

_FIXING = "fixing"

_DOCUMENTING = "documenting"

_AGY_REPO = "owner/agy"

_MIXED_REPO = "owner/mixed"

_INCOMPLETE_REPO = "owner/incomplete"

_LEGACY_REPO = "owner/legacy"

_REPORTED_REPO = "owner/reported"

_FIRST_ISSUE = 71

_ROUND_CAP = 6

_LEGACY_CACHE_READS = 9

_Record = dict[str, Any]

# The groups a run is filed under, in the order each filed run below lists them.
_GROUP_FIELDS = ("repo", STAGE, "backend", "agent_role", "review_round")

# Each run's cost and token evidence, then its repository, stage, backend, role, and review round. Antigravity's cache
# reads beside its input leave its totals unknown, Codex's cached input sits inside its input, a reviewer's run past
# round five lands in the `6+` bucket, and a decomposer run has no round to file under.
_FILED_RUNS = (
    (cases.REPORTED, cases.DISJOINT, _REPORTED_REPO, IMPLEMENTING, _CLAUDE, DEVELOPER, 0),
    (cases.GEMINI_ESTIMATE, cases.UNSETTLED, _AGY_REPO, "validating", _AGY, REVIEWER, 0),
    (cases.LATER_GEMINI_ESTIMATE, cases.UNSETTLED, _AGY_REPO, "validating", _AGY, REVIEWER, 1),
    (cases.REPORTED, cases.DISJOINT, _MIXED_REPO, _FIXING, _CLAUDE, DEVELOPER, 1),
    (cases.OPENAI_ESTIMATE, cases.WITHIN_INPUT, _MIXED_REPO, _FIXING, _CODEX, DEVELOPER, 1),
    (cases.BLENDED, cases.WITHIN_INPUT, _MIXED_REPO, _FIXING, _CODEX, REVIEWER, 2),
    (cases.ANTHROPIC_ESTIMATE, cases.DISJOINT, _INCOMPLETE_REPO, _DOCUMENTING, _CLAUDE, DEVELOPER, 3),
    (cases.INCOMPLETE_SUBTOTAL, cases.DISJOINT, _INCOMPLETE_REPO, _DOCUMENTING, _CLAUDE, DEVELOPER, 3),
    (cases.UNPRICED, cases.DISJOINT, _INCOMPLETE_REPO, _DOCUMENTING, _CLAUDE, REVIEWER, 3),
    (cases.COMPLETE_ZERO, cases.DISJOINT, _LEGACY_REPO, _DOCUMENTING, _CLAUDE, REVIEWER, 7),
    (cases.REPORTED, cases.DISJOINT, _REPORTED_REPO, "decomposing", _CLAUDE, "decomposer", None),
)


def _filed(issue: int, filed_run: tuple) -> _Record:
    spent, tokens, *groups = filed_run
    filed = dict(zip(_GROUP_FIELDS, groups, strict=True))
    return cases.usage_record(issue, spent, tokens, **filed)


_LEGACY_ISSUE = _FIRST_ISSUE + len(_FILED_RUNS)

_FILED_RECORDS = tuple(map(_filed, range(_FIRST_ISSUE, _LEGACY_ISSUE), _FILED_RUNS))

RECORDS = (
    *_FILED_RECORDS,
    # An earlier build's run: no evidence, no backend, no round, and a cache counter that leaves its total unknown.
    cases.unevidenced_record(
        _LEGACY_ISSUE,
        cost_usd=cases.LEGACY_USD,
        cache_read_tokens=_LEGACY_CACHE_READS,
        repo=_LEGACY_REPO,
        stage=_DOCUMENTING,
        agent_role=DEVELOPER,
    ),
    # A stage row states no usage, though it is an event of its stage.
    {**cases.stage_record(_LEGACY_ISSUE + 1), "repo": _REPORTED_REPO, STAGE: IMPLEMENTING},
)

RUNS = tuple(record for record in RECORDS if record["event"] == cases.AGENT_EXIT)


def review_bucket(record: _Record) -> str:
    """The review-round bucket a run is filed under, as the read labels it."""
    review_round = record.get("review_round")
    if review_round is None:
        return "unknown"
    if review_round >= _ROUND_CAP:
        return f"{_ROUND_CAP}+"
    return str(max(review_round, 0))


def grouped(
    key: Callable[[_Record], Any],
    records: Iterable[_Record] = RUNS,
) -> dict[Any, tuple]:
    """The runs under each value `key` reads off them."""
    groups: dict[Any, list] = {}
    for record in records:
        groups.setdefault(key(record), []).append(record)
    return {group: tuple(members) for group, members in groups.items()}


def cohort_answer(cohort: cost_cohorts.CostCohort) -> tuple:
    """A read's cohort as `live_evidence_support.folded_answer` states a cost: the runs, then the rounded evidence."""
    evidence = cohort.evidence
    parts = tuple(
        (part.basis, round(part.amount_usd, 9), part.rates_verified_on)
        for part in evidence.contributions
    )
    return cohort.runs, (evidence.completeness, parts)


def declared_tokens(records: tuple[_Record, ...]) -> tuple[int, ...]:
    """The runs' known declared total, the runs whose total is unknown, and the cache and output counters inside it."""
    totals = [usage_tokens.non_overlapping_total(record) for record in records]
    known = [
        record
        for record, total in zip(records, totals, strict=True)
        if total is not None
    ]
    cache = (
        record.get(counter, 0)
        for record in known
        for counter in usage_tokens.CACHE_COUNTERS
    )
    return (
        sum(total for total in totals if total is not None),
        totals.count(None),
        sum(cache),
        sum(record.get("output_tokens", 0) for record in known),
    )


def token_share_answer(records: Iterable[_Record]) -> tuple[float, ...]:
    """Each run's stated amount split by its cache counters' share of its declared total, summed over the runs."""
    shares = [_run_shares(record) for record in records]
    if not shares:
        return 0, 0, 0
    bands = zip(*shares, strict=True)
    return tuple(map(math.fsum, bands))


def _run_shares(record: _Record) -> tuple[float, float, float]:
    """One run's cache share, the rest, and the amount no declared total splits; a run stating none adds nothing."""
    stated = usage_cost.recorded_cost(record).total_usd or 0
    total = usage_tokens.non_overlapping_total(record)
    if not total:
        return 0, 0, stated
    cached = sum(record.get(counter, 0) for counter in usage_tokens.CACHE_COUNTERS)
    cache_share = stated * cached / total
    return cache_share, stated - cache_share, 0
