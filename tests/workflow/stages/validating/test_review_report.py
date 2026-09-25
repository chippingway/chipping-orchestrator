# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The developer report every reviewer is handed, and what its approval covers.

Each reviewer is handed the report the pull request carries when it spawns --
re-read from the location it settled at and quoted whole -- and the subject it
reviewed is recorded: pull request, head, requirements, and report revision. A
report the thread has moved out of reach is refused rather than reviewed, and a
reading nobody could take holds. An approval of words the pull request no
longer carries is not acted on, and a settled squash handoff moves the label
only while the report its approval covered is still the current one -- so a
report changed on an unchanged commit always reaches a fresh reviewer.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from orchestrator.github.developer_reports import content_digest
from orchestrator.workflow.engine import report_records as _records
from orchestrator.workflow.late_split import handoffs as _late_handoffs
from orchestrator.workflow.stages.validating import review_report as _review_report
from tests.workflow import fix_reports as _fix_world, reviewed_reports as world
from tests.workflow.fixtures import (
    LABEL_DOCUMENTING,
    LABEL_VALIDATING,
    REVIEW_APPROVED_MESSAGE,
    _agent,
    _open_pr_for,
)

ISSUE = 1_797

PR = 17_970

OTHER_PR = 17_971

RUN_AGENT = world.RUN_AGENT

HANDOFF_SHA = _late_handoffs.LATE_COLLAPSE_HANDOFF

NO_REPORT = "No developer report is recorded for this pull request"

# A report a maintainer published on the pull request, which a round verifies.
HUMAN_REPORT = "### Report\n\nRan the suite by hand; every check is green."

HUMAN = "alice"

EDITED = "A different account of the work."

LATE_REVIEWER = "late-reviewer"

# Every settled report no reviewer may be handed: the damage done to it, named
# as the `_DamagedReports` method that does it, and what the park says of it.
REFUSED_REPORTS = (
    ("missing", "deletes", _review_report._MISSING),
    ("edited", "edits", _review_report._EDITED),
    ("truncated", "truncates", _review_report._EDITED),
    ("moved", "moves", _review_report._MOVED.format(settled=PR)),
    ("stale", "unhands", _review_report._STALE),
    ("unreadable", "damages", _review_report._UNREADABLE),
)


class _DamagedReports(world._ReviewedReports):
    """What can happen to a settled report before the next reviewer spawns."""

    def deletes(self) -> None:
        self.pull_request.issue_comments.remove(self.report_comment())

    def edits(self) -> None:
        landed = self.report_comment()
        landed.body = landed.body.replace(world.FIRST_REPORT, EDITED)

    def truncates(self) -> None:
        landed = self.report_comment()
        landed.body = landed.body[: len(landed.body) // 2]

    def moves(self) -> None:
        _open_pr_for(self.github, issue_number=ISSUE, pr_number=OTHER_PR)
        world.restate(self, pr_number=OTHER_PR)

    def unhands(self) -> None:
        handoff = dict(self.pinned()[_records.REPORT_HANDOFF])
        world.restate(self, **{_records.REPORT_HANDOFF: {**handoff, "revision": 2}})

    def damages(self) -> None:
        world.restate(self, **{_records.CURRENT_REPORT: {"revision": "one"}})


class _EditedWhileReviewed:
    """A reviewer that approves while a human edits the report it was handed."""

    def __init__(self, landed) -> None:
        self._landed = landed

    def __call__(self, *_called, **_options):
        edited = self._landed.body
        self._landed.body = f"{edited}\n\nA line added while the reviewer ran."
        return _agent(session_id=LATE_REVIEWER, last_message=REVIEW_APPROVED_MESSAGE)


class HandedReportTest(unittest.TestCase, world._ReviewedReports):
    """What each reviewer is handed, and what an approval records."""

    def test_each_reviewer_reads_the_current_report(self) -> None:
        # Two report-only rounds on one commit: the first reviewer has no
        # report, the second reads the first report, and the third reads the
        # second and never the first -- whatever the pull request still holds
        # as history. The approval records the subject it was given.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)

        first = self.reported_round(world.FIRST_REPORT)
        second = self.reported_round(world.SECOND_REPORT)
        approved = self.reviewed(REVIEW_APPROVED_MESSAGE)

        self.assertIn(NO_REPORT, world.prompt(first))
        self.assertIn(f"> {world.FIRST_REPORT}", world.prompt(second))
        self.assertIn(f"> {world.SECOND_REPORT}", world.prompt(approved))
        self.assertNotIn(world.FIRST_REPORT, world.prompt(approved))
        pinned = self.pinned()
        subject = {
            "pr": PR,
            "sha": _fix_world.PUBLISHED_HEAD,
            "requirements": pinned["user_content_hash"],
            "report_revision": 2,
            "report_content": content_digest(world.SECOND_REPORT),
        }
        self.assertEqual(
            (pinned[world.REVIEWED], pinned[world.APPROVED]), (subject, subject),
        )
        self.assertEqual(self.github.label_history[-1], (ISSUE, LABEL_DOCUMENTING))


class RefusedReportTest(unittest.TestCase, _DamagedReports):
    """A settled report the thread has moved out of reach is never reviewed."""

    def test_a_report_nobody_may_be_handed_parks(self) -> None:
        for name, damage, detail in REFUSED_REPORTS:
            with self.subTest(name):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.reported_round(world.FIRST_REPORT)
                getattr(self, damage)()

                self.assert_refused(self.reviewed(REVIEW_APPROVED_MESSAGE), detail)

    def test_an_unread_report_holds_silently(self) -> None:
        # A location nobody could read this tick is no refusal: nothing is
        # parked or posted, and the reviewer runs once it reads again.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)
        notices = len(self.github.posted_comments)
        self.github.report_failures.unreadable.add(PR)

        self.reviewed()[RUN_AGENT].assert_not_called()

        self.assertEqual(
            (self.pinned().get(world.AWAITING_HUMAN), len(self.github.posted_comments)),
            (False, notices),
        )
        self.github.report_failures.unreadable.clear()
        self.assertIn(f"> {world.FIRST_REPORT}", world.prompt(self.reviewed()))

    def test_a_reply_brings_a_fresh_report(self) -> None:
        # The reply to the park resumes the developer, whose report is
        # published with no commit and handed to the next reviewer.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)
        self.edits()
        self.reviewed()
        _fix_world.replied(self, "please publish the report again")

        self._ticked(
            self._run_validating,
            MagicMock(side_effect=_fix_world._Runs(
                _fix_world.reported(world.SECOND_REPORT),
            )),
            committed=False,
        )

        self.assertIn(f"> {world.SECOND_REPORT}", world.prompt(self.reviewed()))


class ApprovalCoverageTest(unittest.TestCase, world._ReviewedReports):
    """An approval is acted on only for the report the reviewer was handed."""

    def test_an_edit_during_review_voids_approval(self) -> None:
        # A human edits the report while the reviewer runs. The approval that
        # comes back is of words the pull request no longer carries: nothing
        # is announced, recorded as approved, or relabelled, the run itself
        # is recorded, and the next tick refuses the edited report.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)

        self._ticked(
            self._run_validating,
            MagicMock(side_effect=_EditedWhileReviewed(self.report_comment())),
            committed=False,
        )

        pinned = self.pinned()
        self.assertEqual(
            (
                pinned.get("last_review_session_id"),
                world.APPROVED in pinned,
                self.github.label_history[-1],
            ),
            (LATE_REVIEWER, False, (ISSUE, LABEL_VALIDATING)),
        )
        self.assertFalse(any(
            "review approved" in body for _, body in self.github.posted_pr_comments
        ))
        self.assert_refused(self.reviewed(), _review_report._EDITED)

    def test_a_covered_squash_handoff_relabels(self) -> None:
        # A finished squash whose relabel did not land leaves the head the
        # move is owed over. While the report its approval covered is current,
        # the next tick moves the label without a reviewer.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)
        self.reviewed(REVIEW_APPROVED_MESSAGE)
        self.github.apply_foreign_label(self.issue, LABEL_VALIDATING)
        world.restate(self, **{HANDOFF_SHA: self.pull_request.head.sha})

        self.reviewed()[RUN_AGENT].assert_not_called()

        self.assertEqual(self.github.label_history[-1], (ISSUE, LABEL_DOCUMENTING))

    def test_a_later_report_voids_squash_handoff(self) -> None:
        # The same handoff, over an approval of the FIRST report, once the
        # second has settled on that very head: the record is dropped and a
        # fresh reviewer is handed the second report.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)
        self.reported_round(world.SECOND_REPORT)
        world.restate(self, **{
            world.APPROVED: self.pinned()[world.REVIEWED],
            HANDOFF_SHA: self.pull_request.head.sha,
        })

        reviewed = self.reviewed()

        self.assertIn(f"> {world.SECOND_REPORT}", world.prompt(reviewed))
        self.assertEqual(
            (self.pinned().get(HANDOFF_SHA), self.github.label_history[-1]),
            (None, (ISSUE, LABEL_VALIDATING)),
        )


class ConfiguredAuthorTest(unittest.TestCase, world._ReviewedReports):
    """The report reaches the reviewer under whatever allowlist is configured."""

    def test_our_report_passes_a_human_allowlist(self) -> None:
        # The allowlist names the humans; the report this orchestrator
        # published is read as ours by login, not by that list.
        self.allowed = (HUMAN,)
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)

        self.assertIn(f"> {world.FIRST_REPORT}", world.prompt(self.reviewed()))

    def test_a_verified_report_needs_trust(self) -> None:
        # A report a human published and a round verified is handed whole
        # while its author is trusted, and refused once the deployment no
        # longer trusts them.
        for allowed, handed in (((HUMAN,), True), (("bob",), False)):
            with self.subTest(allowed=allowed):
                self.allowed = (HUMAN,)
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                published = _fix_world.published_report(self, HUMAN_REPORT)
                self.requested_fix(
                    _fix_world.verified(PR, published.id, HUMAN_REPORT),
                    committed=False,
                )
                self.allowed = allowed

                reviewed = self.reviewed()

                if handed:
                    self.assertIn("> Ran the suite by hand", world.prompt(reviewed))
                else:
                    self.assert_refused(reviewed, _review_report._EDITED)


if __name__ == "__main__":
    unittest.main()
