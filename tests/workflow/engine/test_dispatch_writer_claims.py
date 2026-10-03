# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a tick does with an issue another poller on this host is writing.

It does nothing for it: no refetch, no guard, no recovery, no handler, and no
evaluation record, on every dispatch mode a tick can take -- while every other
issue in the same tick is dispatched as ever. The next tick after the other
poller lets go takes the issue up as if nothing had happened.
"""
from __future__ import annotations

import unittest

from tests.support.writer_claims import claimable, held_elsewhere
from tests.workflow.engine import cleanup_deferral_support as _deferral
from tests.workflow.engine.cleanup_deferral_support import DeferralCase
from tests.workflow.engine.dispatch_scheduler_test_support import REPO_SLUG
from tests.workflow.engine.writer_claim_test_support import (
    FREE_ISSUES,
    HELD_ISSUES,
    StandInHandler,
    WriterClaimDispatchCase,
)

# Each way a tick can execute its issues, as (name, `parallel_limit`, whether
# the scheduler takes the dispatch over): the sequential loop, the bounded
# in-tick pool, and the scheduler's fan-out submits and family bucket.
_DISPATCH_MODES = (
    ("sequential", 1, False),
    ("pool", 2, False),
    ("scheduler", 4, True),
)

_ALL_ISSUES = HELD_ISSUES | FREE_ISSUES


class ContendedDispatchTest(WriterClaimDispatchCase):
    """A held issue is skipped whole, and retried once it is let go."""

    def test_held_issues_are_skipped_then_retried(self) -> None:
        for mode, limit, scheduled in _DISPATCH_MODES:
            with self.subTest(mode=mode):
                self.seeded()
                stand_in = StandInHandler()

                with held_elsewhere(REPO_SLUG, *HELD_ISSUES):
                    self.ticked(stand_in, limit=limit, scheduled=scheduled)

                self.assertEqual(set(stand_in.ran), set(FREE_ISSUES), "only the free issues run")
                self.assertEqual(self.written_issues(), set(FREE_ISSUES), "nothing is written on a held one")
                self.assertEqual(self.evaluated_issues(), set(FREE_ISSUES), "nothing is accounted for one")

                retry = StandInHandler()
                self.ticked(retry, limit=limit, scheduled=scheduled)

                self.assertEqual(set(retry.ran), set(_ALL_ISSUES), "a released issue runs on the next tick")
                self.assertEqual(self.written_issues(), set(_ALL_ISSUES))

    def test_a_raising_handler_gives_its_claim_back(self) -> None:
        for mode, limit, scheduled in _DISPATCH_MODES:
            with self.subTest(mode=mode):
                self.seeded()

                self.ticked(StandInHandler(_ALL_ISSUES), limit=limit, scheduled=scheduled)

                for issue_number in _ALL_ISSUES:
                    self.assertTrue(claimable(REPO_SLUG, issue_number), f"#{issue_number} still claimed")
                retry = StandInHandler()
                self.ticked(retry, limit=limit, scheduled=scheduled)
                self.assertEqual(set(retry.ran), set(_ALL_ISSUES))


class ContendedCleanupTest(DeferralCase, unittest.TestCase):
    """A close owed to a held owner stays owed, and is swept once it is free.

    The owner is a closed umbrella still holding a snapshot ref, whose close an
    earlier tick observed and wrote down while a worker held it. What a later
    tick owes it is a cleanup pass -- the recovery route, not a stage -- and
    that pass reads the record and writes on the strength of it, so it is a
    writer like any other.
    """

    def setUp(self) -> None:
        super().setUp()
        self._tick_a_worker_held(self._scheduler())
        self.owed = frozenset((_deferral.OWNER_NUMBER,))
        self.assertEqual(self._observed(_deferral.REPO_SLUG), self.owed)

    def test_a_held_owner_keeps_its_observation(self) -> None:
        for mode, limit, scheduled in _DISPATCH_MODES:
            with self.subTest(mode=mode):
                comments = list(self.github.posted_comments)
                record = self.github.pinned_data(_deferral.OWNER_NUMBER)

                with held_elsewhere(REPO_SLUG, _deferral.OWNER_NUMBER):
                    self._ticked_on(limit, scheduled=scheduled)

                self.assertEqual(self._observed(_deferral.REPO_SLUG), self.owed)
                self.assertEqual(self.github.posted_comments, comments)
                self.assertEqual(self.github.pinned_data(_deferral.OWNER_NUMBER), record)
                self.assertFalse(self._cancelled())

    def test_a_released_owner_is_swept_next_tick(self) -> None:
        with held_elsewhere(REPO_SLUG, _deferral.OWNER_NUMBER):
            self._ticked_on(4, scheduled=True)

        self._ticked_on(4, scheduled=True)

        self.assertTrue(self._cancelled())
        self.assertEqual(self._observed(_deferral.REPO_SLUG), frozenset())
        self.stage.assert_not_called()

    def _ticked_on(self, limit: int, *, scheduled: bool) -> None:
        if scheduled:
            self._ticked(self._scheduler())
            return
        _deferral.ticked_directly(self, limit)


if __name__ == "__main__":
    unittest.main()
