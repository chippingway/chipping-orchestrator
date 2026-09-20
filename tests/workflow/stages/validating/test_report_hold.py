# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The reviewer, held while a report this issue recorded is still owed.

A report GitHub has not confirmed holds every validating tick until the
reconciliation settles it, and the reviewer runs on the tick after. A delivery
a later publication carried out -- a failed push the transient recovery landed
-- is bound and settled by the hold itself. What no retry settles parks: a
report written against requirements the issue has since moved past, one whose
commit the pull request never received, one standing over a checkout that
has picked up loose work, and one the thread has moved out of reach -- a
comment somebody edited, a verified location removed or written untrusted --
which no retry settles and a silent hold would suppress every later reviewer
over. A park like that is answered by the repair as much as by a reply: the
settlement that follows one ends the debt, the park, and the hold together.
"""

from __future__ import annotations

import unittest

from orchestrator import config
from orchestrator.workflow.engine import report_delivery as _report_delivery
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow import drift_reports as world
from tests.workflow.fixtures import LABEL_VALIDATING

ISSUE = 1_794

PR = 17_940

RUN_AGENT = "run_agent"

AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"

WATERMARK = "last_action_comment_id"

PENDING = "developer_report_pending"

# What a reviewer that ran says: no verdict, so it parks and nothing else runs.
REVIEW_REPLY = "Looked it over."

ACK_REPLY = "ACK: the pushed commit already covers the second edit."

RETRY_COMMENT_ID = 60_000

CURRENT = "current"

# What a human leaves in place of the report when they edit the comment it
# landed as, and take back out of it when they put the report back.
REWRITTEN = "a human's own words"


class ReportHoldTest(unittest.TestCase, world._DriftReportMixin):
    def test_review_waits_for_the_report(self) -> None:
        # The commit is out and GitHub refused the report: no reviewer runs
        # over work whose report the pull request does not carry. Once the
        # reconciliation lands it, the next tick spawns the reviewer.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.github.report_failures.refused.add(PR)
        self.drift(world.reported())
        self.assertIsNotNone(self.records()["pending"])

        self.drift(REVIEW_REPLY, committed=False)[RUN_AGENT].assert_not_called()

        self.github.report_failures.refused.clear()
        self.reconcile()
        self.assertEqual(len(self.published_reports()), 1)
        _assert_reviewed(self, self.drift(REVIEW_REPLY, committed=False))

    def test_a_recovered_push_publishes_its_report(self) -> None:
        # The push failed after the report was recorded; the silent recovery
        # lands it on a later tick without a developer. The tick after binds
        # the recorded report to that publication, settles it, and only then
        # runs the reviewer -- one report, and no second developer run.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.drift(world.reported(), push_branch=False)
        self.drift(REVIEW_REPLY, committed=False)
        self.assertEqual(self.pull_request.head.sha, world.FIXED_HEAD)

        reviewed = self.drift(REVIEW_REPLY, committed=False)

        self.assertEqual(len(self.published_reports()), 1)
        self.assertEqual(
            self.records()["current"].subject.source_sha, world.FIXED_HEAD,
        )
        _assert_reviewed(self, reviewed)

    def test_a_report_on_moved_requirements_parks(self) -> None:
        # The report was written against the first edit and a second landed
        # before it settled; the resume that answered the second said only
        # `ACK:`. No retry can settle a report stamped with requirements the
        # issue no longer has, so the review parks for one written afresh.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.drift(self.mid_run("edit", world.reported()))
        self.drift(ACK_REPLY, committed=False)

        self.drift(REVIEW_REPLY, committed=False)[RUN_AGENT].assert_not_called()

        _assert_parked(self)

    def test_an_unpushed_commit_parks(self) -> None:
        # The report was recorded and the push never happened -- the process
        # died, or somebody cleared the push park by hand. The checkout is on
        # a commit the pull request does not carry, so binding the report to
        # the head the pull request does carry would describe other work.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.drift(world.reported(), push_branch=False)
        _restate(self, awaiting_human=False, park_reason=None)

        held = self.drift(REVIEW_REPLY, head_shas=(world.FIXED_HEAD,))

        held[RUN_AGENT].assert_not_called()
        _assert_parked(self)
        self.assertIsNotNone(self.records()["delivered"])

    def test_a_park_cleared_into_a_hold_is_written(self) -> None:
        # A reply clearing a reviewer park falls through to the review, which
        # a report still owed on the same requirements holds. The cleared park
        # and the consumed reply are written anyway, so the next tick neither
        # re-reads the reply nor waits on a park nobody is holding.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.github.report_failures.refused.add(PR)
        self.drift(world.reported())
        self.issue.comments.append(FakeComment(
            id=RETRY_COMMENT_ID, body="retry please", user=FakeUser("alice"),
        ))
        answered = world.handed_revision(self.issue)
        _restate(
            self, awaiting_human=True, park_reason="reviewer_failed",
            user_content_hash=answered,
            developer_report_pending={
                **self.pinned()[PENDING], "requirements": answered,
            },
        )

        self.drift(REVIEW_REPLY, committed=False)[RUN_AGENT].assert_not_called()

        self.assertEqual(
            (
                self.pinned().get(AWAITING_HUMAN),
                self.pinned().get(PARK_REASON),
                self.pinned()[WATERMARK],
            ),
            (False, None, RETRY_COMMENT_ID),
        )

    def test_a_dirtied_checkout_parks_the_report(self) -> None:
        # The report is owed and the checkout has since picked up loose work,
        # which the reconciliation defers on for good. The hold parks for a
        # human rather than waiting on a tree nothing here cleans.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.github.report_failures.refused.add(PR)
        self.drift(world.reported())
        self.github.report_failures.refused.clear()

        held = self.drift(REVIEW_REPLY, committed=False, dirty_files=("scratch.txt",))

        held[RUN_AGENT].assert_not_called()
        _assert_parked(self)


class EditedReportTest(unittest.TestCase, world._DriftReportMixin):
    """A report the thread moved out of reach, and the two ways back from it.

    The post landed and its response was lost, so the transaction is still
    owed -- and then a human edited the comment it landed as. No retry settles
    that: the reconciliation stands down on content a human owns, so held
    silently the reviewer would be suppressed for the life of the issue with
    nobody told. It parks instead, for a reply that supersedes the report or a
    repair that restores it.
    """

    def test_an_edited_report_comment_parks(self) -> None:
        # The park, and the road back that writes a new report: the reply
        # resumes the session, and what it writes settles and is reviewed.
        self._edited_after_a_lost_response()

        held = self.drift(REVIEW_REPLY, committed=False)

        held[RUN_AGENT].assert_not_called()
        _assert_parked(self)
        _assert_recovered_by_a_fresh_report(self)

    def test_a_repaired_report_releases_the_review(self) -> None:
        # The same park, answered by the repair rather than by a reply: the
        # human puts the report back where it was, which is what the notice
        # asked for. The reconciliation settles the transaction it was
        # holding, and the debt, the park and the hold end with it rather than
        # leaving the reviewer stopped behind a flag describing a report the
        # pull request carries.
        self._edited_after_a_lost_response()
        self.drift(REVIEW_REPLY, committed=False)
        _assert_parked(self)

        _rewritten_by_hand(self, REWRITTEN, world.REPORT_TEXT)
        self.reconcile()

        self.assertIsNotNone(self.records()[CURRENT])
        self.assertEqual(
            (self.pinned().get(AWAITING_HUMAN), self.pinned().get(PARK_REASON)),
            (False, None),
        )
        _assert_reviewed(self, self.drift(REVIEW_REPLY, committed=False))

    def _edited_after_a_lost_response(self) -> None:
        """A report GitHub took, whose response was lost, a human then edited."""
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.github.report_failures.lost.add(PR)
        self.drift(world.reported())
        self.github.report_failures.lost.clear()
        _rewritten_by_hand(self, world.REPORT_TEXT, REWRITTEN)


def _restate(case: ReportHoldTest, **changed) -> None:
    """Change fields on the pinned record, keeping everything else it holds."""
    case.github.seed_state(ISSUE, **{**case.pinned(), **changed})


def _assert_parked(case: world._DriftReportMixin) -> None:
    """The issue is held for a human over the report it cannot deliver."""
    case.assertEqual(
        (case.pinned().get(AWAITING_HUMAN), case.pinned().get(PARK_REASON)),
        (True, _report_delivery.UNDELIVERABLE_REPORT),
    )


def _assert_recovered_by_a_fresh_report(case: world._DriftReportMixin) -> None:
    """A reply resumes the session, and its report settles and is reviewed."""
    world.human_reply(case, "please write the report again")
    case.drift(world.reported(world.LATER_REPORT_TEXT), committed=False)
    case.assertEqual(len(case.published_reports(world.LATER_REPORT_TEXT)), 1)
    _assert_reviewed(case, case.drift(REVIEW_REPLY, committed=False))


def _rewritten_by_hand(case: world._DriftReportMixin, was: str, now: str) -> None:
    """A human rewrites the comment the report landed as, marker and all left.

    Both ways: the edit that puts the hold's report out of reach, and the
    repair that puts it back, which is what that park asks a human for.
    """
    posted = case.published_reports(was)[0]
    posted.body = posted.body.replace(was, now)


def _assert_reviewed(case: world._DriftReportMixin, mocks) -> None:
    """The tick spawned the reviewer, and nothing else ran first."""
    case.assertEqual(mocks[RUN_AGENT].call_args[0][0], config.REVIEW_AGENT)
