# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a report record refuses, and the bookkeeping a recovered one may write.

Every member is read fail-closed, so a record short of one reads as no record --
and because that is the same answer an issue with nothing recorded gives, the
presence question is asked beside it. A guard that could not tell those two
apart would hand the stage an issue whose outstanding publication it never saw.

The bookkeeping cases are the other risk these records carry. What a recovered
group holds is APPLIED to the pinned comment, so an unbounded one is a write
into any field the workflow has -- a label, a park flag, another stage's
watermark -- and a misshapen value is the same damage one owner further on.
"""
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    drift as _drift,
    report_consumed_values as _consumed,
    report_record_state as _record_state,
    report_records as _records,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.stages.in_review import state as _in_review_state
from tests.workflow.engine import report_record_test_support as support

_BEHIND = 41

_AHEAD = 90

_WATERMARKS = "watermarks"

_SPENDS = "spends"


class DamagedRecordTest(unittest.TestCase):
    """A record nobody can act on reads as none, and still CLAIMS one."""

    def test_a_damaged_member_refuses_the_record(self) -> None:
        # One member per identity, routing, and subject group, because the
        # groups are refused together: a record that answered for whichever
        # member still typed would be acted on as a weaker binding rather than
        # as the damage it is.
        for member, broken in (
            ("receipt", "not a receipt!"),
            ("repo", "chippingway"),
            ("pr", 0),
            ("branch", "a branch with spaces"),
            ("sha", "3f78685"),
            ("requirements", "not-a-digest"),
            ("revision", -1),
            ("mode", "publish-later"),
            ("route", "workflow:inventing"),
            ("report", "   "),
        ):
            with self.subTest(member=member):
                state = support.damaged(support.PUBLISHED, **{member: broken})

                self.assertTrue(
                    _record_state.carries_pending_report(state),
                )
                self.assertIsNone(support.reads_back(state))

    def test_a_non_object_payload_refuses(self) -> None:
        state = PinnedState(state_data={_records.PENDING_REPORT: ["report"]})

        self.assertTrue(_record_state.carries_pending_report(state))
        self.assertIsNone(support.reads_back(state))

    def test_an_unreadable_comment_id_refuses(self) -> None:
        # Answering with the description instead would reread the pull
        # request's body -- a different place, holding somebody else's text --
        # against a revision nobody took there.
        state = support.damaged(support.VERIFIED, location_comment="8080")

        self.assertIsNone(support.reads_back(state))

    def test_a_damaged_handoff_proves_nothing(self) -> None:
        state = PinnedState(state_data={
            _records.REPORT_HANDOFF: {
                "receipt": support.RECEIPT, "pr": support.PR_NUMBER,
            },
        })

        self.assertIsNone(_settlement.read_handoff(state))


class BookkeepingVocabularyTest(unittest.TestCase):
    """A recovered record may only write fields this workflow knows."""

    def test_an_unusable_pair_refuses_the_record(self) -> None:
        for group, broken in (
            (_WATERMARKS, [["workflow_label", "workflow:done"]]),
            (_WATERMARKS, [[support.PR_WATERMARK, "later"]]),
            (_WATERMARKS, [[support.BASELINE, "not-a-digest"]]),
            (_SPENDS, [[support.REVIEW_ROUND, "later"]]),
            (_SPENDS, [[support.PENDING_FIX_AT, _BEHIND]]),
            (_WATERMARKS, "all of them"),
        ):
            with self.subTest(group=group, broken=broken):
                state = support.damaged(support.PUBLISHED, **{group: broken})

                self.assertIsNone(support.reads_back(state))

    def test_an_empty_group_owes_nothing(self) -> None:
        # An initial publication consumed no feedback and closed no reviewer
        # round, so an absent group is nothing owed rather than damage.
        state = support.damaged(
            support.PUBLISHED, **{_WATERMARKS: None, _SPENDS: None},
        )

        recovered = support.reads_back(state)

        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.watermarks, ())
        self.assertEqual(recovered.spends, ())

    def test_consumable_fields_match_their_owners(self) -> None:
        # The vocabulary is spelled as literals so this owner stays free of the
        # stage packages that write these fields, which is exactly what lets
        # the two drift apart unnoticed.
        self.assertEqual(support.PR_WATERMARK, _in_review_state._PR_LAST_COMMENT_ID)
        self.assertEqual(support.BASELINE, _drift._USER_CONTENT_HASH)
        self.assertEqual(_consumed.CONSUMABLE_FIELDS, frozenset((
            "last_action_comment_id",
            support.PR_WATERMARK,
            "pr_last_review_comment_id",
            "pr_last_review_summary_id",
            support.BASELINE,
        )))


class ConsumedWatermarkTest(unittest.TestCase):
    """Watermarks a settlement advances only ever move forward."""

    def test_a_watermark_is_never_moved_backwards(self) -> None:
        # The record was written before the publication it describes, so a
        # human may well have commented since: rolled back, that comment would
        # be handed to the next scan as fresh feedback.
        state = PinnedState(state_data={support.PR_WATERMARK: _AHEAD})

        _consumed.advance_consumed(state, ((support.PR_WATERMARK, _BEHIND),))

        self.assertEqual(state.get(support.PR_WATERMARK), _AHEAD)

    def test_a_forward_watermark_is_applied(self) -> None:
        state = PinnedState(state_data={support.PR_WATERMARK: 1})

        _consumed.advance_consumed(state, ((support.PR_WATERMARK, _BEHIND),))

        self.assertEqual(state.get(support.PR_WATERMARK), _BEHIND)

    def test_the_baseline_is_replaced(self) -> None:
        state = PinnedState(state_data={
            support.BASELINE: support.CONTENT_DIGEST,
        })

        _consumed.advance_consumed(
            state, ((support.BASELINE, support.REQUIREMENTS),),
        )

        self.assertEqual(state.get(support.BASELINE), support.REQUIREMENTS)


if __name__ == "__main__":
    unittest.main()
