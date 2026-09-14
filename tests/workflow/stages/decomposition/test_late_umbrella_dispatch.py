# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The umbrella a late split made, reached through the tick's own guards.

The transaction releases whichever children start immediately and stops. Every
child after those is released by the umbrella's own walk, on a later tick --
and every one of those ticks goes through the dispatcher first, which asks the
pinned comment whether anything is owed before the label's handler is called at
all.

What the retirement leaves on that comment is the publication group with no
count beside it, which is also the shape of a tick that died between the freeze
and the diff. The two are told apart by the record's own settlement. Without
that reading the group would name the stage the gate was entered from rather
than `workflow:umbrella`, every poll would be held for a human in front of the
walk, and a split's own children would be the one thing it can leave
permanently unreleased.

Driven from the transaction rather than from a seeded umbrella, so what the
dispatcher reads is the record the retirement actually writes.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import issue_processing as _issue_processing
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeLabel
from tests.workflow.fixtures import (
    _TEST_SPEC,
    KEY_AWAITING_HUMAN,
    KEY_PARK_REASON,
)
from tests.workflow.stages.decomposition.late_published_split_support import (
    PublishedSplitCase,
)
from tests.workflow.stages.decomposition.late_transaction_support import (
    label_of,
)

# The terminal a resolved child wears, which is what the dep-graph walk reads
# a dependency as satisfied by.
LABEL_DONE = "done"

# What the reconciliation ahead of every handler parks a reading it could not
# take under. A settled split owes no reading, so nothing writes this on the
# road under test; a case about a flag already standing seeds it.
PARK_MEASUREMENT_FAILED = "late_measurement_failed"


class SettledSplitUmbrellaDispatchTest(PublishedSplitCase, unittest.TestCase):
    """A split's own umbrella, polled the way every tick after it polls it."""

    def setUp(self) -> None:
        super().setUp()
        self._transact(generation=self.generation)
        # Slice 0 depends on nothing and was released by the transaction
        # itself; slice 1 depends on it and is what a later tick releases.
        self.children = self.github.created_child_issues

    def test_a_dependent_child_is_released(self) -> None:
        # The second slice depends on the first, so the transaction left it
        # `blocked` and the walk that releases it runs on a later tick. That
        # tick reads a record carrying the publication group and no count:
        # taken for a reading nobody finished, it would put a notice on the
        # thread and stop in front of the walk rather than release anything.
        self._resolved(self.children[0])
        posted = len(self.github.posted_comments)

        self._tick()

        self.assertEqual(self._held_label(), WorkflowLabel.READY)
        self.assertEqual(len(self.github.posted_comments), posted)
        self.assertIsNone(
            self.github.pinned_data(self.issue.number).get(KEY_PARK_REASON),
        )

    def test_a_park_already_standing_is_retired(self) -> None:
        # The park is durable and nothing about a settled split is a human's
        # to answer, so a flag left standing would read as waiting on one
        # forever -- and hold the branch it names out of the base refresh for
        # just as long. The walk runs either way, and the flag goes with it.
        self._resolved(self.children[0])
        self._parked()

        self._tick()

        self.assertIsNone(
            self.github.pinned_data(self.issue.number).get(KEY_PARK_REASON),
        )
        self.assertEqual(self._held_label(), WorkflowLabel.READY)

    def _held_label(self) -> str:
        """The label the child that waits on the first one is wearing."""
        return label_of(self.github, self.children[1].number)

    def _resolved(self, child) -> None:
        """One child of this split reaching its terminal."""
        child.labels = [FakeLabel(LABEL_DONE)]

    def _parked(self) -> None:
        """A measurement park standing on this umbrella's pinned comment."""
        self.github.seed_state(self.issue.number, **{
            **self.github.pinned_data(self.issue.number),
            KEY_AWAITING_HUMAN: True,
            KEY_PARK_REASON: PARK_MEASUREMENT_FAILED,
        })

    def _tick(self) -> None:
        """One poll of the umbrella, through the guards a dispatch runs."""
        _issue_processing._route_issue_to_handler(
            self.github,
            _TEST_SPEC,
            self.issue,
            self.github.workflow_label(self.issue),
        )


if __name__ == "__main__":
    unittest.main()
