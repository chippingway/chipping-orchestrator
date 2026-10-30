# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which window is worth interrupting, and with which banner.

A threshold is what an opening line is decided by, so each is read from both
sides here: a window that crosses it, a window under it, and a window with
nothing to divide by at all. What the banner then says is pinned beside the
severity it carries, because the counts an operator acts on live in the message
text rather than in a field next to it -- a message that stopped naming them
would still be a banner of the right colour.

The unpriced band is read off the window's own cost cohort -- the runs whose
evidence states their cost `incomplete` -- so a run an earlier build recorded
with no evidence is not counted as unpriced: nothing states whether it was.

The two bands are also read together, since one window can cross both and the
order the banners arrive in is the order the page stacks them: the runs that
failed first, then the spend that could not be priced.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from orchestrator.observability.analytics.query.overview_models import Summary
from orchestrator.observability.dashboard import insights
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases

_ERROR = "error"

_WARNING = "warning"

# Three failures in ten runs -- three times the tenth the error band sits at.
_FAILING_RUNS = 10

_FAILURES = 3

# One failure in ten: the band itself, which is raised rather than skipped.
_BAND_FAILURES = 1

# Five in a hundred, half the band, and fifty clean runs beside it.
_QUIET_RUNS = 100

_QUIET_FAILURES = 5

_CLEAN_RUNS = 50

# Three runs in ten unpriced or only partly priced, beside seven priced ones.
_PRICED = (cases.REPORTED,) * 7

_SHORT = (cases.UNPRICED, cases.UNPRICED, cases.INCOMPLETE_SUBTOTAL)

# Ninety-nine priced runs beside one unpriced: a tenth of the band.
_MOSTLY_PRICED_RUNS = 99


def _summary(*, agent_runs: int = 0, failed: int = 0) -> Summary:
    """A window whose agent-run totals are all the failure band reads."""
    return Summary(total_agent_runs=agent_runs, failed_agent_runs=failed)


def _priced(*costs) -> Summary:
    """A window whose runs state `costs`, which is all the unpriced band reads."""
    return Summary(cost=cohort_cases.cohort(*costs))


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


class UnpricedCoverageBannerTest(unittest.TestCase):
    """The band an unpriced share of a window is warned about at."""

    def test_an_unpriced_or_partly_priced_run_counts(self) -> None:
        banners = insights.compute_insights(_priced(*_PRICED, *_SHORT))
        self.assertEqual([banner.severity for banner in banners], [_WARNING])
        self.assertIn("3 of 10", banners[0].message)
        self.assertIn("incomplete subtotal", banners[0].message)

    def test_a_share_under_it_is_quiet(self) -> None:
        # A window with no run at all shares the answer: a page that read no
        # run is not a page whose runs went unpriced. Nor is one whose runs
        # state no cost evidence: nothing says they went unpriced, and the
        # headline already says their completeness is unknown.
        windows = (
            ("one in a hundred", _priced(*(cases.REPORTED,) * _MOSTLY_PRICED_RUNS, cases.UNPRICED)),
            ("no usage", _priced(cases.NO_USAGE, cases.NO_USAGE)),
            ("no evidence", _priced(cases.ABSENT_BASIS, cases.ABSENT_BASIS)),
            ("no run", _priced()),
        )
        for name, summary in windows:
            with self.subTest(window=name):
                self.assertEqual(insights.compute_insights(summary), [])


class BannerOrderTest(unittest.TestCase):
    """A window crossing both bands is stacked in the page's order."""

    def test_failures_are_named_before_pricing(self) -> None:
        window = replace(
            _priced(*_PRICED, *_SHORT),
            total_agent_runs=_FAILING_RUNS,
            failed_agent_runs=_FAILURES,
        )
        banners = insights.compute_insights(window)
        self.assertEqual(
            [banner.severity for banner in banners], [_ERROR, _WARNING],
        )


if __name__ == "__main__":
    unittest.main()
