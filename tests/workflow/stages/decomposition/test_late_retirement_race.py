# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The close a poll takes while a worker is retiring the cycle it names.

A settled `single` ends by dropping its generation, and that write takes the
one thing every reader of a close consults: the cycle identity. A poll running
beside it asks the record whether there is a cycle a close would end, and a
poll that asks a moment too late is told there is not -- so it would drop the
reading, and the barrier the worker asks immediately behind its own write
would find nothing latched.

Both threads are real here. The worker publishes and retires through its own
owner; the poll runs the dispatcher's whole deferral -- observe, ask the
record, keep or drop, write the receipt -- from inside the retirement write.
What the cases pin is that the reading survives that ordering and that what it
leaves on the thread names the cycle it was taken against, which is the only
half of it a restart still has.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import dispatch as _dispatch
from orchestrator.workflow.late_split import endings as _endings, state as _late_state
from orchestrator.workflow.stages.decomposition import (
    late_cancellation as _late_cancellation,
    umbrella as _umbrella,
)
from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.observation_support import ObservedCloseCase, receipt_for
from tests.workflow.stages.decomposition.late_run_support import LateCase
from tests.workflow.stages.decomposition.late_settlement_support import (
    settle_single,
)
from tests.workflow.stages.decomposition.late_test_support import (
    CYCLE_ID,
    KEYS,
    LATE_ISSUE_NUMBER,
    late_generation,
)

_WORKFLOW_LOG = "orchestrator.workflow"

_REPO_SLUG = _TEST_SPEC.slug

# The pinned field a live cycle is named by, and the one the retirement drops.
_KEY_CYCLE_ID = "late_cycle_id"

_PINNED_WRITE = "write_pinned_state"

# The field the retirement leaves behind, outside the group it clears.
_KEY_RETIRED = "late_retired_cycle_id"

# What a process that does not reach its own barrier looks like from here.
_DIED = RuntimeError("the process holding this issue is gone")

# The cycle an operator authorizes after the one a close ended.
_NEXT_CYCLE = CYCLE_ID + 1

_EVENT_CANCELLATION = "late_cancellation"


class _PollsAfterTheRetirement:
    """Answer the write that drops the cycle, then let the poll run.

    The ordering no in-memory check answers on its own: the retirement lands
    first, and only then does the poll observe the close, ask the record what
    the reading is worth, and decide whether to keep it. What it reads is a
    record with no cycle on it at all.

    The whole deferral is run rather than imitated, because what is under
    test is exactly what that path decides -- one read, one receipt, and the
    settle it takes when the record positively says there is nothing to end.

    `dying` ends the run where the write did, which is the other half of the
    same window: the barrier that would answer the latch is this process's,
    and a process that does not reach it leaves only what is on the remote.
    """

    def __init__(
        self, github, issue_number: int, *, dying: bool = False,
    ) -> None:
        self._github = github
        self._number = issue_number
        self._answering = github.write_pinned_state
        self._polled = False
        self._dying = dying

    def __call__(self, *asked, **answering):
        """Answer this write, and poll behind the one that retires."""
        written = self._answering(*asked, **answering)
        if self._polled or asked[1].data.get(_KEY_CYCLE_ID) is not None:
            return written
        self._polled = True
        _dispatch._kept_closed_reading(
            self._github, _TEST_SPEC, self._number,
        )
        if self._dying:
            raise _DIED
        return written

    def answering(self):
        """Put this in front of every pinned write the run makes."""
        return patch.object(
            self._github, _PINNED_WRITE, side_effect=self,
        )


class _SettledSingleCase(ObservedCloseCase, LateCase):
    """One owner whose candidate is settled through to the retirement."""

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()

    def _settled(self):
        """Take the settlement road, which ends by retiring the cycle."""
        return settle_single(self.github, self.issue)


class PollRacingTheRetirementTest(_SettledSingleCase, unittest.TestCase):
    """A poll that reads the record on the far side of the retirement."""

    def test_the_reading_is_not_dropped(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG), self._racing():
            self._settled()

        self.assertEqual(
            self._observed(_REPO_SLUG), frozenset((LATE_ISSUE_NUMBER,)),
        )

    def test_the_cycle_is_put_back_and_ended(self) -> None:
        # What the kept reading buys: the barrier behind the write finds the
        # latch, puts the generation it was carrying back, and ends it -- so
        # the ending has a cycle to be entered from at all.
        with self.assertLogs(_WORKFLOW_LOG), self._racing():
            outcome = self._settled()

        pinned = self._pinned()
        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertEqual(pinned[_KEY_CYCLE_ID], CYCLE_ID)
        self.assertTrue(pinned[KEYS.cancelled])

    def test_the_thread_names_the_retired_cycle(self) -> None:
        # The durable half, and the only half a restart still has. A receipt
        # is scoped to a cycle and the record it was written from had none,
        # so the cycle the worker is retiring is where the scope comes from.
        with self.assertLogs(_WORKFLOW_LOG), self._racing():
            self._settled()

        self.assertEqual(len(self._receipts()), 1)

    def test_a_retirement_nobody_raced_still_ends_it(self) -> None:
        # The baseline the window is measured against: with no poll beside
        # it, a published `single` retires its cycle and keeps nothing.
        self._settled()

        self.assertIsNone(self._pinned().get(_KEY_CYCLE_ID))
        self.assertEqual(self._observed(_REPO_SLUG), frozenset())

    def _racing(self):
        """Run the dispatcher's deferral behind the retirement write."""
        return _PollsAfterTheRetirement(
            self.github, LATE_ISSUE_NUMBER,
        ).answering()

    def _receipts(self) -> list:
        """Every close receipt on this owner's thread for its own cycle."""
        marker = receipt_for(LATE_ISSUE_NUMBER, CYCLE_ID)
        return [
            body for number, body in self.github.posted_comments
            if number == LATE_ISSUE_NUMBER and marker in body
        ]


class _RetiredRecordCase(_SettledSingleCase):
    """One owner whose cycle a retirement dropped, and what reads it back."""

    def _died(self) -> None:
        """Retire the cycle, poll behind the write, and end the process."""
        with self.assertLogs(_WORKFLOW_LOG), _PollsAfterTheRetirement(
            self.github, LATE_ISSUE_NUMBER, dying=True,
        ).answering(), self.assertRaises(RuntimeError):
            self._settled()

    def _guarded(self) -> bool:
        """Ask the dispatcher's own cancelled-cycle guard about this owner."""
        return _late_cancellation._refuses_cancelled(
            self.github, _TEST_SPEC, self.issue,
            self.github.workflow_label(self.issue), self._state(),
        )

    def _state(self):
        """The owner's pinned record as this process reads it now."""
        return self.github.read_pinned_state(
            self.github.get_issue(LATE_ISSUE_NUMBER),
        )


class RestartAfterTheRetirementTest(_RetiredRecordCase, unittest.TestCase):
    """The process dies where the write left it, and never reaches its barrier.

    A latch is memory and so is the generation the reinstatement would put
    back, so what the next process wakes up to is the remote alone: a record
    with no cycle identity on it, and a receipt on the thread naming one. The
    write that dropped the cycle is what has to have said which cycle that
    was, or nothing can be adopted against the receipt at all.
    """

    def test_the_record_says_which_cycle_it_dropped(self) -> None:
        self._died()

        pinned = self._pinned()
        self.assertIsNone(pinned.get(_KEY_CYCLE_ID))
        self.assertEqual(pinned[_KEY_RETIRED], CYCLE_ID)

    def test_the_next_process_adopts_that_receipt(self) -> None:
        # The regression: nothing in memory survives, the issue reads OPEN
        # again, and its record says the cycle is gone. The thread is the
        # only thing left that knows a human ended it.
        self._died()
        self._fresh_process()

        with self.assertLogs(_WORKFLOW_LOG):
            refused = self._guarded()

        self.assertTrue(refused)
        self.assertTrue(self._pinned()[KEYS.cancelled])
        self.assertEqual(self._pinned()[_KEY_CYCLE_ID], CYCLE_ID)

    def test_the_adoption_consumes_the_correlation(self) -> None:
        # It names ONE window, and the adoption is the end of it: the cycle
        # is back on the record, so nothing may correlate that receipt to
        # this owner a second time.
        self._died()
        self._fresh_process()

        with self.assertLogs(_WORKFLOW_LOG):
            self._guarded()

        self.assertIsNone(self._pinned().get(_KEY_RETIRED))

    def test_the_adoption_is_reported_once(self) -> None:
        # A cancellation is reported on two sinks, and a reconstruction that
        # could not name the root of its own lineage is one the domain
        # refuses outright -- so the ending would run and say nothing.
        self._died()
        self._fresh_process()

        with self.assertLogs(_WORKFLOW_LOG):
            self._guarded()

        self.assertEqual(len(self._cancellations()), 1)

    def test_a_later_retry_reports_nothing_more(self) -> None:
        # And once is once: the mark is what bounds the record of it, so a
        # visit that reads the cancellation back adds none.
        self._died()
        self._fresh_process()
        with self.assertLogs(_WORKFLOW_LOG):
            self._guarded()

        with self.assertLogs(_WORKFLOW_LOG):
            self._guarded()

        self.assertEqual(len(self._cancellations()), 1)

    def test_a_thread_with_no_receipt_is_left_alone(self) -> None:
        # The baseline that keeps the adoption narrow: a retirement nobody
        # observed is a publication that completed, and the issue goes back
        # to the ordinary work its label names.
        self._settled()
        self._fresh_process()

        self.assertFalse(self._guarded())

    def _cancellations(self) -> list:
        """Every record of the cancellation both sinks were handed."""
        return [
            record for record in self.github.recorded_events
            if record.get("event") == _EVENT_CANCELLATION
        ]


class SupersededCorrelationTest(_RetiredRecordCase, unittest.TestCase):
    """A receipt is append-only; the correlation that reads it is not.

    A close receipt names a cycle and stays on the thread for good, so what
    decides whether a later process may adopt one is the record's own
    correlation to a retirement. It has to end where its window does: a
    generation with an identity supersedes it, and a terminal that drops a
    cycle because it FINISHED records none at all. Without both, an owner two
    generations later reads an old receipt and moves from `done` to
    `rejected`.
    """

    def test_a_fresh_cycle_supersedes_it(self) -> None:
        self._died()

        self._restarted()

        self.assertIsNone(self._pinned().get(_KEY_RETIRED))

    def test_a_completed_owner_is_not_resurrected(self) -> None:
        # The whole crossing: cycle 3 retired with a close observed inside
        # the write, an operator authorized cycle 4, that one ran to its
        # umbrella terminal -- and the process restarts against a thread
        # still carrying cycle 3's receipt.
        self._died()
        self._restarted()
        self._completed()
        self._fresh_process()

        self.assertFalse(self._guarded())
        self.assertIsNone(self._pinned().get(KEYS.cancelled))

    def test_a_completed_terminal_records_its_own(self) -> None:
        # The correlation belongs to the window this write opens, not to the
        # record's history: a terminal retiring cycle N names N and nothing
        # else, so a receipt for any earlier cycle on the same thread matches
        # nothing an adoption would read.
        state = self._state()
        _endings.record_retired_cycle(state, _NEXT_CYCLE)

        _umbrella._retired_cycle(state)

        self.assertEqual(_endings.read_retired_cycle(state), CYCLE_ID)

    def _restarted(self) -> None:
        """The fresh cycle an operator authorizes, written as one is."""
        state = self._state()
        _late_state.write_late_generation(
            state, late_generation(cycle_id=_NEXT_CYCLE),
        )
        self.github.seed_state(LATE_ISSUE_NUMBER, **state.data)

    def _completed(self) -> None:
        """What that cycle's own umbrella terminal leaves on the record."""
        state = self._state()
        _umbrella._retired_cycle(state)
        self.github.seed_state(LATE_ISSUE_NUMBER, **state.data)


if __name__ == "__main__":
    unittest.main()
