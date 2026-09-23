# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The reviewer, held while a report this issue recorded is still owed.

A report GitHub has not confirmed holds every validating tick until the
reconciliation settles it, and the reviewer runs on the tick after. A delivery
a later publication carried out -- a failed push the transient recovery landed
-- is bound and settled by the hold itself. What no retry settles parks: a
report written against requirements the issue has since moved past, one whose
commit the pull request never received, one standing over a checkout that
has picked up loose work or moved off the commit it is about, and one the
thread has moved out of reach -- a
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
from tests.workflow.fixtures import LABEL_VALIDATING, _agent

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

OWES_A_ROUND = "validating_reviewer_owes_a_round"

# Where a clean checkout ends up when something moves it off the commit the
# transaction in hand is about -- a base refresh that rebased the branch, a
# worktree recreated on a tip that had moved.
MOVED_HEAD = "e" * len(world.FIXED_HEAD)

CURRENT = "current"

# What a human leaves in place of the report when they edit the comment it
# landed as, and take back out of it when they put the report back.
REWRITTEN = "a human's own words"


class _HeldReview(world._DriftReportMixin):
    """What every case here asks of a tick the hold did or did not stop."""

    def assert_parked(self) -> None:
        """The issue is held for a human over the report it cannot deliver."""
        self.assertEqual(
            (self.pinned().get(AWAITING_HUMAN), self.pinned().get(PARK_REASON)),
            (True, _report_delivery.UNDELIVERABLE_REPORT),
        )

    def assert_reviewed(self, mocks) -> None:
        """The tick spawned the reviewer, and nothing else ran first."""
        self.assertEqual(mocks[RUN_AGENT].call_args[0][0], config.REVIEW_AGENT)

    def assert_recovered_by_a_fresh_report(self) -> None:
        """A reply resumes the session, and its report settles and is reviewed."""
        world.human_reply(self, "please write the report again")
        self.drift(world.reported(world.LATER_REPORT_TEXT), committed=False)
        self.assertEqual(len(self.published_reports(world.LATER_REPORT_TEXT)), 1)
        self.assert_reviewed(self.drift(REVIEW_REPLY, committed=False))


class ReportHoldTest(unittest.TestCase, _HeldReview):
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
        self.assert_reviewed(self.drift(REVIEW_REPLY, committed=False))

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
        self.assert_reviewed(reviewed)

    def test_a_recovered_timeout_owes_its_report(self) -> None:
        # The resume was killed by its own timeout with a commit already
        # made, so nothing described it. The silent retry finishes that
        # publication -- it cannot ask a session that is gone, and the park
        # it clears exists to clear without a human -- and records the debt
        # for it in the same write. So no reviewer runs over the head it
        # leaves: the hold parks for the report, and the reply that brings
        # one settles it before the reviewer is spawned.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.drift(_agent(session_id=world.DEV_SESSION, timed_out=True))
        self.drift(REVIEW_REPLY, **world.STRANDED)
        self.assertEqual(self.pull_request.head.sha, world.FIXED_HEAD)

        held = self.drift(REVIEW_REPLY, head_shas=(world.FIXED_HEAD,))

        held[RUN_AGENT].assert_not_called()
        self.assert_parked()
        self.assert_recovered_by_a_fresh_report()

    def test_a_report_on_moved_requirements_parks(self) -> None:
        # The report was written against the first edit and a second landed
        # before it settled; the resume that answered the second said only
        # `ACK:`. No retry can settle a report stamped with requirements the
        # issue no longer has, so the review parks for one written afresh.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.drift(self.mid_run("edit", world.reported()))
        self.drift(ACK_REPLY, committed=False)

        self.drift(REVIEW_REPLY, committed=False)[RUN_AGENT].assert_not_called()

        self.assert_parked()

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
        self.assert_parked()
        self.assertIsNotNone(self.records()["delivered"])

    def test_a_park_cleared_into_a_hold_is_written(self) -> None:
        # A reply clearing a reviewer park falls through to the review, which
        # a report still owed on the same requirements holds. The cleared park
        # is written anyway, so the next tick waits on a park nobody holds;
        # the reply is not, because the round that would have carried it never
        # opened. Nobody read those words, so they are still owed to the round
        # that finally does.
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
                self.pinned().get(WATERMARK, 0) >= RETRY_COMMENT_ID,
                bool(self.pinned().get(OWES_A_ROUND)),
            ),
            (False, None, False, True),
        )

    def test_a_held_retry_falls_to_the_developer(self) -> None:
        # The same clear, a tick later, with the report still owed. The round
        # the reply bought is noted and outlives the tick -- but no reviewer
        # runs behind that debt, and the record it is owed was written
        # against requirements this very reply has moved, which the
        # reconciliation stands down on until a resume answers the edit.
        # Deferring to the held round would leave the two waiting on each
        # other for the life of the issue with nobody told. So the edit takes
        # the developer's road, those words are delivered and recorded there,
        # and the round they bought is still owed behind it.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.github.report_failures.refused.add(PR)
        self.drift(world.reported())
        self.issue.comments.append(FakeComment(
            id=RETRY_COMMENT_ID, body="retry please", user=FakeUser("alice"),
        ))
        _restate(self, awaiting_human=True, park_reason="reviewer_failed")

        held = self.drift(REVIEW_REPLY, committed=False)
        self.drift(world.reported(world.LATER_REPORT_TEXT), committed=False)

        held[RUN_AGENT].assert_not_called()
        self.assertIn(
            ":pencil2:",
            "".join(body for _, body in self.github.posted_comments),
        )
        self.assertEqual(
            (
                self.pinned().get(WATERMARK, 0) >= RETRY_COMMENT_ID,
                bool(self.pinned().get(OWES_A_ROUND)),
            ),
            (True, True),
        )


class CheckoutRefusalTest(unittest.TestCase, _HeldReview):
    """A checkout that can no longer carry the report the pull request is owed.

    The reconciliation proves the checkout before it posts, and stands DOWN on
    both of these rather than holding, so the routes behind it keep running.
    On this stage the only route behind it is the reviewer the hold is already
    stopping, so an unspoken stand-down is a report pending for the life of
    the issue with nobody told.
    """

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
        self.assert_parked()

    def test_a_moved_checkout_parks_the_report(self) -> None:
        # The post was refused, so the transaction is owed -- and the checkout
        # has since moved off the commit that transaction is about, which the
        # reconciliation stands down on for good. Nothing behind the hold runs
        # to notice, so a silent hold would leave the report pending, the
        # reviewer stopped, and nobody told, for the life of the issue.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.github.report_failures.refused.add(PR)
        self.drift(world.reported())
        self.github.report_failures.refused.clear()

        held = self.drift(REVIEW_REPLY, committed=False, head_shas=(MOVED_HEAD,))

        held[RUN_AGENT].assert_not_called()
        self.assert_parked()
        self.assertIsNotNone(self.records()["pending"])
        self.assert_recovered_by_a_fresh_report()


class EditedReportTest(unittest.TestCase, _HeldReview):
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
        self.assert_parked()
        self.assert_recovered_by_a_fresh_report()

    def test_a_repaired_report_releases_the_review(self) -> None:
        # The same park, answered by the repair rather than by a reply: the
        # human puts the report back where it was, which is what the notice
        # asked for. The reconciliation settles the transaction it was
        # holding, and the debt, the park and the hold end with it rather than
        # leaving the reviewer stopped behind a flag describing a report the
        # pull request carries.
        self._edited_after_a_lost_response()
        self.drift(REVIEW_REPLY, committed=False)
        self.assert_parked()

        _rewritten_by_hand(self, REWRITTEN, world.REPORT_TEXT)
        self.reconcile()

        self.assertIsNotNone(self.records()[CURRENT])
        self.assertEqual(
            (self.pinned().get(AWAITING_HUMAN), self.pinned().get(PARK_REASON)),
            (False, None),
        )
        self.assert_reviewed(self.drift(REVIEW_REPLY, committed=False))

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


def _rewritten_by_hand(case: _HeldReview, was: str, now: str) -> None:
    """A human rewrites the comment the report landed as, marker and all left.

    Both ways: the edit that puts the hold's report out of reach, and the
    repair that puts it back, which is what that park asks a human for.
    """
    posted = case.published_reports(was)[0]
    posted.body = posted.body.replace(was, now)
