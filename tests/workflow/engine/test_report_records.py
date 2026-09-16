# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the report records read back as, and what a comment may carry.

The compatibility cases matter most: these keys arrive on issues that are
already running, and an issue that has never seen them has to read back as one
that owes nothing rather than as one whose obligation nobody can describe.
"""
from __future__ import annotations

import unittest
from dataclasses import replace

from orchestrator.github.pinned_state import (
    MAX_PINNED_BODY,
    PinnedState,
    pinned_state_body,
)
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    comments as _comments,
    report_record_state as _record_state,
    report_record_values as _record_values,
    report_records as _records,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.late_split import formats as _formats
from orchestrator.workflow.stages.implementing import (
    late_publication_state as _publication_state,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import report_record_test_support as support

_OTHER_ROUND = 2

# The filler a crowding case fills the rest of the comment with.
_FILLER = "filler"

# The receipt a second transaction on the same issue runs under.
_LATER_RECEIPT = "issue-7-report-2"

# A receipt the published report header could not carry verbatim, so no retry
# could ever find its own comment by it.
_UNCARRIABLE_RECEIPT = "issue 7 report 2"

# A number past what any identity or revision may be recorded as.
_BEYOND_RECORDED = _record_values.MAX_RECORDED_NUMBER + 1


def _reserved() -> int:
    """What a record reserves on the comment for the writes that follow it.

    The comment-id entry publishing the report leaves, and the receipt the
    publication gate writes when it pushes the commit. Both are read off the
    owners the measurement itself replays rather than spelled here, because
    what a crowding case has to allow for IS that measurement: a number of its
    own would pass while the reservation drifted away from it.
    """
    entered = PinnedState()
    _comments._reserve_comment_slot(entered, _record_values.MAX_RECORDED_NUMBER)
    _publication_state._record_publication(
        entered, _WIDEST_COMMIT, _WIDEST_COMMIT, _record_values.MAX_RECORDED_NUMBER,
    )
    return len(pinned_state_body(entered.data)) - len(pinned_state_body({}))


# The widest either commit member of a publication receipt is recorded at.
_WIDEST_COMMIT = "f" * max(_formats.COMMIT_LENGTHS)

_RESERVED = _reserved()


def _published(**fields) -> _records.PendingReport:
    """The publication fixture with one member replaced."""
    return replace(support.PUBLISHED, **fields)


def _verified(**fields) -> _records.PendingReport:
    """The verification fixture with one member replaced."""
    return replace(support.VERIFIED, **fields)


class LegacyCompatibilityTest(unittest.TestCase):
    """An issue that predates these records owes nothing and loses nothing."""

    def test_no_report_keys_owes_nothing(self) -> None:
        state = PinnedState()

        self.assertFalse(_record_state.carries_pending_report(state))
        self.assertIsNone(support.reads_back(state))
        self.assertIsNone(_settlement.read_current_report(state))
        self.assertIsNone(_settlement.read_handoff(state))

    def test_a_cleared_record_reads_as_absent(self) -> None:
        state = PinnedState()
        _record_state.record_pending_report(state, support.PUBLISHED)
        _record_state.clear_pending_report(state)

        self.assertIsNone(support.reads_back(state))

    def test_other_keys_are_untouched(self) -> None:
        state = PinnedState(state_data={
            "pr_number": support.PR_NUMBER,
            support.REVIEW_ROUND: _OTHER_ROUND,
        })

        _record_state.record_pending_report(state, support.PUBLISHED)

        self.assertEqual(state.get("pr_number"), support.PR_NUMBER)
        self.assertEqual(state.get(support.REVIEW_ROUND), _OTHER_ROUND)


class RoundTripTest(unittest.TestCase):
    """Each record reads back exactly what was written."""

    def test_each_transaction_round_trips(self) -> None:
        for shape, pending in (
            ("publication", support.PUBLISHED),
            ("verification", support.VERIFIED),
            # The description is a real location, and the only one whose
            # comment field is recorded as the `null` that means it.
            ("described", _verified(
                location=ReportLocation(pr_number=support.PR_NUMBER),
            )),
        ):
            with self.subTest(shape=shape):
                state = PinnedState()

                self.assertTrue(
                    _record_state.record_pending_report(state, pending),
                )
                self.assertTrue(_record_state.carries_pending_report(state))
                self.assertEqual(support.reads_back(state), pending)

    def test_three_records_coexist(self) -> None:
        # None of the three replaces another. A second publication records its
        # transaction while the previous report and its receipt are still what
        # the pull request carries -- a reader handed the current report during
        # that window needs the one that landed, not the one being written --
        # and the settlement ending it is what replaces them.
        state = PinnedState()
        _settlement.record_current_report(state, support.CURRENT)
        _settlement.record_handoff(state, support.HANDOFF)
        later = _published(
            receipt=_LATER_RECEIPT, report_revision=support.REVISION + 1,
        )

        self.assertTrue(_record_state.record_pending_report(state, later))

        self.assertTrue(_record_state.carries_pending_report(state))
        self.assertTrue(_settlement.carries_settled_record(state))
        self.assertEqual(support.reads_back(state), later)
        self.assertEqual(
            _settlement.read_current_report(state), support.CURRENT,
        )
        self.assertEqual(_settlement.read_handoff(state), support.HANDOFF)

    def test_a_settlement_replaces_what_it_found(self) -> None:
        settling = replace(
            support.CURRENT, report_revision=support.REVISION + 1,
        )
        state = PinnedState()
        _settlement.record_current_report(state, support.CURRENT)
        _record_state.record_pending_report(state, support.PUBLISHED)

        _settlement.record_current_report(state, settling)
        _record_state.clear_pending_report(state)

        self.assertEqual(_settlement.read_current_report(state), settling)
        self.assertIsNone(support.reads_back(state))

    def test_a_settled_record_is_proved_first(self) -> None:
        # Stored, each of these reads back as damage on the very next tick, and
        # the issue then carries a settled record nobody can act on in place of
        # the one the report it just published deserved.
        for refused, writer, settling in (
            (
                "current location elsewhere",
                _settlement.record_current_report,
                replace(support.CURRENT, location=ReportLocation(
                    pr_number=support.PR_NUMBER + 1,
                    comment_id=support.COMMENT_ID,
                )),
            ),
            (
                "current revision past the ceiling",
                _settlement.record_current_report,
                replace(support.CURRENT, report_revision=_BEYOND_RECORDED),
            ),
            (
                "handoff receipt no header could carry",
                _settlement.record_handoff,
                replace(support.HANDOFF, receipt=_UNCARRIABLE_RECEIPT),
            ),
            (
                "handoff revision past the ceiling",
                _settlement.record_handoff,
                replace(support.HANDOFF, report_revision=_BEYOND_RECORDED),
            ),
        ):
            with self.subTest(refused=refused):
                state = PinnedState()

                self.assertFalse(writer(state, settling))
                self.assertEqual(state.data, {})
                self.assertFalse(_settlement.carries_settled_record(state))

    def test_a_settlement_round_trips(self) -> None:
        state = PinnedState()

        _settlement.record_current_report(state, support.CURRENT)
        _settlement.record_handoff(state, support.HANDOFF)

        self.assertEqual(
            _settlement.read_current_report(state), support.CURRENT,
        )
        self.assertEqual(_settlement.read_handoff(state), support.HANDOFF)


class BoundedRecordTest(unittest.TestCase):
    """A record describing a publication this build could not make is refused."""

    def test_a_report_past_the_ceiling_refuses(self) -> None:
        state = support.damaged(
            support.PUBLISHED,
            report="x" * (_record_values.MAX_REPORT_TEXT + 1),
        )

        self.assertIsNone(support.reads_back(state))

    def test_a_report_quoting_a_marker_refuses(self) -> None:
        # A thread is searched for receipts by substring, so a report carrying
        # one would read to that search as the step it names.
        state = support.damaged(
            support.PUBLISHED,
            report="I added <!--orchestrator-developer-report: too",
        )

        self.assertIsNone(support.reads_back(state))

    def test_an_unsettleable_record_is_refused(self) -> None:
        # The settling write happens AFTER the report is posted, so a record
        # accepted at the ceiling and settled past it would leave a published
        # comment, a record still claiming it is owed, and a retry that fails
        # identically for the rest of the issue's life.
        #
        # The fixture owes both groups on purpose. A settlement is not the two
        # records alone: it advances the watermarks the run consumed, closes
        # the round and bookmarks its route spent, and records the comment the
        # published report lands as, and every one of those lands on this same
        # comment -- so a transaction that owes bookkeeping settles LARGER than
        # the pending record it drops even where the report text is the bigger
        # half. The receipt the publication gate writes lands on it too, which
        # is why the room a record needs is more than the record itself.
        measured = PinnedState()
        _record_state.record_pending_report(measured, support.PUBLISHED)
        recorded = measured.get(_records.PENDING_REPORT)
        # Crowd the comment to exactly what the pending record itself needs, so
        # the only room left to refuse on is the settling write's.
        room = MAX_PINNED_BODY - len(pinned_state_body({
            _FILLER: "", _records.PENDING_REPORT: recorded,
        }))
        crowded = PinnedState(state_data={_FILLER: "y" * room})

        self.assertFalse(
            _record_state.record_pending_report(crowded, support.PUBLISHED),
        )
        self.assertFalse(_record_state.carries_pending_report(crowded))
        # The record itself fitted exactly: it is the room settlement needs
        # that this refusal is about.
        self.assertEqual(
            len(pinned_state_body({
                **crowded.data, _records.PENDING_REPORT: recorded,
            })),
            MAX_PINNED_BODY,
        )
        # And the bookkeeping is part of that room: the same transaction owing
        # none of it is accepted where this one was refused, once the writes
        # that follow a record -- the comment-id entry the publication road
        # adds, and the receipt the publication gate writes -- are allowed for
        # beside it.
        self.assertTrue(_record_state.record_pending_report(
            PinnedState(state_data={_FILLER: "y" * (room - _RESERVED)}),
            replace(support.PUBLISHED, watermarks=(), spends=()),
        ))

    def test_an_unreadable_record_is_not_written(self) -> None:
        # Size is only one of the ways a transaction can be unpublishable.
        # Written anyway, every one of these reads back as damage on the very
        # next tick -- and the issue parks for a record this process itself
        # produced. The locationless verification is the one a CALLER can
        # construct by leaving a field at its default, so the refusal has to be
        # returned rather than raised out of the middle of the write. The two
        # unencodable ones would be written and read back happily and raise at
        # the digest that hashes a report or the request that carries it.
        for unwritable, refused in (
            (_published(report="x" * (_record_values.MAX_REPORT_TEXT + 1)), "text"),
            (_published(report_revision=_BEYOND_RECORDED), "revision"),
            (_published(report=support.LONE_SURROGATE), "unencodable report"),
            (_published(subject=replace(
                support.SUBJECT, branch=support.LONE_SURROGATE,
            )), "unencodable branch"),
            (_verified(location=ReportLocation(support.PR_NUMBER + 1)), "elsewhere"),
            (_verified(location=None), "unplaced"),
        ):
            with self.subTest(refused=refused):
                state = PinnedState()

                self.assertFalse(
                    _record_state.record_pending_report(state, unwritable),
                )
                self.assertFalse(
                    _record_state.carries_pending_report(state),
                )

    def test_an_unfittable_record_is_not_written(self) -> None:
        half = MAX_PINNED_BODY // 2
        state = PinnedState(state_data={_FILLER: "y" * half})
        oversized = _records.PendingReport(
            receipt=support.RECEIPT,
            subject=support.SUBJECT,
            report_revision=1,
            mode=_records.ReportMode.PUBLISH,
            route=WorkflowLabel.VALIDATING,
            report="z" * half,
        )

        self.assertFalse(
            _record_state.record_pending_report(state, oversized),
        )
        self.assertFalse(_record_state.carries_pending_report(state))


if __name__ == "__main__":
    unittest.main()
