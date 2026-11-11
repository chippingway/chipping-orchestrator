# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The observations a page is interrupted with, above every panel it draws.

A banner here is something an operator should act on rather than a number to
read off a chart, so the whole owner is the question worth stopping a page for
and the ratio it is raised at: a window whose agent runs exit non-zero more
than a tenth of the time is describing a broken workload rather than the one
the panels below it plot.

The threshold sits beside the arithmetic that crosses it: what is worth
interrupting for is one decision, and a page carrying its own copy of the
number is where the banner raised and the banner documented would drift apart.
The ratio is read off the window's own totals. A window whose runs left its
spend unpriced or only partly priced is not raised here: that warning is part
of the explanation of the page's money, which the Cost details section
(``cost_details``) carries alone.

Crossing nothing is the ordinary answer, and it is an empty list rather than a
banner saying so, because the caller branches on it for a section header that
would otherwise sit above nothing.
"""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.observability.analytics.query.overview_models import Summary

FAILURE_RATE_BANNER_THRESHOLD = 0.1


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
    the failure rate reaching `FAILURE_RATE_BANNER_THRESHOLD`, agent
    runs exiting non-zero 10 % of the time or more.

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
    return banners
