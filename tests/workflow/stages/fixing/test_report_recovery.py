# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a tick coming back to an unfinished report round does with it.

The windows `test_report_settlement.py` leaves open, read from the other side:
a report recorded and never bound, and a round whose publication settled while
nobody was looking. The helpers are reached directly rather than through a
dispatched tick, which is what they are for.

Two distinctions carry every case here, and both are about what an answer is
EVIDENCE of. A checkout that refuses for good -- gone, or proved to be carrying
something -- is a condition no later poll takes back, so it is announced once
and the record it could not publish is released into that notice's own write. A
reading nobody could TAKE is not that at all: it says nothing about the branch,
so it buys nothing -- nothing published, nothing released, nothing said.

The other is the mark. What says a round just closed is the mark its settlement
raised and never the settling, the settled report or the head a pull request
happens to carry, each of which outlives the transaction that made it.
"""
from __future__ import annotations

import contextlib
import dataclasses
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.workflow.engine import (
    report_binding as _report_binding,
    report_delivery as _report_delivery,
    report_record_state as _record_state,
    report_records as _records,
)
from orchestrator.workflow.stages.fixing import report_recovery as _recovery
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.stages.fixing import (
    report_crash_support as crash,
    report_settlement_support as support,
)
from tests.workflow.stages.implementing_fixing_test_cases import (
    posted_comment_contains,
)

# The park reason somebody else's question left standing, which no publication
# of this round's is an answer to.
_ASKED_A_QUESTION = "agent_question"

# All a hand edit left of a record. The key is still CLAIMED, so the debt it
# describes is real and nothing here may read it as an issue with nothing out.
_TRUNCATED_RECEIPT = "issue-880-report-1"

# The checkout a report goes out over: clean, and standing on the very commit
# the pull request carries.
_PROVED = partial(crash.a_checkout, head=support.HEAD_SHA)

# The two readings no later poll takes back. Both leave the report owed for
# the terminal park, and both release the record into it.
_GONE = partial(crash.a_checkout, present=False)

_DIRTY = partial(crash.a_checkout, tree=crash.a_tree(paths=("stray.py",)))

# The two that say only that this poll could not take them.
_UNREAD_TREE = partial(crash.a_checkout, tree=crash.a_tree(readable=False))

_UNREAD_HEAD = partial(crash.a_checkout, head="")


def recovered(case) -> bool:
    """Answer whatever unbound report record this comment is still holding.

    One spelling for every case, since the answer a road gives is what the
    cases differ on rather than the question they ask.
    """
    return _recovery._recovers_an_unbound_delivery(case.ctx())


class SettledRoundTest(unittest.TestCase, support.FixingReportCase):
    """The round a raised mark says settled, and the marks that say nothing.

    A settlement applies this route's bookkeeping and cannot move a label, so
    the round can be over with the issue still sitting on `workflow:fixing`.
    The mark is the whole of the evidence for that, because everything else on
    the comment -- the settled report, the publication receipt, the head the
    pull request carries -- outlives the transaction that wrote it.
    """

    def setUp(self) -> None:
        support.FixingReportCase.setUp(self)

    def test_no_mark_is_no_round_to_finish(self) -> None:
        # Nothing has claimed a hand-back, so there is none to take and
        # nothing to write: the tick carries on to whatever it came to do.
        self.assertFalse(_recovery._finishes_a_settled_round(self.ctx()))

        self.assertEqual(self.gh.posted_comments, [])
        self.assertEqual(
            self.gh.workflow_label(self.issue), WorkflowLabel.FIXING,
        )

    def test_a_placeable_mark_hands_the_round_back(self) -> None:
        # The bookkeeping the record froze is already on the comment, so
        # carrying on would read whatever landed since under a route the
        # settlement has just closed. The round is finished and the tick ends.
        self.records_a_settlement(under=WorkflowLabel.FIXING)

        self.assertTrue(_recovery._finishes_a_settled_round(self.ctx()))

        self.assertIsNone(self.pinned().get(support.SETTLED_ROUND))
        self.assertEqual(
            self.gh.workflow_label(self.issue), WorkflowLabel.VALIDATING,
        )

    def test_a_mark_written_back_reopens_nothing(self) -> None:
        # The mark comes down with the hand-back and the handoff beside it
        # does not: nothing clears one, and a settlement only replaces it. So
        # a comment whose round closed legitimately goes on carrying a
        # readable `workflow:fixing` handoff, both route anchors cleared and
        # no report owed -- which is everything the correlation asks. A mark
        # written back onto it afterwards, over a manual return to
        # `workflow:fixing`, would be correlated into a SECOND hand-back and
        # take the issue to the reviewer past whatever landed in between. What
        # ties a mark to one transaction is the receipt the hand-back stamped.
        self.records_a_settlement(under=WorkflowLabel.FIXING)
        _recovery._finishes_a_settled_round(self.ctx())
        self.gh.set_workflow_label(self.issue, WorkflowLabel.FIXING)
        self.state.set(support.SETTLED_ROUND, True)

        self.assertFalse(_recovery._finishes_a_settled_round(self.ctx()))

        self.assertIsNone(self.pinned().get(support.SETTLED_ROUND))
        self.assertEqual(
            self.gh.workflow_label(self.issue), WorkflowLabel.FIXING,
        )

    def test_a_mark_it_may_not_place_is_retired(self) -> None:
        # Four marks that cannot be about the round in hand: one a settlement
        # of another route's raised, one a hand put there with no settlement
        # behind it at all, one a newer round opened over, and one standing
        # beside a publication that has not happened. Each is CONSUMED rather
        # than left: it is the mark of a round that is over either way, and
        # left standing it would be waiting for whichever fixing round came
        # next -- a round it says nothing about, and one it would then bounce
        # to the reviewer with its feedback unread. Only the relabel is
        # withheld.
        for case, settled_under, damaged, carried in (
            ("settled elsewhere", WorkflowLabel.VALIDATING, None, None),
            ("manually introduced", None, None, None),
            (
                "a newer round opened",
                WorkflowLabel.FIXING, support.PENDING_FIX_AT, support.OPENED_AT,
            ),
            (
                "a publication still owed",
                WorkflowLabel.FIXING, _report_delivery.OWED_REPORT, True,
            ),
        ):
            with self.subTest(case=case):
                self.setUp()
                if settled_under is None:
                    self.state.set(support.SETTLED_ROUND, True)
                else:
                    self.records_a_settlement(under=settled_under)
                if damaged is not None:
                    self.state.set(damaged, carried)

                self.assertFalse(
                    _recovery._finishes_a_settled_round(self.ctx()),
                )

                self.assertIsNone(self.pinned().get(support.SETTLED_ROUND))
                self.assertEqual(
                    self.gh.workflow_label(self.issue), WorkflowLabel.FIXING,
                )


class UnboundDeliveryTest(unittest.TestCase, support.FixingReportCase):
    """A report a crash recorded and left on the comment, answered.

    Every case starts from the record the recording helper really writes, so
    what is read back is the frozen pairs and the frozen round this build
    produces -- and the readers stay where the round found them until the
    write that completes the publication moves them.
    """

    def setUp(self) -> None:
        support.FixingReportCase.setUp(self)
        self.records_the_report()

    def test_a_record_nobody_can_read_parks_once(self) -> None:
        # The debt is CLAIMED by the key alone, so a truncated record is a
        # report this issue still owes and cannot describe. Read as an absence
        # it would fall through to a scan whose watermarks that same record is
        # holding back, and pay a second developer for feedback the first one
        # answered. Nothing is repaired and nothing is dropped: the record is
        # left exactly as found, for whoever fixes or abandons it.
        truncated = {"receipt": _TRUNCATED_RECEIPT}
        self.state.set(_records.DELIVERED_REPORT, truncated)

        self.assertTrue(recovered(self))

        parked = self.pinned()
        self.assertEqual(parked.get(support.PARK_REASON), crash.UNDELIVERABLE)
        self.assertTrue(
            posted_comment_contains(self.gh, crash.UNREADABLE_PHRASE),
        )
        self.assertEqual(parked.get(_records.DELIVERED_REPORT), truncated)

    def test_a_proved_checkout_publishes_and_settles(self) -> None:
        # The checkout is clean and standing on the head the pull request
        # carries, so the report goes out -- and the write that settles it is
        # the one that advances the readers, drops the bookmarks and spends
        # the round. Only then is the reviewer given the head.
        with _PROVED():
            self.assertTrue(recovered(self))

        settled = self.pinned()
        self.assertEqual(len(self.gh.posted_pr_comments), 1)
        self.assertEqual(settled.get(support.PR_WATERMARK), support.CONSUMED_ID)
        self.assertEqual(settled.get(support.REVIEW_ROUND), support.SPENT_ROUND)
        self.assertIsNone(settled.get(support.PENDING_FIX_AT))
        self.assertIsNone(settled.get(support.SETTLED_ROUND))
        self.assertEqual(
            self.gh.workflow_label(self.issue), WorkflowLabel.VALIDATING,
        )

    def test_a_refused_post_leaves_a_transaction(self) -> None:
        # The binding is one local write and the post is a request GitHub can
        # refuse, so a refusal leaves a transaction the reconciliation ahead of
        # a later handler finishes -- not a delivery nothing would go back for.
        # Nothing the publication owes moves until it lands: the readers, the
        # bookmarks, the round and the relabel all wait.
        self.gh.report_failures.refused.add(support.PR_NUMBER)

        with _PROVED():
            self.assertTrue(recovered(self))

        held = self.pinned()
        self.assertEqual(self.gh.posted_pr_comments, [])
        self.assertIsNotNone(_record_state.read_pending_report(self.state))
        self.assertEqual(held.get(support.PR_WATERMARK), support.UNREAD_ID)
        self.assertEqual(held.get(support.REVIEW_ROUND), 1)
        self.assertEqual(held.get(support.PENDING_FIX_AT), support.OPENED_AT)
        self.assertEqual(
            self.gh.workflow_label(self.issue), WorkflowLabel.FIXING,
        )

    def test_a_publication_it_is_not_about_holds(self) -> None:
        # A reading the binding TOOK: the pull request has moved off the
        # commit this checkout proves. Nothing is discarded, nothing is said,
        # and the tick goes on to the roads that answer it -- the one that
        # republishes a commit the pull request has not got among them.
        standing = dataclasses.replace(
            self.pull_request, head=support.FakePRRef(sha=support.MOVED_SHA),
        )

        with _PROVED(), patch.object(
            self.gh, "get_pr", return_value=standing,
        ):
            self.assertFalse(recovered(self))

        self.assertIsNone(self.pinned().get(support.PARK_REASON))
        self.assertIsNotNone(crash.frozen_record(self.state))

    def test_an_unread_world_buys_nothing(self) -> None:
        # Three requests that failed, on both sides of the binding: the tree,
        # the head, and the pull request. None says anything about the branch,
        # so none may buy a publication OR a notice -- a tick that spent one
        # on a park would tell a human this issue is stuck on the strength of
        # a read that did not happen. The tick ends where it stands and the
        # next poll asks again.
        #
        # It buys no WRITE either. The attempt staged nothing, so the comment
        # such a write would leave is the one already on the issue: a request
        # spent saying nothing, which can only lose a race with whoever wrote
        # in between.
        for case, checkout, unread in (
            ("an unreadable tree", _UNREAD_TREE, False),
            ("a head that would not resolve", _UNREAD_HEAD, False),
            ("a pull request nobody could fetch", _PROVED, True),
        ):
            with self.subTest(case=case), contextlib.ExitStack() as reads:
                self.setUp()
                written = self.gh.write_state_calls
                if unread:
                    reads.enter_context(patch.object(
                        self.gh, "get_pr", side_effect=RuntimeError,
                    ))
                reads.enter_context(checkout())

                self.assertTrue(recovered(self))

                self.assertEqual(self.gh.posted_comments, [])
                self.assertEqual(self.gh.posted_pr_comments, [])
                self.assertEqual(self.gh.write_state_calls, written)
                self.assertIsNone(self.pinned().get(support.PARK_REASON))
                self.assertIsNotNone(crash.frozen_record(self.state))

    def test_a_definite_refusal_releases_the_record(self) -> None:
        # A worktree that is GONE and a tree this host PROVED dirty are the
        # two refusals no later poll takes back, so they are announced once
        # rather than left for a tick that finds the same three answers every
        # poll and does nothing with any of them. The record is RELEASED into
        # that notice's own write -- left there, restoring or cleaning the
        # checkout would be enough on its own to publish the report and send
        # the issue to review, which is the decision the notice exists to put
        # in front of a human. What the run CONSUMED goes down with it, off
        # the record's own pairs and before the release drops them. The tick
        # is not ended on it: what the notice settles is this road's question,
        # and the roads behind it each decline such a checkout for themselves.
        for case, checkout in (
            ("a worktree that is gone", _GONE),
            ("a tree proved dirty", _DIRTY),
        ):
            with self.subTest(case=case):
                self.setUp()

                with checkout():
                    self.assertFalse(recovered(self))

                parked = self.pinned()
                self.assertTrue(posted_comment_contains(
                    self.gh, crash.UNPUBLISHABLE_PHRASE,
                ))
                self.assertEqual(
                    parked.get(support.PARK_REASON), crash.UNDELIVERABLE,
                )
                self.assertIsNone(crash.frozen_record(self.state))
                self.assertEqual(
                    parked.get(support.PR_WATERMARK), support.CONSUMED_ID,
                )
                # The debt OUTLIVES the record it drops, which is what keeps
                # the review held and the reply answerable; the round is not
                # spent, because what spends a round is a publication.
                self.assertTrue(parked.get(crash.OWED_REPORT))
                self.assertEqual(parked.get(support.REVIEW_ROUND), 1)
                self.assertEqual(
                    self.gh.workflow_label(self.issue), WorkflowLabel.FIXING,
                )


class SupersededTransactionTest(unittest.TestCase, support.FixingReportCase):
    """A release over a delivery that replaced an outstanding transaction.

    A record minted over one carries its frozen pairs forward and the binding
    behind it is what would have dropped it, so the road that RELEASES that
    record instead has to drop it too -- otherwise the transaction is left for
    the reconciliation to prove, settle and publish, over report text this
    issue has already replaced.
    """

    def setUp(self) -> None:
        support.FixingReportCase.setUp(self)
        self.records_the_report()

    def test_a_release_drops_what_it_replaced(self) -> None:
        # A report recorded over an outstanding transaction SUPERSEDES it: the
        # delivery carries that transaction's frozen pairs forward, and the
        # binding behind it is what would have dropped it. Released instead,
        # nothing else does -- and a transaction left on the comment is one
        # the reconciliation ahead of any later handler proves, settles and
        # publishes, putting report text this issue has already replaced onto
        # the pull request and clearing the debt and this very notice with it.
        #
        # The debt is what has to outlive both, since the report the reply
        # brings is the only thing that answers it.
        self._bound_then_superseded()

        with _DIRTY():
            self.assertFalse(
                _recovery._recovers_an_unbound_delivery(self.ctx()),
            )

        released = self.pinned()
        self.assertIsNone(crash.frozen_record(self.state))
        self.assertIsNone(_record_state.read_pending_report(self.state))
        self.assertFalse(_record_state.carries_pending_report(self.state))
        self.assertTrue(released.get(crash.OWED_REPORT))
        self.assertEqual(
            released.get(support.PARK_REASON), crash.UNDELIVERABLE,
        )

    def _bound_then_superseded(self) -> None:
        """One transaction outstanding, and the delivery that replaced it.

        Written through the engine's own binding rather than seeded, so what
        the release meets is the shape a refused post really leaves: the
        delivery exchanged for a transaction, and a later round's report
        recorded over it at the next revision.
        """
        _report_binding.binds_the_delivery(
            self.gh, self.issue, self.state, _report_binding.ReportPublication(
                pull_request=self.pull_request,
                repo_slug=support.TEST_REPO_SLUG,
                branch=support.BRANCH,
                commit=support.HEAD_SHA,
            ),
        )
        self.assertIsNotNone(_record_state.read_pending_report(self.state))
        self.records_the_report()


class ReportObligationTest(unittest.TestCase, support.FixingReportCase):
    """What an issue's report obligation owes, asked before anything scans.

    The two questions in the order they can be asked, because a settlement has
    already applied this route's bookkeeping: anything read past one is read
    under a route that no longer exists.
    """

    def setUp(self) -> None:
        support.FixingReportCase.setUp(self)

    def test_it_answers_whichever_obligation_stands(self) -> None:
        for case, settled, recorded, ended in (
            ("nothing outstanding", False, False, False),
            ("a round settled elsewhere", True, False, True),
            ("a record nothing bound", False, True, True),
        ):
            with self.subTest(case=case):
                self.setUp()
                if settled:
                    self.records_a_settlement(under=WorkflowLabel.FIXING)
                if recorded:
                    self.records_the_report()

                with _PROVED():
                    self.assertEqual(
                        _recovery._answers_a_report_first(self.ctx()), ended,
                    )


class TerminalParkTest(unittest.TestCase, support.FixingReportCase):
    """The write the notice a checkout no road can publish from rides."""

    def setUp(self) -> None:
        support.FixingReportCase.setUp(self)
        self.records_the_report()

    def test_the_release_rides_any_standing_park(self) -> None:
        # The notice is withheld only where the comment already says what it
        # would, and that is the ONLY thing withheld: the release and the
        # pairs that ride beside it are what the write is for. Skipped, the
        # caller is told the tick ended while the comment still carries the
        # record, and the very next tick publishes the report this road
        # existed to withhold. A park of another road's is a different
        # question on the comment, so this one is asked in its own words and
        # earns its own notice.
        for case, standing, notices in (
            ("this road's own park", crash.UNDELIVERABLE, 0),
            ("a park of another road's", _ASKED_A_QUESTION, 1),
        ):
            with self.subTest(case=case):
                self.setUp()
                crash.a_standing_park(self, standing)

                with _GONE():
                    recovered(self)

                durable = self.pinned()
                self.assertEqual(len(self.gh.posted_comments), notices)
                self.assertEqual(
                    durable.get(support.PARK_REASON), crash.UNDELIVERABLE,
                )
                self.assertIsNone(durable.get(_records.DELIVERED_REPORT))
                self.assertEqual(
                    durable.get(support.PR_WATERMARK), support.CONSUMED_ID,
                )
                self.assertTrue(durable.get(crash.OWED_REPORT))


class PublishedCheckoutTest(unittest.TestCase, support.FixingReportCase):
    """What the checkout holding an unbound report is allowed to prove.

    Every reading is positive, because what an absence would license is a
    report about code the remote does not have. The two empty answers are what
    the whole road turns on: "" is a checkout that answered and said no, and
    None is a reading nobody could take.
    """

    def setUp(self) -> None:
        support.FixingReportCase.setUp(self)

    def test_each_reading_answers_for_itself(self) -> None:
        for case, checkout, proved in (
            ("a clean checkout on a head", _PROVED, support.HEAD_SHA),
            ("a worktree that is gone", _GONE, ""),
            ("a tree proved dirty", _DIRTY, ""),
            ("a status nobody could read", _UNREAD_TREE, None),
            ("a head that would not resolve", _UNREAD_HEAD, None),
        ):
            with self.subTest(case=case), checkout():
                self.assertEqual(
                    _recovery._published_checkout(self.ctx()), proved,
                )


if __name__ == "__main__":
    unittest.main()
