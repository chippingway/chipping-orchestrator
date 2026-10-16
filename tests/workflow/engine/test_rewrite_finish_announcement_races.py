# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Another finish of the landing announcing while a direct finish proves its settled run, the proof's movement kept.

Direct finishes through the coordinator every road hands its landing to
(`settled_route_support`), the other finish of the landing among them:
issue #7's run settled, the issue edited, and right behind the next finish's
proof the edit is put back while another finish announces the landing -- the
attempt advanced, so the run is invalidated over it, or its tip blanked with
no room -- or routes it whole, so the run is retired as the comment stands, or
marked, even with report 2 put back under the very write, or announces it
under the invalidation's write. A finish reads the label afresh under the
mark, and again behind the proof ahead of its relabel, so a relabel another
finish made meanwhile -- even while that proof was answered -- is not made
again -- nor over an attempt another road put in place meanwhile -- and a
retry that cannot read its label holds.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import DEFAULT, Mock, patch

from orchestrator.workflow.engine import verification_settlement_state as _settlement
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad
from tests.workflow.engine import (
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    settled_route_support as route,
    verification_report_fixture as _report,
)
from tests.workflow.interleaving import _RacesPastTheCall

_EDITED_BODY = "Also cover a base that moved twice."

# The issue reads of a direct finish's proof of the run: its first reading,
# which reads the edit, and its last word's.
_THE_LAST_WORDS_READING = 2

# The pull request a later rebase pins an attempt of its own for.
_PR_NUMBER = 42

# The client's read of the issue, which a case makes another finish's moves behind.
_ISSUE_READ = "get_issue"

# The first issue read of the proof ahead of a retry's relabel: behind the two
# of its evidence phase and the label read under the mark.
_THE_RELABELS_PROOF_READING = 4

# The handoff's place on the pinned comment, which the movement mark takes.
_HANDOFF = "verification_evidence_handoff"

# The current evidence's place on the pinned comment, which an invalidation clears.
_CURRENT = "verification_evidence_current"

# The evidence history's place on the pinned comment.
_HISTORY = "verification_evidence_history"

# The run's handoff behind the other finish's route, and whether its history stands.
_IN_PLACE = "as settled"
_HANDOFFS = (
    ("in place", (_IN_PLACE, True)),
    ("missing", (None, True)),
    ("short", ("x", True)),
    ("missing, no history", (None, False)),
    ("short, no history", ("x", False)),
)

# The report and review records report 3's settlement moves, as the pinned comment spells them.
_MOVED_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")


class _RaceCase(route.SettledRouteCase):
    """Issue #7's run settled and its first direct finish killed before the announcement."""

    def settles_then_dies(self, boundary: handoff.Boundary = handoff.BEFORE_THE_ANNOUNCEMENT) -> str:
        """Land a reviewed rebase, settle its run as `run`, and kill its direct finish at `boundary`; the head."""
        head = self.lands_a_reviewed_rebase()
        publishes = partial(self.finalizes, head, FinishRoad.PUBLICATION)
        handoff.dies_at(self.gh, boundary, publishes)
        self.run = readings.pinned_records(self)[1]
        return head

    def assert_invalidated_then_routed(self, head: str) -> None:
        """The run invalidated whole and `head` routed once, nothing parked; another finish changes nothing.

        The run's own entry is the latest in history, its revision and binding
        kept, whatever a case dropped of the history before it.
        """
        run = self.run
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        whole = (entry.receipt, entry.retired.value, entry.revision, entry.binding)
        self.assertEqual(whole, (run.receipt, readings.INVALIDATED, run.revision, run.binding))
        self.assertEqual(readings.pinned_records(self)[:2], (None, None))
        self.assertFalse(self.pinned_fields("awaiting_human")[0])
        self.assert_routed_once(head)
        routed = self.gh.pinned_data(self.issue.number)
        self.assertEqual(self.finalizes(head), FinishOutcome.UNFINISHABLE)
        self.assertEqual(self.gh.pinned_data(self.issue.number), routed)
        self.assert_routed_once(head)

    def assert_marked(self) -> None:
        """The run still current, the mark of movement read under it in its handoff's place."""
        current = readings.pinned_records(self)[1]
        self.assertEqual(current, self.run)
        marked = {"moved": self.run.receipt}
        self.assertEqual(self.pinned_fields(_HANDOFF)[0], marked)

    def assert_run_current(self) -> None:
        """The run current exactly as it settled, and nothing pending beside it."""
        records = readings.pinned_records(self)
        self.assertEqual(records[:2], (None, self.run))

    def writes(self, records: dict) -> None:
        """Write `records` onto the pinned comment as another road would."""
        state = self.gh.read_pinned_state(self.issue)
        for key, recorded in records.items():
            state.set(key, recorded)
        self.gh.write_pinned_state(self.issue, state)


class AnnouncementRaceTest(_RaceCase, unittest.TestCase):
    """A run one finish's proof read moving while another finish of the landing announced it."""

    def test_invalidated_over_the_announcement(self) -> None:
        # The proving finish invalidates the run over the attempt that
        # announcement advanced and routes the head in the same finish, with
        # nothing said twice.
        head = self._proves_beside_an_announcement(full=False)

        self.assert_invalidated_then_routed(head)

    def test_a_full_comment_records_the_movement(self) -> None:
        # Nothing relabelled, the run current, and its base tip blank; room
        # made, the next finish invalidates the run whole and routes the head.
        head = self._proves_beside_an_announcement(full=True)

        self.assertIsNone(readings.pinned(self)[readings.KEY_REWRITE_BASE])
        self.assertEqual(readings.pinned_records(self)[1].receipt, self.run.receipt)
        self.assertEqual(readings.relabels(self), ())
        finish_moves.makes_room(self)
        self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)
        self.assert_invalidated_then_routed(head)

    def test_invalidated_behind_a_completed_route(self) -> None:
        # The other finish routes the head whole, retiring the attempt: the
        # proving finish retires the run as the comment stands and holds, and
        # a later finish finds no attempt and makes nothing.
        head = self._proves_beside_an_announcement(full=False, died=None)

        self.assert_invalidated_then_routed(head)

    def test_a_full_comment_marks_the_completed_route(self) -> None:
        # The comment filled behind that route: the run is marked where its
        # handoff stands, and otherwise -- missing or short, the history absent
        # too on a first settlement -- retired whole at once, so restoring the
        # handoff revives nothing; room made, it ends retired whole.
        for label, spelled in _HANDOFFS:
            with self.subTest(handoff=label):
                self.setUp()
                self._handoff = spelled
                head = self._proves_beside_an_announcement(full=True, died=None)
                if spelled[0] is _IN_PLACE:
                    self.assert_marked()
                else:
                    self.writes({_HANDOFF: self._written})
                    self.assertNotIn(_CURRENT, readings.pinned(self))
                finish_moves.makes_room(self)
                self.assertEqual(self.finalizes(head), FinishOutcome.UNFINISHABLE)
                self.assert_invalidated_then_routed(head)

    def _proves_beside_an_announcement(self, *, full: bool, died=handoff.BEFORE_THE_RELABEL) -> str:
        """Settle the run, edit the issue, and finish again as another finish announces behind the proof; the head.

        That finish dies at `died`, or routes the head whole. The proving
        finish routes the head only behind an announcement with room for the
        run's invalidation, and holds otherwise.
        """
        head = self.settles_then_dies()
        announces = partial(self._announces_elsewhere, head, self.issue.body, full, died)
        self.issue.body = _EDITED_BODY
        reads = _RacesPastTheCall(self.gh.get_issue, _THE_LAST_WORDS_READING, announces)
        expected = FinishOutcome.HELD if full or died is None else FinishOutcome.ROUTED
        with patch.object(self.gh, _ISSUE_READ, reads):
            self.assertEqual(self.finalizes(head), expected)
        return head

    def _announces_elsewhere(self, head: str, written: str, full: bool, died) -> None:
        """Put the issue back as `written` and announce `head` as another finish would, dying at `died`.

        The run's handoff is then spelled as the case asks, the comment filled behind it where `full`.
        """
        self.issue.body = written
        handoff.dies_at(self.gh, died, partial(self.finalizes, head))
        spelled, kept = getattr(self, "_handoff", (_IN_PLACE, True))
        if spelled is not _IN_PLACE:
            state = self.gh.read_pinned_state(self.issue)
            self._written = state.get(_HANDOFF)
            state.set(_HANDOFF, spelled)
            if not kept:
                state.data.pop(_HISTORY)
            self.gh.write_pinned_state(self.issue, state)
        if full:
            finish_moves.fills_the_comment(self)


class LabelRaceTest(_RaceCase, unittest.TestCase):
    """The relabel under the mark, decided on the label read afresh."""

    def test_an_unread_label_holds_the_retry(self) -> None:
        # A finish relabels the head and dies before its retirement; the
        # retry behind it cannot read the label again under the mark, so it
        # holds rather than relabel twice, and the next retry retires the
        # attempt with the run current.
        head = self.settles_then_dies(handoff.BEFORE_THE_RETIREMENT)
        lost = Mock(wraps=self.gh.workflow_label, side_effect=[DEFAULT, RuntimeError("the label would not read")])
        with patch.object(self.gh, "workflow_label", lost):
            self.assertEqual(self.finalizes(head), FinishOutcome.HELD)

        self.assertEqual(readings.relabels(self), readings.ROUTED)
        self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)
        self.assert_routed_once(head)
        self.assert_run_current()

    def test_a_relabel_made_elsewhere_is_kept(self) -> None:
        # A finish announces the head and dies before its relabel; the next
        # one reads the issue's label then, and while it proves the run
        # another finish relabels and dies before its retirement. The label
        # read afresh under the mark is already the route's, so the issue is
        # relabelled, and enters the stage, once.
        head = self.settles_then_dies(handoff.BEFORE_THE_RELABEL)
        finishing = partial(self.finalizes, head)
        relabels = partial(handoff.dies_at, self.gh, handoff.BEFORE_THE_RETIREMENT, finishing)
        reads = _RacesPastTheCall(self.gh.get_issue, _THE_LAST_WORDS_READING, relabels)
        with patch.object(self.gh, _ISSUE_READ, reads):
            self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)

        self.assert_routed_once(head)
        self.assert_run_current()

    def test_a_replacement_while_proving_holds(self) -> None:
        # The retry reads the label still short of the route under the mark,
        # and while it proves the run ahead of its relabel another road puts
        # an attempt of its own in place. The comment read again behind that
        # proof carries that attempt, so nothing is relabelled and the issue
        # never enters the stage, the replacement kept exactly as written.
        head = self.settles_then_dies(handoff.BEFORE_THE_RELABEL)
        replaced: dict = {}
        replaces = partial(self._replaces, head, replaced)
        reads = _RacesPastTheCall(self.gh.get_issue, _THE_RELABELS_PROOF_READING, replaces)
        with patch.object(self.gh, _ISSUE_READ, reads):
            self.assertEqual(self.finalizes(head), FinishOutcome.HELD)

        pinned = readings.pinned(self)
        self.assertEqual({key: pinned.get(key) for key in readings.ATTEMPT_KEYS}, replaced)
        self.assertEqual(readings.relabels(self), ())
        self.assertEqual(handoff.stage_entries(self.gh, self.issue.number), [])

    def test_a_relabel_made_while_proving_is_kept(self) -> None:
        # The retry reads the label still short of the route under the mark,
        # and while it proves the run ahead of its relabel another finish
        # relabels and dies before its retirement. The label is read once more
        # behind that proof's requests, so the issue is relabelled, and enters
        # the stage, once.
        head = self.settles_then_dies(handoff.BEFORE_THE_RELABEL)
        finishing = partial(self.finalizes, head)
        relabels = partial(handoff.dies_at, self.gh, handoff.BEFORE_THE_RETIREMENT, finishing)
        reads = _RacesPastTheCall(self.gh.get_issue, _THE_RELABELS_PROOF_READING, relabels)
        with patch.object(self.gh, _ISSUE_READ, reads):
            self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)

        self.assert_routed_once(head)
        self.assert_run_current()

    def _replaces(self, head: str, replaced: dict) -> None:
        """Pin an attempt of a later rebase anchored on `head`, as another road would; its members into `replaced`."""
        state = self.gh.read_pinned_state(self.issue)
        written = dict.fromkeys(readings.ATTEMPT_KEYS)
        written.update({
            readings.KEY_PENDING_PUSH: head,
            readings.KEY_REWRITE_PR: _PR_NUMBER,
            readings.KEY_REWRITE_STAGE: "in_review",
            readings.KEY_REWRITE_BASE: state.get(readings.KEY_REWRITE_BASE),
        })
        for key, member in written.items():
            state.set(key, member)
        self.gh.write_pinned_state(self.issue, state)
        replaced.update(written)


class RestoredUnderTheRetirementTest(_RaceCase, unittest.TestCase):
    """A run read moving under report 3, retired while another finish's route and report 2 put back race it."""

    def test_the_movement_outlives_the_restore(self) -> None:
        # Behind the proof that read report 3, report 2 is put back while
        # another finish routes the head whole, then report 3 returns, and
        # report 2 is put back once more under the proving finish's very
        # write. The run is retired over the comment read again -- or, the
        # comment full, marked, and the next finish retires it whole.
        for full in (False, True):
            with self.subTest(full=full):
                self.setUp()
                head = self._restores_under_the_write(full=full)
                if full:
                    self.assert_marked()
                    finish_moves.makes_room(self)
                    self.assertEqual(self.finalizes(head), FinishOutcome.UNFINISHABLE)
                self.assert_invalidated_then_routed(head)

    def _restores_under_the_write(self, *, full: bool) -> str:
        """Settle the run, move report 3 under it, and finish again over the race; the head."""
        head = self.settles_then_dies()
        written = self._records()
        self.state = self.gh.read_pinned_state(self.issue)
        _report.settles_report(self, 3, "Covered a base that moved twice as well.", head=head)
        self.gh.write_pinned_state(self.issue, self.state)
        self._reports = (written, self._records())
        self._armed = False
        reads = _RacesPastTheCall(self.gh.get_issue, _THE_LAST_WORDS_READING, partial(self._routes, head, full))
        edits = partial(self._puts_back, self.gh.edit_pinned_state)
        self.enterContext(patch.object(self.gh, "edit_pinned_state", edits))
        with patch.object(self.gh, _ISSUE_READ, reads):
            self.assertEqual(self.finalizes(head), FinishOutcome.HELD)
        self.assertFalse(self._armed)
        return head

    def _routes(self, head: str, full: bool) -> None:
        """Put report 2 back, route `head` whole as another finish would, and move report 3 under it again."""
        written, moved = self._reports
        self.writes(written)
        self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)
        self.writes(moved)
        if full:
            finish_moves.fills_the_comment(self)
        self._armed = True

    def _puts_back(self, live, issue, state, *, over: dict, **options):
        """`live`, the client's pinned edit, with report 2 put back ahead of the first edit once armed."""
        if self._armed:
            self._armed = False
            self.writes(self._reports[0])
        return live(issue, state, over=over, **options)

    def _records(self) -> dict:
        """The report and review records the pinned comment carries now."""
        pinned = readings.pinned(self)
        return {key: pinned.get(key) for key in _MOVED_RECORDS}


class AnnouncedUnderTheInvalidationTest(_RaceCase, unittest.TestCase):
    """A run read moving whose invalidation another finish of the landing announces under."""

    def test_the_movement_outlives_the_announcement(self) -> None:
        # The proof reads the issue edited; as the invalidation is sent, the
        # edit is put back and another finish announces the landing, dying at
        # its relabel, so the write is refused. Read and reconciled once more,
        # the run is retired over the attempt that announcement advanced --
        # or, the comment full, its base tip blanked, and the next finish
        # retires it -- and it is never routed as current again.
        for full in (False, True):
            with self.subTest(full=full):
                self.setUp()
                head = self._announces_under_the_invalidation(full=full)
                if full:
                    self.assertIsNone(readings.pinned(self)[readings.KEY_REWRITE_BASE])
                    finish_moves.makes_room(self)
                    self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)
                self.assert_invalidated_then_routed(head)

    def _announces_under_the_invalidation(self, *, full: bool) -> str:
        """Settle the run, edit the issue, and finish again as another finish announces under the invalidation."""
        head = self.settles_then_dies()
        self._race = partial(self._announces, head, self.issue.body, full)
        self.issue.body = _EDITED_BODY
        edits = partial(self._ahead_of_the_invalidation, self.gh.edit_pinned_state)
        expected = FinishOutcome.HELD if full else FinishOutcome.ROUTED
        with patch.object(self.gh, "edit_pinned_state", edits):
            self.assertEqual(self.finalizes(head), expected)
        self.assertIsNone(self._race)
        return head

    def _ahead_of_the_invalidation(self, live, issue, state, *, over: dict, **options):
        """`live`, the client's pinned edit, with the race made ahead of the first edit retiring current evidence."""
        race = self._race
        held = over.get(_CURRENT) is not None
        if race is not None and held and state.get(_CURRENT) is None:
            self._race = None
            race()
        return live(issue, state, over=over, **options)

    def _announces(self, head: str, written: str, full: bool) -> None:
        """Put the issue back as `written` and announce `head` as another finish would, dying at its relabel."""
        self.issue.body = written
        handoff.dies_at(self.gh, handoff.BEFORE_THE_RELABEL, partial(self.finalizes, head))
        if full:
            finish_moves.fills_the_comment(self)


if __name__ == "__main__":
    unittest.main()
