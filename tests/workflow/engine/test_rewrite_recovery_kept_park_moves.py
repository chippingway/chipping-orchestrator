# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A guarded park that keeps the attempt, proving its run again behind a notice another road wrote past.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
rebased head reviewed, its run settled under the anchor -- or only captured,
the finish dying at its artifact's post -- and the finish killed before its
announcement. The next tick's recovery can neither fetch the branch nor
reset the checkout, so the git owner's abort, handed the workflow's guarded
operations as every recovery is (`guarded_recovery_support`), parks keeping
the attempt: the reset it recorded first moved nothing, so the base tip that
record blanked is staged back and the park writes it as the attempt recorded
it.

While the park's notice is posted another road settles and reviews report 3
of the head, replacing the report the run was bound to, and the park's record
keeps report 3 as the comment then carries it. That record -- landed, or sent
with its answer lost -- carried the move, which is handed to the proof taken
once more behind the notice as movement already read: the run is invalidated,
or abandoned, whole, even where report 2 is put back right behind that record
and before the proof reads the comment again -- and so it is where report 2 is
only written back in another spelling of its revision. Once the park is
continued, the head is routed with nothing current. So is the run behind the
stranded park the dispatcher's hold takes under a label the refresh does not
drive, whose notice's post raises after report 3 settled: the proof is taken
before the error goes on, and nothing is parked. Nothing is run again or
pushed, nothing is announced or relabelled ahead of that route, and no
developer is launched.
"""
from __future__ import annotations

import subprocess
import unittest
from functools import partial
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.git import commands
from orchestrator.github.pinned_state import PinnedEdit
from tests.support.fakes import FakeLabel
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
    verification_report_fixture as _report,
)
from tests.workflow.interleaving import _RacesPastTheCall

_GIT = "_git_hardened"

# A label the refresh does not drive, under which the dispatcher's hold strands the attempt.
_UNDRIVEN = "workflow:resolving_conflict"

# The report and review records report 3's settlement moves, as the pinned comment spells them.
_MOVED_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")

# Report 2 put back right behind a park's record, before the proof behind it.
_RESTORED = MappingProxyType({"restoring": True})

# Each park: whether its run was only captured, and how its record goes --
# report 2 put back only after the tick or right behind the record, that
# record's answer lost, or report 2 respelled rather than report 3 settled.
_KEPT_PARKS = (
    (False, {}),
    (False, _RESTORED),
    (True, {}),
    (True, _RESTORED),
    (False, {**_RESTORED, "lost": True}),
    (True, {**_RESTORED, "lost": True}),
    (False, {**_RESTORED, "respelled": True}),
)


def _refuses(original, *called, **options) -> subprocess.CompletedProcess:
    """`original` git, save a fetch of issue #7's branch or a reset, each failing as git does."""
    fetches = any("issue-7" in str(arg) for arg in called)
    if fetches or called[0] == "reset":
        return subprocess.CompletedProcess(called, 1, "", "refused")
    return original(*called, **options)


def _answering(answer: PinnedEdit, live, issue, state, **options):
    """`live`, the client's pinned edit, its answer lost where it is a park's record and `answer` says so."""
    landed = live(issue, state, **options)
    if answer is PinnedEdit.EDITED or not guarded.parking(issue, state, **options):
        return landed
    return answer


def _settles_a_later_report(case, head: str, replaced: list, *, respelled: bool = False) -> None:
    """Settle report 3 of `head` and hand a reviewer it, as another road would; what it moved, into `replaced`.

    `respelled` writes report 2 back with its revision spelled as a float instead, which reads as the same number.
    """
    case.state = case.gh.read_pinned_state(case.issue)
    replaced.append({key: case.state.get(key) for key in _MOVED_RECORDS})
    if respelled:
        current = dict(case.state.get(_MOVED_RECORDS[0]))
        current["revision"] = float(current["revision"])
        case.state.set(_MOVED_RECORDS[0], current)
    else:
        _report.settles_report(case, 3, "Implemented the change and covered a base that moved twice.", head=head)
    case.gh.write_pinned_state(case.issue, case.state)


def _raises_behind(case, head: str, replaced: list, *_posted, **_options):
    """The issue-thread post of a park's notice, answered by report 3 of `head` settled and then a raise."""
    _settles_a_later_report(case, head, replaced)
    raise RuntimeError("GitHub did not answer the notice's post")


def _puts_back(case, replaced: list) -> None:
    """Write the report and review records back as they stood before report 3 moved them."""
    state = case.gh.read_pinned_state(case.issue)
    for key, recorded in replaced[-1].items():
        state.set(key, recorded)
    case.gh.write_pinned_state(case.issue, state)


class _MovesUnderThePark:
    """The client's strict edit, report 3 of `head` settled under the park's record and put back right behind it."""

    def __init__(self, case, head: str) -> None:
        self._case = case
        self._head = head
        self._live = case.gh.edit_pinned_state
        self._replaced: list = []

    def __call__(self, issue, state, **options):
        """Answer the edit, the park's record the first time with report 3 settled and put back around it."""
        if self._replaced or not guarded.parking(issue, state, **options):
            return self._live(issue, state, **options)
        _settles_a_later_report(self._case, self._head, self._replaced)
        answered = self._live(issue, state, **options)
        _puts_back(self._case, self._replaced)
        return answered


class KeptParkProofTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A park that keeps the attempt proves its run again behind its notice, over what its own record carried."""

    def test_a_kept_park_proves_behind_its_notice(self) -> None:
        # The park keeps the attempt, its base tip as recorded, and records
        # report 3 as the comment carries it, its answer lost or not --
        # report 2 put back right behind that record, before the proof, or
        # only after the tick, or report 2 respelled and put back alike: the
        # run, settled or only captured, is invalidated or abandoned whole,
        # and once the park is continued the head is routed with nothing
        # current.
        for captures, kept in _KEPT_PARKS:
            with self.subTest(captured=captures, **kept):
                self.setUp()
                head, run = self.captures() if captures else self.settles_then_dies()
                onto = self.pinned_fields(readings.KEY_REWRITE_BASE)[0]
                self._parks_under_a_later_report(head, **kept)

                self._assert_kept(head, onto)
                self._assert_retired(run, captured=captures)
                self.continues()
                self.recovers()
                self.assert_routed(head)

    def test_a_raised_notice_proves_behind_it(self) -> None:
        # The dispatcher's hold strands the attempt under a label the refresh
        # does not drive, and its notice's post raises behind report 3: the
        # run is proved again before the error goes on, and invalidated whole,
        # with nothing parked.
        head, settled = self.settles_then_dies()
        self.issue.labels = [FakeLabel(_UNDRIVEN)]
        replaced: list = []
        with patch.object(self.gh, "comment", partial(_raises_behind, self, head, replaced)):
            self.assertRaises(RuntimeError, guarded.answers_a_held_anchor, self)
        self.issue.labels = [FakeLabel(git_support.REVIEWING)]
        _puts_back(self, replaced)

        self.assertFalse(self.pinned_fields(guarded.AWAITING)[0])
        self.assert_invalidated(settled)

    def test_a_move_under_the_parks_edit_is_read(self) -> None:
        # The dispatcher's hold strands the attempt under a label the refresh
        # does not drive, and report 3 settles right under the strict edit of
        # the park's record, which is refused over it, report 2 put back right
        # behind: what that edit read invalidates the run whole, so the head
        # is routed with nothing current once the label is back.
        head, settled = self.settles_then_dies()
        self.issue.labels = [FakeLabel(_UNDRIVEN)]
        with patch.object(self.gh, "edit_pinned_state", _MovesUnderThePark(self, head)):
            guarded.answers_a_held_anchor(self)
        self.issue.labels = [FakeLabel(git_support.REVIEWING)]

        self.assert_invalidated(settled)
        self.recovers()
        self.assert_routed(head)

    def _parks_under_a_later_report(self, head: str, *, restoring=False, lost=False, respelled=False) -> None:
        """Recover over a refused fetch and reset with report 3 of `head` settled behind the park's notice.

        `restoring` puts the records it moved back right behind the park's
        record, before anything behind it reads the comment again, and they
        are put back behind the tick either way; `lost` lands that record and
        loses its answer; `respelled` respells report 2 instead.
        """
        replaced: list = []
        moves = partial(_settles_a_later_report, self, head, replaced, respelled=respelled)
        races = _RacesPastTheCall(self.gh.comment, 1, moves)
        edit = partial(_answering, PinnedEdit.UNCONFIRMED if lost else PinnedEdit.EDITED, self.gh.edit_pinned_state)
        if restoring:
            edit = guarded.BEFORE_THE_RECORD.moving(edit, partial(_puts_back, self, replaced))
        with (
            patch.object(commands, _GIT, partial(_refuses, getattr(commands, _GIT))),
            patch.object(self.gh, "comment", races),
            patch.object(self.gh, "edit_pinned_state", edit),
        ):
            self.recovers()
        _puts_back(self, replaced)

    def _assert_kept(self, head: str, onto: str) -> None:
        """Parked, the attempt kept on its anchor and its base tip `onto`, and the checkout still on `head`."""
        standing = self.pinned_fields(*guarded.ATTEMPT_FIELDS)
        self.assertEqual(standing, (True, self.anchor, onto))
        self.assertEqual(self._wt_head(), head)

    def _assert_retired(self, run, *, captured: bool) -> None:
        """`run` abandoned whole where it was only `captured`, else invalidated whole; nothing else said or made."""
        if not captured:
            self.assert_invalidated(run)
            return
        self.assert_abandoned(run)
        said = (support.announced(self), readings.relabels(self))
        self.assertEqual(said, ([], ()))
        self.assert_made_once()


if __name__ == "__main__":
    unittest.main()
