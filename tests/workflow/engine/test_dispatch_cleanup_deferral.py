# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a poll does with a close no pass has settled.

A closed owner on an adjudication label is submitted for its cleanup, and two
things can leave that submission unsettled. The scheduler admits no second
worker for an issue one is already running, and a pass that WAS admitted can
fail before it has marked anything -- the worker refetches the issue over
GitHub first, and that read can be the thing that breaks.

Every other refusal costs a turn: the work is still there next tick. These
cost an OBSERVATION -- the poll found the issue closed, and a human who
reopens it before the next pass takes that reading away for good.

So the observation is held rather than logged and dropped, in both cases. It
outlives the reading it came from, and the tick after routes the issue to the
sweep on the strength of it -- whatever the issue reads as by then, and
whichever bucket its label would otherwise have put it in. What the sweep
does with an owner that is open again is mark the cancellation the close
already earned and stop there.
"""
from __future__ import annotations

import unittest
from unittest.mock import Mock

from tests.workflow.engine import cleanup_deferral_support as _support
from tests.workflow.engine.cleanup_deferral_support import DeferralCase
from tests.workflow.engine.unfinished_cleanup_support import (
    UnfinishedCleanupCase,
    cleanup_settled,
    refusing,
)
from tests.workflow.fixtures import (
    LABEL_DECOMPOSING,
    LABEL_DONE,
    LABEL_READY,
    LABEL_REJECTED,
    LABEL_UMBRELLA,
)

_OWED = frozenset((_support.OWNER_NUMBER,))


class HeldCleanupObservationTest(DeferralCase, unittest.TestCase):
    """An observation nothing could be submitted for is kept, not dropped."""

    def test_a_free_issue_is_swept_the_same_tick(self) -> None:
        # The baseline the deferral is measured against: with no worker on
        # the issue, this tick sweeps it and holds nothing.
        scheduler = self._scheduler()

        self._ticked(scheduler)

        self.assertTrue(self._cancelled())
        self.assertEqual(self._observed(_support.REPO_SLUG), frozenset())

    def test_a_held_issue_is_owed_the_next_tick(self) -> None:
        scheduler = self._scheduler()

        self._tick_a_worker_held(scheduler)

        self.assertEqual(self._observed(_support.REPO_SLUG), _OWED)

    def test_the_deferral_is_said(self) -> None:
        # An operator watching a closed umbrella sit still for a tick can
        # tell "a worker holds it" from "nothing looked at it".
        scheduler = self._scheduler()

        said = self._tick_a_worker_held(scheduler)

        self.assertTrue(any(_support.DEFERRED in message for message in said), said)
        self.assertTrue(
            any(_support.HELD_BY_A_WORKER in message for message in said), said,
        )

    def test_the_dispatch_thread_writes_nothing(self) -> None:
        # Why the observation is held in memory rather than written down: a
        # pinned comment is written whole, so a second writer here would drop
        # whatever the active worker recorded in between.
        scheduler = self._scheduler()
        before = dict(self.github.pinned_data(_support.OWNER_NUMBER))

        self._tick_a_worker_held(scheduler)

        self.assertEqual(self.github.pinned_data(_support.OWNER_NUMBER), before)

    def test_an_observation_nobody_took_stays_owed(self) -> None:
        # The worker outlives more than one tick, which changes nothing:
        # the hold is dropped by the pass that RAN, never by one that was
        # merely admitted or refused.
        scheduler = self._scheduler()

        self._tick_a_worker_held(scheduler)
        self._reopened()
        self._tick_a_worker_held(scheduler)

        self.assertEqual(self._observed(_support.REPO_SLUG), _OWED)
        self.assertFalse(self._cancelled())


class DurableCloseReceiptTest(DeferralCase, unittest.TestCase):
    """The half of an observation that survives the process holding it.

    A latch is memory, so a restart loses it -- and the tick that comes up
    afterwards finds an issue a human reopened, a record saying the cycle is
    live, and no reason of its own to doubt either. So the poll writes the
    reading down, as a marked COMMENT: the pinned comment is written whole,
    and a second writer racing the worker that owns the issue would drop
    whatever that worker recorded in between.
    """

    def setUp(self) -> None:
        super().setUp()
        self.scheduler = self._scheduler()

    def test_the_thread_is_told_once(self) -> None:
        self._tick_a_worker_held(self.scheduler)

        self.assertEqual(len(_support.receipts_on(self.github)), 1)

    def test_a_second_poll_repeats_nothing(self) -> None:
        # A worker can hold an issue across many polls, and every one of them
        # owes the same cleanup. One receipt is what the thread is owed.
        self._tick_a_worker_held(self.scheduler)
        self._reopened()
        self._tick_a_worker_held(self.scheduler)

        self.assertEqual(len(_support.receipts_on(self.github)), 1)

    def test_a_fresh_process_ends_the_cycle_from_it(self) -> None:
        # The restart, written out: the observation is latched, the human
        # reopens, and the process that was holding the latch dies. What the
        # next one has is the thread.
        self._tick_a_worker_held(self.scheduler)
        self._reopened()
        self._fresh_process()

        self._ticked(self._scheduler(), drained=True)

        self.assertTrue(self._cancelled())
        self.stage.assert_not_called()

    def test_a_refused_receipt_still_latches(self) -> None:
        # The latch is what the post is best effort ON TOP of: a comment
        # GitHub refuses costs the durability of a reading that still ends
        # this cycle on the very next barrier the run reaches.
        _support.tick_with_refused_receipt(self, self.scheduler)

        self.assertEqual(self._observed(_support.REPO_SLUG), _OWED)
        self.assertEqual(_support.receipts_on(self.github), [])

    def test_a_refused_receipt_is_tried_again(self) -> None:
        # And it has to be, because the latch is memory: an observation whose
        # receipt never landed is one a restart takes away entirely, so a
        # refusal is a thing later polls RETRY rather than a thing the first
        # pass simply lost.
        _support.tick_with_refused_receipt(self, self.scheduler)
        self._reopened()

        self._tick_a_worker_held(self.scheduler)

        self.assertEqual(len(_support.receipts_on(self.github)), 1)

    def test_the_retried_receipt_survives_the_restart(self) -> None:
        # The whole of why it is retried: without the second attempt this
        # reopened owner comes up under a fresh process with nothing saying
        # its cycle ever ended.
        _support.tick_with_refused_receipt(self, self.scheduler)
        self._reopened()
        self._tick_a_worker_held(self.scheduler)
        self._fresh_process()

        self._ticked(self._scheduler(), drained=True)

        self.assertTrue(self._cancelled())
        self.stage.assert_not_called()


class FailedCleanupPassTest(DeferralCase, unittest.TestCase):
    """A pass that was admitted and then broke owes the same observation.

    An accepted submit is not a cancellation persisted. The worker mints its
    own client and refetches the issue before anything routes it, and that
    refetch is a GitHub read like any other -- a pass that dies there has
    marked nothing, so the reading it was carrying is still the only one
    there is.
    """

    def setUp(self) -> None:
        super().setUp()
        self.scheduler = self._scheduler()

    def test_the_failed_pass_marks_nothing(self) -> None:
        self._tick_the_pass_failed(self.scheduler)

        self.assertFalse(self._cancelled())

    def test_the_observation_is_owed_again(self) -> None:
        self._tick_the_pass_failed(self.scheduler)

        self.assertEqual(self._observed(_support.REPO_SLUG), _OWED)

    def test_the_failure_is_said(self) -> None:
        # The other half of the operator's reading: an observation held
        # because a pass broke is not one held because a worker has the
        # issue, and the line says which.
        said = self._tick_the_pass_failed(self.scheduler)

        self.assertTrue(any(_support.PASS_FAILED in message for message in said), said)

    def test_a_reopen_after_the_failure_still_ends_it(self) -> None:
        # The whole of it: nothing ever reads this issue closed again, and
        # its label names the handler that walks a dependency graph and
        # activates children. Without the hold the reopened owner would reach
        # exactly that handler over a cycle a close already ended.
        self._tick_the_pass_failed(self.scheduler)
        self._reopened()

        with self.assertLogs(_support.WORKFLOW_LOG):
            self._ticked(self.scheduler)

        self.assertTrue(self._cancelled())
        self.stage.assert_not_called()
        self.assertEqual(self._observed(_support.REPO_SLUG), frozenset())


class ReopenedBeforeTheSweepTest(DeferralCase, unittest.TestCase):
    """The race end to end: closed under an agent, reopened before the pass.

    Nothing ever reads this issue closed again -- the poll that saw it that
    way could hand it nowhere, and by the tick that can take it a human has
    reopened it. What the hold carries across those two ticks is the
    observation itself.
    """

    def setUp(self) -> None:
        super().setUp()
        self.scheduler = self._scheduler()
        self._tick_a_worker_held(self.scheduler)
        self._reopened()

    def test_the_cancellation_is_recorded_anyway(self) -> None:
        self._swept()

        self.assertTrue(self._cancelled())

    def test_the_owner_reaches_no_handler(self) -> None:
        # `umbrella` is a family label, so an open issue carrying it would
        # otherwise be walked by the handler that activates children. The
        # hold overrides the bucket as well as the label.
        self._swept()

        self.stage.assert_not_called()

    def test_nothing_external_is_done_to_it(self) -> None:
        # Marked and stopped there: the ending the mark now owes belongs to
        # the dispatcher's own guard, which owns a reopened cancelled owner.
        deleted = Mock()

        self._swept(remote=deleted)

        deleted.assert_not_called()
        self.assertEqual(self.github.label_history, [])

    def test_the_taken_observation_is_settled(self) -> None:
        self._swept()

        self.assertEqual(self._observed(_support.REPO_SLUG), frozenset())

    def _swept(self, remote=None) -> None:
        """The tick that finally takes the cleanup, on a reopened issue."""
        with self.assertLogs(_support.WORKFLOW_LOG):
            self._ticked(self.scheduler, remote=remote)


class UnfinishedEndingUnderASweptLabelTest(
    UnfinishedCleanupCase, unittest.TestCase,
):
    """A pass that RETURNED is not a pass that finished the ending.

    A cleanup can run every step and leave the ending owed: a remote that
    refuses a delete keeps the ref, and the terminal that would take the owner
    out of the sweep is one more request GitHub can decline. What decides
    whether the reading is kept is not that, though -- it is whether anything
    ELSE would come back. An owner still wearing one of the two swept labels
    is one a later tick reaches on the cadence an operator set, and holding a
    reading over it would buy nothing and cost a cleanup pass per tick for as
    long as the ending is owed.
    """

    def setUp(self) -> None:
        super().setUp()
        self.scheduler = self._scheduler()

    def test_a_refused_delete_hands_the_reading_back(self) -> None:
        with self.assertLogs(_support.WORKFLOW_LOG):
            self._ticked(self.scheduler, remote=refusing())

        self.assertEqual(self._resources()[_support.OWNER_REF], _support.FAILED)
        self.assertEqual(self._label(), LABEL_UMBRELLA)
        self.assertEqual(self._observed(_support.REPO_SLUG), frozenset())

    def test_a_terminal_that_will_not_land_does_too(self) -> None:
        # Everything the ledger holds is settled and the one write that says
        # so is refused. The label staying put IS the retry, so the pass that
        # writes what this one could not is the label's, not the reading's.
        with self.assertLogs(_support.WORKFLOW_LOG), self._refusing_the_label():
            self._ticked(self.scheduler)

        self.assertEqual(self._resources()[_support.OWNER_REF], _support.RECONCILED)
        self.assertEqual(self._label(), LABEL_UMBRELLA)
        self.assertEqual(self._observed(_support.REPO_SLUG), frozenset())

    def test_a_finished_ending_leaves_the_sweep(self) -> None:
        self._ticked(self.scheduler)

        self.assertEqual(self._label(), LABEL_REJECTED)
        self.assertEqual(self._observed(_support.REPO_SLUG), frozenset())

    def test_a_read_that_cannot_answer_keeps_it(self) -> None:
        # Fail-closed: the reading is the one thing this path exists to keep,
        # and a request that failed establishes nothing about the ending.
        self._latch_close(_support.REPO_SLUG, _support.OWNER_NUMBER)

        with self.assertLogs(_support.WORKFLOW_LOG), self._unreadable():
            settled = cleanup_settled(self.github, self._spec(), _support.OWNER_NUMBER)

        self.assertFalse(settled)


class InterruptedEndingSurvivesRestartTest(
    UnfinishedCleanupCase, unittest.TestCase,
):
    """The close/agent race, and the process that exits before any pass runs.

    A decomposition outcome writes `ready` or `blocked`, and a run spawned
    before its owner was observed closed lands after that observation -- so
    the tick that latched the close and receipted it on the thread can be
    followed by a relabel and then by nothing at all. The latch dies with the
    process, and the repair a cleanup pass would have written never happens,
    so what has to find this owner is the sweep's own query.
    """

    def setUp(self) -> None:
        super().setUp()
        self._every_tick_sweeps()
        self._tick_a_worker_held(self._scheduler())
        self._relabelled(LABEL_READY)
        self._fresh_process()

    def test_the_receipt_is_all_that_is_left(self) -> None:
        # The state the restart wakes up to: a close nothing marked, a ref
        # still held, and one comment on the thread saying the cycle ended.
        self.assertFalse(self._cancelled())
        self.assertEqual(self._resources()[_support.OWNER_REF], _support.RETAINED)
        self.assertEqual(self._observed(_support.REPO_SLUG), frozenset())
        self.assertEqual(len(_support.receipts_on(self.github)), 1)

    def test_the_enumeration_finds_it_by_label(self) -> None:
        # And what makes it recoverable at all: the label a decomposition
        # outcome leaves an interrupted ending on is one the closed sweep
        # queries, so the owner is yielded with no reading behind it.
        polled = [issue.number for issue in self.github.list_pollable_issues()]

        self.assertEqual(polled, [_support.OWNER_NUMBER])

    def test_the_restarted_tick_ends_the_cycle(self) -> None:
        self._ticked(self._scheduler(), drained=True)

        self.assertTrue(self._cancelled())
        self.assertEqual(self._resources()[_support.OWNER_REF], _support.RECONCILED)
        self.assertEqual(self._label(), LABEL_REJECTED)

    def test_it_reaches_no_stage_handler(self) -> None:
        # `ready` names the handler that hands an issue to a developer, and a
        # closed owner is routed past it: the sweep runs on the close, never
        # the stage the label names.
        self._ticked(self._scheduler(), drained=True)

        self.stage.assert_not_called()


class ClosedOwnerOffEverySweptLabelTest(
    UnfinishedCleanupCase, unittest.TestCase,
):
    """An ending owed under a label no query asks for at all.

    Four labels bring a tick back to a closed issue. A hand relabel puts an
    owner outside all four -- so does an operator moving a closed owner onto
    a terminal over a cycle that still owes something -- and there the held
    reading is the only route left. It is memory, so the pass that has one
    puts a queried label back before the process carrying it can exit.
    """

    def setUp(self) -> None:
        super().setUp()
        self.scheduler = self._scheduler()
        self._tick_a_worker_held(self.scheduler)
        self._relabelled(LABEL_DONE)

    def test_no_enumeration_would_yield_it(self) -> None:
        # The premise the rest of this rests on: closed, and on a label the
        # sweep asks for under neither spelling.
        self.assertEqual(list(self.github.list_pollable_issues()), [])

    def test_the_held_reading_sweeps_it_anyway(self) -> None:
        self._ticked(self.scheduler)

        self.assertEqual(self._resources()[_support.OWNER_REF], _support.RECONCILED)
        self.assertEqual(self._label(), LABEL_REJECTED)
        self.assertEqual(self._observed(_support.REPO_SLUG), frozenset())

    def test_an_owed_ending_gets_a_queried_label_back(self) -> None:
        # The durable half, because a reading is memory: an owner that still
        # owes the remote is put back where a later process would find it,
        # and the reading is handed back once that route exists.
        with self.assertLogs(_support.WORKFLOW_LOG):
            self._ticked(self.scheduler, remote=refusing())

        self.assertEqual(self._label(), LABEL_UMBRELLA)
        self.assertEqual(self._observed(_support.REPO_SLUG), frozenset())

    def test_an_unconverted_split_gets_its_own_label(self) -> None:
        # Which of the four the record decides, the way the half-finished
        # decomposition recovery decides it: an owner carrying no umbrella
        # flag never got as far as making a child, so where it belongs is
        # where every adjudication runs.
        self._forget_umbrella()

        with self.assertLogs(_support.WORKFLOW_LOG):
            self._ticked(self.scheduler, remote=refusing())

        self.assertEqual(self._label(), LABEL_DECOMPOSING)

    def test_a_repair_that_will_not_land_keeps_it(self) -> None:
        # And the case the reading exists for: the owner is owed, no label
        # queries it, and the write that would fix that was refused. Nothing
        # but the observation is left, so the observation stays.
        with self.assertLogs(_support.WORKFLOW_LOG) as logged, self._refusing_the_label():
            self._ticked(self.scheduler, remote=refusing())
            said = list(logged.output)

        self.assertEqual(self._label(), LABEL_DONE)
        self.assertEqual(self._observed(_support.REPO_SLUG), _OWED)
        self.assertTrue(
            any(_support.ENDING_UNFINISHED in line for line in said), said,
        )

    def test_a_restart_finds_it_by_that_label(self) -> None:
        self._every_tick_sweeps()
        with self.assertLogs(_support.WORKFLOW_LOG):
            self._ticked(self.scheduler, remote=refusing())
        self._fresh_process()

        self._ticked(self._scheduler(), drained=True)

        self.assertEqual(self._resources()[_support.OWNER_REF], _support.RECONCILED)
        self.assertEqual(self._label(), LABEL_REJECTED)


if __name__ == "__main__":
    unittest.main()
