# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A close this process holds ends the cycle it was read against, and no later one.

Another poller on this host can hold a closed owner while this one keeps the
close it read, settle the cycle that close ended, and start the fresh one an
operator authorizes -- all before this process holds the owner again. The
close it kept is scoped to the cycle it ended, so the retry, on every dispatch
mode a tick can take, lets it go without marking, posting, or relabelling
anything on the fresh cycle. A close the record could not be read for is kept
whole, since a reading lost costs the close itself.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.late_split import state as _late_state
from tests.support.writer_claims import held_elsewhere
from tests.workflow.engine import cleanup_deferral_support as _deferral
from tests.workflow.engine.contended_close_support import FirstReadFails, restarted_elsewhere, ticked_on
from tests.workflow.engine.writer_claim_test_support import DISPATCH_MODES

_OWED = frozenset((_deferral.OWNER_NUMBER,))


class SettledElsewhereTest(_deferral.DeferralCase, unittest.TestCase):
    """The closed umbrella owner, its close kept, and the cycle restarted elsewhere."""

    def test_held_close_spares_a_restarted_cycle(self) -> None:
        for mode, limit, scheduled in DISPATCH_MODES:
            with self.subTest(mode=mode):
                self._kept_while_held_elsewhere(limit, scheduled=scheduled)
                restarted_elsewhere(self.github)
                written = _written(self.github)

                ticked_on(self, limit, scheduled=scheduled)

                self._assert_restarted_cycle_spared(written)

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
                written = _written(self.github)

                ticked_on(self, limit, scheduled=scheduled)

                self._assert_restarted_cycle_spared(written)

    def test_failed_retry_spares_a_restarted_cycle(self) -> None:
        # The retry's cleanup pass cannot refetch the owner, so it keeps the
        # close and tries to write it down -- which, against a record on the
        # fresh cycle, would be a receipt ending that cycle on a later tick.
        for mode, limit, scheduled in DISPATCH_MODES:
            with self.subTest(mode=mode):
                self._kept_while_held_elsewhere(limit, scheduled=scheduled)
                restarted_elsewhere(self.github)
                written = _written(self.github)

                failing = FirstReadFails(self.github.get_issue)
                with patch.object(self.github, "get_issue", failing):
                    ticked_on(self, limit, scheduled=scheduled)

                self.assertEqual(_written(self.github), written, "nothing is written for the fresh cycle")
                self.assertEqual(self._observed(_deferral.REPO_SLUG), _OWED, "the failed pass keeps the close")

                ticked_on(self, limit, scheduled=scheduled)

                self._assert_restarted_cycle_spared(written)

    def test_an_unread_record_keeps_the_close(self) -> None:
        for mode, limit, scheduled in DISPATCH_MODES:
            with self.subTest(mode=mode):
                self._seeded_owner()
                with (
                    held_elsewhere(self.github.repo_id, _deferral.OWNER_NUMBER),
                    patch.object(self.github, "read_pinned_state", side_effect=ConnectionError("unreachable")),
                ):
                    ticked_on(self, limit, scheduled=scheduled)

                self.assertEqual(self._observed(_deferral.REPO_SLUG), _OWED, "the close is kept")

                self._reopened()
                ticked_on(self, limit, scheduled=scheduled)

                self.assertTrue(self._cancelled(), "and still ends the cycle it was read against")
                self.stage.assert_not_called()

    def _seeded_owner(self) -> None:
        """The closed owner afresh, in a process that has observed nothing."""
        self.github = _deferral.owner_holding_a_ref()
        self._fresh_process()
        self.stage.reset_mock()

    def _kept_while_held_elsewhere(self, limit: int, *, scheduled: bool) -> None:
        """A tick that reads the owner closed while another poller holds it."""
        self._seeded_owner()
        with held_elsewhere(self.github.repo_id, _deferral.OWNER_NUMBER):
            ticked_on(self, limit, scheduled=scheduled)
        self.assertEqual(self._observed(_deferral.REPO_SLUG), _OWED)

    def _assert_restarted_cycle_spared(self, written: tuple) -> None:
        """The retry left the fresh cycle live and let the settled close go."""
        state = self.github.read_pinned_state(self.github.get_issue(_deferral.OWNER_NUMBER))
        restarted = _late_state.read_late_generation(state)
        self.assertGreater(restarted.cycle_id, _deferral.CYCLE_ID)
        self.assertFalse(restarted.cancelled, "the fresh cycle is not ended by the old close")
        self.assertEqual(_written(self.github), written, "nothing is posted, relabelled, or recorded")
        self.assertEqual(self._observed(_deferral.REPO_SLUG), frozenset(), "the settled close is let go")
        self.stage.assert_not_called()


def _written(github) -> tuple:
    """Everything a pass could leave on the owner: comments, labels, and its record."""
    return (
        list(github.posted_comments),
        list(github.label_history),
        github.pinned_data(_deferral.OWNER_NUMBER),
    )


if __name__ == "__main__":
    unittest.main()
