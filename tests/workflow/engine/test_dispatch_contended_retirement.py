# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A close read while another poller on this host is retiring the owner's cycle.

The record names no cycle then, so the holder notes the cycle it is retiring on
the claim; a close read while that note stands is kept against that cycle and
adopted under the claim once the holder lets go. The record's own correlation
outlives every retirement, and is no such note.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.stages.decomposition import umbrella_terminal as _umbrella_terminal
from tests.support.fakes import FakeLabel
from tests.support.writer_claims import held_elsewhere
from tests.workflow.engine import cleanup_deferral_support as _deferral
from tests.workflow.engine.contended_close_support import ClosedOwnerCase, ticked_on, written
from tests.workflow.engine.writer_claim_test_support import DISPATCH_MODES
from tests.workflow.fixtures import LABEL_IMPLEMENTING

_OWED = frozenset((_deferral.OWNER_NUMBER,))


class ContendedRetirementTest(ClosedOwnerCase, unittest.TestCase):
    """The closed umbrella owner, its cycle retired off the record by another poller."""

    def test_a_close_in_a_noted_retirement_ends_it(self) -> None:
        for mode, limit, scheduled in DISPATCH_MODES:
            with self.subTest(mode=mode):
                self._retired_owner()
                with held_elsewhere(self.github.repo_id, _deferral.OWNER_NUMBER, retiring=_deferral.CYCLE_ID):
                    ticked_on(self, limit, scheduled=scheduled)
                self.assertEqual(self._observed(_deferral.REPO_SLUG), _OWED, "the close is kept")

                self._reopened()
                # Every tick a dependency walk is due on, so nothing but the
                # adopted close keeps the reopened umbrella from its handler.
                with patch.object(config, "DEPENDENCY_POLL_EVERY_N_TICKS", 1):
                    ticked_on(self, limit, scheduled=scheduled)

                adopted = self._generation()
                self.assertEqual(adopted.cycle_id, _deferral.CYCLE_ID, "the retired cycle is put back")
                self.assertTrue(adopted.cancelled, "and ended by the close read inside its retirement")
                self.stage.assert_not_called()

    def test_a_correlation_nobody_noted_keeps_nothing(self) -> None:
        # An owner long gone back to its own work keeps the correlation its
        # split's retirement left, and another poller holds it for that work.
        for mode, limit, scheduled in DISPATCH_MODES:
            with self.subTest(mode=mode):
                self._retired_owner()
                self.github.get_issue(_deferral.OWNER_NUMBER).labels = [FakeLabel(LABEL_IMPLEMENTING)]
                before = written(self.github)

                with held_elsewhere(self.github.repo_id, _deferral.OWNER_NUMBER):
                    ticked_on(self, limit, scheduled=scheduled)

                self.assertEqual(self._observed(_deferral.REPO_SLUG), frozenset(), "no close is kept")
                self.assertEqual(written(self.github), before, "and nothing is written")

    def _retired_owner(self) -> None:
        """The closed owner afresh, its record past the write that retires its cycle."""
        self._seeded_owner()
        owner = self.github.get_issue(_deferral.OWNER_NUMBER)
        state = self.github.read_pinned_state(owner)
        _umbrella_terminal._retired_cycle(state)
        self.github.write_pinned_state(owner, state)


if __name__ == "__main__":
    unittest.main()
