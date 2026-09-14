# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The agent run a late adjudication spends, and what its charge may carry.

The coordinator is the one spawning road that is not a dispatched handler, so
the table that holds every other road to the lifetime ledger cannot drive it
and this is where its half of that coverage lives. What it has to show is the
same thing: the adjudication reaches the charging boundary naming the issue it
is spending, and the spend is read back off that issue's own pinned comment.

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

from orchestrator.workflow.engine import (
    run_ledger_models as _run_ledger_models,
    run_ledger_values as _run_ledger_values,
)
from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from tests.support.fakes import FakeLabel
from tests.workflow.stages.decomposition.late_run_support import (
    adjudicate,
    agent_reply,
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
