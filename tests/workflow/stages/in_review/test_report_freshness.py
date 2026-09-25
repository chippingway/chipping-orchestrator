# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An approval in `in_review` covers the report it was given, on any head.

The docs verdict and the ready ping are keyed on the head alone, so on an
unchanged commit they would speak for a report nobody reviewed. An issue whose
current report is not the one its approval covered -- another revision, or the
approved one edited or removed at its location -- is handed back to
`validating` before anything here reads them, and a fresh approval retires
both, so the report that approval covers earns a ping of its own on the very
head the last one named. A location nobody could read pings nobody.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.stages.validating import review_report as _review_report
from tests.workflow import reviewed_reports as world
from tests.workflow.fixtures import LABEL_VALIDATING, REVIEW_APPROVED_MESSAGE

ISSUE = 1_798

PR = 17_980


def _pings(case) -> list[str]:
    """The ready pings the case's issue thread has been sent so far."""
    return world.ready_pings(case.github)


class _EditedWhileMerging:
    """GitHub answering the mergeability request while a human edits the report."""

    def __init__(self, case) -> None:
        self._case = case

    def __call__(self, *_called, **_options) -> bool:
        world.edits_report(self._case)
        return True


class ReportFreshnessTest(unittest.TestCase, world._ReviewedReports):
    """A report changed on the pinged head goes back for a fresh review."""

    def test_a_later_report_is_reviewed_and_pinged(self) -> None:
        # The issue reaches `in_review` again carrying the first approval, its
        # docs verdict, and its ping, all on the head the second report is
        # about: it goes back for review with a fresh round budget, pinging
        # nobody. The fresh reviewer is handed the second report, its approval
        # retires the stamps the first left, and the docs pass behind it earns
        # a second ping on the head the first ping named.
        head = self._handed_back()
        handed = self._observed()

        approved = self.reviewed(REVIEW_APPROVED_MESSAGE)
        retired = self._stamps()
        self.documented()
        self.in_review_tick()

        self.assertEqual(handed, ((ISSUE, LABEL_VALIDATING), 0, 1))
        self.assertIn(f"> {world.SECOND_REPORT}", world.prompt(approved))
        self.assertEqual(
            (retired, self._observed()[2], self._stamps()[0]),
            ((None, None), 2, head),
        )

    def _observed(self) -> tuple:
        """The label last moved, the round budget, and the pings sent so far."""
        return (
            self.github.label_history[-1],
            self.pinned().get("review_round"),
            len(_pings(self)),
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


class ApprovedReportRereadTest(unittest.TestCase, world._ReviewedReports):
    """The approved report is read again before the approval is relied on."""

    def test_a_report_changed_in_place_goes_back(self) -> None:
        # An edit before the ping, and a deletion after it: no pinned record
        # moves, the location no longer holds the report the approval saw,
        # so the issue goes back and its reviewer refuses what is there.
        for name, pinged, damage, detail in (
            ("edited", False, world.edits_report, _review_report._EDITED),
            ("deleted", True, world.deletes_report, _review_report._MISSING),
        ):
            with self.subTest(name):
                self._approved_and_documented(pinged=pinged)
                pings = len(_pings(self))
                damage(self)

                self.in_review_tick()

                self.assertEqual(
                    (self.github.label_history[-1], len(_pings(self))),
                    ((ISSUE, LABEL_VALIDATING), pings),
                )
                self.assert_refused(self.reviewed(), detail)

    def test_an_unnamed_approval_goes_back(self) -> None:
        # An approval recorded before approvals named a subject, and one whose
        # record has lost its head, over a pull request that carries a report:
        # the docs verdict and the head stand, but nothing says the report was
        # the one approved, so no ping is taken on it and the issue goes back
        # for a review that is.
        for member in ("", "sha"):
            with self.subTest(member=member or "unrecorded"):
                self._approved_and_documented(pinged=False)
                world.forgets_approval(self, member)

                self.in_review_tick()

                self.assertEqual(
                    (self.github.label_history[-1], _pings(self)),
                    ((ISSUE, LABEL_VALIDATING), []),
                )
                self.assertIn(f"> {world.FIRST_REPORT}", world.prompt(self.reviewed()))

    def test_an_edit_while_merging_pings_nobody(self) -> None:
        # The report reads as approved when the tick begins and is edited
        # while GitHub answers whether the pull request is mergeable: the ping
        # is not taken on it, and the next tick hands the issue back.
        self._approved_and_documented(pinged=False)

        with patch.object(self.github, "pr_is_mergeable", _EditedWhileMerging(self)):
            self.in_review_tick()
        pinged = _pings(self)
        self.in_review_tick()

        self.assertEqual(
            (pinged, self.github.label_history[-1]), ([], (ISSUE, LABEL_VALIDATING)),
        )

    def test_an_unread_report_holds_the_ping(self) -> None:
        # A location nobody could read vouches for nothing: no ping and no
        # hand-back, and the ping follows once it reads again.
        self._approved_and_documented(pinged=False)
        relabels = len(self.github.label_history)
        self.github.report_failures.unreadable.add(PR)

        self.in_review_tick()
        held = (len(self.github.label_history), _pings(self))
        self.github.report_failures.unreadable.clear()
        self.in_review_tick()

        self.assertEqual(held, (relabels, []))
        self.assertEqual(len(_pings(self)), 1)

    def _approved_and_documented(self, *, pinged: bool) -> None:
        """Approve the first report, document its head, and ping it if asked."""
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)
        self.reviewed(REVIEW_APPROVED_MESSAGE)
        self.documented()
        if pinged:
            self.in_review_tick()


if __name__ == "__main__":
    unittest.main()
