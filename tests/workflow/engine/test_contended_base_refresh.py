# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A whole tick over an interrupted rebase on an issue another poller is writing.

The refresh and the dispatch take one claim on one key, so while another poller
on the host holds the issue neither of them acts on it -- the recovery is not
run, the handler is not reached, and nothing is written -- while every other
issue in the tick runs. Once it is let go, the next tick's refresh finishes the
recovery and its dispatch runs the handler, and no later tick finishes it
again.
"""
from __future__ import annotations

import unittest

from tests.support.fakes import make_issue
from tests.support.writer_claims import held_elsewhere
from tests.workflow.engine import contended_refresh_support as landed
from tests.workflow.engine.writer_claim_test_support import (
    DISPATCH_MODES,
    StandInHandler,
    WriterClaimDispatchCase,
)
from tests.workflow.fixtures import LABEL_IMPLEMENTING, LABEL_IN_REVIEW, LABEL_VALIDATING

# An issue beside the anchored one that nothing holds.
FREE = 8

_HANDLED_LABELS = (LABEL_IN_REVIEW, LABEL_VALIDATING, LABEL_IMPLEMENTING)

# What each tick once the issue is let go runs, by issue and label.
_RAN_ONCE_RELEASED = frozenset(((landed.ANCHORED, LABEL_VALIDATING), (FREE, LABEL_IMPLEMENTING)))

_RELEASED_TICKS = 2


class ContendedRefreshTickTest(WriterClaimDispatchCase):
    """Held, an anchored issue costs its tick nothing; let go, it is recovered once."""

    def setUp(self) -> None:
        self.checkout = landed.LandedCheckout(self)

    def test_a_held_recovery_waits_for_its_holder(self) -> None:
        for mode, limit, scheduled in DISPATCH_MODES:
            with self.subTest(mode=mode):
                self.fresh_repository()
                landed.seed_anchored(self.github, LABEL_IN_REVIEW)
                self.github.add_issue(make_issue(FREE, label=LABEL_IMPLEMENTING))
                record = self.github.pinned_data(landed.ANCHORED)

                with held_elsewhere(self.github.repo_id, landed.ANCHORED):
                    self.assertEqual(self._ran(limit, scheduled), {(FREE, LABEL_IMPLEMENTING)})

                self.assertEqual(self.github.pinned_data(landed.ANCHORED), record, "nothing is written on it")
                self.assertEqual((self.github.label_history, self.github.posted_pr_comments), ([], []))
                for _ in range(_RELEASED_TICKS):
                    self.assertEqual(self._ran(limit, scheduled), _RAN_ONCE_RELEASED)
                self._assert_recovered_once()

    def _ran(self, limit: int, scheduled: bool) -> set[tuple[int, str]]:
        """Which issues one whole tick ran a handler for, and under which label."""
        stand_in = StandInHandler()
        self.ticked(
            stand_in, limit=limit, scheduled=scheduled,
            labels=_HANDLED_LABELS, refresh=self.checkout.walked(),
        )
        return set(stand_in.ran_on)

    def _assert_recovered_once(self) -> None:
        """One relabel, one notice, one finish, and no anchor left."""
        self.assertEqual(self.github.label_history, [(landed.ANCHORED, LABEL_VALIDATING)])
        self.assertEqual(len(self.github.posted_pr_comments), 1)
        self.assertEqual(landed.finishes(self.github), [landed.RELABEL_ONLY])
        self.assertIsNone(self.github.pinned_data(landed.ANCHORED).get(landed.KEY_PENDING_PUSH_SHA))


if __name__ == "__main__":
    unittest.main()
