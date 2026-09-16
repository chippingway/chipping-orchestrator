# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the report reconciliation completes, and how a crash replays.

The crash cases are the point of the whole transaction, so they are written as
the windows a process can actually die in: after the report was posted and
before the record was dropped, after GitHub accepted a post whose response never
came back, and after the settlement landed. Each is replayed by running the
reconciliation a second time over the state the first one left, and each has to
end with one report on the thread, one handoff, and the round spent once.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.developer_reports import content_digest
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    report_record_state as _record_state,
    report_records as _records,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.engine import report_transaction_test_support as support

_HUMAN_REPORT = "A report a maintainer wrote by hand."

_HUMAN_COMMENT_ID = 4242

_CONSUMED_ID = 41

_LATER_ID = 90

_SPENT_ROUND = 3

_PENDING_FIX_AT = "pending_fix_at"


class SettledTransactionTest(unittest.TestCase, support.ReportTransactionCase):
    """A proved transaction publishes once and records what it owed."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)

    def test_a_proved_publication_settles_once(self) -> None:
        pending = self.record()

        self.assertFalse(self.reconcile())

        self.assertEqual(len(support.report_comments(self)), 1)
        self.assertIsNone(_record_state.read_pending_report(self.state))
        self.assertEqual(
            _settlement.read_handoff(self.state),
            _records.ReportHandoff(
                receipt=support.RECEIPT,
                pr_number=support.PR_NUMBER,
                report_revision=1,
                source_sha=support.SOURCE_SHA,
            ),
        )
        current = _settlement.read_current_report(self.state)
        self.assertEqual(current.subject, pending.subject)
        self.assertEqual(
            current.content_revision, content_digest(support.REPORT_TEXT),
        )
        self.assertEqual(current.location.pr_number, support.PR_NUMBER)

    def test_a_settlement_closes_what_it_owed(self) -> None:
        # The run that consumed the feedback and earned the round is gone by
        # now, so the record is the only account of either.
        self.record(
            watermarks=((support.PR_WATERMARK, _CONSUMED_ID),),
            spends=(
                (support.REVIEW_ROUND, _SPENT_ROUND), (_PENDING_FIX_AT, None),
            ),
        )

        self.assertFalse(self.reconcile())

        self.assertEqual(self.state.get(support.PR_WATERMARK), _CONSUMED_ID)
        self.assertEqual(self.state.get(support.REVIEW_ROUND), _SPENT_ROUND)
        self.assertIsNone(self.state.get(_PENDING_FIX_AT))

    def test_the_published_comment_is_recorded(self) -> None:
        # Left out of the ledger, the report would read back to the drift hash
        # and the feedback scans as a human's fresh comment on the thread.
        self.record()

        self.reconcile()

        posted = _settlement.read_current_report(self.state).location.comment_id
        self.assertIn(posted, self.state.get("orchestrator_comment_ids"))


class ReplayedTransactionTest(unittest.TestCase, support.ReportTransactionCase):
    """A transaction replayed after a crash finishes once, not twice."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)

    def test_a_crash_before_the_write_replays_once(self) -> None:
        # The post landed and the process died before the settlement was
        # written, so the record still says the report is owed. The retry is
        # scoped by the receipt and finds its own comment.
        self.record(spends=((support.REVIEW_ROUND, _SPENT_ROUND),))
        interrupted = self.state.data.copy()
        self.reconcile()
        self.state.data = interrupted

        self.assertFalse(self.reconcile())

        self.assertEqual(len(support.report_comments(self)), 1)
        self.assertEqual(self.state.get(support.REVIEW_ROUND), _SPENT_ROUND)
        self.assertIsNotNone(_settlement.read_handoff(self.state))

    def test_a_lost_response_is_found_by_the_retry(self) -> None:
        # GitHub accepted the comment and the response never arrived, so the
        # tick holds with the comment already on the thread. The retry is
        # scoped by the receipt and has to find that comment rather than post
        # a second one under the same transaction.
        self.record()
        self.gh.report_failures.lost.add(support.PR_NUMBER)

        self.assertTrue(self.reconcile())

        self.assertIsNotNone(_record_state.read_pending_report(self.state))
        self.assertIsNone(_settlement.read_handoff(self.state))

        self.gh.report_failures.lost.discard(support.PR_NUMBER)
        self.assertFalse(self.reconcile())
        self.assertEqual(len(support.report_comments(self)), 1)

    def test_a_finished_handoff_drops_the_record(self) -> None:
        # The settlement landed and the drop did not, which is the one window
        # where the report is on the thread and the record still claims it.
        self.record()
        self.reconcile()
        posted = len(support.report_comments(self))
        _record_state.record_pending_report(self.state, self.pending())

        self.assertFalse(self.reconcile())

        self.assertEqual(len(support.report_comments(self)), posted)
        self.assertIsNone(_record_state.read_pending_report(self.state))

    def test_a_replay_never_counts_a_round_twice(self) -> None:
        owed = ((support.REVIEW_ROUND, _SPENT_ROUND),)
        self.record(spends=owed)
        self.reconcile()
        _record_state.record_pending_report(
            self.state, self.pending(spends=owed),
        )

        self.reconcile()

        self.assertEqual(self.state.get(support.REVIEW_ROUND), _SPENT_ROUND)

    def test_a_replay_never_rolls_a_watermark_back(self) -> None:
        # A human commenting between the record and the replay would otherwise
        # have their comment handed to the next scan as unread feedback.
        consumed = ((support.PR_WATERMARK, _CONSUMED_ID),)
        self.record(watermarks=consumed)
        self.reconcile()
        self.state.set(support.PR_WATERMARK, _LATER_ID)
        _record_state.record_pending_report(
            self.state, self.pending(watermarks=consumed),
        )

        self.reconcile()

        self.assertEqual(self.state.get(support.PR_WATERMARK), _LATER_ID)


class DamagedRecordTest(unittest.TestCase, support.ReportTransactionCase):
    """A record nobody can read holds the tick and says so once."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)

    def test_a_damaged_record_parks_once(self) -> None:
        self.state.set(_records.PENDING_REPORT, {"receipt": support.RECEIPT})

        self.assertTrue(self.reconcile())

        self.assertEqual(
            self.state.get(support.PARK_REASON), support.PARK_DAMAGED,
        )
        self.assertTrue(self.state.get(support.AWAITING_HUMAN))
        posted = len(self.gh.posted_comments)

        self.assertTrue(self.reconcile())

        self.assertEqual(len(self.gh.posted_comments), posted)

    def test_a_repaired_record_clears_the_park(self) -> None:
        # The park's notice promises the next tick resumes on its own, so a
        # record that reads again has to take the park down with it -- left
        # standing, every stage behind this guard reads `awaiting_human` as an
        # issue waiting on a reply nobody owes.
        self.state.set(_records.PENDING_REPORT, {"receipt": support.RECEIPT})
        self.reconcile()
        self.record()

        self.assertFalse(self.reconcile())

        self.assertEqual(len(support.report_comments(self)), 1)
        self.assertIsNone(self.state.get(support.PARK_REASON))
        self.assertFalse(self.state.get(support.AWAITING_HUMAN))

    def test_an_abandoned_record_clears_the_park(self) -> None:
        # Clearing the field is the other way the notice says the damage ends.
        self.state.set(_records.PENDING_REPORT, {"receipt": support.RECEIPT})
        self.reconcile()
        _record_state.clear_pending_report(self.state)

        self.assertFalse(self.reconcile())

        self.assertIsNone(self.state.get(support.PARK_REASON))
        self.assertFalse(self.state.get(support.AWAITING_HUMAN))

    def test_another_owners_park_is_left_alone(self) -> None:
        # Every other park belongs to a stage still waiting for what it asked
        # for, and clearing one here would answer a human's question for them.
        self.state.set(support.AWAITING_HUMAN, True)
        self.state.set(support.PARK_REASON, "agent_timeout")
        self.record()

        self.assertFalse(self.reconcile())

        self.assertEqual(self.state.get(support.PARK_REASON), "agent_timeout")
        self.assertTrue(self.state.get(support.AWAITING_HUMAN))


class VerifiedTransactionTest(unittest.TestCase, support.ReportTransactionCase):
    """A verification re-reads the location and never posts a report."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)
        self.human = FakeComment(
            id=_HUMAN_COMMENT_ID, body=_HUMAN_REPORT, user=FakeUser("alice"),
        )
        self.pull_request.issue_comments.append(self.human)

    def test_a_trusted_match_settles_without_posting(self) -> None:
        self._verification()

        self.assertFalse(self.reconcile())

        self.assertEqual(support.report_comments(self), [])
        self.assertEqual(
            _settlement.read_current_report(self.state).location,
            ReportLocation(
                pr_number=support.PR_NUMBER, comment_id=_HUMAN_COMMENT_ID,
            ),
        )
        self.assertIsNotNone(_settlement.read_handoff(self.state))

    def test_an_edited_report_is_not_accepted(self) -> None:
        self._verification()
        self.human.body = f"{_HUMAN_REPORT} And a sentence added afterwards."

        self.assertTrue(self.reconcile())
        support.assert_still_owed(self)

    def test_a_report_that_is_gone_is_not_accepted(self) -> None:
        self._verification()
        self.pull_request.issue_comments.remove(self.human)

        self.assertTrue(self.reconcile())
        support.assert_still_owed(self)

    def test_an_untrusted_author_is_not_accepted(self) -> None:
        # The location is somebody else's comment, and the marker on it proves
        # nothing: this workflow trusts thread content by author.
        self._verification()
        self.human.user = FakeUser("mallory")

        with patch.object(config, "ALLOWED_ISSUE_AUTHORS", ("alice",)):
            self.assertTrue(self.reconcile())

        support.assert_still_owed(self)

    def _verification(self) -> _records.PendingReport:
        """The transaction a developer's `REPORT: VERIFIED` would record."""
        return self.record(
            mode=_records.ReportMode.VERIFY,
            route=WorkflowLabel.IN_REVIEW,
            report="",
            location=ReportLocation(
                pr_number=support.PR_NUMBER, comment_id=_HUMAN_COMMENT_ID,
            ),
            content_revision=content_digest(_HUMAN_REPORT),
        )


if __name__ == "__main__":
    unittest.main()
