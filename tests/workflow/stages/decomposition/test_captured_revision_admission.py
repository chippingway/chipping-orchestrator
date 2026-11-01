# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A close the dispatcher's admission of a captured late revision reads, kept whatever the issue reads next.

The recovery's admission fetches the issue before the late owner is handed
anything, and again behind its decision; a close either fetch reads, with the
issue open again by the other or by the next dispatch, would otherwise hold
the capture or retire it and leave the cycle live for the reopening to hand
on. Each case holds a revision to its capture, takes the control off, and
dispatches the issue with GitHub answering the admission's fetches closed in
one order or another -- the issue itself never closed, so every later fetch
reads it open -- and reads back what was left: the cycle cancelled, or the
close latched for it where the comment would not read to record that, and
nothing of the capture handed on, consumed, or delivered, then or after.
"""
from __future__ import annotations

import contextlib
import copy
from unittest.mock import patch

from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.stages.decomposition import captured_revision_support as _captured, late_content_support as _support
from tests.workflow.stages.decomposition.late_test_support import GENERATION_NUMBER, KEYS, LATE_ISSUE_NUMBER

# What a revision finished settles, none of which one a close ended may: its
# consumption of the guidance, and its report's delivery.
_UNSETTLED = (_support.KEY_COMMENT_WATERMARK, _captured.DELIVERED)

# The orders the admission's two fetches can read a close in: closed and then
# open again behind its decision, open and then closed, and closed both times.
_ORDERS = ((True, False), (False, True), (True, True))


class ClosedAtAdmissionTest(ObservedCloseCase, _captured.CapturedRevisionCase):
    """A close the admission reads ends the revision's cycle, and no reopening revives the capture."""

    def setUp(self) -> None:
        self._fresh_process()
        self._seed_drifted()
        self._held()
        self._released()

    def test_a_close_at_admission_ends_the_cycle(self) -> None:
        # In whatever order the admission's fetches read the close, it ends
        # the cycle in that dispatch, the capture left pending with nothing
        # of it finished; the next dispatch, reading the issue open, hands
        # none of it on.
        for order in _ORDERS:
            with self.subTest(order=order):
                self.setUp()
                read = _ReadClosed(self, order)

                with read.patched():
                    self._dispatched().assert_not_called()

                self.assertTrue(self._pinned()[KEYS.cancelled])
                self._revived_nothing()

    def test_an_unrecorded_close_stays_latched(self) -> None:
        # Read closed by the admission while the pinned comment will not read
        # again to record the cancellation, the close is latched for the
        # cycle instead, so the dispatch that reads the issue open ends it.
        read = _ReadClosed(self, (True, False), unread=True)

        with read.patched():
            self._dispatched().assert_not_called()

        self.assertFalse(self._pinned().get(KEYS.cancelled))
        self.assertIn(LATE_ISSUE_NUMBER, self._observed(_TEST_SPEC.slug))
        self._dispatched().assert_not_called()
        self.assertTrue(self._pinned()[KEYS.cancelled])
        self._revived_nothing()

    def _revived_nothing(self) -> None:
        """Assert a dispatch over the issue as it reads leaves the capture pending and unsettled, the generation put."""
        self._dispatched().assert_not_called()
        pinned = self._pinned()
        self.assertEqual(
            (_captured.capture_of(pinned).stage, pinned[_support.KEY_GENERATION], self._developer_runs()),
            (_captured.PENDING, GENERATION_NUMBER, 1),
        )
        self.assertEqual([field for field in _UNSETTLED if field in pinned], [])


class _ReadClosed:
    """GitHub answering the issue's next fetches closed or open in `order`, then as it stands; its comment unread too.

    The comment is unread, where `unread` asks, from the first fetch that
    answered closed until the block ends.
    """

    def __init__(self, case: _captured.CapturedRevisionCase, order: tuple, *, unread: bool = False) -> None:
        self._case = case
        self._order = list(order)
        self._unread = unread
        self._fetches = case.github.get_issue
        self._reads = case.github.read_pinned_state
        self.seen = False

    def patched(self) -> contextlib.AbstractContextManager:
        """The fetch and the read, held in place of the double's for the block."""
        held = contextlib.ExitStack()
        held.enter_context(patch.object(self._case.github, "get_issue", self._fetch))
        held.enter_context(patch.object(self._case.github, "read_pinned_state", self._read))
        return held

    def _fetch(self, number: int):
        fetched = self._fetches(number)
        if not (self._order and self._order.pop(0)):
            return fetched
        self.seen = True
        closed = copy.copy(fetched)
        closed.closed = True
        return closed

    def _read(self, issue):
        if self._unread and self.seen:
            raise RuntimeError("GitHub did not answer the pinned comment read")
        return self._reads(issue)
