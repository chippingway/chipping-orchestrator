# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Another finish of the landing announcing while a direct finish proves its settled run, the proof's movement kept.

Every finish held to the dormant settled-evidence policy and handed over
directly (`settled_finish_support`): issue #7's run settled, the issue edited,
and right behind the next finish's proof the edit is put back while another
finish announces the landing -- the attempt advanced, so the run is
invalidated over it, or its tip blanked with no room -- or routes it whole, so
the run is retired as the comment stands, or marked, even with report 2 put
back under the very write; and a retry that cannot read its label holds.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    settled_finish_support as settled,
    verification_report_fixture as _report,
)
from tests.workflow.interleaving import _RacesPastTheCall

_EDITED_BODY = "Also cover a base that moved twice."

# The issue reads of a direct finish's proof of the run: its first reading,
# which reads the edit, and its last word's; behind them, a retry under the
# mark reads the issue's label again.
_THE_LAST_WORDS_READING = 2
_THE_LABELS_READING = 3

# The handoff's place on the pinned comment, which the movement mark takes.
_HANDOFF = "verification_evidence_handoff"

# The report and review records report 3's settlement moves, as the pinned comment spells them.
_MOVED_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")


def _loses_the_issue() -> None:
    """Lose the answer of an issue read just made."""
    raise RuntimeError("the issue would not read")


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

    def test_invalidated_behind_a_completed_route(self) -> None:
        # The other finish routes the head whole, retiring the attempt: the
        # proving finish retires the run as the comment stands and holds, and
        # a later direct finish finds no attempt and makes nothing.
        head, run = self._proves_beside_an_announcement(full=False, died=None)

        self.assertEqual(self.finishes(head, FinishRoad.RECOVERY), FinishOutcome.UNFINISHABLE)
        self.assert_invalidated_then_routed(head, run)

    def test_a_full_comment_marks_the_completed_route(self) -> None:
        # The comment filled behind that route, the run stays current with
        # the mark naming its receipt in its handoff's place; room made, the
        # next direct finish, finding no attempt, retires it whole.
        head, run = self._proves_beside_an_announcement(full=True, died=None)

        self.assertEqual(readings.pinned(self)[_HANDOFF], {"moved": run.receipt})
        self.assertEqual(readings.pinned_records(self)[1].receipt, run.receipt)
        finish_moves.makes_room(self)
        self.assertEqual(self.finishes(head, FinishRoad.RECOVERY), FinishOutcome.UNFINISHABLE)
        self.assert_invalidated_then_routed(head, run)

    def test_an_unread_label_holds_the_retry(self) -> None:
        # A finish relabels the head and dies before its retirement; the
        # retry behind it cannot read the label again, so it holds rather
        # than relabel twice, and the next retry retires the attempt.
        head = self.lands_a_reviewed_rebase()
        handoff.dies_at(self.gh, handoff.BEFORE_THE_RETIREMENT, partial(self.finishes, head))
        run = readings.pinned_records(self)[1]
        reads = _RacesPastTheCall(self.gh.get_issue, _THE_LABELS_READING, _loses_the_issue)
        with patch.object(self.gh, "get_issue", reads):
            self.assertEqual(self.finishes(head, FinishRoad.RECOVERY), FinishOutcome.HELD)

        self.assertEqual(readings.relabels(self), readings.ROUTED)
        self.assertEqual(self.finishes(head, FinishRoad.RECOVERY), FinishOutcome.ROUTED)
        self.assert_routed(head, run)
        self.assertEqual(handoff.stage_entries(self.gh, git_support.ISSUE), ["validating"])

    def _proves_beside_an_announcement(self, *, full: bool, died=handoff.BEFORE_THE_RELABEL) -> tuple:
        """Settle the run, edit the issue, and finish again as another finish announces behind the proof; head and run.

        That finish dies at `died`, or routes the head whole. The proving
        finish routes the head only behind an announcement with room for the
        run's invalidation, and holds otherwise.
        """
        head = self.lands_a_reviewed_rebase()
        handoff.dies_at(self.gh, handoff.BEFORE_THE_ANNOUNCEMENT, partial(self.finishes, head))
        run = readings.pinned_records(self)[1]
        announces = partial(self._announces_elsewhere, head, self.issue.body, full, died)
        self.issue.body = _EDITED_BODY
        reads = _RacesPastTheCall(self.gh.get_issue, _THE_LAST_WORDS_READING, announces)
        expected = FinishOutcome.HELD if full or died is None else FinishOutcome.ROUTED
        with patch.object(self.gh, "get_issue", reads):
            self.assertEqual(self.finishes(head, FinishRoad.RECOVERY), expected)
        return head, run

    def _announces_elsewhere(self, head: str, written: str, full: bool, died) -> None:
        """Put the issue back as `written` and announce `head` as another finish would, dying at `died`."""
        self.issue.body = written
        finishing = partial(self.finishes, head, FinishRoad.RECOVERY)
        handoff.dies_at(self.gh, died, finishing)
        if full:
            finish_moves.fills_the_comment(self)



class RestoredUnderTheRetirementTest(settled.SettledGuardedCase, unittest.TestCase):
    """A run read moving under report 3, retired while another finish's route and report 2 put back race it."""

    def test_the_movement_outlives_the_restore(self) -> None:
        # Behind the proof that read report 3, report 2 is put back while
        # another finish routes the head whole, then report 3 returns, and
        # report 2 is put back once more under the proving finish's very
        # write. The run is retired over the comment read again -- or, the
        # comment full, marked, and the next direct finish retires it whole.
        for full in (False, True):
            with self.subTest(full=full):
                self.setUp()
                head, run = self._restores_under_the_write(full=full)
                if full:
                    self.assertEqual(readings.pinned(self)[_HANDOFF], {"moved": run.receipt})
                    finish_moves.makes_room(self)
                    self.assertEqual(self.finishes(head, FinishRoad.RECOVERY), FinishOutcome.UNFINISHABLE)
                self.assert_invalidated_then_routed(head, run)

    def _restores_under_the_write(self, *, full: bool) -> tuple:
        """Settle the run, move report 3 under it, and finish again over the race; the head and the run."""
        head = self.lands_a_reviewed_rebase()
        handoff.dies_at(self.gh, handoff.BEFORE_THE_ANNOUNCEMENT, partial(self.finishes, head))
        run = readings.pinned_records(self)[1]
        self._reports = (self._records(), None)
        self.state = self.gh.read_pinned_state(self.issue)
        _report.settles_report(self, 3, "Covered a base that moved twice as well.", head=head)
        self.gh.write_pinned_state(self.issue, self.state)
        self._reports = (self._reports[0], self._records())
        self._armed = False
        routes = partial(self._routes, head, full)
        reads = _RacesPastTheCall(self.gh.get_issue, _THE_LAST_WORDS_READING, routes)
        edits = partial(self._puts_back, self.gh.edit_pinned_state)
        self.enterContext(patch.object(self.gh, "edit_pinned_state", edits))
        with patch.object(self.gh, "get_issue", reads):
            self.assertEqual(self.finishes(head, FinishRoad.RECOVERY), FinishOutcome.HELD)
        self.assertFalse(self._armed)
        return head, run

    def _routes(self, head: str, full: bool) -> None:
        """Put report 2 back, route `head` whole as another finish would, and move report 3 under it again."""
        written, moved = self._reports
        self._writes(written)
        self.assertEqual(self.finishes(head, FinishRoad.RECOVERY), FinishOutcome.ROUTED)
        self._writes(moved)
        if full:
            finish_moves.fills_the_comment(self)
        self._armed = True

    def _puts_back(self, live, issue, state, *, over: dict):
        """`live`, the client's pinned edit, with report 2 put back ahead of the first edit once armed."""
        if self._armed:
            self._armed = False
            self._writes(self._reports[0])
        return live(issue, state, over=over)

    def _records(self) -> dict:
        """The report and review records the pinned comment carries now."""
        pinned = readings.pinned(self)
        return {key: pinned.get(key) for key in _MOVED_RECORDS}

    def _writes(self, records: dict) -> None:
        """Write `records` onto the pinned comment as another road would."""
        state = self.gh.read_pinned_state(self.issue)
        for key, recorded in records.items():
            state.set(key, recorded)
        self.gh.write_pinned_state(self.issue, state)


if __name__ == "__main__":
    unittest.main()
