# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The close a split transaction has to catch before it has made a child.

A child is the one thing this orchestrator creates that nothing takes back,
and the transaction is not one moment: a push and a fetch stand between the
verdict and the first child, and a create, a record, and a seed stand between
every child and the next. A human can close the issue in any of those gaps,
and a close observed by the poll while this worker holds the issue reaches no
cleanup pass on the tick it happened -- the scheduler admits no second worker
for an issue one is already running. What the run does with what it can see
for itself is this module's subject, one gap at a time.

The gaps PAST the last child -- the announcement, the supersession, and the
retirement -- are the same rule applied to steps with a different consequence,
and they have their own module beside this one.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.late_split.models import LatePhase
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from tests.workflow.stages.decomposition import late_transaction_support as _support
from tests.workflow.stages.decomposition.late_close_race_support import (
    closes_when_children_exist,
)
from tests.workflow.stages.decomposition.late_settlement_support import (
    EVENT_LATE_CANCELLATION,
    PARK_OWNER_UNREADABLE,
)
from tests.workflow.stages.decomposition.late_test_support import (
    KEYS,
    PLAN_PR_NUMBER,
)
from tests.workflow.stages.decomposition.late_transaction_support import HeldPlanPrSplitCase, LateSplitCase

_RESOURCE_SNAPSHOT = "snapshot_ref"
_PR_OPEN = "open"
_STATE_RETAINED = "retained"

# What the fake reports when the request behind the read fails outright, which
# is the answer the transaction may not read as "still open".
_OUTAGE = ConnectionError("github unreachable")

_WORKFLOW_LOG = "orchestrator.workflow"

# What the parent still carries while its transaction is unfinished.
_DECOMPOSING = "workflow:decomposing"

# What a child carries until something releases it.
_BLOCKED = "workflow:blocked"


class ClosedBeforeChildrenTest(LateSplitCase, unittest.TestCase):
    """A close between the snapshot and the first child creates nothing."""

    def setUp(self) -> None:
        super().setUp()
        # Closed after the guarded read that cleared this verdict, which is
        # the only place this state can come from: the transaction is entered
        # from an OPEN reading and takes no other one before here.
        self.issue.closed = True

    def test_no_child_is_created(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG):
            outcome = self._transact()

        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertEqual(self.github.created_child_issues, [])
        self.assertIsNone(self._pinned().get(_support.KEY_CHILDREN))
        self.assertIsNone(self._pinned().get(_support.KEY_UMBRELLA))

    def test_the_mark_records_its_boundary(self) -> None:
        # `snapshotting` is where the interruption happened, and keeping it is
        # what later lets the ref go: nothing was cut from it.
        with self.assertLogs(_WORKFLOW_LOG):
            self._transact()

        pinned = self._pinned()
        self.assertTrue(pinned[KEYS.cancelled])
        self.assertTrue(pinned[KEYS.cancelled_at])
        self.assertEqual(
            pinned[KEYS.cancelled_phase], LatePhase.SNAPSHOTTING.value,
        )

    def test_the_ref_it_pushed_stays_owed(self) -> None:
        # The push landed before the read, so the remote holds an object the
        # cleanup path has to be told about rather than left to find.
        with self.assertLogs(_WORKFLOW_LOG):
            self._transact()

        self.assertEqual(
            self._resources()[(_RESOURCE_SNAPSHOT, _support.SNAPSHOT_REF)],
            _STATE_RETAINED,
        )

    def test_one_cancellation_is_reported(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG):
            self._transact()

        self.assertEqual(len(self._events_named(EVENT_LATE_CANCELLATION)), 1)


class ClosedHoldingPlanPrTest(HeldPlanPrSplitCase, unittest.TestCase):
    """Nothing external is reclaimed here; the ending owns all of it."""

    def test_the_held_plan_pr_is_left_alone(self) -> None:
        self.issue.closed = True

        with self.assertLogs(_WORKFLOW_LOG):
            self._transact()

        self.assertEqual(self.github.pulls[PLAN_PR_NUMBER].state, _PR_OPEN)
        self.assertEqual(self.github.posted_pr_comments, [])
        self.assertEqual(self.github.deleted_remote_branches, [])


class UnreadableBeforeChildrenTest(LateSplitCase, unittest.TestCase):
    """A reading that established nothing is not "still open"."""

    def test_an_outage_creates_no_child_and_parks(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG), self._outage():
            outcome = self._transact()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(self.github.created_child_issues, [])
        self.assertEqual(
            self._pinned().get(KEYS.park_reason), PARK_OWNER_UNREADABLE,
        )

    def test_the_read_stays_owed_on_the_record(self) -> None:
        # Which is what brings a tick back to it: the claim is the retry
        # obligation, and it is taken under the boundary the transaction
        # reached rather than over it, so the ledger still reads as cut.
        with self.assertLogs(_WORKFLOW_LOG), self._outage():
            self._transact()

        pinned = self._pinned()
        self.assertTrue(pinned[KEYS.owner_check_pending])
        self.assertEqual(pinned[KEYS.phase], LatePhase.SNAPSHOTTING.value)

    def test_the_next_tick_finishes_the_split(self) -> None:
        # No agent is re-run and no second ref is pushed: the park costs the
        # tick it happened on and nothing else.
        with self.assertLogs(_WORKFLOW_LOG), self._outage():
            self._transact()

        outcome = self._resume()

        self.assertEqual(outcome.disposition, _LateDisposition.SETTLED)
        self.assertEqual(len(self.github.created_child_issues), 2)
        self.assertIsNone(self._pinned().get(KEYS.park_reason))

    def _outage(self):
        """Answer this tick's owner re-read the way a dead API does."""
        return patch.object(
            self.github, "get_issue", side_effect=_OUTAGE,
        )


class ClosedMidLoopTest(LateSplitCase, unittest.TestCase):
    """A close between two children stops at the one that already exists."""

    def setUp(self) -> None:
        super().setUp()
        self.closing = closes_when_children_exist(self, children=1)

    def test_the_remaining_children_are_not_created(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG), self.closing:
            outcome = self._transact()

        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertEqual(len(self.github.created_child_issues), 1)

    def test_the_one_that_exists_is_recorded(self) -> None:
        # A real issue on GitHub the parent does not know about is the state
        # nothing can clean up, so the record is what the loop keeps whole.
        with self.assertLogs(_WORKFLOW_LOG), self.closing:
            self._transact()

        pinned = self._pinned()
        self.assertEqual(
            pinned[_support.KEY_SPLIT_CHILDREN],
            [self.github.created_child_issues[0].number],
        )
        self.assertEqual(pinned[_support.KEY_EXPECTED_CHILDREN], len(_support.CHILDREN))

    def test_the_boundary_says_the_loop_was_running(self) -> None:
        # Which is what keeps the ref: one child of two is a partial split,
        # and the register the reclamation compares is short.
        with self.assertLogs(_WORKFLOW_LOG), self.closing:
            self._transact()

        pinned = self._pinned()
        self.assertTrue(pinned[KEYS.cancelled])
        self.assertEqual(
            pinned[KEYS.cancelled_phase], LatePhase.SPLITTING.value,
        )
        self.assertEqual(
            self._resources()[(_RESOURCE_SNAPSHOT, _support.SNAPSHOT_REF)],
            _STATE_RETAINED,
        )

    def test_nothing_is_published_over_it(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG), self.closing:
            self._transact()

        self.assertIsNone(self._pinned().get(_support.KEY_LINKS_ANNOUNCED))
        self.assertEqual(_support.label_of(self.github, self.issue.number), _DECOMPOSING)


class ClosedBeforeActivationTest(LateSplitCase, unittest.TestCase):
    """Every child exists, and none of them is started.

    The last gap, and the widest one in consequence: past it the plan pull
    request is closed over a supersession notice, the parent becomes an
    umbrella, and the children this walk releases are handed to agents. A
    cycle a close ended takes none of that -- the pull request it holds is
    the cancellation's to close, over a notice that says so.
    """

    def setUp(self) -> None:
        super().setUp()
        self.closing = closes_when_children_exist(self, len(_support.CHILDREN))

    def test_every_child_was_created_and_recorded(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG), self.closing:
            outcome = self._transact()

        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertEqual(len(self.github.created_child_issues), len(_support.CHILDREN))
        self.assertEqual(
            len(self._pinned()[_support.KEY_SPLIT_CHILDREN]), len(_support.CHILDREN),
        )

    def test_none_of_them_is_started(self) -> None:
        # A settled split releases the one child with no dependency of its
        # own; this one releases neither, so both stay where the create left
        # them and no agent is ever spawned against a closed parent's slice.
        with self.assertLogs(_WORKFLOW_LOG), self.closing:
            self._transact()

        self.assertEqual(
            [
                _support.label_of(self.github, child.number)
                for child in self.github.created_child_issues
            ],
            [_BLOCKED for _ in _support.CHILDREN],
        )

    def test_the_parent_is_not_made_an_umbrella(self) -> None:
        # The label, not the flag: the flag goes down before the first child
        # so a partial split can be read back, and the LABEL is the last
        # thing a finished transaction writes.
        with self.assertLogs(_WORKFLOW_LOG), self.closing:
            self._transact()

        self.assertEqual(_support.label_of(self.github, self.issue.number), _DECOMPOSING)
        self.assertIsNone(self._pinned().get(_support.KEY_LINKS_ANNOUNCED))

    def test_the_record_proves_the_loop_finished(self) -> None:
        # Which is what lets the ending release the ref once the children
        # end: the count and the register agree, at whatever boundary the
        # cancellation interrupted.
        with self.assertLogs(_WORKFLOW_LOG), self.closing:
            self._transact()

        pinned = self._pinned()
        self.assertTrue(pinned[KEYS.cancelled])
        self.assertEqual(
            pinned[_support.KEY_EXPECTED_CHILDREN], len(pinned[_support.KEY_SPLIT_CHILDREN]),
        )


if __name__ == "__main__":
    unittest.main()
