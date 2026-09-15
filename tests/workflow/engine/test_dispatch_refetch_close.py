# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The close the REFETCH is the first thing to see.

An issue open when the enumeration listed it carries no reading at all: the
poll latched nothing and wrote nothing down, because there was nothing to
latch. The refetch every pass takes on its way to a handler can be where that
stops being true -- a human closes the issue in between -- and from there the
reading exists in exactly one place, the object the refetch just returned.

Everything behind it can fail. The pinned read the guard is built on answers a
refusal of its own, and the write that marks the cancellation is a request
like any other; a pass that dies on either leaves nothing saying a close was
ever seen, and a human who reopens the issue before the next poll takes the
reading off the remote for good. So the observation is taken where it is first
established, by both paths that refetch: the sequential loop, which has no
hand-off to hold one for it, and the worker, which has one carrying the poll's
older reading instead.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import dispatch, dispatch_workers as _dispatch_workers
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.late_split.phases import LatePhase
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import LABEL_UMBRELLA
from tests.workflow.observation_support import ObservedCloseCase, receipt_for

_SPEC = SimpleNamespace(slug="acme/widget")

_OWNER_NUMBER = 61

_CYCLE_ID = 8

_CANDIDATE_SHA = "c0ffee0000000000000000000000000000000061"

_WORKFLOW_LOG = "orchestrator.workflow"

_KEY_CANCELLED = "late_cancelled"

_PINNED_WRITE = "write_pinned_state"

_GET_ISSUE = "get_issue"

_DEPENDENCY_CADENCE_ATTR = "DEPENDENCY_POLL_EVERY_N_TICKS"

# What GitHub declining the write that marks a cancellation looks like here.
_REFUSED = RuntimeError("pinned write rejected")


class _ClosingOnRefetch:
    """Close the issue as the read that would have found it open runs.

    The window this module is about, planted where it actually is: the
    enumeration answered open, and the refetch behind it is the first request
    that could ever say otherwise.
    """

    def __init__(self, github: FakeGitHubClient) -> None:
        self._reading = github.get_issue

    def __call__(self, number: int):
        """Answer the refetch, having closed the issue it asked for."""
        refetched = self._reading(number)
        refetched.closed = True
        return refetched


class _RefetchedCloseCase(ObservedCloseCase):
    """One owner open at enumeration and closed by the time it is read."""

    def setUp(self) -> None:
        self._fresh_process()
        # Dispatched straight off the object with no enumeration in front of
        # it, so no poll is counted that the dependency cadence could be due
        # on; the refetch is the subject, not which tick walks the umbrella.
        every_tick = patch.object(config, _DEPENDENCY_CADENCE_ATTR, 1)
        every_tick.start()
        self.addCleanup(every_tick.stop)
        self.github = _owner_with_a_live_cycle()
        self.polled = self.github.get_issue(_OWNER_NUMBER)

    def _reopened(self) -> None:
        """What a human does before the next poll, and nothing else reads."""
        self.github.get_issue(_OWNER_NUMBER).closed = False

    def _receipts(self) -> list:
        """Every close receipt on this owner's thread for its own cycle."""
        marker = receipt_for(_OWNER_NUMBER, _CYCLE_ID)
        return [
            body for number, body in self.github.posted_comments
            if number == _OWNER_NUMBER and marker in body
        ]

    def _refused(self, dispatched) -> None:
        """Run one pass whose cancellation write GitHub will not take."""
        with self.assertLogs(_WORKFLOW_LOG), patch.object(
            self.github, _GET_ISSUE, side_effect=_ClosingOnRefetch(self.github),
        ), patch.object(
            self.github, _PINNED_WRITE, side_effect=_REFUSED,
        ), self.assertRaises(RuntimeError):
            dispatched()

    def _cancelled(self) -> bool:
        """Whether the owner's own record now says the cycle ended."""
        return bool(
            self.github.pinned_data(_OWNER_NUMBER).get(_KEY_CANCELLED),
        )


class SequentialRefetchCloseTest(_RefetchedCloseCase, unittest.TestCase):
    """The path with no hand-off: it classifies and refetches on its own."""

    def test_a_refused_mark_keeps_the_reading(self) -> None:
        self._refused(self._polled)

        self.assertFalse(self._cancelled())
        self.assertEqual(
            self._observed(_SPEC.slug), frozenset((_OWNER_NUMBER,)),
        )

    def test_a_refused_mark_is_told_on_the_thread(self) -> None:
        # A latch is memory, so the reading needs a half that is not.
        self._refused(self._polled)

        self.assertEqual(len(self._receipts()), 1)

    def test_a_reopen_after_it_still_ends_the_cycle(self) -> None:
        # The regression in full: nothing the next pass can READ says closed,
        # and the reading the failed one kept is the only thing that does.
        self._refused(self._polled)
        self._reopened()

        with self.assertLogs(_WORKFLOW_LOG):
            self._polled()

        self.assertTrue(self._cancelled())

    def _polled(self) -> None:
        """Dispatch this issue the way the sequential loop does."""
        dispatch._process_polled_issue(self.github, _SPEC, self.polled)


class WorkerRefetchCloseTest(_RefetchedCloseCase, unittest.TestCase):
    """The worker's own refetch, which carries the poll's older reading."""

    def test_a_refused_mark_keeps_the_reading(self) -> None:
        self._refused(self._ran)

        self.assertFalse(self._cancelled())
        self.assertEqual(
            self._observed(_SPEC.slug), frozenset((_OWNER_NUMBER,)),
        )

    def test_a_refused_mark_is_told_on_the_thread(self) -> None:
        self._refused(self._ran)

        self.assertEqual(len(self._receipts()), 1)

    def test_a_reopen_after_it_still_ends_the_cycle(self) -> None:
        self._refused(self._ran)
        self._reopened()

        with self.assertLogs(_WORKFLOW_LOG):
            self._ran()

        self.assertTrue(self._cancelled())

    def _ran(self) -> None:
        """Run the task a fan-out submit hands the scheduler."""
        _dispatch_workers._refetch_and_process(self.github, _SPEC, _OWNER_NUMBER)


def _owner_with_a_live_cycle() -> FakeGitHubClient:
    """An OPEN umbrella whose record still carries a cycle a close would end."""
    github = FakeGitHubClient()
    github.add_issue(make_issue(_OWNER_NUMBER, label=LABEL_UMBRELLA))
    state = github.read_pinned_state(github.get_issue(_OWNER_NUMBER))
    _late_state.write_late_generation(state, LateGeneration(
        cycle_id=_CYCLE_ID,
        generation=1,
        root_issue=_OWNER_NUMBER,
        current_issue=_OWNER_NUMBER,
        candidate_sha=_CANDIDATE_SHA,
        phase=LatePhase.CLEANING_UP,
    ))
    github.seed_state(_OWNER_NUMBER, **state.data)
    return github


if __name__ == "__main__":
    unittest.main()
