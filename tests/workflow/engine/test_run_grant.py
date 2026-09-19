# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one add-agent-runs request moves, and what it leaves exactly alone.

The grammar a line has to satisfy before it is a request at all is pinned
beside its own owner (`test_run_grant_request`); what is pinned here is what
happens to an issue once one arrives. A request buys runs only while this park
stands and only on a trusted author's word. Everything else leaves the ledger
where it found it -- the allowance and the runs spent against it both -- and
says so once, or says nothing at all where saying something would be answering
an outsider.

A grant is pinned as an absolute ceiling rather than an increment, because
that is what makes it safe to hand out before the write that records it: read
twice, the same command buys the same runs.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.pinned_state import PINNED_STATE_MARKER
from orchestrator.workflow.engine import (
    comments as _comments,
    run_budget as _run_budget,
    run_grant as _run_grant,
    run_grant_request as _run_grant_request,
)
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.engine import (
    run_budget_test_support as budget,
    run_grant_case as _grant_case,
    run_grant_test_support as grant,
    run_limit_seeds as _limit_seeds,
    run_limit_test_support as support,
)

_ALLOWLIST = "ALLOWED_ISSUE_AUTHORS"

# What a human wrote for the developer on the parked issue before the circuit
# refused the resume that would have delivered it.
_GUIDANCE = "make the table smaller"

# The same kind of reply, quoting the pinned record's marker while asking.
_QUOTES_THE_RECORD = f"it still reads {PINNED_STATE_MARKER} ... -- smaller, please"


class GrantTest(_grant_case._ParkCase):
    """What a valid command buys, and what it leaves alone."""

    def test_a_valid_command_buys_exactly_used_plus_n(self) -> None:
        lifted = self._lift(grant.command(grant.VALID))

        self.assertTrue(lifted)
        recorded = self._recorded()
        self.assertEqual(
            recorded[support.ALLOWANCE_FIELD], grant.GRANTED_ALLOWANCE,
        )
        # Nothing here returns a run: what widens is the ceiling.
        self.assertEqual(recorded[support.USED_FIELD], _limit_seeds.ALLOWANCE)
        self.assertFalse(recorded[_limit_seeds.AWAITING_HUMAN])
        self.assertIsNone(recorded[_limit_seeds.PARK_REASON])
        self.assertEqual(support.phases(self.gh), [support.GRANTED])

    def test_the_command_is_said_and_consumed_once(self) -> None:
        self._lift(grant.command(grant.VALID))

        said = self.gh.posted_comments
        self.assertEqual(len(said), 1)
        self.assertIn(str(grant.GRANTED_ALLOWANCE), said[0][1])
        # The receipt is consumed with the command, so the road the grant
        # opens does not read the orchestrator answering itself as guidance.
        self.assertEqual(
            self._recorded()[support.LAST_ACTION_COMMENT_ID],
            self.gh.latest_comment_id(self.issue),
        )

    def test_a_lost_write_says_it_once(self) -> None:
        # The acknowledgement lands and the write that records it does not, so
        # the next tick reads the same command off the same thread. An
        # allowance written as `used + N` says the same thing then -- an
        # increment would not -- and the receipt already on the thread is what
        # keeps the same sentence from being said a second time.
        self._lost_the_write(grant.command(grant.VALID))

        lifted = self._replayed()

        self.assertTrue(lifted)
        self.assertEqual(len(self.gh.posted_comments), 1)
        self.assertEqual(
            self._recorded()[support.ALLOWANCE_FIELD], grant.GRANTED_ALLOWANCE,
        )

    def test_an_owed_sentence_reads_no_command(self) -> None:
        # The hold above says that sentence and moves the response boundary
        # past everything under the old one, so a command read here would be
        # bought and then consumed by the notice explaining the park.
        lifted = self._lift(
            grant.command(grant.VALID), state=grant.spent_state(owing=True),
        )

        self.assertFalse(lifted)
        self.assertEqual(self.gh.posted_comments, [])
        self._assert_ledger_untouched()


class GrantRecordTest(_grant_case._ParkCase):
    """What the budget stream is told when a human buys past a ceiling.

    The record is tied to the write that widens the allowance, which is what
    an operator is counting: how often a deployment's limit has to be bought
    past, and by how much.
    """

    def test_a_grant_records_the_ceiling_it_bought(self) -> None:
        self._lift(_grant_case._asking())

        recorded = budget.audited(self.gh)[0]
        self.assertEqual(recorded[budget.PHASE], budget.EXTENDED)
        self.assertEqual(recorded[budget.ALLOWANCE], grant.GRANTED_ALLOWANCE)
        # Nothing gives a run back, so what the grant bought is what is left.
        self.assertEqual(recorded[budget.USED], _limit_seeds.ALLOWANCE)
        self.assertEqual(recorded[budget.REMAINING], grant.ADDED)
        self.assertNotIn(budget.AGENT_ROLE, recorded)
        self.assertNotIn(budget.RESERVATION_ID, recorded)

    def test_a_replayed_command_records_one_grant(self) -> None:
        # The tick whose write was lost bought nothing durable, so the
        # extension the next tick makes is the only one there is to report.
        self._lost_the_write(_grant_case._asking())

        self._replayed()

        self.assertEqual(
            budget.phases(budget.audited(self.gh)), [budget.EXTENDED],
        )

    def test_a_record_cannot_break_the_tick_it_rides(self) -> None:
        # The budget record is built on the far side of the grant: the park is
        # already down and the tick is on its way to the stage its label
        # names. A read that fails there must cost the field it was for, never
        # the grant, the tick, or the transition both sinks are owed.
        self._thread(_grant_case._asking())
        self.state = grant.spent_state()
        with (
            patch.object(
                self.gh, "workflow_label", side_effect=_grant_case._FlakyLabel(self.gh),
            ),
            self.assertLogs(_run_budget.log, level="ERROR"),
        ):
            lifted = _run_grant._lifts_the_park(
                self.gh, self.issue, self.state,
            )

        self.assertTrue(lifted)
        self.assertEqual(
            self._recorded()[support.ALLOWANCE_FIELD], grant.GRANTED_ALLOWANCE,
        )
        recorded = budget.audited(self.gh)[0]
        self.assertEqual(recorded[budget.PHASE], budget.EXTENDED)
        self.assertNotIn(budget.STAGE, recorded)

    def test_a_request_buying_nothing_records_nothing(self) -> None:
        # A refusal moved neither count, so there is no transition for the
        # budget stream to carry -- the receipt it earned is the whole answer.
        self._lift(_grant_case._asking("/orchestrator add-agent-runs three"))

        self.assertEqual(budget.audited(self.gh), [])


class RefusalTest(_grant_case._ParkCase):
    """What every other request earns, and how often it earns it."""

    def test_an_unbuyable_request_changes_nothing(self) -> None:
        for asked in grant.UNBUYABLE:
            with self.subTest(asked=asked):
                lifted = self._lift(
                    grant.command(f"/orchestrator add-agent-runs {asked}"),
                )

                self.assertFalse(lifted)
                self._assert_ledger_untouched()
                self.assertTrue(self.state.get(_limit_seeds.AWAITING_HUMAN))
                self.assertEqual(len(self.gh.posted_comments), 1)
                self.assertEqual(support.phases(self.gh), [support.REFUSED])

    def test_the_receipt_names_the_bound(self) -> None:
        self._lift(grant.command("/orchestrator add-agent-runs 999"))

        said = self.gh.posted_comments[0][1]
        self.assertIn(str(_run_grant_request.MAX_RUNS_PER_COMMAND), said)
        self.assertIn(config.HITL_MENTIONS, said)
        self.assertEqual(
            self._recorded()[support.LAST_ACTION_COMMENT_ID],
            self.gh.latest_comment_id(self.issue),
        )

    def test_a_receipt_on_the_thread_is_not_repeated(self) -> None:
        # The post and the write that consumes the request cannot be made one
        # operation, so a tick that died between them re-reads the request --
        # and the marker its own receipt carries is what stops the repeat.
        asked = grant.command("/orchestrator add-agent-runs 0")
        self._lost_the_write(asked)
        receipt = self.gh.posted_comments[0][1]

        replayed = self._replayed()

        self.assertFalse(replayed)
        self.assertEqual(len(self.gh.posted_comments), 1)
        self.assertIn(
            _run_grant._REFUSED_MARKER.format(
                issue=support.ISSUE_NUMBER, comment=asked.id,
            ),
            receipt,
        )
        self._assert_ledger_untouched()

    def test_an_outsiders_marker_silences_nothing(self) -> None:
        # A marker is plain text on a public thread. Read from anybody, one
        # pasted below the request would suppress the answer a human is owed.
        marker = _run_grant._REFUSED_MARKER.format(
            issue=support.ISSUE_NUMBER, comment=grant.FIRST_ASK,
        )
        self._lift(
            grant.command(
                "/orchestrator add-agent-runs x", comment_id=grant.FIRST_ASK,
            ),
            grant.command(
                marker, comment_id=grant.SECOND_ASK, author=support.OUTSIDER,
            ),
        )

        self.assertEqual(len(self.gh.posted_comments), 1)


class UnansweredRequestTest(_grant_case._ParkCase):
    """The threads this owner buys nothing from and says nothing to."""

    def test_an_untrusted_command_buys_nothing(self) -> None:
        # What the command spends is agent time, so it is worth exactly the
        # trust of the account that wrote it -- and answering an outsider
        # would spend the watermark a real operator is read against.
        with patch.object(config, _ALLOWLIST, (grant.OPERATOR,)):
            lifted = self._lift(
                grant.command(grant.VALID, author=support.OUTSIDER),
            )

        self.assertFalse(lifted)
        self.assertEqual(self.gh.posted_comments, [])
        self.assertEqual(self.gh.write_state_calls, 0)
        self._assert_ledger_untouched()

    def test_only_the_spent_ledger_park_is_answered(self) -> None:
        # Read anywhere else, the same words would clear a park waiting for
        # something they do not say, or hand a running issue a ceiling
        # nobody decided.
        for reason in (None, "retry_cap", "agent_question"):
            with self.subTest(park_reason=reason):
                parked = grant.spent_state(**{
                    _limit_seeds.AWAITING_HUMAN: reason is not None,
                    _limit_seeds.PARK_REASON: reason,
                })

                lifted = self._lift(grant.command(grant.VALID), state=parked)

                self.assertFalse(lifted)
                self.assertEqual(self.gh.posted_comments, [])
                self._assert_ledger_untouched()

    def test_a_thread_with_no_command_is_left_alone(self) -> None:
        lifted = self._lift(grant.command("any update here?"))

        self.assertFalse(lifted)
        self.assertEqual(self.gh.posted_comments, [])
        self.assertEqual(self.gh.write_state_calls, 0)

    def test_an_unreadable_thread_holds_the_park(self) -> None:
        # A park held one poll too long is answered by the next read, while a
        # grant handed out on a thread nobody could read buys runs no human
        # asked for.
        self._thread(grant.command(grant.VALID))
        self.state = grant.spent_state()

        with patch.object(
            self.gh, "comments_after", side_effect=RuntimeError("502"),
        ):
            lifted = _run_grant._lifts_the_park(
                self.gh, self.issue, self.state,
            )

        self.assertFalse(lifted)
        self.assertEqual(self.gh.posted_comments, [])
        self._assert_ledger_untouched()


class ConcurrentCommentTest(_grant_case._ParkCase):
    """What a tick may mark answered is what it read, and nothing after it."""

    def test_a_racing_comment_stays_unread(self) -> None:
        # The thread is read once and the receipt is written after that read.
        # A watermark taken from the thread as it stands afterwards would mark
        # a comment nobody here has seen as answered -- and a comment under
        # the mark is not delayed, it is lost: every stage below decides what
        # is unread by exactly that number.
        for asked in (grant.VALID, "/orchestrator add-agent-runs 0"):
            with self.subTest(asked=asked):
                self._lift_racing(grant.command(asked))

                consumed = self._recorded()[support.LAST_ACTION_COMMENT_ID]
                self.assertEqual(consumed, grant.COMMAND_ID)
                self.assertIn(
                    grant.RACING_COMMENT_ID,
                    [
                        unread.id
                        for unread in self.gh.comments_after(
                            self.issue, consumed,
                        )
                    ],
                )

    def test_the_answer_still_lands(self) -> None:
        # The boundary is the only thing the race moves: the command is still
        # answered, and answered once.
        lifted = self._lift_racing(grant.command(grant.VALID))

        self.assertTrue(lifted)
        self.assertEqual(len(self.gh.posted_comments), 1)
        self.assertEqual(
            self._recorded()[support.ALLOWANCE_FIELD], grant.GRANTED_ALLOWANCE,
        )


class InterruptedBatchTest(_grant_case._ParkCase):
    """A reply the park interrupted is no answer to the park.

    The park records the thread read through our own comments and no further,
    so a reply it could not walk past -- the input a refused resume was handed
    -- leaves the mark under the park's own notice. A command written after
    that notice answers the park; it does not answer the reply below it, and a
    watermark is one number, so the command cannot be consumed without it.
    """

    def test_the_grant_leaves_it_unread(self) -> None:
        # Asked again of a reply quoting the pinned record's marker. Read by
        # that marker the reply would vanish from the grant's read, the batch
        # would look like replies to the park alone, and the grant would
        # consume straight over it.
        for said in (_GUIDANCE, _QUOTES_THE_RECORD):
            with self.subTest(said=said):
                lifted = self._lift(
                    grant.command(said, comment_id=grant.FIRST_ASK),
                    self._notice(),
                    _grant_case._asking(),
                    state=grant.spent_state(**{
                        support.LAST_ACTION_COMMENT_ID: support.WATERMARK,
                        support.LEDGER_FIELD: [grant.SECOND_ASK],
                    }),
                )

                self.assertTrue(lifted)
                self.assertEqual(
                    self._recorded()[support.ALLOWANCE_FIELD],
                    grant.GRANTED_ALLOWANCE,
                )
                self.assertEqual(
                    self._recorded()[support.LAST_ACTION_COMMENT_ID],
                    support.WATERMARK,
                )

    def _notice(self) -> FakeComment:
        """The park's own notice, above the reply and in the id ledger."""
        return FakeComment(
            id=grant.SECOND_ASK,
            body=f"{support.notice_text()}\n\n{_comments._ORCH_COMMENT_MARKER}",
            user=FakeUser(support.BOT_LOGIN),
        )


if __name__ == "__main__":
    unittest.main()
