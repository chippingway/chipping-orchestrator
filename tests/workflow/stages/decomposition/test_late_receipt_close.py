# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The receipts a reclaimed ref owes, delivered one child at a time.

Every child cut from a snapshot is told once that the ref is gone, and each
telling is a comment on somebody ELSE's issue. So the walk is not one moment:
a close observed after the first receipt is one the second may not be written
over, because a cancelled cycle owes its children nothing at all -- it does
not close them, relabel them, write their pinned state, or put a word on their
threads.

The mark therefore goes down between the two, and the walk stops telling the
children after it. It still answers "all told", because a cycle that owes no
receipt has left none undelivered.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import observations as _observations
from orchestrator.workflow.late_split import models as _late_models, obligations as _obligations, phases as _late_phases
from orchestrator.workflow.stages.decomposition import (
    late_cleanup_state as _late_cleanup_state,
    late_consumer_release as _late_consumer_release,
    parents as _parents,
)
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.stages.decomposition.late_cleanup_support import (
    PARENT_NUMBER,
    SNAPSHOT_REF,
    UMBRELLA,
)
from tests.workflow.stages.decomposition.late_observation_seams import (
    ISSUE_COMMENT,
    latches_on_call,
)
from tests.workflow.stages.decomposition.late_test_support import (
    late_generation,
)

_WORKFLOW_LOG = "orchestrator.workflow"

_TEST_SLUG = _TEST_SPEC.slug

_KEY_CANCELLED = "late_cancelled"

# Two children cut from the same ref, so a walk nothing stopped tells both.
_SIBLINGS = (911, 912)

# The read that proves one consumer untold, and the window this module's
# last case is about.
_CHILD_THREAD = "get_comments"


class LatchedInsideTheFirstReceiptTest(
    ObservedCloseCase, unittest.TestCase,
):
    """A receipt is a comment on somebody else's issue, one child at a time.

    Two children were cut from this ref, so a walk nothing stopped tells
    both. A close observed after the first is one the second may not be
    written over: the children left are owed nothing at all, and a
    cancellation the pass has not persisted yet is one that would let the
    walk go on writing to them.
    """

    def setUp(self) -> None:
        self._fresh_process()
        self.github = FakeGitHubClient()
        self.owner = make_issue(PARENT_NUMBER, label=UMBRELLA)
        self.github.add_issue(self.owner)
        for number in _SIBLINGS:
            self.github.add_issue(make_issue(number, closed=True))

    def test_only_the_first_sibling_is_told(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG):
            self._released()

        self.assertEqual(
            [number for number, _ in self.github.posted_comments],
            [_SIBLINGS[0]],
        )

    def test_the_cancellation_is_persisted(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG):
            generation, told = self._released()

        self.assertTrue(generation.cancelled)
        self.assertTrue(
            self.github.pinned_data(PARENT_NUMBER)[_KEY_CANCELLED],
        )
        self.assertTrue(told)

    def test_a_walk_nobody_latched_tells_both(self) -> None:
        _, told = self._released(closing=False)

        self.assertEqual(
            [number for number, _ in self.github.posted_comments],
            list(_SIBLINGS),
        )
        self.assertTrue(told)

    def test_a_close_in_the_thread_read_tells_none(self) -> None:
        # Proving a child untold is a request of its own, and the poll runs
        # beside it: the latch is asked between that reading and the comment
        # it authorizes, so the FIRST child is never written to either.
        with self.assertLogs(_WORKFLOW_LOG):
            generation, told = self._released(closing=False, reading=True)

        self.assertEqual(self.github.posted_comments, [])
        self.assertTrue(generation.cancelled)
        self.assertTrue(told)

    def _released(self, *, closing: bool = True, reading: bool = False):
        """Deliver this ref's receipts, closing inside the first if asked."""
        walk = _late_cleanup_state._Pass(
            gh=self.github,
            spec=_TEST_SPEC,
            issue=self.owner,
            state=self.github.read_pinned_state(self.owner),
            scan=_scan_of(self.github),
        )
        generation = _consuming_both()
        if reading:
            first = self.github.get_issue(_SIBLINGS[0])
            with _LatchingChildThread(first, PARENT_NUMBER).answering():
                return _late_consumer_release._release_consumers(
                    walk, generation, SNAPSHOT_REF, walk.scan,
                )
        if not closing:
            return _late_consumer_release._release_consumers(
                walk, generation, SNAPSHOT_REF, walk.scan,
            )
        with latches_on_call(
            self.github, _TEST_SLUG, PARENT_NUMBER, ISSUE_COMMENT,
        ):
            return _late_consumer_release._release_consumers(
                walk, generation, SNAPSHOT_REF, walk.scan,
            )


class _LatchingChildThread:
    """Latch the owner's close from inside a CHILD's own thread walk.

    The one window between the reading that proves a consumer untold and the
    comment that tells it: the walk is a request, and what stands behind it
    is the only cleanup effect that writes to somebody else's issue.

    Planted on the FIRST consumer alone, which is the only one this window
    reaches: what the latch earns is a cycle that owes its children nothing,
    so the walk stops where it stands and the second is never read.
    """

    def __init__(self, child, owner: int) -> None:
        self._child = child
        self._owner = owner

    def __call__(self):
        """Latch the owner's close, then answer the walk it interrupted."""
        _observations.observe_close(_TEST_SLUG, self._owner)
        return list(self._child.comments)

    def answering(self):
        """Put this in front of the thread walk that reads this child."""
        return patch.object(self._child, _CHILD_THREAD, self)


def _consuming_both() -> _late_models.LateGeneration:
    """A live generation whose ref two children were cut from."""
    return late_generation(
        threshold=None, additions=None,
        phase=_late_phases.LatePhase.CLEANING_UP,
        obligations=_obligations.LateObligations().with_consumers(_SIBLINGS),
    )


def _scan_of(github: FakeGitHubClient):
    """The reading a reclamation proves its consumers ended on."""
    return _parents._read_child_labels(
        github, github.get_issue(PARENT_NUMBER), list(_SIBLINGS),
    )


if __name__ == "__main__":
    unittest.main()
