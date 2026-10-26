# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An approval in `in_review` covers the report it was given, on any head.

The docs verdict and the ready ping are keyed on the head alone, so on an
unchanged commit they would speak for a report nobody reviewed. An issue whose
current report is not the one its approval covered -- another revision, or the
approved one edited or removed at its location -- is handed back to
`validating` before anything here reads them, and a fresh approval retires
both, so the report that approval covers earns a ping of its own on the very
head the last one named. So is an approval of other requirements than the ones
the drift baseline holds. A location nobody could read pings nobody, and
neither does anything a human moves while the ping is being decided -- the
report or the issue edited, or the approval's verification artifact edited or
deleted -- nor is the state the tick holds written over it. A later report
settles between ticks, never inside one, and the tick behind it hands the
issue back before any ping is decided.

A final docs pass that completed on a docs commit leaves the approved report
about the commit the reviewer was handed, and that report is still the
current one there -- the head moving is no report moving. The report itself
moving is, on that head as on any other: edited in place, or a later revision
settled about the docs commit, it is handed back for review, pinging nobody.
"""

from __future__ import annotations

import unittest
from itertools import product
from unittest.mock import patch

from orchestrator.workflow.stages.validating import review_report as _review_report
from tests.workflow import (
    drift_reports as _drift_world,
    reviewed_reports as world,
)
from tests.workflow.fixtures import LABEL_DOCUMENTING, LABEL_VALIDATING, REVIEW_APPROVED_MESSAGE
from tests.workflow.stages.in_review import (
    completion_test_support as _completion,
    readiness_test_support as _readiness_support,
    ready_ping_test_support as _ping_support,
)

ISSUE = 1_798

PR = 17_980

# A requirements revision the issue's drift baseline does not hold.
OTHER_REQUIREMENTS = "abcdef01" * 8

# A head a push lands on while the ping is being decided.
PUSHED_HEAD = "d0c5" * 10


# What moves the report a completed docs pass left current: the report edited
# in place at its location, and a later revision settled about the docs commit.
_COMPLETED_REPORT_MOVES = (
    ("edited", _readiness_support.EvidenceMoves.edits_the_report),
    ("refreshed", _completion.WorldMoves.refreshes_the_report),
)

# The completions that leave the pull request on a docs commit.
_ON_A_DOCS_COMMIT = (_completion.EXECUTED, _completion.UNCONFIGURED)


def _pings(case) -> list[str]:
    """The ready pings the case's issue thread has been sent so far."""
    return world.ready_pings(case.github)


def _edits_the_issue(case) -> None:
    """A human editing the issue's requirements."""
    _drift_world.edits(case, _drift_world.LATER_BODY)


def _pushes(case) -> None:
    """A push landing on the pull request's branch."""
    case.pull_request.head.sha = PUSHED_HEAD


class _ChangedWhileMerging:
    """GitHub answering one merge-gate request while something else changes.

    `answer` is what the request comes back with: mergeable, by default.
    """

    def __init__(self, case, change, *, answer: bool = True) -> None:
        self._case = case
        self._change = change
        self._answer = answer

    def __call__(self, *_called, **_options) -> bool:
        self._change(self._case)
        return self._answer


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

    def test_a_fresh_approval_rearms_a_lost_ping(self) -> None:
        # The first approval's ping is posted and the write recording it
        # refused, so the thread carries a ping only its armed receipt names.
        # A second report approved on the same head retires that receipt with
        # the stamp: the ping this approval earns is armed with a receipt of
        # its own and posted, not taken for the first approval's comment.
        unrecorded = self._pinged_unrecorded()
        self.github.apply_foreign_label(self.issue, LABEL_VALIDATING)
        self.reported_round(world.SECOND_REPORT)
        self.documented()
        self.in_review_tick()

        self._approved_and_pinged()

        said = "".join(world.ready_pings(self.github))
        receipts = set(_ping_support.RECEIPT.findall(said))
        self.assertEqual(unrecorded, (1, None))
        head = self.pull_request.head.sha
        stamp = self._stamps()[0]
        self.assertEqual((len(receipts), stamp), (2, head))

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

    def _pinged_unrecorded(self) -> tuple:
        """Approve and document the first report, and ping it with the write recording the ping refused.

        Returns the pings on the thread and the head recorded as pinged.
        """
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)
        self.reviewed(REVIEW_APPROVED_MESSAGE)
        self.documented()
        with _ping_support.failing(self, _ping_support.REFUSED, settling=True):
            self.in_review_tick()
        return (len(world.ready_pings(self.github)), self._stamps()[0])


class ApprovedReportRereadTest(unittest.TestCase, world._ReviewedReports, _readiness_support.EvidenceMoves):
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

    def test_a_change_while_merging_pings_nobody(self) -> None:
        # The subject reads as approved when the tick begins, and a human
        # moves it while GitHub answers whether the pull request is
        # mergeable: the report edited, the issue edited, or the approval's
        # verification artifact edited or deleted. The ping is not taken,
        # and the next tick answers the change instead of pinging: a changed
        # report goes back for review, an edit goes down the drift road, and
        # evidence that no longer stands is announced over by nobody, the
        # issue left where it is.
        for name, change, current, answered in (
            ("report edited", world.edits_report, 2, LABEL_VALIDATING),
            ("issue edited", _edits_the_issue, 2, LABEL_DOCUMENTING),
            ("artifact edited", _readiness_support.EvidenceMoves.edits_the_artifact, 2, LABEL_DOCUMENTING),
            ("artifact deleted", _readiness_support.EvidenceMoves.deletes_the_artifact, 2, LABEL_DOCUMENTING),
        ):
            with self.subTest(name):
                self._approved_and_documented(pinged=False)

                with patch.object(
                    self.github, "pr_is_mergeable", _ChangedWhileMerging(self, change),
                ):
                    self.in_review_tick()
                raced = self.records()["current"].report_revision
                self.in_review_tick()

                self.assertEqual(
                    (raced, _pings(self), self.github.label_history[-1]),
                    (current, [], (ISSUE, answered)),
                )

    def test_a_push_while_vetting_pings_nobody(self) -> None:
        # A push lands while GitHub answers whether the head carries a
        # standing veto. The head that check and the approval check read is
        # not the one the pull request stands on any more, so nobody is told
        # the pushed head is ready, and nothing is recorded as pinged.
        self._approved_and_documented(pinged=False)

        with patch.object(
            self.github, "pr_has_changes_requested",
            _ChangedWhileMerging(self, _pushes, answer=False),
        ):
            self.in_review_tick()

        self.assertEqual(
            (world.ready_pings(self.github), self.pinned().get("ready_ping_sha")),
            ([], None),
        )

    def test_other_requirements_go_back(self) -> None:
        # The approval names requirements other than the ones the drift
        # baseline holds the issue to -- somebody was handed requirements
        # since that no reviewer was. Its report and head still stand, but
        # it is not advertised as ready: the issue goes back for a review.
        self._approved_and_documented(pinged=False)
        approved = {**self.pinned()[world.APPROVED], "requirements": OTHER_REQUIREMENTS}
        world.restate(self, **{world.APPROVED: approved})

        self.in_review_tick()

        self.assertEqual(
            (self.github.label_history[-1], self.pinned().get("ready_ping_sha")),
            ((ISSUE, LABEL_VALIDATING), None),
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


class CompletedReportFreshnessTest(_completion._CompletionFixture, unittest.TestCase):
    """The approved report on a docs commit a completion names: current as it stands, stale once it moves."""

    def test_a_moved_report_on_docs_goes_back(self) -> None:
        # The approved report is about the commit the reviewer was handed, and
        # the pull request stands on the docs commit. Moved in place, or
        # replaced by a later report about the docs commit, it is no longer
        # the one approved: the issue goes back for review with its round
        # reset, and nobody is pinged.
        for kind, (name, moves) in product(_ON_A_DOCS_COMMIT, _COMPLETED_REPORT_MOVES):
            with self.subTest(kind=kind, report=name):
                self.completed(kind)
                moves(self)

                self.tick()

                handed = (self.github.label_history, self.pinned()["review_round"])
                self.assertEqual(handed, ([(_ping_support.ISSUE, LABEL_VALIDATING)], 0))
                self.assertEqual(self.pings(), [])
                self.doCleanups()
                self.setUp()


if __name__ == "__main__":
    unittest.main()
