# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An approval in `in_review` covers the report it was given, on any head.

The docs verdict and the ready ping are keyed on the head alone, so on an
unchanged commit they would speak for a report nobody reviewed. An issue whose
current report is not the one its approval covered is handed back to
`validating` before anything here reads them, and a fresh approval retires
both -- so the report that approval covers earns a ping of its own on the very
head the last one named.
"""

from __future__ import annotations

import unittest

from tests.workflow import reviewed_reports as world
from tests.workflow.fixtures import LABEL_VALIDATING, REVIEW_APPROVED_MESSAGE

ISSUE = 1_798

PR = 17_980


class ReportFreshnessTest(unittest.TestCase, world._ReviewedReports):
    """A report changed on the pinged head goes back for a fresh review."""

    def test_a_later_report_is_handed_back(self) -> None:
        # The issue reaches `in_review` again carrying the first approval, its
        # docs verdict, and its ping, all on the head the second report is
        # about: it goes back for review with a fresh round budget, pinging
        # nobody.
        self._handed_back()

        self.assertEqual(
            (
                self.github.label_history[-1],
                self.pinned().get("review_round"),
                len(world.ready_pings(self.github)),
            ),
            ((ISSUE, LABEL_VALIDATING), 0, 1),
        )

    def test_a_fresh_approval_pings_the_same_head(self) -> None:
        # The fresh reviewer is handed the second report, its approval retires
        # the stamps the first left, and the docs pass behind it earns a
        # second ping on the head the first ping named.
        head = self._handed_back()

        approved = self.reviewed(REVIEW_APPROVED_MESSAGE)
        retired = self._stamps()
        self.documented()
        self.in_review_tick()

        self.assertIn(f"> {world.SECOND_REPORT}", world.prompt(approved))
        self.assertEqual(retired, (None, None))
        self.assertEqual(
            (
                len(world.ready_pings(self.github)),
                self.pinned().get("ready_ping_sha"),
                self.pull_request.head.sha,
            ),
            (2, head, head),
        )

    def _stamps(self) -> tuple:
        """The ready ping and the docs verdict, as the pinned comment holds them."""
        pinned = self.pinned()
        return (pinned.get("ready_ping_sha"), pinned.get("docs_verdict"))

    def _handed_back(self) -> str:
        """Approve, document, and ping the first report; land a second on its head.

        Returns the head, which none of it moves.
        """
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)
        self._approved_and_pinged()
        self.github.apply_foreign_label(self.issue, LABEL_VALIDATING)
        self.reported_round(world.SECOND_REPORT)
        self.documented()
        self.in_review_tick()
        return self.pull_request.head.sha

    def _approved_and_pinged(self) -> None:
        """Approve the current report, document its head, and ping it."""
        self.reviewed(REVIEW_APPROVED_MESSAGE)
        self.documented()
        self.in_review_tick()


if __name__ == "__main__":
    unittest.main()
