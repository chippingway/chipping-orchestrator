# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A fresh cycle's close, read by a poller refused the issue's claim as the holder restarts the cycle.

The holder can restart the cycle between the contender's first record read and
its issue read, and a human can close the fresh cycle there. The first read
named only the cycle before it -- still live, or already marked over -- so the
record read again behind the issue is what ties the close to the fresh cycle:
on every dispatch mode, a reopen before this process holds the issue again
cannot take it away, and no handler runs.
"""
from __future__ import annotations

import importlib
import itertools
import unittest
from unittest.mock import Mock, patch

from orchestrator.workflow.engine import observations as _observations, stage_targets as _stage_targets
from tests.support.fakes import FakeGitHubClient, FakeLabel
from tests.support.writer_claims import held_elsewhere
from tests.workflow.engine import cleanup_deferral_support as _deferral
from tests.workflow.engine.contended_close_support import ClosedOwnerCase, restarted_elsewhere, ticked_on
from tests.workflow.engine.writer_claim_test_support import DISPATCH_MODES
from tests.workflow.fixtures import LABEL_IMPLEMENTING, LABEL_UMBRELLA

# The handler an `implementing` owner reaches, and must not once its cycle is closed.
_IMPLEMENTING_TARGET = _stage_targets._STAGE_HANDLER_TARGETS[LABEL_IMPLEMENTING]

# Each mode, with the owner on the cleanup-swept umbrella label and an ordinary
# stage's, and the cycle the contender's first record read finds still live or
# already ended.
_CASES = tuple(itertools.product(DISPATCH_MODES, (LABEL_UMBRELLA, LABEL_IMPLEMENTING), (False, True)))


class RestartedBehindTheReadTest(ClosedOwnerCase, unittest.TestCase):
    """The closed owner another poller holds, restarted behind the contender's first record read."""

    def test_the_fresh_close_outlives_a_reopen(self) -> None:
        for mode, label, ended in _CASES:
            with self.subTest(mode=mode[0], label=label, ended_before_the_read=ended):
                fresh = self._closed_behind_the_read(mode, label=label, ended=ended)
                self.assertGreater(fresh, _deferral.CYCLE_ID)
                self.assertEqual(
                    _observations.close_scope(_deferral.REPO_SLUG, _deferral.OWNER_NUMBER), fresh,
                    "the kept close is tied to the fresh cycle",
                )
                self._reopened()

                stand_in = self._ticked_twice(mode)

                self.assertEqual(self._generation().cycle_id, fresh)
                self.assertTrue(self._generation().cancelled, "the fresh cycle is ended by its close")
                self.stage.assert_not_called()
                stand_in.assert_not_called()

    def _closed_behind_the_read(self, mode: tuple, *, label: str, ended: bool) -> int:
        """One tick over the closed owner while another poller holds it and restarts its cycle.

        Answers the fresh cycle's id.
        """
        self._seeded_owner()
        self.github.get_issue(_deferral.OWNER_NUMBER).labels = [FakeLabel(label)]
        if ended:
            self._ended_over()
        with (
            held_elsewhere(self.github.repo_id, _deferral.OWNER_NUMBER),
            patch.object(self.github, "read_pinned_state", _RestartedBehindTheRead(self.github)),
        ):
            self._ticked_in(mode)
        return self._generation().cycle_id

    def _ticked_twice(self, mode: tuple) -> Mock:
        """Two ticks over the reopened owner, once the holder has let go.

        Every tick a dependency walk is due on, so nothing but the kept close
        keeps the reopened owner from its handler. Answers the handler an
        `implementing` owner reaches.
        """
        stand_in = Mock()
        owner, name = _IMPLEMENTING_TARGET
        with (
            patch.object(importlib.import_module(owner), name, stand_in),
            patch("orchestrator.config.DEPENDENCY_POLL_EVERY_N_TICKS", 1),
        ):
            self._ticked_in(mode)
            self._ticked_in(mode)
        return stand_in

    def _ticked_in(self, mode: tuple) -> None:
        """One tick over the owner through `mode`, a scheduler's drained before it returns.

        An open umbrella owner reaches the family bucket, which a wait on the
        issue's own key can return ahead of, so the scheduler is shut down
        behind the tick and every pass it took has run by the time it answers.
        """
        if mode[2]:
            self._ticked(self._scheduler(), drained=True)
            return
        ticked_on(self, mode[1], scheduled=False)


class _RestartedBehindTheRead:
    """A record read the holder restarts the closed owner's cycle behind, and a human closes the fresh one.

    The first read answers the record as it stood; before the issue is read
    behind it, the holder settles that cycle, an operator restarts it, and the
    fresh cycle is closed again -- a close the first read never named.
    """

    def __init__(self, github: FakeGitHubClient) -> None:
        self._github = github
        self._reading = github.read_pinned_state
        self._restarted = False

    def __call__(self, issue):
        """Read the record, then restart its cycle and close the fresh one the first time."""
        state = self._reading(issue)
        if not self._restarted:
            self._restarted = True
            with patch.object(self._github, "read_pinned_state", self._reading):
                restarted_elsewhere(self._github)
            self._github.get_issue(_deferral.OWNER_NUMBER).closed = True
        return state


if __name__ == "__main__":
    unittest.main()
