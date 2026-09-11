# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a fan-out submit refused for a CLOSED issue was carrying.

The scheduler admits no second worker for an issue one is already running,
and a refusal costs a turn -- except where the submission carried an
OBSERVATION. The cleanup route says so from the label; the window this module
is about says so from nowhere at all.

A `single` verdict hands its issue to `workflow:implementing` a moment before
it retires the cycle, so a close landing there wears a label whose handler is
an ordinary terminal. Nothing about the route says a late cycle is standing
under it, so the reading is established from the RECORD instead -- a read this
path can afford, since it runs only when a worker is already holding the
issue.
"""
from __future__ import annotations

import importlib
import unittest
from unittest.mock import Mock, patch

from orchestrator.workflow.engine import dispatch, observations
from tests.support.fakes import FakeGitHubClient
from tests.workflow.engine import refused_submit_support as _support
from tests.workflow.engine.refused_submit_support import RefusingOnce, Retiring, Scheduler
from tests.workflow.fixtures import LABEL_IMPLEMENTING
from tests.workflow.observation_support import ObservedCloseCase, receipt_for


class RefusedClosedSubmitTest(ObservedCloseCase, unittest.TestCase):
    """A closed issue the scheduler refused, with and without a live cycle."""

    def setUp(self) -> None:
        self._fresh_process()

    def test_a_live_cycle_is_latched(self) -> None:
        github = _live_owner()

        with self.assertLogs(_support.WORKFLOW_LOG):
            self._submitted(github)

        self.assertEqual(
            self._observed(_support.SPEC.slug), frozenset((_support.OWNER_NUMBER,)),
        )

    def test_the_thread_is_told(self) -> None:
        # The durable half goes with it, because a latch is memory and this
        # window is exactly the one a restart would take the reading from.
        github = _live_owner()

        with self.assertLogs(_support.WORKFLOW_LOG):
            self._submitted(github)

        self.assertEqual(len(github.posted_comments), 1)

    def test_a_record_with_no_cycle_latches_nothing(self) -> None:
        # The baseline that keeps the blanket off: every other closed issue
        # is owed a turn, not an observation, and routing one to the sweep
        # would cost it the terminal arc its own label names.
        github = _support.closed_owner(live=False)

        self._submitted(github)

        self.assertEqual(self._observed(_support.SPEC.slug), frozenset())
        self.assertEqual(github.posted_comments, [])

    def test_a_read_failure_keeps_the_latch(self) -> None:
        # The probe is a request, and a request that fails proves nothing.
        # The reading the poll took is the one thing this path exists to
        # keep, so it is latched FIRST and dropped only on a positive answer.
        github = _live_owner()

        with self.assertLogs(_support.WORKFLOW_LOG), patch.object(
            github, _support.PINNED_READ, side_effect=_support.OUTAGE,
        ):
            self._submitted(github)

        self.assertEqual(
            self._observed(_support.SPEC.slug), frozenset((_support.OWNER_NUMBER,)),
        )

    def test_a_retirement_that_finished_settles_it(self) -> None:
        # The other side of the same ordering, with the worker's own barrier
        # already behind it: the record positively says there is nothing left
        # to end and no worker is holding that question open. That one IS
        # dropped -- the publication completed, and the ordinary terminal its
        # label names owns the closed issue from here.
        github = _live_owner()

        with patch.object(
            github, _support.PINNED_READ,
            side_effect=Retiring(github),
        ):
            self._submitted(github)

        self.assertEqual(self._observed(_support.SPEC.slug), frozenset())

    def _submitted(self, github: FakeGitHubClient) -> None:
        """Offer this tick's fan-out issues to a scheduler that takes none."""
        _support.offered(github, Scheduler(admits=False))


class EnumerationLatchTest(ObservedCloseCase, unittest.TestCase):
    """The latch goes down where the close is READ, not where it is carried.

    Between the two stands the rest of the enumeration -- a label read per
    issue in the repository -- and a worker already holding this issue asks
    the latch before every irreversible step it takes for the whole of that
    window.
    """

    def setUp(self) -> None:
        self._fresh_process()

    def test_it_is_latched_before_any_submit(self) -> None:
        # The window this closes: a worker already holding the issue asks the
        # latch before every irreversible step it takes, and between the read
        # that saw the close and the submit that would carry it stands the
        # rest of the enumeration -- a label read per issue in the repository.
        # Nothing has been submitted at all here.
        github = _live_owner()

        dispatch._partition_pollable_issues(github, _support.SPEC)

        self.assertTrue(
            observations.close_observed(_support.SPEC.slug, _support.OWNER_NUMBER),
        )

    def test_an_open_issue_latches_nothing(self) -> None:
        # The baseline that keeps it narrow: a reading is only taken where
        # this poll actually saw the issue closed.
        github = _live_owner()
        github.get_issue(_support.OWNER_NUMBER).closed = False

        dispatch._partition_pollable_issues(github, _support.SPEC)

        self.assertEqual(self._observed(_support.SPEC.slug), frozenset())

    def test_an_admission_is_decided_over_a_latch(self) -> None:
        # Either answer, and for the same reason: the worker the scheduler is
        # deciding around reads the latch, not the partition.
        github = _live_owner()
        admitting = Scheduler(admits=True)

        _support.offered(github, admitting)

        self.assertEqual(admitting.latched, [True])

    def test_a_refusal_is_decided_over_a_latch(self) -> None:
        # And it is still standing when the scheduler answers, whichever way
        # it answers: the refused branch keeps the reading deliberately.
        github = _live_owner()
        refusing = Scheduler(admits=False)

        with self.assertLogs(_support.WORKFLOW_LOG):
            _support.offered(github, refusing)

        self.assertEqual(refusing.latched, [True])


class _AdmittedCase(ObservedCloseCase):
    """One closed owner whose submit an idle scheduler took."""

    def setUp(self) -> None:
        self._fresh_process()
        self.github = _live_owner()
        self.scheduler = Scheduler(admits=True)
        _support.offered(self.github, self.scheduler)

    def _ran(self) -> Mock:
        """Run the task this tick handed the scheduler, holding its handler."""
        module_name, handler_name = dispatch._STAGE_HANDLER_TARGETS[
            LABEL_IMPLEMENTING
        ]
        dispatched = Mock()
        with patch.object(
            importlib.import_module(module_name), handler_name, dispatched,
        ):
            self.scheduler.task()
        return dispatched


class AdmittedClosedSubmitTest(_AdmittedCase, unittest.TestCase):
    """An admitted submit carries a reading the enumeration already latched.

    The latch goes down where the close is READ, which is the earliest
    anything in this process knows it -- so a worker already holding the
    issue is answered for the whole of the window between that reading and
    this submit. What the task carries with it is the same reading, bound
    rather than re-derived: the worker refetches the issue, so a human who
    reopens it in that window would otherwise have the fresh object say open
    and a live cycle resume.
    """

    def test_a_task_that_never_runs_keeps_the_reading(self) -> None:
        # The submit was accepted and the task was never called -- a
        # shutdown, or a process that died between the two. Nothing settled
        # the reading, so the next tick is still owed it.
        self.assertEqual(
            self._observed(_support.SPEC.slug), frozenset((_support.OWNER_NUMBER,)),
        )

    def test_a_task_that_never_runs_is_told(self) -> None:
        # And the latch is memory, so the reading needs a half that is not.
        # The receipt goes down where the poll established the close, which
        # is the only moment before an accepted task can be lost.
        marker = receipt_for(_support.OWNER_NUMBER, _support.CYCLE_ID)
        self.assertEqual(
            [body for _, body in self.github.posted_comments if marker in body],
            [body for _, body in self.github.posted_comments],
        )
        self.assertEqual(len(self.github.posted_comments), 1)

    def test_a_restart_over_a_reopen_still_ends_it(self) -> None:
        # The regression in full: the task never ran, the process died with
        # the latch in it, and a human reopened the issue before the next one
        # polled. Nothing the fresh process can READ says closed and it
        # carries no reading of its own -- only the thread says so.
        self.github.get_issue(_support.OWNER_NUMBER).closed = False
        self._fresh_process()

        with self.assertLogs(_support.WORKFLOW_LOG):
            dispatched = self._polled_afresh()

        dispatched.assert_not_called()
        self.assertTrue(
            self.github.pinned_data(_support.OWNER_NUMBER)[_support.KEY_CANCELLED],
        )

    def test_a_reopen_before_the_refetch_still_ends(self) -> None:
        # The regression: nothing this task can read says closed by the time
        # it runs, and the reading it was handed is the only thing that does.
        self.github.get_issue(_support.OWNER_NUMBER).closed = False

        with self.assertLogs(_support.WORKFLOW_LOG):
            dispatched = self._ran()

        dispatched.assert_not_called()
        self.assertTrue(
            self.github.pinned_data(_support.OWNER_NUMBER)[_support.KEY_CANCELLED],
        )

    def test_an_owner_with_no_cycle_is_dispatched(self) -> None:
        # The baseline that keeps the binding narrow: a closed issue with
        # nothing to end still reaches the terminal arc its label names.
        self.github = _support.closed_owner(live=False)
        self.scheduler = Scheduler(admits=True)
        _support.offered(self.github, self.scheduler)

        dispatched = self._ran()

        dispatched.assert_called_once()

    def _polled_afresh(self) -> Mock:
        """Dispatch this issue the way a process that lost the latch would."""
        module_name, handler_name = dispatch._STAGE_HANDLER_TARGETS[
            LABEL_IMPLEMENTING
        ]
        dispatched = Mock()
        with patch.object(
            importlib.import_module(module_name), handler_name, dispatched,
        ):
            dispatch._process_issue(
                self.github, _support.SPEC, self.github.get_issue(_support.OWNER_NUMBER),
            )
        return dispatched


class AdmittedPassKeepsTheReadingTest(_AdmittedCase, unittest.TestCase):
    """What the pass this tick admitted does with the reading it carries.

    It is the only thing that will ever act on it, so it settles the reading
    exactly where the record positively says there is nothing left to end --
    and leaves the latch standing every other way it can end.
    """

    def test_a_pass_that_ran_settles_it(self) -> None:
        with self.assertLogs(_support.WORKFLOW_LOG):
            self._ran()

        self.assertEqual(self._observed(_support.SPEC.slug), frozenset())

    def test_a_failed_pass_keeps_the_reading(self) -> None:
        # The task the tick just admitted IS what would have acted on the
        # reading, so a failure anywhere in it -- the refetch, the pinned
        # read, the write that marks the cancellation -- would drop the close
        # with it unless the pass leaves the latch exactly where it was.
        with self.assertLogs(_support.WORKFLOW_LOG), self.assertRaises(
            ConnectionError,
        ), patch.object(self.github, "get_issue", side_effect=_support.OUTAGE):
            self.scheduler.task()

        self.assertEqual(
            self._observed(_support.SPEC.slug), frozenset((_support.OWNER_NUMBER,)),
        )

    def test_a_pass_that_marked_nothing_keeps_it(self) -> None:
        # A pass can fail to SPEND the reading without failing at all: the
        # pinned read the guard is built on answers a refusal of its own, so
        # a tick that could not read the record refuses the issue and marks
        # nothing. The reading is unspent either way.
        with self.assertLogs(_support.WORKFLOW_LOG), patch.object(
            self.github, _support.PINNED_READ, side_effect=RefusingOnce(self.github),
        ):
            self.scheduler.task()

        self.assertEqual(
            self._observed(_support.SPEC.slug), frozenset((_support.OWNER_NUMBER,)),
        )


def _live_owner() -> FakeGitHubClient:
    """The closed `implementing` owner every case here starts from."""
    return _support.closed_owner(live=True)


if __name__ == "__main__":
    unittest.main()
