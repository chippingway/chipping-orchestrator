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
    prompt_delivery as _delivery,
    report_consumed_values as _consumed,
    report_record_state as _record_state,
    report_record_values as _record_values,
    report_records as _records,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.stages.in_review import state as _in_review_state
from tests.workflow.engine import report_record_test_support as support

_BEHIND = 41

_AHEAD = 90

_WATERMARKS = "watermarks"

_SPENDS = "spends"

_LOCATION_PR = "location_pr"

# A number past what any identity, revision, or watermark may be recorded as.
_BEYOND_RECORDED = _record_values.MAX_RECORDED_NUMBER + 1


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
            ("report", support.LONE_SURROGATE),
            ("branch", support.LONE_SURROGATE),
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

    def test_a_widest_number_refuses_every_reader(self) -> None:
        # Each of these is copied into the records a settlement adds, so a
        # number wider than anything GitHub issues is a record that fits the
        # comment now and settles into one GitHub refuses -- after the report
        # is already on the thread.
        for member, broken in (
            ("pr", _BEYOND_RECORDED),
            ("revision", _BEYOND_RECORDED),
            ("location_comment", _BEYOND_RECORDED),
        ):
            with self.subTest(member=member):
                self.assertIsNone(support.reads_back(
                    support.damaged(support.VERIFIED, **{member: broken}),
                ))
        self.assertIsNone(_settlement.read_current_report(PinnedState(
            state_data={_records.CURRENT_REPORT: support.settled(
                revision=_BEYOND_RECORDED,
            )},
        )))

    def test_a_damaged_handoff_proves_nothing(self) -> None:
        state = PinnedState(state_data={
            _records.REPORT_HANDOFF: {
                "receipt": support.RECEIPT, "pr": support.PR_NUMBER,
            },
        })

        self.assertTrue(_settlement.carries_settled_record(state))
        self.assertIsNone(_settlement.read_handoff(state))

    def test_a_nulled_settled_record_still_claims(self) -> None:
        # Nothing clears either settled record -- a settlement REPLACES one --
        # so `null` there is a truncated write or a hand edit. Read as the
        # absence the pending record's own `null` means, it would be silently
        # replaced after the next report is posted, or published over a second
        # time because the handoff proving the first could not be seen.
        for key in (_records.CURRENT_REPORT, _records.REPORT_HANDOFF):
            with self.subTest(record=key):
                state = PinnedState(state_data={key: None})

                self.assertTrue(_settlement.carries_settled_record(state))
                self.assertIsNone(_settlement.read_current_report(state))
                self.assertIsNone(_settlement.read_handoff(state))


class ExactLocationTest(unittest.TestCase):
    """A location is exact in both halves, on the pending and settled records.

    Both readers answer through one owner, so both refuse the same two things:
    a comment id that cannot be read, and a place on some other pull request.
    A location names somewhere in the repository whatever the record is about --
    PR #13's description is perfectly readable and holds somebody else's text.
    """

    def test_an_unreadable_comment_id_refuses(self) -> None:
        self._refuses_pending(
            support.recorded(support.VERIFIED) | {support.LOCATION_COMMENT: "8080"},
        )

    def test_a_truncated_comment_field_refuses(self) -> None:
        # The writer puts the field on every place it records, so an absent one
        # was truncated. Read as the description, the verification would reread
        # the pull request's own body against a revision it took off a comment.
        self._refuses_pending(support.without(
            support.recorded(support.VERIFIED), support.LOCATION_COMMENT,
        ))

    def test_a_location_elsewhere_refuses(self) -> None:
        # Unbound, a transaction recorded for one pull request would reread
        # another's comment, find trusted content at the revision claimed, and
        # record it as the report this one carries.
        self._refuses_pending(support.recorded(support.VERIFIED) | {
            _LOCATION_PR: support.PR_NUMBER + 1,
        })

    def test_a_settled_truncation_refuses(self) -> None:
        # A current report answering with the description would hand a reviewer
        # the pull-request body in place of the comment the report is on.
        self._refuses_settled(
            support.without(support.settled(), support.LOCATION_COMMENT),
        )

    def test_a_settled_location_elsewhere_refuses(self) -> None:
        # A subject naming one pull request beside a location on another says
        # the report this pull request carries is somewhere else -- which is
        # what a reviewer would be handed, and what a later transaction would
        # compare its own revision against.
        self._refuses_settled(
            support.settled(location_pr=support.PR_NUMBER + 1),
        )

    def _refuses_pending(self, recorded: dict) -> None:
        """The pending record this object is claims nothing readable."""
        state = PinnedState(state_data={_records.PENDING_REPORT: recorded})

        self.assertTrue(_record_state.carries_pending_report(state))
        self.assertIsNone(support.reads_back(state))

    def _refuses_settled(self, recorded: dict) -> None:
        """The current report this object is claims nothing readable."""
        state = PinnedState(state_data={_records.CURRENT_REPORT: recorded})

        self.assertTrue(_settlement.carries_settled_record(state))
        self.assertIsNone(_settlement.read_current_report(state))


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
            # JSON is free to write a field name as an array, and a vocabulary
            # is a mapping: looked up, that pair raises out of the state read
            # instead of reading back as the damage it is. Both groups, because
            # each is bounded by a table of its own.
            (_WATERMARKS, [[[], 1]]),
            (_SPENDS, [[[], 1]]),
            # A boundary past every id GitHub will issue is one no later
            # comment can pass, and the ratchet that applies it only moves
            # forward: every human reply after it reads as already answered.
            (_WATERMARKS, [[support.PR_WATERMARK, _BEYOND_RECORDED]]),
        ):
            with self.subTest(group=group, broken=broken):
                state = support.damaged(support.PUBLISHED, **{group: broken})

                self.assertIsNone(support.reads_back(state))

    def test_an_empty_group_owes_nothing(self) -> None:
        # An initial publication consumed no feedback and closed no reviewer
        # round, and the encoder writes that as an empty array.
        state = support.damaged(
            support.PUBLISHED, **{_WATERMARKS: [], _SPENDS: []},
        )

        recovered = support.reads_back(state)

        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.watermarks, ())
        self.assertEqual(recovered.spends, ())

    def test_a_missing_group_is_damage(self) -> None:
        # The encoder writes both arrays on every record, so a group that is
        # not there was truncated or hand-edited. Read as an empty one, the
        # record would publish while silently dropping the watermarks and the
        # round it was supposed to close; only the whole additive record is a
        # legacy-safe absence.
        for group, nulled in (
            (_WATERMARKS, True),
            (_WATERMARKS, False),
            (_SPENDS, True),
            (_SPENDS, False),
        ):
            with self.subTest(group=group, nulled=nulled):
                recorded = support.recorded(support.PUBLISHED)
                recorded[group] = None
                if not nulled:
                    recorded.pop(group)
                state = PinnedState(state_data={
                    _records.PENDING_REPORT: recorded,
                })

                self.assertIsNone(support.reads_back(state))

    def test_consumable_fields_are_the_producers(self) -> None:
        # Read off the owner that PRODUCES these pairs rather than respelled,
        # because a surface it gained and this table had not would make one
        # member unreadable -- which refuses the whole group and holds a
        # transaction whose report is written and whose feedback is answered.
        self.assertEqual(_consumed.CONSUMABLE_FIELDS, frozenset((
            *_delivery.WATERMARK_FIELDS, _delivery.PINNED_USER_CONTENT_HASH,
        )))
        for field_name, allowed in (
            (support.PR_WATERMARK, _BEHIND),
            (support.BASELINE, support.REQUIREMENTS),
        ):
            with self.subTest(field=field_name):
                self.assertTrue(_consumed.consumable([field_name, allowed]))

    def test_the_producers_name_live_pinned_fields(self) -> None:
        # The other half of the binding: the producer's spellings are the keys
        # the stages that scan and ratchet them already carry on live issues,
        # so neither list can move without the other being wrong here.
        self.assertEqual(
            _delivery.PINNED_PR_LAST_COMMENT_ID,
            _in_review_state._PR_LAST_COMMENT_ID,
        )
        self.assertEqual(
            _delivery.PINNED_USER_CONTENT_HASH, _drift._USER_CONTENT_HASH,
        )
        self.assertEqual(support.PR_WATERMARK, _delivery.PINNED_PR_LAST_COMMENT_ID)
        self.assertEqual(support.BASELINE, _delivery.PINNED_USER_CONTENT_HASH)


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


class FrozenBookkeepingTest(unittest.TestCase):
    """The round and bookmarks a settlement closes come off the record."""

    def test_replaying_a_settlement_counts_once(self) -> None:
        # A round computed from the counter would be counted again by the tick
        # that replays a settlement a crash hid; re-applying the value the
        # transaction froze changes nothing the second time.
        state = PinnedState(state_data={support.REVIEW_ROUND: _BEHIND})

        _consumed.close_bookkeeping(state, support.PUBLISHED.spends)
        closed = dict(state.data)
        _consumed.close_bookkeeping(state, support.PUBLISHED.spends)

        self.assertEqual(state.data, closed)
        for owed_field, spent in support.PUBLISHED.spends:
            with self.subTest(owed=owed_field):
                self.assertEqual(state.get(owed_field), spent)


if __name__ == "__main__":
    unittest.main()
