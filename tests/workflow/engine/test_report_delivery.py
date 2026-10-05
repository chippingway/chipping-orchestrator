# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report a completed run leaves behind, and the transaction it becomes.

Two halves, in the order they happen. A run's outcome is recorded before its
code is published, holding everything the session settled and nothing a pull
request decides -- and what the transaction it becomes will cost is reserved
there too, since the binding happens after the push and a report refused then
is one the code went out without. Then the publication arrives and the record
is bound to it: one write that drops the delivery and records the transaction,
or no write at all and a refusal that says which of the two it was.

Beside them, what the comment has to have room for before either happens, and
which of those measurements a refusal for the room names -- apart from a report
its own reading refuses, which no room would make recordable -- and what the
park a refused report takes tells the human who has to answer it.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState, pinned_state_body
from orchestrator.workflow.engine import (
    report_delivery as _delivery,
    report_delivery_state as _delivery_state,
    report_record_room as _room,
    report_record_state as _record_state,
    report_record_values as _record_values,
    report_records as _records,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow import report_refusals as _refusals
from tests.workflow.engine import (
    report_commit_test_support as commit_support,
    report_delivery_test_support as delivery_support,
    report_record_test_support as support,
)
from tests.workflow.fixtures import (
    PROVIDER_OVERLOAD_MESSAGE,
    _agent,
)

# Why a delivered report's own reading refuses it.
_REFUSAL = _record_values.RecordRefusal

# A finished run's message ending on the report the ordinary delivery records.
_READY = delivery_support.ready(delivery_support.DELIVERED.report)

# A notice offered to a park that is still standing, which nobody may be sent.
_SECOND_NOTICE = "The report this issue owes still cannot be delivered."

# What a park may tell a human whose pull request is open, and what it may not.
_NEVER_OPENED = "no pull request was opened"

_STILL_STANDS = "the pull request still stands on the commit it already carried"

# The roads that record a report, by whether the work already has a pull
# request when this owner parks.
_ROADS = (
    (WorkflowLabel.IMPLEMENTING, False),
    (_records.HandedRun(WorkflowLabel.VALIDATING, support.REQUIREMENTS), True),
    (WorkflowLabel.IN_REVIEW, True),
)

# The two parks this owner takes: a run that committed and reported nothing,
# and a report no record could hold -- here, one past what a comment carries,
# over a comment naming no requirements for a subject to be proved against.
_PARKS = (
    ("a run that reported nothing", "implemented"),
    (
        "a report no record holds",
        delivery_support.ready(delivery_support.UNPUBLISHABLE_REPORTS[0][1]),
    ),
)


class DeliveredReportRecordTest(unittest.TestCase):
    def test_both_modes_round_trip(self) -> None:
        for delivered_report in (delivery_support.DELIVERED, delivery_support.ASSERTED):
            with self.subTest(mode=delivered_report.mode):
                state = PinnedState()

                self.assertIsNone(_delivery_state.stage_delivered_report(
                    state, delivered_report,
                ))

                self.assertTrue(
                    _delivery_state.carries_delivered_report(state),
                )
                self.assertEqual(
                    _delivery_state.read_delivered_report(state),
                    delivered_report,
                )

    def test_a_claim_is_not_an_absence(self) -> None:
        # A record cleared holds `null` and owes nothing; one a hand edit left
        # as something else owes a report nobody can describe, and the two may
        # never read the same.
        cleared = PinnedState()
        _delivery_state.clear_delivered_report(cleared)
        claimed = PinnedState(state_data={_records.DELIVERED_REPORT: []})

        self.assertFalse(_delivery_state.carries_delivered_report(cleared))
        self.assertTrue(_delivery_state.carries_delivered_report(claimed))
        for state in (cleared, claimed):
            with self.subTest(recorded=state.get(_records.DELIVERED_REPORT)):
                self.assertIsNone(
                    _delivery_state.read_delivered_report(state),
                )

    def test_an_unpublishable_report_is_refused(self) -> None:
        # Each is a record describing a publication this build could never
        # make, refused for the reason its reading names -- the receipt it
        # quotes and the length past its ceiling apart from every other
        # invalid record -- and none of them writes anything, so the caller
        # hears it while the run is still there. Offered a comment with no
        # room for its transaction either, each is still refused for what it
        # says rather than for the room: no room would make it recordable.
        for described, text, refusal in delivery_support.UNPUBLISHABLE_REPORTS:
            with self.subTest(report=described):
                state = delivery_support.crowded_comment(
                    delivery_support.CROWDED_FOR_RESERVATION,
                )
                found = dict(state.data)

                self.assertIs(
                    _delivery_state.stage_delivered_report(
                        state, replace(delivery_support.DELIVERED, report=text),
                    ),
                    refusal,
                )

                self.assertEqual(state.data, found)

    def test_a_locationless_verify_is_refused(self) -> None:
        # A location is what a verification is: with none there is nothing to
        # re-read, so the record is refused rather than written as a
        # publication with no text.
        state = PinnedState()

        self.assertIs(
            _delivery_state.stage_delivered_report(
                state, replace(delivery_support.ASSERTED, location=None),
            ),
            _REFUSAL.INVALID_RECORD,
        )

        self.assertEqual(state.data, {})

    def test_a_refusal_keeps_the_standing_delivery(self) -> None:
        # Whatever refuses a second report -- its text, its record, or the
        # room its transaction would need -- writes nothing, so the delivery an
        # earlier run left is still the one the comment carries, and the
        # boolean writer is refused wherever the structured one is.
        for described, report, _ in (
            *delivery_support.UNPUBLISHABLE_REPORTS,
            ("no room for its transaction", delivery_support.REDELIVERED.report, None),
        ):
            with self.subTest(refused=described):
                crowded = delivery_support.crowded_comment(
                    delivery_support.CROWDED_FOR_RESERVATION,
                    {_records.DELIVERED_REPORT: delivery_support.delivered_object()},
                )
                found = dict(crowded.data)

                self.assertIsNotNone(_delivery_state.stage_delivered_report(
                    crowded, replace(delivery_support.REDELIVERED, report=report),
                ))
                self.assertFalse(_delivery_state.record_delivered_report(
                    crowded, replace(delivery_support.REDELIVERED, report=report),
                ))

                self.assertEqual(crowded.data, found)
                self.assertEqual(
                    _delivery_state.read_delivered_report(crowded),
                    delivery_support.DELIVERED,
                )


class DeliveredReportCapacityTest(unittest.TestCase):
    """What the comment has to have room for before a record is accepted.

    Four writes, and the record's own is only the first: the transaction it
    is bound into after the push, the code-publication receipt the push
    itself leaves, and the fields a stale-approval hand-back adds on the road
    a review stage's drift resume takes all land on this same comment. A
    record accepted without room for any of them is one refused when nothing
    can be asked of the run that wrote the report -- and refused here, it is
    refused for the room, naming which of those comments came out too large.
    """

    def test_a_record_past_the_comment_is_refused(self) -> None:
        # The record shares the comment with everything else this issue has
        # recorded, so what is measured is the write it would make -- and
        # that write's own size is what the refusal reports.
        crowded = delivery_support.crowded_comment(0)

        overflow = _overflow_of(self, crowded, delivery_support.DELIVERED)

        self.assertEqual(
            (overflow.write, overflow.later, overflow.size),
            (
                _room.MeasuredWrite.RECORD,
                _room.LaterWrites(),
                len(pinned_state_body({
                    **crowded.data,
                    _records.DELIVERED_REPORT: delivery_support.delivered_object(),
                })),
            ),
        )

    def test_a_transaction_past_the_comment(self) -> None:
        # The delivered record fits and the transaction it will be bound into
        # does not, which is the whole reason the second write is measured
        # where the first one is: the binding happens after the push, so a
        # report accepted here and refused there is one the code went out
        # without. The refusal is the transaction's own writer's, carried
        # through as the binding it is from the delivery's side.
        crowded = delivery_support.crowded_comment(delivery_support.CROWDED_FOR_RESERVATION)

        self.assertTrue(_record_state.fits_the_comment({
            **crowded.data, _records.DELIVERED_REPORT: delivery_support.delivered_object(),
        }))
        overflow = _overflow_of(self, crowded, delivery_support.DELIVERED)

        self.assertEqual(
            (overflow.write, overflow.later),
            (_room.MeasuredWrite.BINDING, _room.LaterWrites()),
        )

    def test_the_reservation_is_the_write_it_makes(self) -> None:
        # What is reserved is the comment the BINDING leaves, which is the
        # delivery dropped and the transaction in its place. A first delivery
        # has to carry the `null` that drop writes; a redelivery gets back the
        # room the record it replaces is holding. Measured over the comment as
        # it stands, the first is accepted and then refused with the code
        # already pushed, and the second is refused with room to spare. What
        # the first runs out of is that transaction's settlement beside the
        # receipt the push writes, which its writer measures and this refusal
        # carries through unchanged.
        tombstoned = delivery_support.crowded_comment(
            delivery_support.CROWDED_FOR_TOMBSTONE, reviewed=True,
        )
        replaced = delivery_support.crowded_comment(
            delivery_support.CROWDED_FOR_REDELIVERY,
            {_records.DELIVERED_REPORT: delivery_support.delivered_object()},
            reviewed=True,
        )

        overflow = _overflow_of(self, tombstoned, delivery_support.DELIVERED)
        self.assertTrue(
            _delivery_state.record_delivered_report(replaced, delivery_support.DELIVERED),
        )

        self.assertEqual(
            (overflow.write, overflow.later),
            (_room.MeasuredWrite.SETTLEMENT, _room.LaterWrites(receipt=True)),
        )
        self.assertEqual(
            _delivery_state.binds_delivered_report(
                PinnedState(state_data={
                    **tombstoned.data,
                    _records.DELIVERED_REPORT: delivery_support.delivered_object(),
                }),
                delivery_support.DELIVERED,
                delivery_support.WIDEST_SUBJECT,
            ),
            _delivery_state.CROWDED_COMMENT,
        )
        self.assertEqual(
            _delivery_state.binds_delivered_report(
                replaced, delivery_support.DELIVERED, delivery_support.WIDEST_SUBJECT,
            ),
            "",
        )

    def test_the_push_s_own_write_is_reserved(self) -> None:
        # Between this record and the transaction it becomes stands the push,
        # and the gate that pushes writes the code-publication receipt onto
        # this same comment. So the comment this write leaves has to still
        # have room for that one -- over everything the issue already carries,
        # a transaction an earlier publication left outstanding included,
        # which is a world the exchanged reservation never measures.
        crowded = delivery_support.crowded_comment(
            delivery_support.OUTSTANDING_REPORT
            + delivery_support.CROWDED_FOR_RECEIPT,
            delivery_support.outstanding_comment(),
        )
        staged = {
            **crowded.data,
            _records.DELIVERED_REPORT: delivery_support.delivered_object(),
        }
        pushed = {
            **_room.with_later_writes(crowded, receipt=True).data,
            _records.DELIVERED_REPORT: delivery_support.delivered_object(),
        }

        self.assertTrue(_record_state.fits_the_comment(staged))
        self.assertFalse(_record_state.fits_the_comment(pushed))
        overflow = _overflow_of(self, crowded, delivery_support.DELIVERED)

        self.assertEqual(
            (overflow.write, overflow.later, overflow.size),
            (
                _room.MeasuredWrite.RECORD,
                _room.LaterWrites(receipt=True),
                len(pinned_state_body(pushed)),
            ),
        )

    def test_the_hand_back_s_own_write_is_reserved(self) -> None:
        # A report the `in_review` drift resume records is accepted before
        # the stale-approval hand-back runs, and that hand-back writes a
        # fresh review round, the marker saying the label move is owed, and
        # the record that this publication's budget is already reset -- all
        # onto this same comment, between the record and the binding. This
        # comment has room for the record and for the transaction it becomes,
        # and none for them with those fields beside them: accepted there,
        # the binding is the write refused, with the code out and no run left
        # to ask. It is reserved for the one route that makes that write:
        # the same comment takes an implementation's report, whose road
        # never hands an approval back and must not be charged for one.
        crowded = delivery_support.crowded_comment(
            delivery_support.CROWDED_FOR_HAND_BACK, reviewed=True,
        )
        ordinary = delivery_support.crowded_comment(
            delivery_support.CROWDED_FOR_HAND_BACK, reviewed=True,
        )
        staged = {
            **crowded.data,
            _records.DELIVERED_REPORT: delivery_support.delivered_object(
                delivery_support.HANDED_BACK,
            ),
        }

        self.assertTrue(_record_state.fits_the_comment(staged))
        self.assertEqual(
            _delivery_state.binds_delivered_report(
                PinnedState(state_data=staged),
                delivery_support.HANDED_BACK,
                delivery_support.WIDEST_SUBJECT,
            ),
            "",
        )
        overflow = _overflow_of(self, crowded, delivery_support.HANDED_BACK)
        self.assertTrue(_delivery_state.record_delivered_report(
            ordinary, delivery_support.DELIVERED,
        ))

        self.assertEqual(
            (overflow.write, overflow.later),
            (
                _room.MeasuredWrite.SETTLEMENT,
                _room.LaterWrites(receipt=True, hand_back=True),
            ),
        )

    def test_the_widest_branch_is_reserved(self) -> None:
        # What the comment charges for a branch is not what the reader counts:
        # the field is bounded in codepoints and the comment in the characters
        # JSON renders them as, so one codepoint outside the BMP costs twelve
        # -- and a ref of 256 of them is one git makes without complaint.
        # Reserved at the ASCII width, this report is accepted and then
        # refused with the code already pushed; reserved at the width the
        # rendering charges, it is refused here instead, while the comment
        # that does have room for it binds that branch.
        wide = replace(delivery_support.WIDEST_SUBJECT, branch=delivery_support.WIDEST_BRANCH)
        crowded = delivery_support.crowded_comment(
            delivery_support.CROWDED_FOR_ASCII_BRANCH, reviewed=True,
        )
        roomy = delivery_support.crowded_comment(
            delivery_support.CROWDED_FOR_RESERVED_SUBJECT, reviewed=True,
        )

        overflow = _overflow_of(self, crowded, delivery_support.DELIVERED)
        self.assertTrue(
            _delivery_state.record_delivered_report(roomy, delivery_support.DELIVERED),
        )

        self.assertIs(overflow.write, _room.MeasuredWrite.BINDING)
        self.assertEqual(
            _delivery_state.binds_delivered_report(roomy, delivery_support.DELIVERED, wide), "",
        )

    def test_the_text_s_ceiling_is_not_the_comment_s(self) -> None:
        # A report at its own ceiling is a report, and on a comment whose
        # other records take the headroom that ceiling leaves it is refused for
        # the ROOM; one character past it is refused for its LENGTH on every
        # comment, an empty one included, since no room makes it recordable.
        at_ceiling = replace(
            delivery_support.DELIVERED,
            report=delivery_support.FILLER * _record_values.MAX_REPORT_TEXT,
        )
        past_ceiling = replace(
            at_ceiling, report=f"{at_ceiling.report}{delivery_support.FILLER}",
        )
        headroom = {
            delivery_support.CROWDING: delivery_support.FILLER * (
                MAX_PINNED_BODY - _record_values.MAX_REPORT_TEXT
            ),
        }
        for described, carried in (
            ("an empty comment", {}),
            ("a comment without the headroom", headroom),
        ):
            with self.subTest(comment=described):
                self.assertIs(
                    _delivery_state.stage_delivered_report(
                        PinnedState(state_data=dict(carried)), past_ceiling,
                    ),
                    _REFUSAL.REPORT_TOO_LONG,
                )
        self.assertIsNone(
            _delivery_state.stage_delivered_report(PinnedState(), at_ceiling),
        )
        self.assertIs(
            _overflow_of(self, PinnedState(state_data=dict(headroom)), at_ceiling).write,
            _room.MeasuredWrite.RECORD,
        )


def _overflow_of(
    case: unittest.TestCase,
    state: PinnedState,
    delivered: _records.DeliveredReport,
) -> _room.CommentOverflow:
    """The room this delivery is refused for, having written nothing.

    Every overflow names a comment past the one ceiling GitHub holds a pinned
    comment to, and the caller's state is exactly as it was found.
    """
    found = dict(state.data)
    refused = _delivery_state.stage_delivered_report(state, delivered)

    case.assertIsInstance(refused, _room.CommentOverflow)
    case.assertEqual(refused.limit, MAX_PINNED_BODY)
    case.assertGreater(refused.size, refused.limit)
    case.assertEqual(state.data, found)
    return refused


class ReportedRunTest(unittest.TestCase):
    """What a run EARNS, and what recording it leaves on the comment.

    A run that completed owes a report, because every developer prompt asks
    for one; a run that never reached its own end owes nothing, because there
    was nobody to hold to the contract. What a run that DID report leaves is
    a durable record, minted past every revision this issue has already used.
    """

    def test_a_run_that_reported_nothing_holds(self) -> None:
        # Every way a run that COMPLETED can hand over no report: no marker at
        # all, a question, a block nothing closed, and a verification naming
        # another repository -- which is a location this workflow would
        # re-read on somebody else's thread. Each holds the tick and parks,
        # and the park is what remembers the debt, since there is no report to
        # record.
        messages = (
            ("no marker at all", "implemented"),
            ("a question", "which database should this use?"),
            ("a report block nothing closed", "REPORT: READY\nthe report"),
            ("another repository", (
                "REPORT: VERIFIED https://github.com/someone/else/pull/3"
                f" sha256:{support.CONTENT_DIGEST}"
            )),
        )
        for described, message in messages:
            with self.subTest(message=described):
                state = PinnedState(state_data={delivery_support.BASELINE: support.REQUIREMENTS})

                self.assertTrue(commit_support.records(state, _agent(last_message=message))[0])

                self.assertFalse(
                    _delivery_state.carries_delivered_report(state),
                )
                self.assertEqual(
                    (state.get(delivery_support.PARK_REASON), _delivery.owes_a_report(state)),
                    (_delivery.UNDELIVERABLE_REPORT, True),
                )

    def test_the_debt_outlives_its_park(self) -> None:
        # The flags are single, so a later park -- a resumed run that timed out
        # -- replaces the reason. The debt is kept beside it, so the issue
        # still owes its report, until a run that reports retires both.
        state = PinnedState(state_data={delivery_support.BASELINE: support.REQUIREMENTS})
        _stopped, *seeded = commit_support.records(state, _agent(last_message="implemented"))
        state.set(delivery_support.PARK_REASON, "agent_timeout")
        self.assertEqual(
            (state.get(_delivery.OWED_REPORT), _delivery.owes_a_report(state)),
            (True, True),
        )

        self.assertFalse(_delivery.recording_stops_the_tick(
            *seeded, state,
            _agent(last_message=delivery_support.ready("The report.")),
            WorkflowLabel.IMPLEMENTING,
        ))

        self.assertIsNone(state.get(_delivery.OWED_REPORT))
        self.assertTrue(_delivery_state.carries_delivered_report(state))

    def test_a_standing_legacy_park_takes_the_debt(self) -> None:
        # A park taken before the debt had a field of its own carries the
        # reason alone. Met again while it stands, it is told nothing new, and
        # the debt is written down, so the park that replaces the reason next
        # leaves the report still owed.
        github, issue = delivery_support.seeded_issue()
        state = PinnedState(state_data=dict(delivery_support.OWED) | {
            delivery_support.AWAITING_HUMAN: True,
        })

        _delivery.parks_an_undeliverable_report(
            github, issue, state, _SECOND_NOTICE,
        )
        state.set(delivery_support.PARK_REASON, "agent_timeout")

        self.assertEqual(
            (
                [posted.body for posted in issue.comments].count(_SECOND_NOTICE),
                github.pinned_data(issue.number)[_delivery.OWED_REPORT],
                _delivery.owes_a_report(state),
            ),
            (0, True, True),
        )

    def test_a_run_no_process_finished_holds_nothing(self) -> None:
        # Every way a run falls short of its own end: one no process produced
        # at all -- the sentence a caller synthesizes to publish committed
        # work an earlier run left -- and the four a shutdown kill, the
        # orchestrator's own timeout, a provider refusal -- the marker the
        # provider sends beside a nonzero exit -- and an exit of its own. The
        # rest carry a well-formed report, so the judgement is visibly about
        # the RUN rather than about its message: none of these is a developer
        # declining to report, so nothing is recorded and nothing is held.
        runs = (
            ("nothing invoked", {"invoked": False}),
            ("a shutdown kill", {"interrupted": True}),
            ("the orchestrator's timeout", {"timed_out": True}),
            (
                "a provider refusal",
                {"last_message": PROVIDER_OVERLOAD_MESSAGE, "exit_code": 1},
            ),
            ("a nonzero exit", {"exit_code": 3}),
        )
        for described, run in runs:
            with self.subTest(run=described):
                state = PinnedState(state_data={delivery_support.BASELINE: support.REQUIREMENTS})

                finished = _agent(**{"last_message": _READY, **run})

                self.assertFalse(commit_support.records(state, finished)[0])

                self.assertFalse(_delivery.owes_a_report(state))

    def test_a_verified_report_is_recorded(self) -> None:
        # A run that says the report is already on this repository's thread
        # records the exact place and the digest it read there. Nothing of it
        # is believed here: what settles is a fresh read of that location.
        state = PinnedState(state_data={delivery_support.BASELINE: support.REQUIREMENTS})

        self.assertFalse(commit_support.records(state, _agent(last_message=_ASSERTING))[0])

        self.assertEqual(
            _delivery_state.read_delivered_report(state), delivery_support.ASSERTED,
        )

    def test_a_repository_nobody_could_read(self) -> None:
        # The one reading on this road that leaves the process: whether the
        # location a verification names is on this repository. Raised, it
        # would take the tick down with the only copy of what the developer
        # said and leave the commit in a worktree nothing had said anything
        # about -- so it is held for a human exactly as a location on somebody
        # else's repository is.
        state = PinnedState(
            state_data={delivery_support.BASELINE: support.REQUIREMENTS},
        )
        github, issue = commit_support.pinned(delivery_support.seeded_issue(), state)
        delivery_support.unreachable_repository(github)

        self.assertTrue(_delivery.recording_stops_the_tick(
            github, issue, state, _agent(last_message=(
                f"done\n\nREPORT: VERIFIED https://github.com/{support.SLUG}"
                f"/pull/{support.PR_NUMBER} sha256:{support.CONTENT_DIGEST}"
            )),
            WorkflowLabel.IMPLEMENTING,
        ))

        self.assertFalse(_delivery_state.carries_delivered_report(state))
        self.assertEqual(
            (
                state.get(delivery_support.AWAITING_HUMAN),
                state.get(delivery_support.PARK_REASON),
            ),
            (True, _delivery.UNDELIVERABLE_REPORT),
        )

    def test_no_baseline_parks_the_tick(self) -> None:
        # The requirements revision is the one member of a subject the run
        # settles, and a record without it is a transaction nothing could
        # prove again -- so the report cannot be recorded, and a report this
        # build cannot record holds the tick rather than letting the code go
        # out without one.
        state = PinnedState()

        self.assertTrue(commit_support.records(state, _agent(last_message=_READY))[0])

        self.assertFalse(_delivery_state.carries_delivered_report(state))
        self.assertEqual(
            (state.get(delivery_support.AWAITING_HUMAN), state.get(delivery_support.PARK_REASON)),
            (True, _delivery.UNDELIVERABLE_REPORT),
        )


# The report records a refusal has to leave exactly as it found them.
_REPORT_RECORDS = (
    _records.DELIVERED_REPORT, _records.PENDING_REPORT, _records.CURRENT_REPORT,
)

# The ceiling a recorded report is held to, and one character past it.
_CEILING = _record_values.MAX_REPORT_TEXT

_PAST_CEILING = _CEILING + 1

# The refusals a report's own record is given, whatever room the comment has:
# the report that earns each, the requirements the comment names, and what is
# said. A quoted receipt and an invalid record were measured for nothing, so
# neither says anything about size; a report past its ceiling names its own
# length and never the comment's room. The invalid one is recorded over a
# comment naming no requirements, a member no rewrite of the report supplies.
_OWN_REFUSALS = (
    ("a quoted receipt", _refusals.QUOTING_REPORT, support.REQUIREMENTS, _refusals.RECEIPT_REFUSAL),
    (
        "a report past its ceiling",
        delivery_support.FILLER * _PAST_CEILING,
        support.REQUIREMENTS,
        _refusals.Said(
            notice=(
                f"the report is {_PAST_CEILING} characters long, past the {_CEILING} a recorded report may be",
                f"Reply asking for a report of at most {_CEILING} characters",
            ),
            logged=f"of {_PAST_CEILING} characters, past the {_CEILING} a recorded report may be (report_too_long)",
            unsaid=("GitHub accepts", "room"),
        ),
    ),
    (
        "an invalid record",
        delivery_support.DELIVERED.report,
        None,
        _refusals.Said(
            notice=("would not hand back as written", "Inspect this issue's pinned comment"),
            logged="(invalid_record; route workflow:implementing, requirements revision none)",
        ),
    ),
)

# What a notice for the comment's room never claims: that the report is past
# its own ceiling, which it is inside of.
_NOT_THE_TEXT = ("a recorded report may be",)

# What a notice asking for a rewrite says the rewrite has to save, in the
# comment's own characters; `{over}` is the measured overflow. And the words a
# notice that asks for no rewrite may not use.
_REWRITE = "Reply asking for a report whose escaped text is at least {over} characters smaller"

_NO_SHORTENING = (*_NOT_THE_TEXT, "characters shorter")

_NO_REWRITE = (*_NO_SHORTENING, "escaped text", "characters smaller")

# A report outside the BMP throughout. JSON stores every such character as a
# surrogate-pair escape, so its text takes twelve times its length on the
# comment, and the room a rewrite has to save is not a count of its characters.
_ESCAPED_LENGTH = 1800

_SURROGATE_PAIR_ESCAPE = len(r"\ud83d\ude00")

_ESCAPED_STORED = _ESCAPED_LENGTH * _SURROGATE_PAIR_ESCAPE

_ESCAPED = replace(delivery_support.DELIVERED, report="\U0001f600" * _ESCAPED_LENGTH)

# A report whose text closes an HTML comment four times, and the room that
# leaves its comment: past the ceiling by a few characters in the record's own
# write and in no measurement before it. A comment that far over is rendered
# with those terminators unescaped -- escaping them only adds -- and fits
# exactly when that rendering does, so neither the overflow nor any saving
# counts the five characters an escaped terminator would take.
_CLOSING = replace(
    delivery_support.DELIVERED, report="".join(("The gate reads left --> right, " * 4, "and nothing else.")),
)

_CLOSING_LENGTH = len(_CLOSING.report)

_CLOSING_SLACK = 380

# A run asserting its report is already on this repository's thread.
_ASSERTING = (
    f"done\n\nREPORT: VERIFIED https://github.com/{support.SLUG}"
    f"/pull/{support.PR_NUMBER}#issuecomment-{support.COMMENT_ID}"
    f" sha256:{support.CONTENT_DIGEST}"
)

# The writes a report can be refused room in: each write, the room its comment
# is left with and whether that room is measured against the settling write, the
# run -- what it is, the record it makes, and the message it ends on -- and what
# is said. The record
# and the transaction carry a written-out report's text, so a rewrite saving
# the overflow in ESCAPED characters gives that write its room back; the
# settlement carries where the report landed, and a verification is recorded
# with no text at all, so neither is asked for a rewrite -- the room has to be
# freed on the comment.
_ROOM_REFUSALS = (
    (
        _room.MeasuredWrite.RECORD,
        (delivery_support.CROWDED_FOR_PARK, False),
        ("a written-out report", delivery_support.DELIVERED, delivery_support.ready(delivery_support.DELIVERED.report)),
        _refusals.Said(
            notice=("the record of it would leave the pinned comment", _REWRITE),
            logged="(publish): the record write leaves the pinned comment",
            unsaid=_NO_SHORTENING,
        ),
    ),
    (
        _room.MeasuredWrite.RECORD,
        (delivery_support.CROWDED_FOR_PARK, False),
        ("an escaped report", _ESCAPED, delivery_support.ready(_ESCAPED.report)),
        _refusals.Said(
            notice=(
                f"stores the report's {_ESCAPED_LENGTH} characters of text as {_ESCAPED_STORED} once escaped for JSON",
                _REWRITE,
            ),
            logged="(publish): the record write leaves the pinned comment",
            unsaid=_NO_SHORTENING,
        ),
    ),
    (
        _room.MeasuredWrite.BINDING,
        (delivery_support.CROWDED_FOR_RESERVATION, False),
        ("a written-out report", delivery_support.DELIVERED, delivery_support.ready(delivery_support.DELIVERED.report)),
        _refusals.Said(
            notice=(
                (
                    "the publication transaction it becomes once its code reaches a pull request would leave "
                    "the pinned comment"
                ),
                _REWRITE,
            ),
            logged="(publish): the binding write leaves the pinned comment",
            unsaid=_NO_SHORTENING,
        ),
    ),
    (
        _room.MeasuredWrite.BINDING,
        (delivery_support.CROWDED_FOR_RESERVATION, False),
        ("a verification", delivery_support.ASSERTED, _ASSERTING),
        _refusals.Said(
            notice=(
                "A verified report is recorded as where it stands and the digest read there, never as its text",
                "free room on the pinned comment, then reply",
            ),
            logged="(verify): the binding write leaves the pinned comment",
            unsaid=_NO_REWRITE,
        ),
    ),
    (
        _room.MeasuredWrite.SETTLEMENT,
        (delivery_support.CROWDED_FOR_TOMBSTONE, True),
        ("a written-out report", delivery_support.DELIVERED, delivery_support.ready(delivery_support.DELIVERED.report)),
        _refusals.Said(
            notice=(
                "the write that settles that transaction once the report is out would leave the pinned comment",
                ", counting the code-publication receipt the push writes,",
                "That write carries where the report landed rather than its text",
                "free room on the pinned comment, then reply",
            ),
            logged="(publish): the settlement write leaves the pinned comment",
            unsaid=_NO_REWRITE,
        ),
    ),
)


class ParkNoticeTest(unittest.TestCase):
    """What a park this owner takes tells the human who has to answer it.

    The notice is the whole of what a human is told, and the two roads that
    reach these parks are in different places: one has published nothing yet,
    and the other is answering an edit on a pull request that is open. A
    report that cannot be recorded is told WHY as well, in the notice and the
    log line alike, since each refusal asks the reply for something different.
    """

    def test_each_park_names_what_it_withheld(self) -> None:
        # The implementing seam is the first publication of all, so there is
        # no pull request yet; a resume under review has one that stands where
        # it stood, and telling that human none was opened would deny the pull
        # request they are reading. Both parks, since both notices say it.
        for described, message in _PARKS:
            for route, open_pr in _ROADS:
                with self.subTest(park=described, road=str(route)):
                    self._assert_notice(message, route, open_pr)

    def test_a_report_s_own_refusal_names_its_cause(self) -> None:
        # Each is refused for what the report or its record IS, and the notice
        # and the log line both say which, with the correction it needs and
        # nothing about a size nobody measured. The delivery an earlier run
        # left and the report the pull request carries are untouched, and
        # nothing but the notice is posted.
        for described, report, requirements, said in _OWN_REFUSALS:
            with self.subTest(refusal=described):
                state = PinnedState(state_data={
                    _records.DELIVERED_REPORT: delivery_support.delivered_object(),
                    delivery_support.BASELINE: requirements,
                })
                _settlement.record_current_report(state, support.CURRENT)

                said.assert_said(self, *self._refused(state, delivery_support.ready(report)))

    def test_a_refusal_for_room_names_the_write(self) -> None:
        # A report that reads and does not fit is refused for the comment's
        # room, and the notice and the log line name the write measured, the
        # size it came to and how far past GitHub's ceiling that is, and what
        # frees it: a rewrite saving that much ESCAPED text only where the
        # write carries a written-out report's text, and room freed on the
        # comment wherever it does not -- never the report's own ceiling,
        # which it is inside of.
        for write, crowding, run, said in _ROOM_REFUSALS:
            with self.subTest(write=write.value, run=run[0]):
                state = delivery_support.crowded_comment(
                    crowding[0], reviewed=crowding[1], baselined=True,
                )
                self._assert_measured(state, write, run, said)

    def test_the_saving_asked_for_is_exact(self) -> None:
        # The notice counts the report's text in the rendering its write was
        # refused in -- the JSON escape alone, none of the terminator escape a
        # comment past the ceiling never carries -- and asks for exactly the
        # saving that write needs: a rewrite one character short of it leaves
        # the same write refused by one, and one saving all of it fits there.
        crowded = delivery_support.crowded_comment(_CLOSING_SLACK, baselined=True)
        refused = _delivery_state.stage_delivered_report(PinnedState(state_data=dict(crowded.data)), _CLOSING)
        over = refused.size - refused.limit
        retried = [
            _delivery_state.stage_delivered_report(
                PinnedState(state_data=dict(crowded.data)),
                replace(_CLOSING, report=_CLOSING.report[saved:]),
            )
            for saved in (over - 1, over)
        ]

        measured = (_room.MeasuredWrite.RECORD, _room.LaterWrites())
        self.assertEqual(
            [
                (refused.write, refused.later),
                (retried[0].write, retried[0].later),
                retried[0].size - retried[0].limit,
            ],
            [measured, measured, 1],
        )
        self.assertNotEqual(
            (
                getattr(retried[1], "write", None),
                getattr(retried[1], "later", None),
            ),
            measured,
        )
        _refusals.Said(
            notice=(
                f"stores the report's {_CLOSING_LENGTH} characters of text as {_CLOSING_LENGTH} once escaped for JSON",
                f"at least {over} characters smaller",
            ),
            logged="(publish): the record write leaves the pinned comment",
            unsaid=_NO_SHORTENING,
        ).assert_said(self, *self._refused(crowded, delivery_support.ready(_CLOSING.report)))

    def _assert_notice(self, message: str, route, open_pr: bool) -> None:
        """One park, taken on one road, says what that road withheld."""
        stopped, _github, issue = commit_support.records(
            PinnedState(), _agent(last_message=message), route,
        )

        self.assertTrue(stopped)
        notice = next(
            posted.body for posted in issue.comments
            if "developer run finished" in (posted.body or "")
        )
        self.assertEqual(
            (_NEVER_OPENED in notice, _STILL_STANDS in notice),
            (not open_pr, open_pr),
        )

    def _assert_measured(self, state: PinnedState, write: _room.MeasuredWrite, run: tuple, said) -> None:
        """One refusal for room says `said`, with the size the writer measured and the ceiling it passed.

        `run` names the run, the record it makes, and the message it ends on;
        `{over}` in what is said is the overflow the writer measured.
        """
        overflow = _delivery_state.stage_delivered_report(
            PinnedState(state_data=dict(state.data)), run[1],
        )
        self.assertIs(overflow.write, write)
        over = overflow.size - overflow.limit
        owed = replace(said, notice=tuple(
            fragment.format(over=over) for fragment in said.notice
        ))
        refused = self._refused(state, run[2])

        for expected in (owed, _refusals.Said(
            notice=(
                f"{overflow.size} characters long",
                f"{over} past the {overflow.limit} GitHub accepts in one comment",
            ),
            logged=f"leaves the pinned comment {overflow.size} characters long",
            unsaid=(),
        )):
            expected.assert_said(self, *refused)

    def _refused(self, state: PinnedState, message: str) -> tuple[str, str]:
        """The notice and the log line one implementation run ending on `message` earns, refused.

        Held, with the report records the comment carried exactly as found,
        and with the notice the one comment posted: no pull request opened,
        no report published.
        """
        found = {key: state.get(key) for key in _REPORT_RECORDS}

        with self.assertLogs("orchestrator.workflow", "ERROR") as captured:
            recorded = commit_support.records(state, _agent(last_message=message))
            logged = "\n".join(captured.output)

        self.assertTrue(recorded[0])
        github = recorded[1]
        self.assertEqual(
            (
                {key: state.get(key) for key in _REPORT_RECORDS},
                state.get(delivery_support.PARK_REASON),
                len(github.posted_comments),
                github.opened_prs,
            ),
            (found, _delivery.UNDELIVERABLE_REPORT, 1, []),
        )
        return github.posted_comments[0][1], logged


class DeliveredRevisionTest(unittest.TestCase):
    """What the record a finished run leaves SAYS, once the run is gone.

    Every report this issue has already recorded pins a revision it has used,
    and the receipt is spelled from that revision -- so the record has to move
    past all of them, and it has to be on GitHub before the code it is about
    goes anywhere.
    """

    def test_the_revision_moves_forward(self) -> None:
        # A settled report and an outstanding transaction each pin a revision
        # this issue has used: one because a settlement replaces the current
        # report, the other because a transaction's receipt is spelled from
        # its revision and may not be minted twice.
        state = PinnedState(state_data={delivery_support.BASELINE: support.REQUIREMENTS})
        _settlement.record_current_report(state, support.CURRENT)
        _record_state.record_pending_report(state, support.PUBLISHED)
        commit_support.records(state, _agent(last_message=_READY))

        recorded = _delivery_state.read_delivered_report(state)
        self.assertEqual(recorded.report_revision, support.REVISION + 1)
        self.assertEqual(recorded.receipt, f"issue-{delivery_support.ISSUE_NUMBER}-report-3")

    def test_a_redelivery_moves_past_the_delivery(self) -> None:
        # The reply an undeliverable-report park earns writes over the
        # delivery standing on the comment, so that record pins a revision
        # this issue has used exactly as the other two do: minted at its
        # revision, the replacement would carry the receipt the record it
        # replaces already carries -- which is what a retry finds its own
        # comment by.
        state = PinnedState(state_data={delivery_support.BASELINE: support.REQUIREMENTS})
        _delivery_state.record_delivered_report(state, delivery_support.DELIVERED)
        commit_support.records(state, _agent(
            last_message=delivery_support.ready("the report the park asked for"),
        ))

        recorded = _delivery_state.read_delivered_report(state)
        self.assertEqual(
            (recorded.report_revision, recorded.receipt),
            (2, f"issue-{delivery_support.ISSUE_NUMBER}-report-2"),
        )

    def test_a_handed_revision_outranks_the_baseline(self) -> None:
        # A caller that snapshotted what it handed the run is believed over
        # the baseline on the comment, which may have moved on since the
        # spawn; the route travels with the snapshot unchanged.
        state = PinnedState()
        state.set(delivery_support.BASELINE, support.REQUIREMENTS)
        handed = "b" * len(support.REQUIREMENTS)

        commit_support.records(
            state, _agent(last_message=delivery_support.ready("the resume's report")),
            _records.HandedRun(WorkflowLabel.VALIDATING, handed),
        )

        recorded = state.get(_records.DELIVERED_REPORT)
        self.assertEqual(
            (recorded["requirements"], recorded["route"]),
            (handed, WorkflowLabel.VALIDATING),
        )

    def test_the_delivery_is_durable(self) -> None:
        # The write is the owner's own, because what makes the report
        # recoverable is that it is on GitHub before the size gate reads the
        # candidate and before the push sends it.
        github, issue = delivery_support.seeded_issue()
        github.seed_state(issue)
        state = github.read_pinned_state(issue)
        state.set(delivery_support.BASELINE, support.REQUIREMENTS)

        _delivery.recording_stops_the_tick(
            github, issue, state, _agent(last_message=_READY), WorkflowLabel.IMPLEMENTING,
        )

        self.assertEqual(
            github.pinned_data(delivery_support.ISSUE_NUMBER)[_records.DELIVERED_REPORT],
            state.get(_records.DELIVERED_REPORT),
        )
        self.assertTrue(_delivery.owes_a_report(state))


class DeliveredReportBindingTest(unittest.TestCase):
    def test_binding_exchanges_the_records(self) -> None:
        state = PinnedState()
        _delivery_state.record_delivered_report(state, delivery_support.DELIVERED)

        self.assertEqual(
            _delivery_state.binds_delivered_report(
                state, delivery_support.DELIVERED, support.SUBJECT,
            ),
            "",
        )

        self.assertFalse(_delivery_state.carries_delivered_report(state))
        self.assertEqual(
            _record_state.read_pending_report(state),
            _records.PendingReport(
                receipt=delivery_support.DELIVERED.receipt,
                subject=support.SUBJECT,
                report_revision=delivery_support.DELIVERED.report_revision,
                mode=delivery_support.DELIVERED.mode,
                route=delivery_support.DELIVERED.route,
                report=delivery_support.DELIVERED.report,
            ),
        )

    def test_a_refused_binding_writes_nothing(self) -> None:
        # A subject the transaction's own writer will not store, and a
        # verification asserting a report on another pull request. Neither may
        # half-apply: a delivery dropped with no transaction beside it is a
        # finished run's report lost. Both answer UNBINDABLE, since no room
        # the comment could get back would make either of them acceptable.
        refused = (
            (
                "a subject naming no pull request",
                delivery_support.DELIVERED,
                _records.ReportSubject(
                    repo_slug=support.SLUG,
                    pr_number=0,
                    branch=support.BRANCH,
                    source_sha=support.SOURCE_SHA,
                    requirements_revision=support.REQUIREMENTS,
                ),
            ),
            ("a location on another pull request", delivery_support.ASSERTED, _records.ReportSubject(
                repo_slug=support.SLUG,
                pr_number=support.PR_NUMBER + 1,
                branch=support.BRANCH,
                source_sha=support.SOURCE_SHA,
                requirements_revision=support.REQUIREMENTS,
            )),
        )
        for described, delivered_report, subject in refused:
            with self.subTest(binding=described):
                state = PinnedState()
                _delivery_state.record_delivered_report(state, delivered_report)

                self.assertEqual(
                    _delivery_state.binds_delivered_report(
                        state, delivered_report, subject,
                    ),
                    _delivery_state.UNBINDABLE_RECORD,
                )

                self.assertEqual(
                    _delivery_state.read_delivered_report(state),
                    delivered_report,
                )
                self.assertFalse(_record_state.carries_pending_report(state))

    def test_a_crowded_comment_is_its_own_refusal(self) -> None:
        # A sound record the comment cannot carry the transaction for is told
        # apart from one nothing could ever bind, because the two are cleared
        # by different things: room comes back as the routes behind a report
        # still owed write to the comment, and the record is left standing for
        # the tick that finds it.
        crowded = delivery_support.crowded_comment(
            delivery_support.CROWDED_FOR_BINDING,
            {_records.DELIVERED_REPORT: delivery_support.delivered_object()},
        )

        self.assertEqual(
            _delivery_state.binds_delivered_report(
                crowded, delivery_support.DELIVERED, support.SUBJECT,
            ),
            _delivery_state.CROWDED_COMMENT,
        )

        self.assertEqual(
            _delivery_state.read_delivered_report(crowded), delivery_support.DELIVERED,
        )
        self.assertFalse(_record_state.carries_pending_report(crowded))

    def test_a_foreign_requirements_revision(self) -> None:
        # The requirements revision belongs to the run and was frozen with the
        # report, so a subject restating it differently is refused before
        # anything is staged: bound, the transaction would claim the report
        # answers content the run never saw and prove it against that content
        # on the tick it settles.
        state = PinnedState()
        _delivery_state.record_delivered_report(state, delivery_support.DELIVERED)

        self.assertEqual(
            _delivery_state.binds_delivered_report(
                state, delivery_support.DELIVERED, replace(
                    support.SUBJECT,
                    requirements_revision=support.CONTENT_DIGEST,
                ),
            ),
            _delivery_state.UNBINDABLE_RECORD,
        )

        self.assertEqual(
            _delivery_state.read_delivered_report(state), delivery_support.DELIVERED,
        )
        self.assertFalse(_record_state.carries_pending_report(state))

    def test_a_delivery_the_comment_does_not_carry(self) -> None:
        # What is bound is the report the COMMENT holds. The argument reaches
        # here across a push and a pull request, so it can name a report this
        # issue never recorded, one nothing can read, or one a later report
        # has already replaced -- and the write drops whatever the record
        # holds, so binding on any of them would replace a finished run's
        # report with a value the comment never carried, or with none at all.
        carried = (
            ("nothing delivered at all", PinnedState()),
            (
                "a claim nothing can read",
                PinnedState(state_data={_records.DELIVERED_REPORT: []}),
            ),
            (
                "a record the issue has moved past",
                PinnedState(state_data={
                    _records.DELIVERED_REPORT: delivery_support.delivered_object(delivery_support.REDELIVERED),
                }),
            ),
        )
        for described, state in carried:
            with self.subTest(delivery=described):
                before = dict(state.data)

                self.assertEqual(
                    _delivery_state.binds_delivered_report(
                        state, delivery_support.DELIVERED, support.SUBJECT,
                    ),
                    _delivery_state.UNBINDABLE_RECORD,
                )

                self.assertEqual(state.data, before)
                self.assertFalse(_record_state.carries_pending_report(state))

if __name__ == "__main__":
    unittest.main()
