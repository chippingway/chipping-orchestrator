# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A close read on an issue an operator parked is kept on every dispatch mode.

`backlog` and `paused` park an issue outside the state machine, with one
exception: an issue read CLOSED. Its close ends a live late cycle, and the pass
the park would discard is the only one that records it -- an owner reopened
and unparked later would come back with that cycle live and reach the handler
its label names. So every mode lets a closed reading past the filter and takes
the issue's writer claim for it: a holder marks the cycle and leaves everything
after the mark to the park, and a contender keeps the close in its own latch
for the pass that holds the claim next.
"""
from __future__ import annotations

import importlib
import unittest
from unittest.mock import Mock, patch

from orchestrator.github.labels import BACKLOG_LABEL, PAUSED_LABEL
from orchestrator.workflow.engine import stage_targets as _stage_targets
from tests.support.fakes import FakeLabel
from tests.support.writer_claims import held_elsewhere
from tests.workflow.engine import cleanup_deferral_support as _deferral
from tests.workflow.engine.contended_close_support import ClosedOwnerCase, ticked_on, written
from tests.workflow.engine.writer_claim_test_support import DISPATCH_MODES
from tests.workflow.fixtures import LABEL_IMPLEMENTING

_OWED = frozenset((_deferral.OWNER_NUMBER,))

# The handler an open `implementing` owner reaches, and must not while the
# cycle the close ended is still live.
_IMPLEMENTING_TARGET = _stage_targets._STAGE_HANDLER_TARGETS[LABEL_IMPLEMENTING]

# Every dispatch mode, under each control label that parks an issue.
_PARKED = tuple(
    (mode, control) for mode in DISPATCH_MODES for control in (BACKLOG_LABEL, PAUSED_LABEL)
)


class ParkedCloseTest(ClosedOwnerCase, unittest.TestCase):
    """A closed `implementing` owner wearing a live late cycle and a control label."""

    def test_a_held_close_is_marked_and_parked(self) -> None:
        # The close ends the cycle, and the park defers everything after the
        # mark: no terminal, and no handler.
        for mode, control in _PARKED:
            with self.subTest(mode=mode[0], control=control):
                self._parked_owner(control)
                stand_in = Mock()

                with _intercepted(stand_in):
                    ticked_on(self, mode[1], scheduled=mode[2])

                self.assertTrue(self._cancelled(), "the close ends the cycle")
                self.assertEqual(self.github.label_history, [], "the park defers the terminal")
                stand_in.assert_not_called()

    def test_a_contended_close_outlives_the_park(self) -> None:
        # Another poller holds the owner while this one reads it closed, so
        # nothing is written -- but the close is kept, and once a human has
        # reopened and unparked the owner the pass under the claim ends the
        # cycle with it rather than handing the live one to the handler.
        for mode, control in _PARKED:
            with self.subTest(mode=mode[0], control=control):
                self._parked_owner(control)
                before = written(self.github)
                stand_in = Mock()

                with held_elsewhere(self.github.repo_id, _deferral.OWNER_NUMBER), _intercepted(stand_in):
                    ticked_on(self, mode[1], scheduled=mode[2])
                self.assertEqual(self._observed(_deferral.REPO_SLUG), _OWED, "the contender keeps the close")
                self.assertEqual(written(self.github), before, "and writes nothing for the issue")
                self._unparked_and_reopened()
                with _intercepted(stand_in):
                    ticked_on(self, mode[1], scheduled=mode[2])

                self.assertTrue(self._cancelled(), "the next pass ends the cycle the close ended")
                stand_in.assert_not_called()

    def _parked_owner(self, control: str) -> None:
        """The closed owner afresh, on `implementing` and parked by `control`."""
        self._seeded_owner()
        self.github.get_issue(_deferral.OWNER_NUMBER).labels = [
            FakeLabel(LABEL_IMPLEMENTING), FakeLabel(control),
        ]

    def _unparked_and_reopened(self) -> None:
        """What a human does once the holder has let go: the park comes off and the issue opens."""
        owner = self.github.get_issue(_deferral.OWNER_NUMBER)
        owner.labels = [FakeLabel(LABEL_IMPLEMENTING)]
        owner.closed = False


def _intercepted(stand_in: Mock):
    """Stand `stand_in` in for the handler an `implementing` owner reaches."""
    owner, name = _IMPLEMENTING_TARGET
    return patch.object(importlib.import_module(owner), name, stand_in)


if __name__ == "__main__":
    unittest.main()
