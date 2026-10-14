# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Another finish of the landing announcing while a direct finish proves its settled run, the proof's movement kept.

Every finish held to the dormant settled-evidence policy and handed over
directly (`settled_finish_support`): issue #7's run settled and its finish
killed before its announcement, the issue edited, and the next finish's proof
reading the edit. Right behind that proof the edit is put back and another
finish announces the landing and dies before its relabel -- the attempt
advanced, not replaced -- so the run is invalidated whole over the attempt as
it stands and the head routed, everything said and relabelled once; with the
comment filled behind that announcement, the base tip is blanked instead and
the next finish, room made, invalidates the run and routes the head.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad
from tests.workflow.engine import (
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    settled_finish_support as settled,
)
from tests.workflow.interleaving import _RacesPastTheCall

_EDITED_BODY = "Also cover a base that moved twice."

# The issue reads of a direct finish's proof of the run: its first reading,
# which reads the edit, and its last word's.
_THE_LAST_WORDS_READING = 2


class AnnouncementRaceTest(settled.SettledGuardedCase, unittest.TestCase):
    """A run one finish's proof read moving while another finish of the landing announced it."""

    def test_invalidated_over_the_announcement(self) -> None:
        # The proving finish invalidates the run over the attempt that
        # announcement advanced and routes the head in the same tick, with
        # nothing said twice; a later poll finds no attempt.
        head, run = self._proves_beside_an_announcement(full=False)

        self.assert_invalidated_then_routed(head, run)

    def test_a_full_comment_records_the_movement(self) -> None:
        # Nothing relabelled, the run current, and its base tip blank; room
        # made, the next finish invalidates the run whole and routes the head.
        head, run = self._proves_beside_an_announcement(full=True)

        self.assertIsNone(readings.pinned(self)[readings.KEY_REWRITE_BASE])
        self.assertEqual(readings.pinned_records(self)[1].receipt, run.receipt)
        self.assertEqual(readings.relabels(self), ())
        finish_moves.makes_room(self)
        self.assertEqual(self.finishes(head, FinishRoad.RECOVERY), FinishOutcome.ROUTED)
        self.assert_invalidated_then_routed(head, run)

    def _proves_beside_an_announcement(self, *, full: bool) -> tuple:
        """Settle the run, edit the issue, and finish again as another finish announces behind the proof; head and run.

        The proving finish's outcome is ROUTED with room for the run's
        invalidation, and HELD where the comment was filled to its limit
        behind that announcement (`full`).
        """
        head = self.lands_a_reviewed_rebase()
        handoff.dies_at(self.gh, handoff.BEFORE_THE_ANNOUNCEMENT, partial(self.finishes, head))
        run = readings.pinned_records(self)[1]
        announces = partial(self._announces_elsewhere, head, self.issue.body, full)
        self.issue.body = _EDITED_BODY
        reads = _RacesPastTheCall(self.gh.get_issue, _THE_LAST_WORDS_READING, announces)
        with patch.object(self.gh, "get_issue", reads):
            outcome = self.finishes(head, FinishRoad.RECOVERY)
        self.assertEqual(outcome, FinishOutcome.HELD if full else FinishOutcome.ROUTED)
        return head, run

    def _announces_elsewhere(self, head: str, written: str, full: bool) -> None:
        """Put the issue back as `written` and announce `head` as another finish would, dying at its relabel."""
        self.issue.body = written
        finishing = partial(self.finishes, head, FinishRoad.RECOVERY)
        handoff.dies_at(self.gh, handoff.BEFORE_THE_RELABEL, finishing)
        if full:
            finish_moves.fills_the_comment(self)


if __name__ == "__main__":
    unittest.main()
