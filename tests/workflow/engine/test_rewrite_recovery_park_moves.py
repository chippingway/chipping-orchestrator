# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed rewrite's recovery parking behind a reset while another road writes the comment, and dying there.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
rebased head reviewed, its run settled under the anchor, and the finish killed
before its announcement. The next tick's recovery cannot fetch the branch, so
it takes the fail-closed abort: the checkout goes back onto the anchor, and
the park behind that reset releases the attempt and invalidates the settled
run in one write. While the park's notice is posted, another road writes the
comment: it settles and reviews report 3 of the head, or records a newer
transaction for it beside the run.

The park's record lands over the comment as it then stands, never over the
tick's whole reading: report 3 is kept beside the park, and a newer
transaction -- a record the park was decided on -- refuses it, so the next
tick's recovery answers the attempt again and records the park around that
transaction. A process killed before the record lands is answered the same
way, and a poll behind the park changes nothing. The run is invalidated whole
and made once, and nothing is announced, relabelled, pushed, or launched.
"""
from __future__ import annotations

import subprocess
import unittest
from functools import partial
from typing import NamedTuple
from unittest.mock import patch

from orchestrator import config
from orchestrator.git import branch_transport
from orchestrator.github.verification_evidence import VerifiedCommand
from orchestrator.workflow.engine import (
    verification_record_state as _record_state,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
    verification_report_fixture as _report,
)
from tests.workflow.interleaving import _RacesPastTheCall

_AWAITING = "awaiting_human"

_CURRENT_REPORT = "developer_report_current"

_FETCH = branch_transport._authed_fetch


def _unfetched(spec, ref: str, **options) -> subprocess.CompletedProcess:
    """The branch transport's fetch, failing for issue #7's branch alone."""
    if "issue-7" in ref:
        return subprocess.CompletedProcess([], 1, "", "fetch failed")
    return _FETCH(spec, ref, **options)


def _parking(_issue, state, *, over: dict) -> bool:
    """Whether a pinned-comment edit is the park's record, which the comment lacks."""
    return bool(state.get(_AWAITING)) and not over.get(_AWAITING)


_BEFORE_THE_RECORD = handoff.Boundary("noticed, before the park is recorded", "edit_pinned_state", _parking)


def _settles_a_later_report(case: support.CapturedRunCase, head: str) -> None:
    """Settle report 3 of `head` and hand a reviewer it, over the comment as it stands."""
    case.state = case.gh.read_pinned_state(case.issue)
    _report.settles_report(case, 3, "Implemented the change and covered a base that moved twice.", head=head)
    case.gh.write_pinned_state(case.issue, case.state)


def _records_a_newer_run(case: support.CapturedRunCase, _head: str) -> str:
    """Record a newer transaction beside the settled run, carrying its binding, as another road would; its receipt.

    Its transcript is the configured command passing, as the settled run's own reads.
    """
    state = case.gh.read_pinned_state(case.issue)
    binding = readings.pinned_records(case)[1].binding
    command = config.VERIFY_COMMANDS[0]
    passed = (VerifiedCommand(command=command, exit_status=0, output=git_support.CHECKED),)
    newer = _record_state.mint_pending_evidence(state, git_support.ISSUE, binding, passed)
    case.assertTrue(_record_state.record_pending_evidence(state, newer))
    case.gh.write_pinned_state(case.issue, state)
    return newer.receipt


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

# Each write, with the first poll running through or killed before the park's record.
_CASES = tuple((write, boundary) for write in _WRITES for boundary in (None, _BEFORE_THE_RECORD))


class ResetParkMoveTest(support.CapturedRunCase, unittest.TestCase):
    """A reset park's record keeps what another road wrote under its notice, whether or not the process lived."""

    def test_the_park_keeps_what_moved_under_it(self) -> None:
        # Report 3 lands beside the park, or the newer transaction refuses
        # it and the next tick parks around it; a death before the record is
        # answered alike, and every poll behind the park changes nothing.
        for write, boundary in _CASES:
            named = getattr(boundary, "name", "uninterrupted")
            with self.subTest(write=write.name, boundary=named):
                self.setUp()
                self._parks_under(write, boundary)

    def _parks_under(self, write: _Write, boundary: handoff.Boundary | None) -> None:
        """Land a reviewed rebase, settle its run, kill the finish before its announcement, and recover over `write`."""
        head = self.lands_a_reviewed_rebase()
        handoff.dies_at(self.gh, handoff.BEFORE_THE_ANNOUNCEMENT, partial(self.finishes, head))
        settled = readings.pinned_records(self)[1]
        written = self._recovers(head, write, boundary)

        self._assert_parked(settled, written, write.revision)
        self._assert_kept_whole(settled)
        self._assert_nothing_said()

    def _recovers(self, head: str, write: _Write, boundary: handoff.Boundary | None) -> str | None:
        """Poll three times over an unfetched branch, `write` made behind the first park's notice; what it answered.

        The first poll is killed at `boundary`, and records the park only
        where it ran through and `write` refuses nothing.
        """
        written: list = []
        writes = partial(_kept, written, write.writes, self, head)
        races = _RacesPastTheCall(self.gh.comment, 1, writes)
        with patch.object(branch_transport, "_authed_fetch", _unfetched):
            with patch.object(self.gh, "comment", races):
                handoff.dies_at(self.gh, boundary, self.recovers)
            parked = readings.pinned(self).get(_AWAITING) is True
            self.recovers()
            self.recovers()
        self.assertEqual(parked, boundary is None and not write.refuses)
        return written[0]

    def _assert_parked(self, settled, receipt: str | None, revision: int) -> None:
        """Parked, the attempt released and `settled` invalidated; `receipt` pending, report `revision` current."""
        pinned = readings.pinned(self)
        parked = (pinned[_AWAITING], pinned[_CURRENT_REPORT]["revision"])
        self.assertEqual(parked, (True, revision))
        self.assertEqual(readings.attempt(pinned), readings.RETIRED)
        records = readings.pinned_records(self)
        self.assertEqual(getattr(records[0], "receipt", None), receipt)
        retired = (*git_support.invalidated(self), (settled.receipt, readings.INVALIDATED))
        self.assertEqual(records[1:], (None, retired))

    def _assert_kept_whole(self, settled) -> None:
        """`settled` retired into history with its revision and binding kept."""
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (settled.revision, settled.binding))

    def _assert_nothing_said(self) -> None:
        """Nothing announced or relabelled, the run made once, nothing pushed or launched."""
        said = (support.announced(self), readings.relabels(self))
        self.assertEqual(said, ([], ()))
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (1, 0, 0))


if __name__ == "__main__":
    unittest.main()
