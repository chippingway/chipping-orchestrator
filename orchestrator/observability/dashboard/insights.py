# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The observations a page is interrupted with, above every panel it draws.

A banner here is something an operator should act on rather than a number to
read off a chart, so the whole owner is the two questions worth stopping a page
for and the ratio each is raised at. A window whose agent runs exit non-zero
more than a tenth of the time is describing a broken workload rather than the
one the panels below it plot; a window whose runs arrive unpriced or only
partly priced that often is one whose spend is an incomplete subtotal, because
the price catalogue in `observability/usage/prices.py` has no active row for
models the parser is seeing in the wild.

Each threshold sits beside the arithmetic that crosses it: what is worth
interrupting for is one decision, and a page carrying its own copy of either
number is where the banner raised and the banner documented would drift apart.
Both ratios are read off the window's own totals. The unpriced one counts the
runs whose cost evidence states it `incomplete` -- the evidence, not the
`cost_source` tag beside it -- so a run an earlier build recorded with no
evidence is not counted as unpriced: nothing states whether it was, and the
headline totals already say that their completeness is unknown.

Crossing nothing is the ordinary answer, and it is an empty list rather than a
banner saying so, because the caller branches on it for a section header that
would otherwise sit above nothing.
"""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.observability.analytics.query.overview_models import Summary

FAILURE_RATE_BANNER_THRESHOLD = 0.1
UNPRICED_COVERAGE_THRESHOLD = 0.1


@dataclass(frozen=True)
class InsightBanner:
    """A single banner line displayed at the top of the page.

    `severity` is one of `success` / `info` / `warning` / `error`;
    the dashboard renders each through the matching coloured insight
    block. Keeping severity a plain string (rather than an Enum)
    means the helpers stay importable without Streamlit and the
    tests can compare against string literals.
    """

    severity: str
    message: str


def compute_insights(summary: Summary) -> list[InsightBanner]:
    """Banner lines surfaced at the top of the redesigned page.

    Each banner is a single observation the operator should act on:

    - Failure rate exceeds `FAILURE_RATE_BANNER_THRESHOLD`: agent
      runs are exiting non-zero more than 10 % of the time.
    - Unpriced coverage exceeds `UNPRICED_COVERAGE_THRESHOLD`: runs
      whose cost evidence is `incomplete` leave the window's spend a
      subtotal, and the price catalogue in
      `observability/usage/prices.py` has no active row for the models
      they ran.

    The helper returns an empty list when nothing crosses a
    threshold, so the caller can branch on `if banners:` for the
    section header.
    """
    banners: list[InsightBanner] = []
    if summary.total_agent_runs > 0:
        rate = summary.failed_agent_runs / summary.total_agent_runs
        if rate >= FAILURE_RATE_BANNER_THRESHOLD:
            rate *= 100
            banners.append(
                InsightBanner(
                    severity="error",
                    message=(
                        f"{summary.failed_agent_runs} of "
                        f"{summary.total_agent_runs} agent runs failed "
                        f"({rate:.0f}%)."
                    ),
                )
            )
    cost = summary.cost
    if cost.runs > 0:
        ratio = cost.incomplete_runs / cost.runs
        if ratio >= UNPRICED_COVERAGE_THRESHOLD:
            ratio *= 100
            banners.append(
                InsightBanner(
                    severity="warning",
                    message=(
                        f"{cost.incomplete_runs} of {cost.runs} agent runs "
                        f"are unpriced or only partly priced ({ratio:.0f}%), "
                        "so the window's spend is an incomplete subtotal -- "
                        "check the price catalogue in "
                        "`observability/usage/prices.py` for the models "
                        "they ran."
                    ),
                )
            )
    return banners
