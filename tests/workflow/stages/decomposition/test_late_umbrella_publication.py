# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an umbrella a split made owes the pull request that split closed.

The transaction is not the last thing to release a child of a published split.
It hands the issue to `umbrella` and stops; from then on the umbrella's own
walk releases them, on every dependency poll until the manifest is done. Every
one of those releases is licensed by the pull request their work was
superseded on still being closed, and that pass is long gone -- so a human who
reopens the change afterwards would otherwise have its work handed over anyway.

Which is why the question is asked inside the walk rather than by whoever
called it: the child scan a caller decides on is a request per child, and the
relabels behind it are one request each, so a licence taken anywhere but
immediately in front of a relabel is one the relabel has already outlived.

And why the walk asks its own cheap barrier on BOTH sides of that question:
the licence costs a lookup, and a close a poll observed inside it would reach
nothing else before the relabel landed.

Which is what the retirement keeps the publication group for. The measurement
goes, because that is what pins `workflow:decomposing`; the pull request and
the head it was closed over stay, because they are the only thing on the issue
that could answer this question again.

Driven from the transaction rather than from a seeded umbrella, since what is
under test is the record the transaction actually leaves: a fixture that wrote
the group by hand would pass while the retirement dropped it.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.stages.decomposition import (
    late_publication as _late_publication,
    late_supersession_reading as _late_supersession_reading,
    umbrella as _umbrella,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.stages.decomposition.late_published_split_support import (
    STATE_CLOSED,
    PublishedSplitCase,
)
from tests.workflow.stages.decomposition.late_race_support import (
    interleaved_after,
)
from tests.workflow.stages.decomposition.late_test_support import (
    LATE_ISSUE_NUMBER,
)
from tests.workflow.stages.decomposition.late_transaction_support import (
    ERROR,
    first_child,
)

# A manifest whose slices depend on nothing, so one walk has two relabels to
# make and a human has a window between them.
INDEPENDENT = (
    {"title": "A", "body": "the first slice"},
    {"title": "B", "body": "the second slice"},
)

# The reading the walk takes immediately in front of every relabel it makes.
RELEASE_GATE = "_release_undone"

# The barrier the transaction takes in front of every step its supersession
# licenses. Interleaving behind its first call is how a case puts the reopen
# inside the retirement write -- the one window that pass cannot close.
PUBLICATION_BARRIER = "_publication_holds"

WARNING = "WARNING"


class ReopenedPublicationUmbrellaTest(PublishedSplitCase, unittest.TestCase):
    """The ticks that come AFTER the pass that saw the reopen.

    That pass holds its own children and keeps its own branch, and neither
    answer is durable on its own: the umbrella walks this issue on every
    dependency poll from then on, and nothing it reads is about a pull request.
    So the record is what has to carry the question, and these are the two
    readers of it.
    """

    def test_the_next_umbrella_tick_holds_children(self) -> None:
        # The walk releases a child the moment its dependencies read
        # satisfied, and it would do it beside a change carrying the very work
        # that child is taking over.
        self._reopened_past_the_barrier()

        with self.assertLogs(level=ERROR):
            self._umbrella_tick()

        self.assertEqual(
            [
                child.labels[0].name
                for child in self.github.created_child_issues
            ],
            [WorkflowLabel.BLOCKED, WorkflowLabel.BLOCKED],
        )

    def _reopened_past_the_barrier(self) -> None:
        """One split settled with the publication reopened behind its close."""
        with interleaved_after(
            _late_supersession_reading, PUBLICATION_BARRIER, self.reopened,
        ), self.assertLogs(level=ERROR):
            self._transact(generation=self.generation)

    def _umbrella_tick(self) -> None:
        """One real umbrella poll over the issue the transaction left."""
        _umbrella._handle_umbrella(self.github, _TEST_SPEC, self.issue)


class ReopenedBetweenRelabelsTest(PublishedSplitCase, unittest.TestCase):
    """A change reopened between one child being released and the next.

    The window a single reading of the publication cannot cover, and the one
    the walk's own per-relabel ask exists for: two independent slices are two
    relabels, each a request, and a human moving the pull request between them
    licenses the first and not the second.
    """

    def test_the_second_child_is_not_released(self) -> None:
        self._settled_with_both_children_held()
        self.published_pr.state = STATE_CLOSED

        with interleaved_after(
            _late_publication, RELEASE_GATE, self.reopened,
        ), self.assertLogs(level=ERROR):
            _umbrella._handle_umbrella(
                self.github, _TEST_SPEC, self.issue,
            )

        released = [
            child.labels[0].name
            for child in self.github.created_child_issues
        ]
        self.assertEqual(released.count(WorkflowLabel.BLOCKED), 1)
        self.assertEqual(released.count(WorkflowLabel.READY), 1)

    def _settled_with_both_children_held(self) -> None:
        """A split whose two independent slices were never released."""
        with interleaved_after(
            _late_supersession_reading, PUBLICATION_BARRIER, self.reopened,
        ), self.assertLogs(level=ERROR):
            self._transact(
                generation=self.generation, children=INDEPENDENT,
            )


class LatchedInsideTheLicenceTest(
    ObservedCloseCase, PublishedSplitCase, unittest.TestCase,
):
    """A close observed inside the request the licence itself costs.

    The publication read is a round-trip, and a poll runs beside it: the
    parent can be closed while the walk is asking whether its children may
    start. Asked only in front of that read, the latch would answer about a
    world one request old and the relabel would land anyway -- which is the
    one write this walk exists to withhold, since past it an agent runs on
    somebody's repository.
    """

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()

    def test_a_close_in_the_lookup_holds_the_child(self) -> None:
        with interleaved_after(
            _late_publication, RELEASE_GATE, self._latched_close,
        ), self.assertLogs(level=WARNING):
            self._transact(generation=self.generation)

        self.assertEqual(
            first_child(self.github).labels[0].name, WorkflowLabel.BLOCKED,
        )

    def _latched_close(self) -> None:
        """What the polling thread does with a close it can hand nowhere."""
        self._latch_close(_TEST_SPEC.slug, LATE_ISSUE_NUMBER)


if __name__ == "__main__":
    unittest.main()
