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
"""
from __future__ import annotations

import unittest

from orchestrator.git.publication.models import BRANCH_INTACT, _SquashOutcome
from orchestrator.workflow.engine import report_settlement_state as _settlement
from orchestrator.workflow.stages.implementing import late_collapse_state as _late_collapse_state
from tests.workflow import published_reports as _published_reports
from tests.workflow.stages.validating import squash_approval_support as _support
from tests.workflow.stages.validating.squash_approval_support import (
    _CollapseWorldMixin,
    _SquashApprovalFixtureMixin,
)
from tests.workflow.stages.validating.test_squash_route import HANDED_ON

REVIEW_ROUND = "review_round"

# The agent runs this issue has been charged, which the reviewer's run adds one to.
AGENT_RUNS = "issue_agent_runs"


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


if __name__ == "__main__":
    unittest.main()
