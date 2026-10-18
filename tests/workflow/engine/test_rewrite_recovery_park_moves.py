# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The guarded recovery park behind a reset, landed while another road writes the comment, or dying there.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
rebased head reviewed, its run settled under the anchor, and the finish killed
before its announcement. The next tick cannot fetch the branch, or count the checkout's lag against base, so it
takes the fail-closed abort with the workflow's guarded operations (`guarded_recovery_support`): the reset is
recorded first by blanking the base tip, and the park behind that
reset releases the attempt and invalidates the settled run in one write. While
the park's notice is posted, another road writes the comment: it settles and
reviews report 3 of the head, or records a newer transaction for it beside the
run.

The park's record lands over the comment as it then stands, never over the
tick's whole reading -- a run the finish only captured is abandoned in it
the same way: report 3 is kept beside the park, and a newer
transaction -- a record the park was decided on -- refuses it, so the next
tick's recovery answers the attempt again and records the park around that
transaction. A process killed before the record lands is answered the same
way, and so is a record GitHub refused; one that landed with its answer lost
is found parked, and a poll behind the park changes nothing. The park's
notice is said and its event filed once across all of it: a park made again
takes in the notice the conversation already carries. The run is invalidated
whole and made once, and nothing is announced, relabelled, pushed, or
launched.
"""
from __future__ import annotations

import unittest
from functools import partial
from itertools import product
from typing import NamedTuple
from unittest.mock import patch

from orchestrator.git import branch_transport
from orchestrator.workflow.engine import base_refresh
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    settled_finish_support as settled,
    verification_report_fixture as _report,
)
from tests.workflow.interleaving import _RacesPastTheCall

_CURRENT_REPORT = "developer_report_current"

_FETCHES = "_authed_fetch"


def _settles_a_later_report(case, head: str) -> None:
    """Settle report 3 of `head` and hand a reviewer it, over the comment as it stands."""
    case.state = case.gh.read_pinned_state(case.issue)
    _report.settles_report(case, 3, "Implemented the change and covered a base that moved twice.", head=head)
    case.gh.write_pinned_state(case.issue, case.state)


def _records_a_newer_run(case, _head: str) -> str:
    """Record a newer transaction beside the settled run, as another road would; its receipt."""
    return settled.records_a_newer_run(case).receipt


def _kept(answers: list, writes, *args) -> None:
    """Make another road's write with `args`, keeping what it answered in `answers`."""
    answers.append(writes(*args))


class _Write(NamedTuple):
    """What another road writes while the park's notice is posted, the report current behind it, and its refusal.

    `refuses` is a write moving a record the park was decided on, which
    refuses the park's record for the next tick to make.
    """

    name: str
    writes: object
    revision: int
    refuses: bool


_WRITES = (
    _Write("a later report settled and reviewed", _settles_a_later_report, 3, refuses=False),
    _Write("a newer transaction recorded beside the run", _records_a_newer_run, 2, refuses=True),
)

class _Abort(NamedTuple):
    """What sends every poll into the git owner's abort: the step that fails, on its owner, and its answer."""

    name: str
    owner: object
    step: str
    answered: object


# The fetch of the pull request's branch, which the recovery answers with the abort, and the count of the checkout's
# lag against base, which the refresh answers with it ahead of any recovery road.
_ABORTS = (
    _Abort("the branch's fetch failed", branch_transport, _FETCHES, guarded.unfetched),
    _Abort("the base lag was not counted", base_refresh, "_worktree_behind_base", lambda *_args: None),
)


class _Case(NamedTuple):
    """An abort and a write, with the first poll running through or killed at `boundary` before the park's record."""

    abort: _Abort
    write: _Write
    boundary: handoff.Boundary | None

    def named(self) -> dict:
        """The case as a subtest names it."""
        boundary = getattr(self.boundary, "name", None)
        return {"aborted": self.abort.name, "write": self.write.name, "boundary": boundary}


_BOUNDARIES = (None, guarded.BEFORE_THE_RECORD)

# The event every park files.
_PARKED = "park_awaiting_human"

_CASES = tuple(map(_Case._make, product(_ABORTS, _WRITES, _BOUNDARIES)))


class ResetParkMoveTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A reset park's record keeps what another road wrote under its notice, whether or not the process lived."""

    def test_the_park_keeps_what_moved_under_it(self) -> None:
        # Whichever road takes the abort, its reset is recorded ahead of it.
        # Report 3 lands beside the park, or the newer transaction refuses
        # it and the next tick parks around it; a death before the record is
        # answered alike, and every poll behind the park changes nothing.
        for case in _CASES:
            with self.subTest(**case.named()):
                self.setUp()
                head, settled = self.settles_then_dies()
                written = self._recovers(head, case)

                self._assert_parked(settled, written, case.write.revision)

    def test_an_unconfirmed_park_is_answered_again(self) -> None:
        # The park's record is refused, or lands with its answer lost: the
        # tick records nothing over it, and the next one finds the park
        # already made or answers the attempt again and parks it, the run
        # invalidated whole either way.
        for failing in ("refused", "lost"):
            with self.subTest(record=failing):
                self.setUp()
                settled = self.settles_then_dies()[1]
                parked = self._parks_unconfirmed(failing)

                self.assertEqual(parked, failing == "lost")
                self._assert_parked(settled, None, 2)

    def test_a_captured_run_goes_with_the_release(self) -> None:
        # A run the finish captured and never settled is abandoned whole in
        # the very write that releases the attempt behind the reset.
        captured = self.captures()[1]
        with patch.object(branch_transport, _FETCHES, guarded.unfetched):
            self.recovers()

        self.assert_released()
        self.assert_abandoned(captured)
        self.assertEqual((self.pushes.call_count, self.developer.call_count), (0, 0))

    def _recovers(self, head: str, case: _Case) -> str | None:
        """Poll three times into `case`'s abort, its write made behind the first park's notice; what that answered.

        The first poll is killed at `case`'s boundary, and records the park only where it ran through and the write
        refuses nothing; whatever it came to, the reset was recorded ahead of it, the attempt's base tip blank.
        """
        written: list = []
        writes = partial(_kept, written, case.write.writes, self, head)
        races = _RacesPastTheCall(self.gh.comment, 1, writes)
        with patch.object(case.abort.owner, case.abort.step, case.abort.answered):
            with patch.object(self.gh, "comment", races):
                handoff.dies_at(self.gh, case.boundary, self.recovers)
            parked = readings.pinned(self).get(guarded.AWAITING) is True
            self.assertIsNone(self.pinned_fields(readings.KEY_REWRITE_BASE)[0])
            self.recovers()
            self.recovers()
        self.assertEqual(parked, case.boundary is None and not case.write.refuses)
        return written[0]

    def _parks_unconfirmed(self, failing: str) -> bool:
        """Poll three times over an unfetched branch, the first park's record `failing`; whether that one parked."""
        fails = getattr(self.gh.pinned_failures, failing)
        races = _RacesPastTheCall(self.gh.comment, 1, partial(fails.add, git_support.ISSUE))
        with patch.object(branch_transport, _FETCHES, guarded.unfetched):
            with patch.object(self.gh, "comment", races):
                self.recovers()
            fails.discard(git_support.ISSUE)
            parked = readings.pinned(self).get(guarded.AWAITING) is True
            self.recovers()
            self.recovers()
        return parked

    def _assert_parked(self, settled, receipt: str | None, revision: int) -> None:
        """Parked and released, report `revision` current, `settled` invalidated whole beside `receipt` pending.

        Its notice said and its `park_awaiting_human` event filed once, however
        many polls parked it: a park made again over a record that never
        landed takes in the notice the conversation carries, and files its
        event only where the stream lacks it.
        """
        self.assert_released()
        self.assertEqual(readings.pinned(self)[_CURRENT_REPORT]["revision"], revision)
        self.assert_invalidated(settled, receipt)
        noticed = [body for number, body in self.gh.posted_comments if number == git_support.ISSUE]
        filed = [event for event in self.gh.recorded_events if event["event"] == _PARKED]
        self.assertEqual((len(noticed), len(filed)), (1, 1))


if __name__ == "__main__":
    unittest.main()
