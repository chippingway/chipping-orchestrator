# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A close held across this process's own restart of the cycle, which no claim note records.

Settled under a publication hold, it is retried by the next poll without
ending or receipting the fresh cycle; a close read after the restart is the
fresh cycle's own.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import (
    dispatch_closure as _dispatch_closure,
    observations,
    publication_holds as _publication_holds,
)
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.observation_support import ObservedCloseCase, read_now, receipt_for
from tests.workflow.stages.decomposition import late_restart_support as _fix
from tests.workflow.stages.decomposition.late_test_support import LATE_ISSUE_NUMBER

_SLUG = _TEST_SPEC.slug


class RestartedHereTest(_fix.RestartCase, ObservedCloseCase, unittest.TestCase):
    """An owner this process restarts while a publication hold keeps an older close."""

    def setUp(self) -> None:
        self._fresh_process()
        self._seed()
        _publication_holds.claim_publication(_SLUG, LATE_ISSUE_NUMBER)
        self.addCleanup(_publication_holds.release_publication, _SLUG, LATE_ISSUE_NUMBER)
        observations.observe_close(_SLUG, LATE_ISSUE_NUMBER, read_now())
        observations.settle_close(_SLUG, LATE_ISSUE_NUMBER)
        self._reported_route()
        self.assertEqual(self._pinned()[_fix.KEY_CYCLE_ID], _fix.RESTART_CYCLE_ID)

    def test_the_old_close_spares_the_fresh_cycle(self) -> None:
        _dispatch_closure._recorded_at_poll(self.github, _TEST_SPEC, self.issue, None)

        self.assertFalse(self._receipted(), "no receipt names the fresh cycle")
        self.assertFalse(
            observations.close_ends(_SLUG, LATE_ISSUE_NUMBER, _fix.RESTART_CYCLE_ID, repo_id=self.github.repo_id),
            "and no barrier ends it",
        )
        _publication_holds.release_publication(_SLUG, LATE_ISSUE_NUMBER)
        self.assertEqual(self._observed(_SLUG), frozenset(), "the retry withdrew no settlement")

    def test_a_fresh_close_is_receipted(self) -> None:
        self.issue.closed = True

        _dispatch_closure._recorded_at_poll(self.github, _TEST_SPEC, self.issue, read_now())

        self.assertTrue(self._receipted())

    def _receipted(self) -> bool:
        """Whether the thread carries a close receipt for the fresh cycle."""
        receipt = receipt_for(LATE_ISSUE_NUMBER, _fix.RESTART_CYCLE_ID)
        return any(receipt in body for _, body in self.github.posted_comments)


if __name__ == "__main__":
    unittest.main()
