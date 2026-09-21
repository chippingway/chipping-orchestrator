# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a fixing round's report records, settles, and hands a relabel back on.

The helpers are reached directly rather than through a dispatched tick, which
is what they are for: the disposition a fix round's report takes is one question
at a time -- which reply this is, whether the head it describes is proved, what
the record carries, what one write applies, and whether the mark that write
raises still places the round in hand.

The atomic cases are the point of the whole subsystem, so they are written as
the windows a process can die in: after the report is recorded and before the
publication lands, and after the settlement. Nothing a round consumed or spent
may be durable before the report reaches the pull request, and all of it has to
be durable the moment it does.

The LIVE roads those helpers are reached from are `test_report_recovery.py`
beside this, driven through whole dispatched ticks: what they are about is the
order a tick asks its questions in, which no single helper's answer shows.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_delivery_state as _delivery_state,
    report_publishing as _publishing,
    report_record_state as _record_state,
    report_records as _records,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.stages.fixing import (
    reporting as _reporting,
    round_marks as _round_marks,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.stages.fixing import report_settlement_support as support
from tests.workflow.stages.implementing_fixing_test_cases import (
    posted_comment_contains,
)

# What every road that cannot move a report parks under.
_UNDELIVERABLE = _report_delivery.UNDELIVERABLE_REPORT

# A phrase out of each notice, enough to say which of the three a park took.
_MISREAD_PHRASE = "reaches for the completion-report contract"

_UNDESCRIBED_PHRASE = "committed work while a report an"

_STALLED_PHRASE = "no road left on this workflow can get it there"

# The park reason somebody else's question left standing.
_ASKED_A_QUESTION = "agent_question"

# What a caller that proved no commit at all hands a binding.
_UNPROVED = ""

class ReportedRoundContractTest(unittest.TestCase, support.FixingReportCase):
    """Which replies a reported fix round may act on, and which it may not."""

    def setUp(self) -> None:
        support.FixingReportCase.setUp(self)

    def test_a_report_records_what_the_run_owed(self) -> None:
        # Both report outcomes reach the same record, and the difference
        # between them is only what the publication owes -- a comment to post
        # or a location to re-read. What rides the record is identical on
        # either: the readers the run consumed, the route bookkeeping it
        # closes, and the mark saying a fixing round's transaction settled.
        for message, mode in (
            (support.READY_MESSAGE, _records.ReportMode.PUBLISH),
            (support.VERIFIED_MESSAGE, _records.ReportMode.VERIFY),
        ):
            with self.subTest(mode=mode):
                self.setUp()

                self.assertFalse(_reporting._recording_stops_the_tick(
                    self.ctx(),
                    self.resume_run(dev_result=support.agent(message)),
                    support.consumed_batch(),
                    support.owed_round(),
                ))

                delivered = _delivery_state.read_delivered_report(self.state)
                self.assertEqual(delivered.mode, mode)
                self.assertEqual(delivered.watermarks, support.consumed_batch())
                self.assertEqual(
                    delivered.spends,
                    support.owed_round().fields + (
                        (support.SETTLED_ROUND, True),
                    ),
                )

    def test_a_misread_reply_is_held_for_a_human(self) -> None:
        # An `ACK:` beside a report is one broken contract, not two answers:
        # read on either half alone it is wrong in a way nothing later undoes.
        self.assertTrue(self._holds(support.MISREAD_MESSAGE))

        self.assertEqual(self.pinned().get(support.PARK_REASON), _UNDELIVERABLE)
        self.assertTrue(posted_comment_contains(self.gh, _MISREAD_PHRASE))
        self.assertIsNone(_delivery_state.read_delivered_report(self.state))

    def test_an_ordinary_reply_is_left_alone(self) -> None:
        # A question, a disagreement, a plain `ACK:` -- every stage already
        # knows what to do with one, and this owner may not take it. Neither
        # does an unread head beside one: a probe that answered nothing says
        # nothing about whether this run committed, and the disposition behind
        # this refuses to push blind anyway.
        for case, head in (("no commit", support.HEAD_SHA), ("unread", "")):
            with self.subTest(case=case):
                self.setUp()
                self.state.set(_report_delivery.OWED_REPORT, True)

                self.assertFalse(
                    self._holds(support.ACK_MESSAGE, after_sha=head),
                )

                self.assertIsNone(self.pinned().get(support.PARK_REASON))

    def test_a_commit_over_an_owed_report_holds(self) -> None:
        # A delivered record carries no commit: what it is ABOUT is the branch
        # as its own run left it, and the only thing saying so is that nothing
        # has been committed over it since.
        self.state.set(_report_delivery.OWED_REPORT, True)

        self.assertTrue(
            self._holds(support.ACK_MESSAGE, after_sha=support.MOVED_SHA),
        )

        self.assertTrue(posted_comment_contains(self.gh, _UNDESCRIBED_PHRASE))
        self.assertTrue(self.pinned().get(_report_delivery.UNREPORTED_WORK))

    def test_a_misread_over_a_commit_names_it(self) -> None:
        # Both readings hold and only the notice picks: the reply is what the
        # human has to fix, and the report their reply earns retires both. The
        # undescribed flag still goes down, or the commit would later get the
        # earlier round's report published over it.
        self.state.set(_report_delivery.OWED_REPORT, True)

        self.assertTrue(
            self._holds(support.MISREAD_MESSAGE, after_sha=support.MOVED_SHA),
        )

        self.assertTrue(posted_comment_contains(self.gh, _MISREAD_PHRASE))
        self.assertTrue(self.pinned().get(_report_delivery.UNREPORTED_WORK))

    def _holds(self, message: str, **run_fields) -> bool:
        """Ask the hold about one reply that wrote no usable report."""
        return _reporting._holds_for_a_human(
            self.ctx(),
            self.resume_run(
                dev_result=support.agent(message), reported=False, **run_fields
            ),
        )


class AtomicSettlementTest(unittest.TestCase, support.FixingReportCase):
    """Everything a reported round owed lands in the write that publishes it."""

    def setUp(self) -> None:
        support.FixingReportCase.setUp(self)
        _reporting._recording_stops_the_tick(
            self.ctx(), self.resume_run(), support.consumed_batch(),
            support.owed_round(),
        )

    def test_nothing_is_durable_before_the_report(self) -> None:
        # The record is down and the publication has not happened. Spent here,
        # a crash in the window between leaves the feedback answered and the
        # round counted for a report nobody published.
        recorded = self.pinned()

        self.assertEqual(recorded.get(support.PR_WATERMARK), support.UNREAD_ID)
        self.assertEqual(recorded.get(support.REVIEW_ROUND), 1)
        self.assertEqual(recorded.get(support.PENDING_FIX_AT), support.OPENED_AT)
        self.assertIsNone(recorded.get(support.SETTLED_ROUND))

    def test_one_write_settles_all_it_owed(self) -> None:
        self.assertFalse(
            _reporting._holds_an_unpublished_report(
                self.ctx(), support.HEAD_SHA,
            ).owed,
        )

        settled = self.pinned()
        self.assertEqual(settled.get(support.PR_WATERMARK), support.CONSUMED_ID)
        self.assertEqual(settled.get(support.REVIEW_ROUND), support.SPENT_ROUND)
        self.assertIsNone(settled.get(support.PENDING_FIX_AT))
        self.assertIsNone(settled.get(support.PENDING_FIX_ISSUE_MAX_ID))
        self.assertTrue(settled.get(support.SETTLED_ROUND))
        self.assertIsNone(_record_state.read_pending_report(self.state))
        self.assertIsNotNone(_settlement.read_current_report(self.state))
        self.assertFalse(_report_delivery.owes_a_report(self.state))

    def test_the_handoff_names_the_settling_label(self) -> None:
        # Read off the issue the settlement re-reads, never off the copy in
        # hand: a human who relabelled while the developer ran is invisible
        # there, and a settlement stamped with a label the issue has left
        # claims a stage was standing behind it.
        for moved, recorded in (
            (None, WorkflowLabel.FIXING),
            (WorkflowLabel.IN_REVIEW, WorkflowLabel.IN_REVIEW),
        ):
            with self.subTest(moved=moved):
                self.setUp()
                if moved is not None:
                    self.gh.apply_foreign_label(self.issue, str(moved))

                _reporting._holds_an_unpublished_report(
                    self.ctx(), support.HEAD_SHA,
                )

                self.assertEqual(
                    _settlement.read_handoff(self.state).settled_under, recorded,
                )

    def test_an_unread_label_settles_without_one(self) -> None:
        # The labels are a lazy read that can fail like any request. Raised,
        # the report would be on the pull request with the transaction still
        # outstanding; answered None, the readers behind it hold to the
        # stricter reading and the hand-back waits for a road that can prove
        # where the settlement happened.
        with patch.object(
            _publishing._labels, "workflow_label", side_effect=RuntimeError,
        ):
            self.assertFalse(_reporting._holds_an_unpublished_report(
                self.ctx(), support.HEAD_SHA,
            ).owed)

        self.assertIsNone(_settlement.read_handoff(self.state).settled_under)
        self.assertIsNone(_record_state.read_pending_report(self.state))

    def test_a_markless_settlement_retires_a_mark(self) -> None:
        # The mark and the handoff beside it have to be one fact. Left
        # standing, a mark an earlier settlement raised somewhere this stage
        # was not behind survives -- and the next settlement of any route's
        # hands it a handoff of its own to correlate against, which a manual
        # relabel onto `workflow:fixing` is then bounced on.
        support.FixingReportCase.setUp(self)
        self.state.set(support.SETTLED_ROUND, True)
        _report_delivery.recording_stops_the_tick(
            self.gh, self.issue, self.state,
            support.agent(support.READY_MESSAGE),
            _records.HandedRun(route=WorkflowLabel.VALIDATING),
        )

        _reporting._holds_an_unpublished_report(self.ctx(), support.HEAD_SHA)

        self.assertIsNone(self.pinned().get(support.SETTLED_ROUND))
        self.assertIsNotNone(_settlement.read_handoff(self.state))


class ReportOnlyRoundTest(unittest.TestCase, support.FixingReportCase):
    """A round whose whole answer is its report needs its head proved.

    Beside it, the round that answered in code and handed no report over at
    all: the same question asked of the other reply a no-commit road may not
    be given.
    """

    def setUp(self) -> None:
        support.FixingReportCase.setUp(self)

    def test_a_commit_with_no_report_is_withheld(self) -> None:
        # Work a review round earns reaches the pull request with the report
        # of it or not at all, so a run that committed and handed one over is
        # held whether it declined to report or never finished at all -- the
        # engine leaves an incomplete run alone, and this road publishes.
        for case, finished in (
            ("declined", support.agent(support.ACK_MESSAGE)),
            ("did not finish", support.agent("", exit_code=1)),
        ):
            with self.subTest(case=case):
                self.setUp()

                self.assertTrue(_reporting._recording_stops_the_tick(
                    self.ctx(),
                    self.resume_run(dev_result=finished, reported=False),
                    (),
                    support.owed_round(),
                ))

                pinned = self.pinned()
                self.assertEqual(pinned.get(support.PARK_REASON), _UNDELIVERABLE)
                self.assertTrue(pinned.get(_report_delivery.UNREPORTED_WORK))
                self.assertIsNone(
                    _delivery_state.read_delivered_report(self.state),
                )

    def test_a_proved_unmoved_head_reports_alone(self) -> None:
        with support.a_checkout():
            self.assertTrue(
                _reporting._is_report_only(self.ctx(), self.resume_run()),
            )

    def test_every_absence_refuses_the_road(self) -> None:
        # No absence proves the code this report describes is the code the
        # pull request carries: a head nobody read comes back empty, and a
        # tree nobody could read answers with no loose paths.
        for case, run, readable in (
            ("timed out", self.resume_run(dev_result=support.agent(
                support.READY_MESSAGE, timed_out=True,
            )), True),
            ("unread head", self.resume_run(after_sha=""), True),
            ("head moved", self.resume_run(after_sha=support.MOVED_SHA), True),
            ("unreadable tree", self.resume_run(), False),
        ):
            with self.subTest(case=case), support.a_checkout(readable=readable):
                self.assertFalse(_reporting._is_report_only(self.ctx(), run))

    def test_a_pull_request_that_moved_refuses(self) -> None:
        # The copy the preflight fetched says the head never moved of a pull
        # request anybody may have pushed to while the developer was out.
        self.pull_request.head.sha = support.MOVED_SHA

        with support.a_checkout():
            self.assertFalse(
                _reporting._is_report_only(self.ctx(), self.resume_run()),
            )

    def test_a_pull_request_nobody_could_read_holds(self) -> None:
        # The one refusal here about this tick rather than about the round:
        # the report is valid and the branch is where it says it is, so the
        # caller holds everything where it stands rather than parking for a
        # human nobody ever needed.
        with patch.object(self.gh, "get_pr", side_effect=RuntimeError):
            self.assertIsNone(
                _reporting._is_report_only(self.ctx(), self.resume_run()),
            )


class StaleCorrelationTest(unittest.TestCase, support.FixingReportCase):
    """A raised mark is a claim on the next relabel, placed before it is spent."""

    def setUp(self) -> None:
        support.FixingReportCase.setUp(self)

    def test_no_mark_places_every_relabel(self) -> None:
        # The no-feedback bounce relabels on every tick that finds nothing to
        # do, and a road that decided on its own reasons waits on nobody.
        self.assertTrue(_round_marks._places_the_round_in_hand(self.state))

    def test_a_settled_fixing_round_places_itself(self) -> None:
        self.records_a_settlement(under=WorkflowLabel.FIXING)

        self.assertTrue(_round_marks._places_the_round_in_hand(self.state))

    def test_a_settlement_elsewhere_withholds_it(self) -> None:
        # A settlement that landed anywhere but `workflow:fixing` is a round
        # this stage was not behind, and one nobody can place is a mark
        # nothing should act on. Acting on either relabels the issue off the
        # label a human chose, past feedback nobody has read.
        for under in (WorkflowLabel.VALIDATING, None):
            with self.subTest(under=under):
                self.setUp()
                self.records_a_settlement(under=under)

                self.assertFalse(
                    _round_marks._places_the_round_in_hand(self.state),
                )

    def test_a_newer_round_withholds_it(self) -> None:
        # A settlement clears both route anchors and drops the transaction, so
        # a mark found over either anchor belongs to a round that opened AFTER
        # it was raised, one beside an owed report to a publication that has
        # not happened, and one beside an unreadable handoff to a settlement
        # this build cannot place at all.
        for case, damaged, carried in (
            ("owed report", _report_delivery.OWED_REPORT, True),
            ("unreadable handoff", _records.REPORT_HANDOFF, "truncated"),
            ("newer route anchor", support.PENDING_FIX_AT, support.OPENED_AT),
            ("reviewer anchor", support.REVIEWER_ANCHOR, support.CONSUMED_ID),
        ):
            with self.subTest(case=case):
                self.setUp()
                self.records_a_settlement(under=WorkflowLabel.FIXING)
                self.state.set(damaged, carried)

                self.assertFalse(
                    _round_marks._places_the_round_in_hand(self.state),
                )

    def test_the_mark_falls_before_the_label_moves(self) -> None:
        # Relabelled first, a tick that dies leaves a raised mark under a
        # label that has moved on, and nothing later can tell it from a round
        # that has just settled.
        self.records_a_settlement(under=WorkflowLabel.FIXING)
        recorder = support.RelabelRecorder(self)

        with patch.object(self.gh, "set_workflow_label", recorder):
            _reporting._hands_the_round_back(self.ctx())

        self.assertEqual(recorder.durable, [None])
        self.assertEqual(
            self.gh.workflow_label(self.issue), WorkflowLabel.VALIDATING,
        )

    def test_a_withheld_move_still_drops_the_mark(self) -> None:
        # The mark is this round's and this round is over, so it comes down
        # either way; what a refusal withholds is only the move.
        self.records_a_settlement(under=WorkflowLabel.VALIDATING)

        _reporting._hands_the_round_back(self.ctx())

        self.assertIsNone(self.pinned().get(support.SETTLED_ROUND))
        self.assertEqual(
            self.gh.workflow_label(self.issue), WorkflowLabel.FIXING,
        )


class SettledParkTest(unittest.TestCase, support.FixingReportCase):
    """The park a settled round's publication answered, and the one it does not.

    The window is the whole subject: a `push_failed` park is filed by the very
    push a recorded report rides, and the retry that lands that push writes its
    receipt durably a step ahead of the publication it carries -- so the
    hand-back is reached over a park that is still standing.
    """

    def setUp(self) -> None:
        support.FixingReportCase.setUp(self)
        self.records_a_settlement(under=WorkflowLabel.FIXING)
        self.state.set(support.AWAITING_HUMAN, True)

    def test_the_park_the_push_answered_falls_with_it(self) -> None:
        # Relabelled on top of that park, the issue arrives at
        # `workflow:validating` still `awaiting_human`: a recovery poll nobody
        # needs, and one nothing ends once the checkout it retries against is
        # gone.
        self.state.set(support.PARK_REASON, support.PARK_PUSH_FAILED)
        recorder = support.RelabelRecorder(self)

        with patch.object(self.gh, "set_workflow_label", recorder):
            _reporting._hands_the_round_back(self.ctx())

        # Durable BEFORE the move, like the mark beside it: a tick dying in
        # that window leaves nothing for a later road to relabel over.
        self.assertEqual(recorder.parked, [(False, None)])
        self.assertEqual(
            self.gh.workflow_label(self.issue), WorkflowLabel.VALIDATING,
        )

    def test_a_park_waiting_on_a_human_is_left_alone(self) -> None:
        # Only the parks a later tick may retry silently are ones a landed
        # publication answers. A question park is waiting on a person, and a
        # round ending is no reply to them.
        self.state.set(support.PARK_REASON, _ASKED_A_QUESTION)

        _reporting._hands_the_round_back(self.ctx())

        pinned = self.pinned()
        self.assertTrue(pinned.get(support.AWAITING_HUMAN))
        self.assertEqual(pinned.get(support.PARK_REASON), _ASKED_A_QUESTION)


class UnpublishedReportTest(unittest.TestCase, support.FixingReportCase):
    """What binds a recorded report, and what is left when nothing can."""

    def setUp(self) -> None:
        support.FixingReportCase.setUp(self)
        _reporting._recording_stops_the_tick(
            self.ctx(), self.resume_run(), support.consumed_batch(),
            support.owed_round(),
        )

    def test_nothing_the_caller_could_not_prove_binds(self) -> None:
        # A binding takes the commit the CALLER proved and no other: the
        # code-publication receipt is persistent, so on a tick that did not
        # push it names an older round's commit -- and work recorded as
        # undescribed is a head the standing report was never written over.
        for case, candidate, undescribed in (
            ("no candidate", _UNPROVED, False),
            ("undescribed work", support.HEAD_SHA, True),
        ):
            with self.subTest(case=case):
                self.setUp()
                if undescribed:
                    self.state.set(_report_delivery.UNREPORTED_WORK, True)

                self.assertTrue(_reporting._holds_an_unpublished_report(
                    self.ctx(), candidate,
                ).owed)

                self.assertIsNotNone(
                    _delivery_state.read_delivered_report(self.state),
                )

    def test_a_stalled_report_is_announced_once(self) -> None:
        _reporting._holds_a_stalled_report(self.ctx())
        posted = len(self.gh.posted_comments)

        _reporting._holds_a_stalled_report(self.ctx())

        self.assertTrue(posted_comment_contains(self.gh, _STALLED_PHRASE))
        self.assertEqual(len(self.gh.posted_comments), posted)

    def test_a_park_somebody_else_took_stands(self) -> None:
        # The issue is already waiting on a human, which is what this would
        # have asked for, and replacing the reason answers their question on
        # their behalf.
        self.state.set(support.AWAITING_HUMAN, True)
        self.state.set(support.PARK_REASON, _ASKED_A_QUESTION)

        _reporting._holds_a_stalled_report(self.ctx())

        self.assertEqual(
            self.state.get(support.PARK_REASON), _ASKED_A_QUESTION,
        )
        self.assertEqual(self.gh.posted_comments, [])

    def test_a_settled_round_is_handed_back(self) -> None:
        _reporting._finishes_a_reported_round(
            self.ctx(), support.owed_round(), support.HEAD_SHA,
        )

        self.assertEqual(
            self.pinned().get(support.REVIEW_ROUND), support.SPENT_ROUND,
        )
        self.assertIsNone(self.pinned().get(support.SETTLED_ROUND))
        self.assertEqual(
            self.gh.workflow_label(self.issue), WorkflowLabel.VALIDATING,
        )

    def test_an_owed_report_holds_the_relabel(self) -> None:
        # The code is out and the report it is about is not, so a reviewer
        # sent to that head would read an implementation nothing describes.
        self.state.set(_report_delivery.UNREPORTED_WORK, True)

        _reporting._finishes_a_reported_round(
            self.ctx(), support.owed_round(), support.HEAD_SHA,
        )

        self.assertEqual(self.pinned().get(support.REVIEW_ROUND), 1)
        self.assertEqual(
            self.gh.workflow_label(self.issue), WorkflowLabel.FIXING,
        )


if __name__ == "__main__":
    unittest.main()
