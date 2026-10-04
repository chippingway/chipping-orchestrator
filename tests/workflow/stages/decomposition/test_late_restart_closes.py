# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A close held across this process's own restart of the cycle, which no claim note records.

Settled under a publication hold, it is retried by the next poll without
ending or receipting the fresh cycle, and so is one fetched closed before the
restart or recorded while its write is in flight; a close read after the
restart is the fresh cycle's own.
"""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import (
    dispatch_closure as _dispatch_closure,
    observations,
    poll_models as _poll_models,
    publication_holds as _publication_holds,
)
from orchestrator.workflow.late_split import state as _late_state
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

        self.assertFalse(_receipted(self.github), "no receipt names the fresh cycle")
        self.assertFalse(
            observations.close_ends(_SLUG, LATE_ISSUE_NUMBER, _fix.RESTART_CYCLE_ID, repo_id=self.github.repo_id),
            "and no barrier ends it",
        )
        _publication_holds.release_publication(_SLUG, LATE_ISSUE_NUMBER)
        self.assertEqual(self._observed(_SLUG), frozenset(), "the retry withdrew no settlement")

    def test_a_fresh_close_is_receipted(self) -> None:
        self.issue.closed = True

        _dispatch_closure._recorded_at_poll(self.github, _TEST_SPEC, self.issue, read_now())

        self.assertTrue(_receipted(self.github))

    def test_a_stale_closed_fetch_ties_nothing(self) -> None:
        # A refused cleanup submit reads beside this process's writer, so the
        # issue it fetched closed before the restart is no close of the fresh
        # cycle the record names behind it: only a read after the record is.
        fetched = _FetchedBeforeTheRestart(self.github)

        with patch.object(self.github, "get_issue", fetched):
            _dispatch_closure._refused_submit(
                self.github, _TEST_SPEC, LATE_ISSUE_NUMBER, _poll_models._PollReading(cleanup_only=True, closed=True),
            )

        self.assertFalse(_receipted(self.github), "no receipt names the fresh cycle")
        self.assertIsNone(observations.close_scope(_SLUG, LATE_ISSUE_NUMBER), "nor is the old close tied to it")


class RestartWindowTest(_fix.RestartCase, ObservedCloseCase, unittest.TestCase):
    """A poll answered beside the restart's own write, after the fresh record lands and before it returns."""

    def test_only_a_close_read_after_it_ties(self) -> None:
        self._fresh_process()
        self._seed()
        polled = _PolledMidRestart(self.github, _closed_copy(self.issue), read_now())

        with patch.object(self.github, "write_pinned_state", polled):
            self._reported_route()

        self.assertTrue(polled.answered)
        self.assertFalse(_receipted(self.github), "the older close receipts nothing for the fresh cycle")
        _dispatch_closure._recorded_at_poll(self.github, _TEST_SPEC, _closed_copy(self.issue), read_now())
        self.assertTrue(_receipted(self.github), "a close read after the restart does")


class _PolledMidRestart:
    """A pinned write that, once it lands the fresh live cycle, has a poll's older reading recorded behind it."""

    def __init__(self, github, issue, read_at: int) -> None:
        self._write = github.write_pinned_state
        self._github = github
        self._polled = (issue, read_at)
        self.answered = False

    def __call__(self, issue, state):
        """Land the write, then record the reading the first time the fresh cycle is on the record."""
        self._write(issue, state)
        generation = _late_state.read_late_generation(state)
        if self.answered or generation.cycle_id != _fix.RESTART_CYCLE_ID or generation.cancelled:
            return
        self.answered = True
        _dispatch_closure._recorded_at_poll(self._github, _TEST_SPEC, *self._polled)


def _closed_copy(issue):
    """The issue as a poll that read it closed holds it, apart from the live one."""
    snapshot = copy.copy(issue)
    snapshot.closed = True
    return snapshot


def _receipted(github) -> bool:
    """Whether the thread carries a close receipt for the fresh cycle."""
    receipt = receipt_for(LATE_ISSUE_NUMBER, _fix.RESTART_CYCLE_ID)
    return any(receipt in body for _, body in github.posted_comments)


class _FetchedBeforeTheRestart:
    """Independent issue snapshots, the first one taken before the restart reopened the issue."""

    def __init__(self, github) -> None:
        self._read = github.get_issue
        self._stale = True

    def __call__(self, number: int):
        """Answer a copy of the issue, closed the first time."""
        snapshot = copy.copy(self._read(number))
        snapshot.closed = snapshot.closed or self._stale
        self._stale = False
        return snapshot


if __name__ == "__main__":
    unittest.main()
