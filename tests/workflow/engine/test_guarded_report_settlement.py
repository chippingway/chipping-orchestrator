# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A finished report settles, and a transaction retires, over the pinned comment as it stands.

The settlement is one guarded commit, prepared before the report is posted and
committed behind the post and the re-reads; the reconciliation's drop and the
retirement of its own park are guarded commits too. Another road may write the
comment in any of those windows. What it writes outside the write's own fields
survives; a record the write is decided on, or a field it writes, moving under
it refuses it with nothing written over the comment -- and before the post,
with nothing posted. A road that leaves the transaction owed behind the post
asks the comment once more, so nothing behind it writes the tick's state back
over another road; and a settlement lands only where the writes it is followed
by still fit beside it. A post or a settlement GitHub took and never confirmed
is finished by a later tick with one report, one handoff, and every frozen pair
applied once.
"""

from __future__ import annotations

import copy
import itertools
import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState, pinned_state_body
from orchestrator.workflow.engine import (
    report_delivery as _delivery,
    report_record_state as _record_state,
    report_records as _records,
    report_settlement_state as _settlement,
)
from tests.workflow.engine import (
    report_commit_test_support as commit_support,
    report_transaction_test_support as support,
)

# Fields other roads write that no report write decides on: another domain's
# evidence and verdict, and a usage total.
_EVIDENCE = "verification_evidence_current"

_VERDICT = "review_returned_verdict"

_TOKENS = "issue_total_tokens"

# The request a published report goes out as.
_POST = "publish_developer_report"

_CONSUMED_ID = 41

# A reading of the pull request conversation further than the run's.
_FURTHER_ID = 90

# A comment another road posted and recorded as this orchestrator's own.
_OTHER_POST = 9

_SPENT_ROUND = 3

# What another road writes while a settlement is out, none of which it owns
# or decides on -- save the watermark and the ledger, whose two moves are kept.
_ANOTHER_ROAD = MappingProxyType({
    _EVIDENCE: {"revision": 3},
    _VERDICT: {"round": 2},
    _TOKENS: 150,
    support.PR_WATERMARK: _FURTHER_ID,
    support.LEDGER: [_OTHER_POST],
})

# Every move another road can make that a settlement may not land over: a
# report record, the handoff, the publication or its receipt, the park and
# debt it decides what to retire by, and a field it writes moved another way.
_MOVES = (
    ("a newer transaction", MappingProxyType({_records.PENDING_REPORT: "recorded since"})),
    ("a delivery", MappingProxyType({_records.DELIVERED_REPORT: "delivered since"})),
    ("a settled report", MappingProxyType({_records.CURRENT_REPORT: "settled since"})),
    ("a handoff", MappingProxyType({_records.REPORT_HANDOFF: "handed since"})),
    ("a repointed pull request", MappingProxyType({"pr_number": support.OTHER_PR_NUMBER})),
    ("a moved receipt", MappingProxyType({support.PUBLISHED_SHA: support.MOVED_SHA})),
    ("a park", MappingProxyType({support.PARK_REASON: "agent_timeout"})),
    ("the debt", MappingProxyType({_delivery.OWED_REPORT: True})),
    ("undescribed work", MappingProxyType({_delivery.UNREPORTED_WORK: True})),
    ("the round it spends", MappingProxyType({support.REVIEW_ROUND: _SPENT_ROUND + 1})),
)


class _Comment(support.ReportTransactionCase):
    """One owed transaction's world, and the pinned comment as GitHub holds it."""

    def owes_a_round(self) -> None:
        """Record the transaction a fix round's report left: a reader it consumed and a round it spends."""
        self.record(
            watermarks=((support.PR_WATERMARK, _CONSUMED_ID),),
            spends=((support.REVIEW_ROUND, _SPENT_ROUND),),
        )

    def pinned(self) -> dict:
        """What the pinned comment carries now."""
        return self.gh.pinned_data(support.ISSUE_NUMBER)


class SettlementInterleavingTest(unittest.TestCase, _Comment):
    """The settlement lands beside another road's writes, and nowhere a record it rests on moved."""

    def setUp(self) -> None:
        _Comment.setUp(self)
        self.owes_a_round()

    def test_another_road_s_fields_survive_settling(self) -> None:
        # Evidence, a verdict and a usage total another road writes while the
        # report is being posted are the comment's; the watermark keeps the
        # further reading, and the ledger both roads' posts.
        with commit_support.behind(self.gh, self.issue, _POST, **_ANOTHER_ROAD):
            self.assertFalse(self.reconcile())

        pinned = self.pinned()
        posted = _settlement.read_current_report(self.state).location.comment_id
        support.assert_one_report(self)
        self.assertEqual(
            (
                {field: pinned[field] for field in _UNOWNED},
                pinned[support.PR_WATERMARK],
                sorted(pinned[support.LEDGER]),
                pinned[support.REVIEW_ROUND],
                pinned[_records.PENDING_REPORT],
                _settlement.read_handoff(self.state).receipt,
            ),
            (
                {field: _ANOTHER_ROAD[field] for field in _UNOWNED},
                _FURTHER_ID,
                sorted((_OTHER_POST, posted)),
                _SPENT_ROUND,
                None,
                support.RECEIPT,
            ),
        )
        self.assertEqual(self.state.data, pinned)

    def test_a_move_before_the_post_posts_nothing(self) -> None:
        # Moved between the tick's reading and the settlement's preparation:
        # nothing is posted, nothing written, and the tick holds with its state
        # withheld, for the next one to decide afresh.
        for moved, fields in _MOVES:
            with self.subTest(moved=moved):
                self.setUp()
                left = {**copy.deepcopy(self.state.data), **fields}

                self.assertTrue(self.reconcile(**fields))

                self.assertEqual(
                    (support.reports_posted(self), self.pinned(), self.state.withheld),
                    (0, left, True),
                )

    def test_a_move_behind_the_post_settles_nothing(self) -> None:
        # Moved while the report was being posted: the report is on the pull
        # request and the settlement is refused, so the comment is exactly what
        # the other road left -- nothing spent, nothing advanced, no handoff --
        # and the tick holds with its state withheld.
        for moved, fields in _MOVES:
            with self.subTest(moved=moved):
                self.setUp()
                left = {**copy.deepcopy(self.state.data), **fields}

                with commit_support.behind(self.gh, self.issue, _POST, **fields):
                    self.assertTrue(self.reconcile())

                self.assertEqual(
                    (support.reports_posted(self), self.pinned(), self.state.withheld),
                    (1, left, True),
                )

    def test_a_spoiled_comment_holds_writing_nothing(self) -> None:
        # The comment replaced by another carrying the same records, or edited
        # into something that does not parse, before the preparation or while
        # the report is being posted. Nothing is written over either, and a
        # report is posted only where the preparation still found the comment
        # the tick read.
        for spoils, (request, posts) in itertools.product(("replaces", "unparses"), _SPOILED_BEHIND):
            with self.subTest(spoils=spoils, behind=request):
                self.setUp()
                written = self.gh.write_state_calls

                with patch.object(self.gh, request, _Behind(self, request, spoils)):
                    self.assertTrue(self.reconcile())

                self.assertEqual(
                    (support.reports_posted(self), self.gh.write_state_calls, self.state.withheld),
                    (posts, written, True),
                )

    def test_an_owed_exit_rechecks_the_comment(self) -> None:
        # The post went out and the transaction is left owed: its answer lost,
        # which holds, or the requirements edited under it, which stands down.
        # Over a comment nobody else wrote, that answer stands and the tick's
        # state may still be written; over one another road wrote while the
        # report was posted, the state is withheld and the tick holds, so
        # nothing behind it puts that road's evidence back.
        for (exit_, holds), interleaved in _OWED_CASES:
            with self.subTest(exit=exit_, interleaved=interleaved):
                self.setUp()
                road = _ANOTHER_ROAD if interleaved else {}

                self.assertEqual(
                    (
                        self._reconciles_owed(exit_, road),
                        self.state.withheld,
                        self.pinned().get(_EVIDENCE),
                        _record_state.carries_pending_report(self.state),
                        support.reports_posted(self),
                    ),
                    (holds or interleaved, interleaved, road.get(_EVIDENCE), True, 1),
                )

    def _reconciles_owed(self, exit_: str, road) -> bool:
        """Reconcile with the post left owed by `exit_`, another road writing `road` behind it; whether it held."""
        if exit_ == _LOST_POST:
            owed = patch.object(self.gh.report_failures, "lost", {support.PR_NUMBER})
        else:
            owed = patch.object(self.gh, _POST, _Behind(self, _POST, "edits"))
        with owed, commit_support.behind(self.gh, self.issue, _POST, **road):
            return self.reconcile()


class SettlementRecoveryTest(unittest.TestCase, _Comment):
    """A settlement that did not land, or landed unconfirmed, is finished by a later tick once."""

    def setUp(self) -> None:
        _Comment.setUp(self)
        self.owes_a_round()

    def test_the_next_tick_settles_the_one_report(self) -> None:
        # A park another road took while the report was being posted refused
        # the settlement. The next tick finds that report by its receipt and
        # settles it, posting nothing again and leaving the other road's park
        # standing; the round is spent once and the reader advanced once.
        parked = {support.PARK_REASON: "agent_timeout", support.AWAITING_HUMAN: True}
        with commit_support.behind(self.gh, self.issue, _POST, **parked):
            self.assertTrue(self.reconcile())

        self.assertFalse(self.reconcile(afresh=True))

        pinned = self.pinned()
        support.assert_one_report(self)
        self.assertEqual(
            (
                _settlement.read_handoff(self.state).receipt,
                pinned[support.REVIEW_ROUND],
                pinned[support.PR_WATERMARK],
                pinned[support.PARK_REASON],
                pinned[support.AWAITING_HUMAN],
            ),
            (support.RECEIPT, _SPENT_ROUND, _CONSUMED_ID, "agent_timeout", True),
        )

    def test_a_lost_settlement_is_finished_once(self) -> None:
        # GitHub took the settlement and its answer never came back, so the
        # tick holds over a state it may not write. The comment carries the
        # settlement, and the next tick finds nothing owed: no second report,
        # no second write, the round spent and the reader advanced once.
        self.gh.pinned_failures.lost.add(support.ISSUE_NUMBER)
        self.assertTrue(self.reconcile())
        self.gh.pinned_failures.lost.discard(support.ISSUE_NUMBER)
        self.assertTrue(self.state.withheld)
        written = self.gh.write_state_calls

        self.assertFalse(self.reconcile(afresh=True))

        support.assert_one_report(self)
        self.assertEqual(
            (
                self.gh.write_state_calls,
                _record_state.carries_pending_report(self.state),
                _settlement.read_handoff(self.state).receipt,
                self.state.get(support.REVIEW_ROUND),
                self.state.get(support.PR_WATERMARK),
            ),
            (written, False, support.RECEIPT, _SPENT_ROUND, _CONSUMED_ID),
        )

    def test_a_lost_post_beside_others_settles_once(self) -> None:
        # GitHub took the post and lost its answer while another road wrote
        # evidence: the tick holds with its state withheld, so that evidence
        # stands. The next tick finds the report by its receipt and settles it
        # beside the evidence -- one report, the round spent once, the reader
        # advanced once.
        with (
            patch.object(self.gh.report_failures, "lost", {support.PR_NUMBER}),
            commit_support.behind(self.gh, self.issue, _POST, **_ANOTHER_ROAD),
        ):
            self.assertTrue(self.reconcile())
        self.assertTrue(self.state.withheld)

        self.assertFalse(self.reconcile(afresh=True))

        support.assert_one_report(self)
        self.assertEqual(
            (
                self.pinned()[_EVIDENCE],
                _settlement.read_handoff(self.state).receipt,
                self.state.get(support.REVIEW_ROUND),
                self.state.get(support.PR_WATERMARK),
            ),
            (_ANOTHER_ROAD[_EVIDENCE], support.RECEIPT, _SPENT_ROUND, _FURTHER_ID),
        )

    def test_growth_behind_the_post_settles_nothing(self) -> None:
        # Another road fills the comment while the report is posted, so the
        # settlement no longer fits beside what it wrote. Nothing is written
        # over it and the tick holds; the next tick, over that full comment,
        # posts nothing again and stands down with the report still owed.
        filler = {_FILLER: _CROWDING * _largest_filler(self.state.data)}
        with commit_support.behind(self.gh, self.issue, _POST, **filler):
            self.assertTrue(self.reconcile())

        self.assertFalse(self.reconcile(afresh=True))

        support.assert_one_report(self)
        self.assertEqual(
            (
                self.pinned()[_FILLER],
                _record_state.carries_pending_report(self.state),
                _settlement.read_handoff(self.state),
            ),
            (filler[_FILLER], True, None),
        )


class CompletionRoomTest(unittest.TestCase, _Comment):
    """A settlement lands only where the writes it is followed by still fit beside it."""

    def test_the_commit_keeps_room_for_the_hand_back(self) -> None:
        # Another road fills the comment while a fixing round's report is
        # posted, to exactly what the settlement alone would leave at the
        # ceiling. Landed, it would leave the hand-back that settlement owes no
        # room at all. So it is refused with the transaction kept, the tick
        # holds, and the next tick, over that full comment, posts nothing again
        # and stands down with the report still owed.
        filler = {_FILLER: _CROWDING * self._settled_brim()}
        self._owes_a_fixing_round()

        with commit_support.behind(self.gh, self.issue, _POST, **filler):
            self.assertTrue(self.reconcile())

        self.assertFalse(self.reconcile(afresh=True))

        support.assert_one_report(self)
        self.assertEqual(
            (
                _record_state.carries_pending_report(self.state),
                _settlement.read_handoff(self.state),
                len(pinned_state_body(self.pinned())) <= MAX_PINNED_BODY,
            ),
            (True, None, True),
        )

    def _owes_a_fixing_round(self) -> None:
        """A fresh world whose transaction raises the fixing mark, settled while the issue is on `fixing`."""
        _Comment.setUp(self)
        self.gh.apply_foreign_label(self.issue, support.WorkflowLabel.FIXING)
        self.record(spends=((_records.SETTLED_ROUND, True),))

    def _settled_brim(self) -> int:
        """How much filler the comment that round's settlement leaves carries and stays one GitHub accepts."""
        self._owes_a_fixing_round()
        self.assertFalse(self.reconcile())
        return _largest_filler(self.state.data)


class RetirementCommitTest(unittest.TestCase, _Comment):
    """A drop and this owner's own park coming down land beside another road's writes, and nowhere else."""

    def setUp(self) -> None:
        _Comment.setUp(self)

    def test_an_ending_drops_beside_another_road(self) -> None:
        # The pull request merged, so the transaction is dropped -- and the
        # evidence and usage another road wrote meanwhile stay as it wrote them.
        self.record()
        self.pull_request.merged = True

        self.assertFalse(self.reconcile(**_ANOTHER_ROAD))

        pinned = self.pinned()
        self.assertEqual(
            (pinned[_records.PENDING_REPORT], pinned[_EVIDENCE], pinned[_TOKENS]),
            (None, _ANOTHER_ROAD[_EVIDENCE], _ANOTHER_ROAD[_TOKENS]),
        )
        self.assertEqual(support.reports_posted(self), 0)

    def test_a_moved_record_is_never_dropped(self) -> None:
        # A newer transaction, a settlement, or a park another road wrote since
        # the tick decided the one it read was over is not dropped with it: the
        # tick holds and the comment is that road's.
        for moved, fields in _DROP_MOVES:
            with self.subTest(moved=moved):
                self.setUp()
                self.record()
                self.pull_request.merged = True
                left = {**copy.deepcopy(self.state.data), **fields}

                self.assertTrue(self.reconcile(**fields))

                self.assertEqual(self.pinned(), left)

    def test_the_damage_park_retires_beside_others(self) -> None:
        # The damaged record was abandoned, so this owner's park comes down --
        # beside the evidence another road wrote since the tick read the
        # comment, and never over a record that road wrote in its place.
        for since, retires in _DAMAGE_PARK_SINCE:
            with self.subTest(retires=retires):
                self.setUp()
                self.state.set(_records.PENDING_REPORT, {"receipt": support.RECEIPT})
                self.reconcile()
                _record_state.clear_pending_report(self.state)
                left = {**copy.deepcopy(self.state.data), **since}

                self.assertEqual(self.reconcile(**since), not retires)

                self.assertEqual(self.pinned(), {
                    **left, support.PARK_REASON: None, support.AWAITING_HUMAN: False,
                } if retires else left)


# The fields `_ANOTHER_ROAD` writes that no report write owns.
_UNOWNED = (_EVIDENCE, _VERDICT, _TOKENS)

# The moves a drop is decided on: a report record, the handoff, and the park.
_DROP_MOVES = (*_MOVES[:4], _MOVES[6])

# What another road writes beside an abandoned record's park, and whether the
# park comes down over it: unrelated fields, and a newer transaction.
_DAMAGE_PARK_SINCE = ((_ANOTHER_ROAD, True), (_MOVES[0][1], False))

# The two roads that leave a posted transaction owed, and whether each holds
# the tick on its own: a post whose answer was lost, and requirements edited
# under the post, which stand down for the drift resume.
_LOST_POST = "a lost post"

_OWED_EXITS = ((_LOST_POST, True), ("moved requirements", False))

# Each of those, over a comment nobody else wrote and over one another road
# wrote while the report was posted.
_OWED_CASES = tuple(itertools.product(_OWED_EXITS, (False, True)))

# The request a spoiled comment is spoiled behind, and how many reports go out:
# the pull request read ahead of the preparation, and the post itself.
_SPOILED_BEHIND = (("get_pr", 0), (_POST, 1))

# What a case crowds the rest of the comment with.
_FILLER = "filler"

_CROWDING = "y"


def _largest_filler(comment: dict) -> int:
    """How much filler `comment` carries and stays one GitHub accepts.

    Searched against the rendered body rather than any writer under test, so
    what is pinned is the ceiling itself: the comment another road leaves is
    valid, and the settlement is what no longer fits beside it.
    """
    low, high = 0, MAX_PINNED_BODY
    while low < high:
        tried = (low + high + 1) // 2
        if len(pinned_state_body({**comment, _FILLER: _CROWDING * tried})) <= MAX_PINNED_BODY:
            low = tried
        else:
            high = tried - 1
    return low


class _Behind:
    """One request, with something done once it is sent, named by the case: one of the methods below."""

    def __init__(self, case, request: str, done: str) -> None:
        self._case = case
        self._sends = getattr(case.gh, request)
        self._done = getattr(self, done)
        self._pending = True

    def __call__(self, *request, **options):
        """Send the request, then do what the case named, once."""
        answered = self._sends(*request, **options)
        if self._pending:
            self._pending = False
            self._done()
        return answered

    def replaces(self) -> None:
        """Replace the pinned comment with another carrying the same record."""
        github, issue = self._case.gh, self._case.issue
        github.seed_state(issue, **github.pinned_data(issue.number))

    def unparses(self) -> None:
        """Edit the pinned comment in place into something that does not parse."""
        github, issue = self._case.gh, self._case.issue
        github._pinned[issue.number] = PinnedState(
            comment_id=github.read_pinned_state(issue).comment_id, parsed=False,
        )

    def edits(self) -> None:
        """Edit the issue's requirements, which the settlement re-reads behind the post."""
        issue = self._case.issue
        issue.body = f"{issue.body}\n\nAnd one more requirement."


if __name__ == "__main__":
    unittest.main()
