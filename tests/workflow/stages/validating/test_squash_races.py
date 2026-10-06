# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What another road writes while the approval's squash runs, and what the squash's own writes do to it.

The squash writes the state in hand whole wherever it writes, and its reply
does not say whether it wrote. So each of its writes of the pinned comment is
held to the report, pull-request, verdict, and evidence records in hand and
laid over the comment as read then, and the tail's next reading is measured
from the last of them -- or from the reading before the squash, where it
wrote none.

A round another road spends while the squash runs is therefore kept whether
the squash wrote or not, and a run the squash's own write already carried is
charged once. A later report settled ahead of the squash's first write --
the record of the collapse it is about to make -- refuses that write the way
GitHub refusing it would: nothing is rewritten, the later report and the
round it spent stand, and the approval is not handed on.

Each of those writes then lands as a guarded commit over the comment read
afresh, so a road writing between that reading and the commit is answered the
same way: a later report refuses it, and another road's own bookkeeping is
kept beside the record and through the handoff behind it. A record whose
commit lands with its response lost is taken as refused by the squash, which
rewrites nothing; the next tick's recovery finishes the collapse it claims. A
record refused outright -- its edit unanswered, or the comment left with no
room for it -- leaves what the reading ahead of it took in put back with the
state, so another road's write it read is never taken for one the tick
deleted.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from orchestrator.git.publication.models import BRANCH_INTACT, _SquashOutcome
from orchestrator.workflow.engine import report_settlement_state as _settlement
from orchestrator.workflow.stages.implementing import late_collapse_state as _late_collapse_state
from tests.workflow import published_reports as _published_reports
from tests.workflow.stages.validating import (
    approval_commit_test_support as _one,
    review_write_test_support as _roads,
    squash_approval_support as _support,
)
from tests.workflow.stages.validating.squash_approval_support import (
    _CollapseWorldMixin,
    _LandsWithACollapseRecorded,
    _SquashApprovalFixtureMixin,
)
from tests.workflow.stages.validating.test_squash_route import HANDED_ON

REVIEW_ROUND = "review_round"

# The agent runs this issue has been charged, which the reviewer's run adds one to.
AGENT_RUNS = "issue_agent_runs"

# A note of another road's own, which no write of the squash or its tail owns.
THEIR_NOTE = "another_road_note"

_NOTES = _roads.Writes({THEIR_NOTE: "kept"})

# What the notice a published collapse owes the pull request opens with.
_NOTICE = ":package: squashed"

_RETURNED_VERDICT = "review_returned_verdict"

_APPROVED_SUBJECT = "review_approved_subject"

# The squash's record of its collapse: the guarded commit staging it.
_THE_RECORD = _one.staging(_support.COLLAPSE_KEY)


def _spends_a_round(github, issue) -> None:
    """Another road's write of the next review round, through `github` itself rather than the squash's client."""
    spent = github.read_pinned_state(issue)
    spent.set(REVIEW_ROUND, spent.get(REVIEW_ROUND) + 1)
    github.write_pinned_state(issue, spent)


class _SpendsARoundWhileSquashing:
    """A squash with nothing to rewrite, while another road spends a review round on `github`.

    Where `writes` says, the squash first puts the state in hand down through
    the client its gate carries, as one that records anything does, so the
    round lands behind a write of the squash's own; otherwise it writes
    nothing at all.
    """

    def __init__(self, github, *, writes: bool) -> None:
        self._github = github
        self._writes = writes

    def __call__(self, gate, _branch, _pr_number) -> _SquashOutcome:
        if self._writes:
            gate.gh.write_pinned_state(gate.issue, gate.state)
        _spends_a_round(self._github, gate.issue)
        return _SquashOutcome(success=True, sha=_support.SQUASHED_SHA, count=0)


class _SettlesAReportAheadOfItsRecord:
    """A squash whose record of the collapse it is about to make another road's later report lands ahead of.

    The record goes down through the squash's own owner, the one write that
    has to land before anything is rewritten; where it is refused, the squash
    answers as that owner has it answer, with the approved commits intact.
    """

    def __init__(self, github) -> None:
        self._github = github

    def __call__(self, gate, _branch, _pr_number) -> _SquashOutcome:
        _published_reports.republishes_the_report(self._github, gate.issue, "A later report.")
        _spends_a_round(self._github, gate.issue)
        refusal = _late_collapse_state._records_the_collapse(
            gate, head=_support.COLLAPSED_HEAD, base_sha=_support.COLLAPSED_BASE, count=_support.COLLAPSED_COMMITS,
        )
        if refusal:
            return _SquashOutcome(error=refusal, standing=BRANCH_INTACT)
        return _SquashOutcome(success=True, sha=_support.SQUASHED_SHA, count=_support.COLLAPSED_COMMITS)


class _RecordsItsCollapse:
    """A squash recording the collapse it is about to make through its gate's client, as the real one does.

    `ahead`, where given, is another road's work right ahead of that record,
    answering the context the record is then written in.
    """

    def __init__(self, ahead=None) -> None:
        self._ahead = ahead

    def __call__(self, gate, _branch, _pr_number) -> _SquashOutcome:
        if self._ahead is None:
            return self._records(gate)
        with self._ahead():
            return self._records(gate)

    def _records(self, gate) -> _SquashOutcome:
        refusal = _late_collapse_state._records_the_collapse(
            gate, head=_support.COLLAPSED_HEAD, base_sha=_support.COLLAPSED_BASE, count=_support.COLLAPSED_COMMITS,
        )
        if refusal:
            return _SquashOutcome(error=refusal, standing=BRANCH_INTACT)
        return _SquashOutcome(success=True, sha=_support.SQUASHED_SHA, count=_support.COLLAPSED_COMMITS)


def _settles_a_later_report(case) -> None:
    """Another road settling a later report on `case`'s issue and spending the round its handover bought."""
    _published_reports.republishes_the_report(case.github, case.issue, "A later report.")
    _spends_a_round(case.github, case.issue)


class SquashRaceTest(
    unittest.TestCase,
    _SquashApprovalFixtureMixin,
    _CollapseWorldMixin,
):
    """The squash's own writes, and another road's around them."""

    def test_a_round_spent_during_the_squash_is_kept(self) -> None:
        # The squash may write the state in hand or nothing at all, and its
        # reply says neither: the reading behind it is measured from its last
        # write, or from the reading before it where it made none. Either way
        # the round another road spent while it ran is kept rather than
        # written back over, and the reviewer's run a write of the squash's
        # own already carried is charged once.
        for writes in (False, True):
            with self.subTest(writes=writes):
                github, issue, _pr = self._setup()

                self._run_squash_approval(github, issue, _SpendsARoundWhileSquashing(github, writes=writes))

                written = github.read_pinned_state(issue)
                self.assertEqual(
                    (written.get(REVIEW_ROUND), written.get(AGENT_RUNS), HANDED_ON in github.label_history),
                    (1, 1, True),
                )

    def test_a_report_ahead_of_its_record_refuses_it(self) -> None:
        # Another road settles a later report, spending a round, between the
        # tail's last reading and the squash's first write. That write would
        # put the older report and round back and leave the tail reading them
        # as the records its approval stands on, so it is refused: nothing is
        # recorded or rewritten, the later report and its round stand, and
        # the approval is neither parked nor handed on.
        github, issue, _pr = self._setup()

        self._run_squash_approval(github, issue, _SettlesAReportAheadOfItsRecord(github))

        written = github.read_pinned_state(issue)
        self.assertEqual(
            (
                _settlement.read_current_report(written).report_revision,
                written.get(REVIEW_ROUND),
                _support.COLLAPSE_KEY in written.data,
                bool(written.get(_support.AWAITING_HUMAN)),
                github.label_history,
            ),
            (2, 1, False, False, []),
        )

    def test_a_write_right_ahead_of_its_record_commit(self) -> None:
        # Another road writes after the squash's write read the comment and
        # before its commit. A later report refuses that commit as the read
        # would have: nothing is recorded or rewritten, the report and its
        # round stand, nothing parks, and the label stays. A note of the other
        # road's own is kept beside the record, and through every write of
        # the tail behind it to the handoff.
        for name, road, kept in (
            ("a later report", _settles_a_later_report, (2, 1, False, None, [])),
            ("its own note", _NOTES, (1, 0, False, "kept", [HANDED_ON])),
        ):
            with self.subTest(name):
                self.assertEqual(self._ahead_of_the_record(road), kept)

    def test_a_lost_record_is_finished_once(self) -> None:
        # The squash's record of the collapse it is about to make lands and its
        # response is lost. The squash takes the write as refused and rewrites
        # nothing, so nothing is published, announced, parked, or relabeled
        # behind it. The record landed with the approval the tail had staged
        # beside it, which the tail's next reading finds where it last read
        # none: what it posted is recorded and the verdict that approval
        # finishes is retired, the approval itself standing on the comment.
        # The next tick's recovery owns the collapse that record claims and
        # finishes it under that approval -- one squash, one notice, the label
        # moved -- with no second reviewer.
        github, issue, _pr = self._setup()
        with _one.LosesOneResponse(SimpleNamespace(github=github), _THE_RECORD).patched():
            self._run_squash_approval(github, issue, _RecordsItsCollapse())
        written = github.read_pinned_state(issue).data
        self.assertEqual(
            (
                (_support.COLLAPSE_KEY in written, written.get(_APPROVED_SUBJECT) is not None),
                (written.get(_RETURNED_VERDICT), bool(written.get(_support.AWAITING_HUMAN))),
                (github.label_history, self._notices(github)),
            ),
            ((True, True), (None, False), ([], 0)),
        )

        mocks = self._run_squash_approval(github, issue, _LandsWithACollapseRecorded())

        written = github.read_pinned_state(issue).data
        self.assertEqual(
            (
                (mocks[_support.RUN_AGENT].call_count, mocks[_support.SQUASH_SEAM].call_count),
                (github.label_history, self._notices(github)),
                (_support.COLLAPSE_KEY in written, bool(written.get(_support.AWAITING_HUMAN))),
            ),
            ((0, 1), ([HANDED_ON], 1), (False, False)),
        )

    def test_a_refused_record_keeps_their_note(self) -> None:
        # Another road leaves a note of its own while the squash runs, and
        # the record of the collapse it is about to make is refused: its edit
        # unanswered, or the comment that note filled left with no room for
        # it. Nothing is rewritten, and what the reading ahead of the record
        # took in is put back with the state, so the note is never read as
        # one the tick deleted: it stands beside the park the failure takes
        # -- or, on a comment with no room even for that park, beside nothing
        # written at all.
        for unreadable, parked in ((True, _support.PARK_SQUASH_FAILED), (False, None)):
            with self.subTest(unreadable=unreadable):
                github, issue = self._setup()[:2]

                self._run_squash_approval(github, issue, _RecordsItsCollapse(
                    _one.refusing_the_record(github, issue, unreadable=unreadable),
                ))

                pinned = github.pinned_data(_support.APPROVAL_ISSUE)
                self.assertEqual(
                    (_one.NOTE in pinned, pinned.get(_support.PARK_REASON), _support.COLLAPSE_KEY in pinned),
                    (True, parked, False),
                )

    def _notices(self, github) -> int:
        """How many collapse notices the pull request carries."""
        return sum(_NOTICE in body for _, body in github.posted_pr_comments)

    def _ahead_of_the_record(self, road) -> tuple:
        """One approval whose squash records its collapse, `road` right ahead of that commit; what it left.

        The report revision and round current, whether a collapse or a park
        stands, another road's note, and every relabel.
        """
        github, issue, _pr = self._setup()
        ahead = _roads.AnotherRoadAhead(SimpleNamespace(github=github, issue=issue), _THE_RECORD, road)
        with ahead.patched():
            self._run_squash_approval(github, issue, _RecordsItsCollapse())
        written = github.read_pinned_state(issue)
        return (
            _settlement.read_current_report(written).report_revision,
            written.get(REVIEW_ROUND),
            _support.COLLAPSE_KEY in written.data or bool(written.get(_support.AWAITING_HUMAN)),
            written.get(THEIR_NOTE),
            github.label_history,
        )


if __name__ == "__main__":
    unittest.main()
