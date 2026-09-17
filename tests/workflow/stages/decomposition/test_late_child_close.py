# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The close a split has to catch between the steps that make a child.

A child is the one thing this orchestrator creates that nothing takes back,
and making one is not a moment: the write that forces the parent to be an
umbrella stands ahead of the first, the walk that looks a half-created slice
up stands ahead of the create, and the read of the child's own comment stands
ahead of the one write this transaction makes to it. Every one of those is a
request the poll runs beside.

So the latch is asked at each of them, and what it earns is two different
answers. Before the create: no issue is opened at all. After it: the issue
exists, the parent RECORDS it -- a child nothing names is the one state no
pass can clean up -- and nothing is written to the child itself, because a
cancelled cycle leaves every child it already made entirely untouched.

Every case here runs against an issue GitHub reports OPEN, which is what makes
the latch the only thing that knows.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.stages.decomposition.late_observation_seams import (
    CREATE_CHILD,
    ORPHAN_WALK,
    latches_on_call,
    latches_on_child_read,
    latches_on_write,
)
from tests.workflow.stages.decomposition.late_test_support import KEYS
from tests.workflow.stages.decomposition.late_transaction_support import (
    CHILDREN,
    KEY_EXPECTED_CHILDREN,
    KEY_SPLIT_CHILDREN,
    KEY_UMBRELLA,
    LateSplitCase,
)

_WORKFLOW_LOG = "orchestrator.workflow"

REPO_SLUG = _TEST_SPEC.slug

_EVENT_CANCELLATION = "late_cancellation"


class LatchedCloseStopsTheSplitTest(
    ObservedCloseCase, LateSplitCase, unittest.TestCase,
):
    """A latched close creates no child, on an issue GitHub reports open."""

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()
        self._latch_close(REPO_SLUG, self.issue.number)

    def test_no_child_is_created(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG):
            outcome = self._transact()

        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertEqual(self.github.created_child_issues, [])
        self.assertTrue(self._pinned()[KEYS.cancelled])


class LatchedInsidePreparationTest(
    ObservedCloseCase, LateSplitCase, unittest.TestCase,
):
    """The window the first child's own reading has to cover.

    A split forces its parent to be an umbrella before a single child exists,
    and that write is a request: the count and the flag go to the remote, and
    a poll can observe the close inside it. The first child therefore takes a
    reading of its own rather than borrowing the caller's, which was taken
    before that write.
    """

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()

    def test_the_first_child_is_not_created(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG), self._closing():
            outcome = self._transact()

        pinned = self._pinned()
        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertEqual(self.github.created_child_issues, [])
        self.assertTrue(pinned[KEYS.cancelled])
        # The umbrella write landed, and a partial split is a state the record
        # already describes: the count says how many children were expected
        # and the register says none exist, which is what keeps the ref.
        self.assertEqual(pinned[KEY_EXPECTED_CHILDREN], len(CHILDREN))
        self.assertTrue(pinned[KEY_UMBRELLA])

    def _closing(self):
        """Answer the umbrella write, having latched the close inside it."""
        return latches_on_write(
            self.github, REPO_SLUG, self.issue.number, KEY_EXPECTED_CHILDREN,
        )


class LatchedInsideOrphanLookupTest(
    ObservedCloseCase, LateSplitCase, unittest.TestCase,
):
    """The widest window of all, and the one right against the create.

    A resumed pass looks each unrecorded slice up by walking the repository
    for the marker its body would carry -- minutes of remote work on a large
    repository -- and what stands immediately after that walk is the create
    itself. So the latch is asked once more there, against the one step in
    this loop nothing takes back.
    """

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()
        # An earlier pass got as far as the umbrella write and no further,
        # which is the only state the orphan lookup is asked from.
        self.github.seed_state(
            self.issue.number,
            **{**self._pinned(), KEY_EXPECTED_CHILDREN: len(CHILDREN)},
        )

    def test_no_child_is_created(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG), self._closing():
            outcome = self._transact()

        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertEqual(self.github.created_child_issues, [])
        self.assertTrue(self._pinned()[KEYS.cancelled])

    def _closing(self):
        """Answer the orphan walk, having latched the close inside it."""
        return latches_on_call(
            self.github, REPO_SLUG, self.issue.number, ORPHAN_WALK,
        )


class LatchedInsideCreateTest(
    ObservedCloseCase, LateSplitCase, unittest.TestCase,
):
    """A close latched inside the create leaves the child it made alone.

    The create is a request, so the close can land inside it -- and what it
    leaves is a real GitHub issue. Two things follow, and they are not the
    same thing: the parent RECORDS it, because a child nothing names is the
    one state no pass can clean up; and nothing is written to the child
    itself, because a cancelled cycle owes its children nothing.
    """

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()

    def test_the_child_it_made_is_recorded_untouched(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG), self._closing():
            outcome = self._transact()

        pinned = self._pinned()
        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertEqual(len(self.github.created_child_issues), 1)
        self.assertEqual(
            pinned[KEY_SPLIT_CHILDREN],
            [self.github.created_child_issues[0].number],
        )
        # The seed is the one write to the child's own state, and a cancelled
        # cycle's children are not closed, not relabelled, and not written to
        # -- what happens to them next is a human's decision.
        child = self.github.created_child_issues[0]
        self.assertEqual(self.github.pinned_data(child.number), {})

    def _closing(self):
        """Answer the create, having latched the close inside it."""
        return latches_on_call(
            self.github, REPO_SLUG, self.issue.number, CREATE_CHILD,
        )


class LatchedInsideTheChildReadTest(
    ObservedCloseCase, LateSplitCase, unittest.TestCase,
):
    """The last window before this transaction writes a child's own state.

    Seeding reads the child's pinned comment and then adds to it, and the
    read is a request the poll runs beside. A cancelled cycle leaves every
    child that already exists entirely untouched -- not closed, not
    relabelled, and not written to -- so the latch is asked between the two.
    """

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()

    def test_the_child_it_made_is_the_last_one(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG), self._closing():
            outcome = self._transact()

        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertEqual(
            self._pinned()[KEY_SPLIT_CHILDREN],
            [self.github.created_child_issues[0].number],
        )
        self._assert_nothing_is_written_to_it()
        self._assert_no_further_slice_is_opened()
        # Several barriers reach the same closed reading in one run, and the
        # cycle ended at the first of them: one `late_cancellation` per cycle
        # is what a sink is handed, not one per barrier.
        self.assertEqual(len(self._cancellations()), 1)

    def _assert_nothing_is_written_to_it(self) -> None:
        child = self.github.created_child_issues[0]

        self.assertEqual(self.github.pinned_data(child.number), {})

    def _assert_no_further_slice_is_opened(self) -> None:
        # The seed is the LAST step of one child's turn, so a caller told it
        # succeeded opens the next slice's issue against a cycle that has
        # just ended. The manifest names more than one.
        self.assertEqual(len(self.github.created_child_issues), 1)
        self.assertLess(len(self.github.created_child_issues), len(CHILDREN))

    def _cancellations(self) -> list:
        """Every record of the cancellation both sinks were handed."""
        return [
            record for record in self.github.recorded_events
            if record.get("event") == _EVENT_CANCELLATION
        ]

    def _closing(self):
        """Latch the close inside the read taken of the child's own state."""
        return latches_on_child_read(
            self.github, REPO_SLUG, self.issue.number,
        )


if __name__ == "__main__":
    unittest.main()
