# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which window is worth interrupting, and with which banner.

A threshold is what an opening line is decided by, so it is read from both
sides here: a window that crosses it, a window under it, and a window with
nothing to divide by at all. What the banner then says is pinned beside the
severity it carries, because the counts an operator acts on live in the message
text rather than in a field next to it -- a message that stopped naming them
would still be a banner of the right colour.

A window whose runs went unpriced or only partly priced is no banner here: that
warning belongs to the explanation of the page's money, which the Cost details
section carries alone, so a window failing its runs and leaving its spend short
is interrupted for the failures only.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from orchestrator.observability.analytics.query.overview_models import Summary
from orchestrator.observability.dashboard import insights
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases

_ERROR = "error"

# Three failures in ten runs -- three times the tenth the error band sits at.
_FAILING_RUNS = 10

_FAILURES = 3

# One failure in ten: the band itself, which is raised rather than skipped.
_BAND_FAILURES = 1

# Five in a hundred, half the band, and fifty clean runs beside it.
_QUIET_RUNS = 100

_QUIET_FAILURES = 5

_CLEAN_RUNS = 50

# Three runs in ten unpriced or only partly priced, beside seven priced ones:
# three times the share the Cost details section warns at.
_PRICED = (cases.REPORTED,) * 7

_SHORT = (cases.UNPRICED, cases.UNPRICED, cases.INCOMPLETE_SUBTOTAL)


def _summary(*, agent_runs: int = 0, failed: int = 0) -> Summary:
    """A window whose agent-run totals are all the failure band reads."""
    return Summary(total_agent_runs=agent_runs, failed_agent_runs=failed)


class FailureBannerTest(unittest.TestCase):
    """The band a window's non-zero exits are raised as an error at."""

    def test_a_crossed_band_names_the_counts(self) -> None:
        banners = insights.compute_insights(
            _summary(agent_runs=_FAILING_RUNS, failed=_FAILURES),
        )
        self.assertEqual([banner.severity for banner in banners], [_ERROR])
        self.assertIn("3 of 10", banners[0].message)

    def test_the_band_itself_is_crossed(self) -> None:
        banners = insights.compute_insights(
            _summary(agent_runs=_FAILING_RUNS, failed=_BAND_FAILURES),
        )
        self.assertEqual([banner.severity for banner in banners], [_ERROR])

    def test_a_window_under_it_is_quiet(self) -> None:
        # The empty window is listed beside the healthy ones because it is the
        # only one the ratio cannot be taken over at all.
        windows = (
            _summary(agent_runs=_QUIET_RUNS, failed=_QUIET_FAILURES),
            _summary(agent_runs=_CLEAN_RUNS),
            _summary(),
        )
        for summary in windows:
            with self.subTest(agent_runs=summary.total_agent_runs):
                self.assertEqual(insights.compute_insights(summary), [])


class UnpricedWindowTest(unittest.TestCase):
    """A window whose spend is short raises no banner of its own."""

    def test_only_the_failures_interrupt(self) -> None:
        # The unpriced share is told in the Cost details section's label, so
        # repeating it in a banner would explain the window's money twice.
        short = Summary(cost=cohort_cases.cohort(*_PRICED, *_SHORT))
        self.assertEqual(insights.compute_insights(short), [])
        failing = replace(short, total_agent_runs=_FAILING_RUNS, failed_agent_runs=_FAILURES)
        banners = insights.compute_insights(failing)
        self.assertEqual([banner.severity for banner in banners], [_ERROR])
        self.assertNotIn("priced", banners[0].message)


if __name__ == "__main__":
    unittest.main()
