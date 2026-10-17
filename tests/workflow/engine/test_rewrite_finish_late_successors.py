# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A successor settled behind a dormant finish's readings, proved on the issue and records each of them pairs.

Direct finishes held to the dormant settled-evidence policy
(`settled_route_support`): issue #7's reviewed rebase, its run settled under
the anchor and its finish killed before its announcement.

- The readiness proof of the run reads the issue and the comment twice, and
  another road settles a newer run of the head right as the issue is read the
  second time. Bound to the run's own records, beside that issue reading a
  requirement the issue never kept, the newer run is disproved by that very
  reading and retired whole, so no later finish routes it; bound to a
  requirement the issue really gained there, it is proved on that reading and
  kept current.
- The relabel lands with a requirement added to the issue for a moment, so
  the proof behind it invalidates the run, and the fresh reading behind that
  invalidation puts the issue back and takes in a newer run bound to report
  3, report 2 put back right behind it. The retirement is sent over that newer
  run beside report 2 and its answer lost, report 3 put back right behind it:
  the record it sent read the newer run off its own binding, so it is retired
  whole however soon report 3 is back, and the next finish routes the head
  once with nothing current.
- The next finish proves the run over a requirement added to the issue for
  a moment, so the proof invalidates it and the fresh reading behind that
  takes in the same newer run, report 2 put back right behind it. A write is
  then prepared over that newer run beside report 2, report 3 put back right
  behind the preparation -- the retirement, the finish before having died at
  the relabel's record, or the checkpoint, that one having died before its
  announcement: the record it measured read the newer run off its own
  binding, so it is retired whole before anything reads report 3 back, and
  the head is routed once with nothing current.
"""
from __future__ import annotations

import copy
import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator.github.pinned_state import PinnedEdit
from orchestrator.workflow.engine import (
    rewrite_finish_readiness as _readiness,
    rewrite_finish_rechecks as _rechecks,
    rewrite_finish_writes as _finish_writes,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad
from tests.workflow.engine import (
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    settled_finish_support as settled_support,
    settled_route_support as route,
    verification_report_fixture as _report,
)

# The report and review records report 3's settlement moves, as the pinned comment spells them.
_REPORT_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")

# A requirement the issue reads with for a moment, or gains for good.
_ADDED = "\nAlso cover a base that moved twice."

# What report 3 says.
_REPORT_THREE = "Covered a base that moved twice as well."

# Where the earlier finish dies, and the write whose preparation the next one reads the newer run off its binding with.
_PREPARED = (
    (handoff.BEFORE_THE_RELABEL_RECORD, _finish_writes.FINISH),
    (handoff.BEFORE_THE_ANNOUNCEMENT, _finish_writes.CHECKPOINT),
)


def _writes(case, records: dict) -> dict:
    """Write `records` onto `case`'s comment as it stands; what they replaced."""
    state = case.gh.read_pinned_state(case.issue)
    replaced = {key: state.get(key) for key in records}
    for key, recorded in records.items():
        state.set(key, recorded)
    case.gh.write_pinned_state(case.issue, state)
    return replaced


def _beside_report_three(case, run, head: str):
    """Settle report 3 of `head` over the issue as it reads now; `run`'s binding moved onto it and its requirements."""
    case.state = case.gh.read_pinned_state(case.issue)
    subject = _report.settles_report(case, 3, _REPORT_THREE, head=head)
    case.gh.write_pinned_state(case.issue, case.state)
    publication = replace(run.binding.target.publication, requirements_revision=subject.requirements_revision)
    target = replace(run.binding.target, publication=publication, subject=subject.recorded())
    return replace(run.binding, target=target)


class _SettlesAtTheSecondIssue:
    """The client's issue reads, each a snapshot, the second beside a newer run of `head` another road settles then.

    Bound to `run`'s own records, the issue that reading answers carries a
    requirement the issue itself never keeps; or, `gains`, the issue gains it
    for good and report 3 is settled over it, the newer run bound to both.
    """

    def __init__(self, case, run, head: str, *, gains: bool) -> None:
        self._case = case
        self._run = run
        self._head = head
        self._gains = gains
        self._live = case.gh.get_issue
        self._reads = 0
        self.successor = None

    def __call__(self, number: int):
        """Read the issue as a snapshot, the second time behind the newer run settled, answered as above."""
        self._reads += 1
        if self._reads == 2:
            self._settles()
        issue = copy.copy(self._live(number))
        if self._reads == 2 and not self._gains:
            issue.body += _ADDED
        return issue

    def _settles(self) -> None:
        """Settle the newer run -- over report 3 and the requirement the issue gains, where it `gains` one."""
        binding = self._run.binding
        if self._gains:
            self._case.issue.body += _ADDED
            binding = _beside_report_three(self._case, self._run, self._head)
        self.successor = settled_support.records_a_newer_run(self._case, settles=True, binding=binding)


class _LosesTheRetirement:
    """A relabel adding a requirement for a moment, a newer run taken in behind it, and the retirement's answer lost.

    The relabel lands and the issue gains a requirement for a moment
    (`relabels`), so the proof behind it invalidates the run; the fresh reading
    behind that invalidation puts the issue back and takes in a newer run bound
    to report 3, report 2 put back right behind it (`reads`); and the
    retirement is sent over that newer run beside report 2, report 3 put back
    right behind it and its answer lost (`edits`).
    """

    def __init__(self, case, run, head: str) -> None:
        self._case = case
        self._run = run
        self._head = head
        self._label = case.gh.set_workflow_label
        self._read = _rechecks.read_afresh
        self._edit = case.gh.edit_pinned_state
        self._later: dict = {}
        self.successor = None
        self.lost = False

    def relabels(self, *labelled, **correlation) -> None:
        """Relabel the issue, a requirement added to it right behind."""
        self._label(*labelled, **correlation)
        self._case.issue.body += _ADDED

    def reads(self, finish):
        """Read the comment afresh, the first time behind the relabel over the newer run, report 2 put back behind."""
        case = self._case
        if not case.issue.body.endswith(_ADDED) or self.successor is not None:
            return self._read(finish)
        case.issue.body = case.issue.body.removesuffix(_ADDED)
        earlier = {key: readings.pinned(case).get(key) for key in _REPORT_RECORDS}
        binding = _beside_report_three(case, self._run, self._head)
        self.successor = settled_support.records_a_newer_run(case, settles=True, binding=binding)
        durable = self._read(finish)
        self._later = _writes(case, earlier)
        return durable

    def edits(self, issue, state, *, over: dict, **options):
        """Answer the edit, the retirement the first time landing with report 3 put back behind it, its answer lost."""
        retires = state.get(readings.KEY_PENDING_PUSH) is None
        retires = retires and over.get(readings.KEY_PENDING_PUSH) is not None
        answered = self._edit(issue, state, over=over, **options)
        if not retires or self.lost:
            return answered
        self.lost = True
        _writes(self._case, self._later)
        return PinnedEdit.UNCONFIRMED


class _RestoresBehindThePreparation(_LosesTheRetirement):
    """The newer run `_LosesTheRetirement` takes in, report 3 put back right behind `behind`'s preparation instead.

    The requirement is on the issue before the finish proves the run, so that
    proof invalidates it and the newer run is taken in (`reads`) ahead of the
    finish's writes, the first `behind` of them then prepared over it beside
    report 2 (`prepares`).
    """

    def __init__(self, case, run, head: str, behind) -> None:
        super().__init__(case, run, head)
        self._prepare = _finish_writes.prepares
        self._behind = behind
        self.restored = False

    def prepares(self, finish, staged, write, *observed, **reserves):
        """Prepare `staged` as `write`, report 3 put back behind the first `behind` prepared over the newer run."""
        prepared = self._prepare(finish, staged, write, *observed, **reserves)
        if write is self._behind and self.successor is not None and not self.restored:
            self.restored = True
            _writes(self._case, self._later)
        return prepared


def _proves(case, reads: _SettlesAtTheSecondIssue, run, finish):
    """`run` proved ready over `finish` (`rewrite_finish_readiness.stands_ready`), the issue read through `reads`."""
    with patch.object(case.gh, "get_issue", reads):
        return _readiness.stands_ready(finish, run)


class LateSuccessorTest(route.SettledRouteCase, unittest.TestCase):
    """A successor settled behind a dormant finish's readings answers for the issue and records they read with it."""

    def test_each_reading_pairs_its_issue(self) -> None:
        # The newer run settled at the proof's second issue reading is asked
        # beside that very issue: disproved by a requirement it reads, it is
        # retired whole and no later finish routes it; bound to the
        # requirement that issue gained, it is kept current.
        for gains in (False, True):
            with self.subTest(gains=gains):
                self.setUp()
                head, run = self.dies_unannounced()
                reads = _SettlesAtTheSecondIssue(self, run, head, gains=gains)
                self.asks_dormant(partial(_proves, self, reads, run), head)

                current = readings.pinned_records(self)[1]
                if gains:
                    self.assertEqual(getattr(current, "receipt", None), reads.successor.receipt)
                    continue
                self._assert_retired(reads.successor)
                self.finalizes(head)
                self._assert_retired(reads.successor)

    def test_a_lost_retirement_keeps_its_read_move(self) -> None:
        # The retirement's answer is lost after it was sent over the newer
        # run beside report 2, and report 3 is put back right behind it: the
        # record it sent read the newer run off its own binding, so it is
        # retired whole, and the next finish routes the head once with
        # nothing current.
        head, run = self.dies_unannounced()
        races = _LosesTheRetirement(self, run, head)
        with (
            patch.object(self.gh, "set_workflow_label", races.relabels),
            patch.object(_rechecks, "read_afresh", races.reads),
            patch.object(self.gh, "edit_pinned_state", races.edits),
        ):
            self.assertEqual(self.finalizes(head), FinishOutcome.UNCONFIRMED)

        self.assertTrue(races.lost)
        self._assert_retired(races.successor)
        self.finalizes(head)
        self._assert_retired(races.successor)
        self.assert_routed_once(head)

    def test_a_prepared_write_keeps_its_read_move(self) -> None:
        # A write is prepared over the newer run beside report 2, and report 3
        # is put back right behind that preparation, before anything behind it
        # reads the comment -- the retirement, ahead of the relabel's recheck,
        # or the checkpoint, ahead of the event's record: the record it
        # measured read the newer run off its own binding, so it is retired
        # whole, and the head is routed once with nothing current.
        for death, behind in _PREPARED:
            with self.subTest(behind=death.name):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                handoff.dies_at(self.gh, death, partial(self.finalizes, head, FinishRoad.PUBLICATION))
                races = _RestoresBehindThePreparation(self, readings.pinned_records(self)[1], head, behind)
                self.issue.body += _ADDED
                with (
                    patch.object(_rechecks, "read_afresh", races.reads),
                    patch.object(_finish_writes, "prepares", races.prepares),
                ):
                    self.finalizes(head)

                self.assertTrue(races.restored)
                self._assert_retired(races.successor)
                self.finalizes(head)
                self._assert_retired(races.successor)
                self.assert_routed_once(head)

    def _assert_retired(self, successor) -> None:
        """Nothing current, `successor` the last evidence invalidated into history."""
        current, retired = readings.pinned_records(self)[1:]
        invalidated = (successor.receipt, readings.INVALIDATED)
        self.assertEqual((current, retired[-1]), (None, invalidated))


if __name__ == "__main__":
    unittest.main()
