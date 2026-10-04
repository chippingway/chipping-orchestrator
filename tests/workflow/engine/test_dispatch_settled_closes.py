# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A close this process holds ends the cycle it was read against, and no later one.

Another poller on this host can hold a closed owner while this one keeps the
close it read, settle the cycle that close ended, and start the fresh one an
operator authorizes -- all before this process holds the owner again. The
close it kept is scoped to the cycle it ended, so the retry, on every dispatch
mode a tick can take, lets it go without marking, posting, or relabelling
anything on the fresh cycle. A close no read tied to a cycle is the subject of
`test_dispatch_unconfirmed_closes.py`.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.support.writer_claims import held_elsewhere
from tests.workflow.engine import cleanup_deferral_support as _deferral
from tests.workflow.engine.contended_close_support import (
    ClosedOwnerCase,
    FirstReadFails,
    restarted_elsewhere,
    ticked_on,
    written,
)
from tests.workflow.engine.writer_claim_test_support import DISPATCH_MODES

_OWED = frozenset((_deferral.OWNER_NUMBER,))


class SettledElsewhereTest(ClosedOwnerCase, unittest.TestCase):
    """The closed umbrella owner, its close kept, and the cycle restarted elsewhere."""

    def test_held_close_spares_a_restarted_cycle(self) -> None:
        for mode, limit, scheduled in DISPATCH_MODES:
            with self.subTest(mode=mode):
                self._kept_while_held_elsewhere(limit, scheduled=scheduled)
                restarted_elsewhere(self.github)
                before = written(self.github)

                ticked_on(self, limit, scheduled=scheduled)

                self._assert_restarted_cycle_spared(before)

    def test_worker_close_spares_a_restarted_cycle(self) -> None:
        # Observed under the claim this time, beside this process's own worker,
        # and written down: the other poller takes the owner once that worker
        # lets it go, and before this process sweeps it.
        for mode, limit, scheduled in DISPATCH_MODES:
            with self.subTest(mode=mode):
                self._seeded_owner()
                self._tick_a_worker_held(self._scheduler())
                self.assertEqual(self._observed(_deferral.REPO_SLUG), _OWED)
                restarted_elsewhere(self.github)
                before = written(self.github)

                ticked_on(self, limit, scheduled=scheduled)

                self._assert_restarted_cycle_spared(before)

    def test_failed_retry_spares_a_restarted_cycle(self) -> None:
        # The retry's cleanup pass cannot refetch the owner, so it keeps the
        # close and tries to write it down -- which, against a record on the
        # fresh cycle, would be a receipt ending that cycle on a later tick.
        for mode, limit, scheduled in DISPATCH_MODES:
            with self.subTest(mode=mode):
                self._kept_while_held_elsewhere(limit, scheduled=scheduled)
                restarted_elsewhere(self.github)
                before = written(self.github)

                failing = FirstReadFails(self.github.get_issue)
                with patch.object(self.github, "get_issue", failing):
                    ticked_on(self, limit, scheduled=scheduled)

                self.assertEqual(written(self.github), before, "nothing is written for the fresh cycle")
                self.assertEqual(self._observed(_deferral.REPO_SLUG), _OWED, "the failed pass keeps the close")

                ticked_on(self, limit, scheduled=scheduled)

                self._assert_restarted_cycle_spared(before)

    def _kept_while_held_elsewhere(self, limit: int, *, scheduled: bool) -> None:
        """A tick that reads the owner closed while another poller holds it."""
        self._seeded_owner()
        with held_elsewhere(self.github.repo_id, _deferral.OWNER_NUMBER):
            ticked_on(self, limit, scheduled=scheduled)
        self.assertEqual(self._observed(_deferral.REPO_SLUG), _OWED)


if __name__ == "__main__":
    unittest.main()
