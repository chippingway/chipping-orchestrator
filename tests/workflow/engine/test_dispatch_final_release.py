# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A close latched between a scheduled worker letting go of its claim and of its hold.

Another poller can restart the cycle in that window, and the drop decided for
the old cycle may not take a fresh close of the new one with it.
"""
from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from orchestrator.git.snapshots import refs as _snapshot_refs
from orchestrator.workflow.engine import (
    dispatch_workers as _dispatch_workers,
    issue_processing as _issue_processing,
    poll_models as _poll_models,
    publication_holds as _publication_holds,
    scheduled_dispatch as _scheduled_dispatch,
)
from tests.support.fakes import FakeLabel
from tests.support.writer_claims import held_elsewhere
from tests.workflow.engine import cleanup_deferral_support as _deferral
from tests.workflow.engine.contended_close_support import ClosedOwnerCase, restarted_elsewhere
from tests.workflow.fixtures import LABEL_UMBRELLA

_OWED = frozenset((_deferral.OWNER_NUMBER,))

# What a cleanup submit hands its worker.
_CLEANUP = _poll_models._PollReading(cleanup_only=True, closed=True)


class LatchedAfterTheClaimTest(ClosedOwnerCase, unittest.TestCase):
    """The closed umbrella owner's cleanup, and a restart landing behind its claim."""

    def test_the_fresh_close_outlives_the_old_drop(self) -> None:
        self._swept_behind_a_restart()
        kept = self._observed(_deferral.REPO_SLUG)
        fresh = self._generation().cycle_id
        self._reopened()
        self._ticked(self._scheduler())

        self.assertEqual(kept, _OWED, "the fresh close is still held once the hold is given back")
        self.assertGreater(fresh, _deferral.CYCLE_ID)
        self.assertEqual(self._generation().cycle_id, fresh)
        self.assertTrue(self._generation().cancelled, "the next pass ends the fresh cycle with it")
        self.stage.assert_not_called()

    def _swept_behind_a_restart(self) -> None:
        """One scheduled cleanup of cycle 4's close, with the restart landing before its hold is given back."""
        self._seeded_owner()
        self._latch_close(_deferral.REPO_SLUG, _deferral.OWNER_NUMBER)
        _publication_holds.claim_publication(_deferral.REPO_SLUG, _deferral.OWNER_NUMBER)
        task = _dispatch_workers._fanout_task(
            self.github, self._spec(), _deferral.OWNER_NUMBER, reading=_CLEANUP,
        )
        with patch.object(
            _snapshot_refs, "delete_snapshot_ref", Mock(return_value=_snapshot_refs.SnapshotOutcome.DELETED),
        ):
            _scheduled_dispatch._releases_the_claim(
                _deferral.REPO_SLUG, _deferral.OWNER_NUMBER, _RestartedBehindTheClaim(self, task),
            )


class _RestartedBehindTheClaim:
    """The worker's task, then what happens once it has let go of the claim.

    Another poller takes the owner, settles the cycle the pass just ended,
    and restarts it under the label the owner works on; then, still holding
    it, sees it closed again -- and this process, refused the claim, reads
    that close of the fresh cycle.
    """

    def __init__(self, case: ClosedOwnerCase, task) -> None:
        self._case = case
        self._task = task

    def __call__(self) -> None:
        """Run the task, then restart the owner elsewhere and read its fresh close as a contender."""
        self._task()
        github = self._case.github
        restarted_elsewhere(github)
        owner = github.get_issue(_deferral.OWNER_NUMBER)
        owner.labels = [FakeLabel(LABEL_UMBRELLA)]
        with held_elsewhere(github.repo_id, _deferral.OWNER_NUMBER):
            owner.closed = True
            with _issue_processing._writer_claim(
                github, self._case._spec(), _deferral.OWNER_NUMBER, closed=owner,
            ) as held:
                self._case.assertFalse(held, "the other poller holds the owner")


if __name__ == "__main__":
    unittest.main()
