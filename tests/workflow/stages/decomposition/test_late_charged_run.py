# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The agent run a late adjudication spends, and what its charge may carry.

The coordinator is the one spawning road that is not a dispatched handler, so
the table that holds every other road to the lifetime ledger cannot drive it
and this is where its half of that coverage lives. What it has to show is the
same thing: the adjudication reaches the charging boundary naming the issue it
is spending, and the spend is read back off that issue's own pinned comment. A
record naming no branch a verdict could settle on never reaches that boundary:
it is refused before anything is charged, spawned, or written.

The second case is what makes this road different from the rest. Everything
between the retry gate and the spawn is one transaction of the coordinator's
own -- the slot it charged is held in memory while the write that records the
attempt goes out without it, so a run the tick then declines costs the daily
budget nothing. The agent-run charge lands inside that window, and it writes
to the issue. Those two facts have to coexist: the run is durably paid for and
the slot the coordinator was holding out is still held out.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from orchestrator.git.worktrees import naming as _naming
from orchestrator.workflow.engine import (
    run_ledger_models as _run_ledger_models,
    run_ledger_values as _run_ledger_values,
)
from orchestrator.workflow.stages.decomposition import late_coordinator as _coordinator
from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from tests.support.fakes import FakeLabel
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.stages.decomposition.late_run_support import (
    adjudicate,
    agent_reply,
    late_run_context,
)
from tests.workflow.stages.decomposition.late_test_support import (
    KEYS,
    LATE_ISSUE_NUMBER,
    SINGLE_REPLY,
    seeded_late_issue,
)

PAUSED_LABEL = "paused"

# An allowance with room left under it, and a spend the issue arrived with, so
# a charge that started the count over rather than adding to it is visible.
_ALLOWANCE = 8

_SPENT_BEFORE = 2

_STARTED = _run_ledger_models.RunPhase.STARTED

# Records naming no branch a late verdict could be settled on: a pull request
# with no branch beside it, and the flat pre-namespacing name.
_REFUSED_RECORDS = (
    ("a pull request with no branch", {"pr_number": 77, "branch": None}),
    ("the flat branch", {"branch": f"orchestrator/issue-{LATE_ISSUE_NUMBER}"}),
)


class _PausedDuringRun:
    """An operator applying `paused` while the adjudicator is still running."""

    def __init__(self, issue, agent_result) -> None:
        self._issue = issue
        self._agent_result = agent_result

    def __call__(self, *_args, **_kwargs):
        self._issue.labels.append(FakeLabel(PAUSED_LABEL))
        return self._agent_result


class ChargedLateAdjudicationTest(unittest.TestCase):
    """No late generation is adjudicated on a run nobody was charged for."""

    def setUp(self) -> None:
        seeded = seeded_late_issue(**{
            _run_ledger_values.AGENT_RUN_ALLOWANCE: _ALLOWANCE,
            _run_ledger_values.AGENT_RUNS_USED: _SPENT_BEFORE,
        })
        self.github = seeded[0]
        self.issue = seeded[1]

    def test_an_adjudication_charges_its_issue(self) -> None:
        outcome, spawn = adjudicate(
            self.github, self.issue, agent_reply(SINGLE_REPLY),
        )

        spawn.assert_called_once()
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self._assert_charged()

    def test_a_paused_run_keeps_the_slot_held_out(self) -> None:
        # The charge is durable and the coordinator's own transaction is
        # intact: a merge that carried the caller's whole object back would
        # publish the retry slot this run is holding, and a run the pause
        # declines would have spent a day's budget on nothing.
        paused = _PausedDuringRun(self.issue, agent_reply(SINGLE_REPLY))

        outcome, spawn = adjudicate(self.github, self.issue, paused)

        spawn.assert_called_once()
        self.assertEqual(outcome.disposition, _LateDisposition.DEFERRED)
        self._assert_charged()
        self.assertNotIn(KEYS.retry_count, self._pinned())
        self.assertNotIn(KEYS.verdict, self._pinned())

    def test_a_refused_branch_charges_nothing(self) -> None:
        # Every verdict settles on the branch -- an acceptance pushes to it, a
        # split supersedes the pull request on it -- so a record naming none
        # live work may use is refused at the admission gate, before the pull
        # request is held or the retry slot, the run ledger, or the spawn is
        # touched. No pull request is seeded: the refusal reads none.
        for described, record in _REFUSED_RECORDS:
            github, issue = seeded_late_issue(**record)
            spawn = MagicMock()
            with self.subTest(record=described), late_run_context(spawn):
                self.assertRaises(
                    _naming.BranchRefused,
                    _coordinator._adjudicate_late_generation,
                    github, _TEST_SPEC, issue, github.read_pinned_state(issue),
                )
                spawn.assert_not_called()
            # The record as an untouched seed of the same issue reads.
            self.assertEqual(
                github.pinned_data(LATE_ISSUE_NUMBER),
                seeded_late_issue(**record)[0].pinned_data(LATE_ISSUE_NUMBER),
                described,
            )
            self.assertEqual(github.label_history, [], described)

    def _assert_charged(self) -> None:
        """The issue durably paid for the process this adjudication ran."""
        pinned = self._pinned()
        self.assertEqual(
            pinned.get(_run_ledger_values.AGENT_RUNS_USED), _SPENT_BEFORE + 1,
        )
        self.assertEqual(
            pinned.get(_run_ledger_values.AGENT_RUN_RESERVATION), _STARTED,
        )

    def _pinned(self) -> dict:
        return self.github.pinned_data(LATE_ISSUE_NUMBER)


if __name__ == "__main__":
    unittest.main()
