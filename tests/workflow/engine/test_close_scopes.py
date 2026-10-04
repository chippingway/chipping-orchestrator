# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which cycle a latched close ends, as a pass holding the writer claim asks it.

A close tied to a cycle by a read ends that cycle and no other. One no read
tied ends the cycle a holder asks about only where no other poller on this
host has held the issue since the moment the close was read at -- so a cycle
another poller settled and restarted is ended by a close read after it let go,
never by the reading it settled. A retirement made under the claim notes its
cycle there for the pollers it refuses, and reports a close latched inside it
only where that close ends the cycle being retired. A restart this process
writes, which no claim note records, holds every close read before it ended
off the fresh cycle; and a receipt scan asked under the claim is owed again
once another poller has held the issue since it walked.

Asked directly: no production pass carries a read moment, scopes a close,
opens a retirement window with the repository's id, fences a restart, or
scans under the claim yet.
"""
from __future__ import annotations

import unittest

from orchestrator.scheduler import claim_notes as _claim_notes, writer_claims as _writer_claims
from orchestrator.workflow.engine import (
    observation_receipts as _observation_receipts,
    observations as _observations,
    retiring_cycles as _retiring_cycles,
)
from tests.support.writer_claims import claimable, signed_by_another_poller
from tests.workflow.observation_support import ObservedCloseCase

_SLUG = "acme/widget"
_REPO_ID = 4242
_ISSUE = 7720
_CYCLE = 6
_RESTARTED = _CYCLE + 1


def _held_here():
    """This process's own writer claim on the issue, as a pass under it holds it."""
    return _writer_claims.issue_writer(_REPO_ID, _ISSUE)


def _ends_the_restarted_cycle() -> bool:
    """Whether the held close ends the restarted cycle, asked with the repository's id."""
    return _observations.close_ends(_SLUG, _ISSUE, _RESTARTED, repo_id=_REPO_ID)


class CloseScopeTest(ObservedCloseCase, unittest.TestCase):
    """A close ends the cycle it was read against, and none another poller started after it."""

    def setUp(self) -> None:
        self._fresh_process()

    def test_a_scoped_close_ends_only_its_cycle(self) -> None:
        self._latch_close(_SLUG, _ISSUE)
        _observations.scope_close(_SLUG, _ISSUE, _CYCLE)

        self.assertTrue(_observations.close_ends(_SLUG, _ISSUE, _CYCLE))
        with _held_here():
            self.assertFalse(
                _observations.close_ends(_SLUG, _ISSUE, _RESTARTED, repo_id=_REPO_ID),
                "a close read with no moment proves nothing about the restarted cycle",
            )
            self.assertTrue(_observations.close_observed(_SLUG, _ISSUE), "and it is still held")
            _observations.observe_close(_SLUG, _ISSUE, _claim_notes.moment())
            self.assertTrue(
                _observations.close_ends(_SLUG, _ISSUE, _RESTARTED, repo_id=_REPO_ID),
                "until a closed reading taken since the last other hold ends the restarted cycle",
            )
        self.assertEqual(_observations.close_scope(_SLUG, _ISSUE), _RESTARTED)

    def test_an_undisturbed_close_ends_the_cycle(self) -> None:
        # This process held the issue last, before the close was read: an
        # acquisition finds no later hold of anybody else's.
        self.assertTrue(claimable(_REPO_ID, _ISSUE))
        _observations.observe_close(_SLUG, _ISSUE, _claim_notes.moment())

        self.assertFalse(
            _observations.close_ends(_SLUG, _ISSUE, _CYCLE),
            "asked without the repository's id, it ends nothing",
        )
        with _held_here():
            self.assertTrue(_observations.close_ends(_SLUG, _ISSUE, _CYCLE, repo_id=_REPO_ID))
        self.assertEqual(_observations.close_scope(_SLUG, _ISSUE), _CYCLE, "and is tied to it from then on")

    def test_a_disturbed_close_waits_to_be_reread(self) -> None:
        # The other poller held the issue after the close was read, so it may
        # have settled the cycle that close ended and restarted it: only a
        # closed reading taken after it let go ends the cycle the claim finds.
        read_at = _claim_notes.moment()
        _observations.observe_close(_SLUG, _ISSUE, read_at)
        signed_by_another_poller(_REPO_ID, _ISSUE)

        with _held_here():
            disturbed = _observations.close_ends(_SLUG, _ISSUE, _RESTARTED, repo_id=_REPO_ID)
            self.assertIsNone(_observations.close_scope(_SLUG, _ISSUE))
            _observations.observe_close(_SLUG, _ISSUE, _claim_notes.moment())
            _observations.observe_close(_SLUG, _ISSUE, read_at)
            later = _observations.close_ends(_SLUG, _ISSUE, _RESTARTED, repo_id=_REPO_ID)

        self.assertFalse(disturbed, "the reading the other poller may have settled ends nothing")
        self.assertTrue(later, "the latest reading is kept, and it ends the restarted cycle")

    def test_settling_drops_the_scope_and_the_moment(self) -> None:
        _observations.observe_close(_SLUG, _ISSUE, _claim_notes.moment())
        _observations.scope_close(_SLUG, _ISSUE, _CYCLE)

        self._settle_latches(_SLUG)
        self._latch_close(_SLUG, _ISSUE)

        self.assertIsNone(_observations.close_scope(_SLUG, _ISSUE))
        with _held_here():
            self.assertFalse(_observations.close_ends(_SLUG, _ISSUE, _CYCLE, repo_id=_REPO_ID))


class ClaimedRetirementTest(ObservedCloseCase, unittest.TestCase):
    """A retirement window opened with the repository's id, under the writer claim."""

    def setUp(self) -> None:
        self._fresh_process()

    def test_the_window_is_noted_for_the_hold(self) -> None:
        with _held_here():
            window = _retiring_cycles.retiring(_SLUG, _ISSUE, _CYCLE, _REPO_ID)
            with window.held():
                inside = _claim_notes.noted_retirement(_REPO_ID, _ISSUE)
            after_the_window = _claim_notes.noted_retirement(_REPO_ID, _ISSUE)
        after_the_hold = _claim_notes.noted_retirement(_REPO_ID, _ISSUE)

        self.assertEqual((inside, after_the_window), (_CYCLE, _CYCLE))
        self.assertIsNone(after_the_hold, "a hold that let go notes nothing")

    def test_the_window_reports_its_own_cycle(self) -> None:
        for scope, reported in ((_CYCLE, True), (_RESTARTED, False)):
            with self.subTest(scope=scope):
                self._fresh_process()
                window = _retiring_cycles.retiring(_SLUG, _ISSUE, _CYCLE, _REPO_ID)
                with _held_here(), window.held():
                    self._latch_close(_SLUG, _ISSUE)
                    _observations.scope_close(_SLUG, _ISSUE, scope)
                self.assertIs(window.observed, reported)

    def test_a_window_without_the_id_notes_none(self) -> None:
        # Every production retirement leaves the id out: nothing is noted on
        # the claim, and any close latched inside the window is reported.
        window = _retiring_cycles.retiring(_SLUG, _ISSUE, _CYCLE)
        with _held_here(), window.held():
            self._latch_close(_SLUG, _ISSUE)
            _observations.scope_close(_SLUG, _ISSUE, _RESTARTED)
            noted = _claim_notes.noted_retirement(_REPO_ID, _ISSUE)

        self.assertIsNone(noted)
        self.assertTrue(window.observed)


class RestartFenceTest(ObservedCloseCase, unittest.TestCase):
    """A restart this process writes under the claim, which no claim note records."""

    def setUp(self) -> None:
        self._fresh_process()
        self.assertTrue(claimable(_REPO_ID, _ISSUE))

    def test_a_close_read_after_the_write_ends_it(self) -> None:
        # Read while the write was in flight -- and the write's answer lost --
        # the close may be the old cycle's, so it ends the fresh one only once
        # it is read again behind the write.
        with self.assertRaises(ConnectionError), _held_here(), _retiring_cycles.restarting(_SLUG, _ISSUE):
            _observations.observe_close(_SLUG, _ISSUE, _claim_notes.moment())
            during = _ends_the_restarted_cycle()
            raise ConnectionError("the restart write's answer was lost")

        with _held_here():
            after = _ends_the_restarted_cycle()
            _observations.observe_close(_SLUG, _ISSUE, _claim_notes.moment())
            reread = _ends_the_restarted_cycle()

        self.assertFalse(during, "no moment ties a close while the write is in flight")
        self.assertFalse(after, "nor one read before it ended, however it ended")
        self.assertTrue(reread, "a close read behind the write is the fresh cycle's")

    def test_a_scoped_close_is_not_fenced(self) -> None:
        # The fence holds off the read moment alone: a close a read tied to
        # the fresh cycle ends it whenever it was latched.
        with _retiring_cycles.restarting(_SLUG, _ISSUE):
            self._latch_close(_SLUG, _ISSUE)
            _observations.scope_close(_SLUG, _ISSUE, _RESTARTED)

        with _held_here():
            self.assertTrue(_ends_the_restarted_cycle())


class ClaimedScanTest(ObservedCloseCase, unittest.TestCase):
    """The receipt walk a pass under the claim owes, against another poller's holds."""

    def setUp(self) -> None:
        self._fresh_process()

    def test_another_pollers_hold_owes_the_walk_again(self) -> None:
        with _held_here():
            first = self._walked()
            undisturbed = self._walked()
        signed_by_another_poller(_REPO_ID, _ISSUE)
        with _held_here():
            disturbed = self._walked()
            walked_since = self._walked()

        self.assertEqual((first, undisturbed), (True, False), "nothing has held the issue since the walk")
        self.assertTrue(disturbed, "the other poller may have posted a receipt meanwhile")
        self.assertFalse(walked_since, "and the walk taken behind its hold is bounded again")

    def _walked(self) -> bool:
        """Whether this cycle's thread is owed a walk, asked under the claim."""
        with _observation_receipts.scanning_receipt(_SLUG, _ISSUE, _CYCLE, repo_id=_REPO_ID) as claimed:
            return claimed


if __name__ == "__main__":
    unittest.main()
