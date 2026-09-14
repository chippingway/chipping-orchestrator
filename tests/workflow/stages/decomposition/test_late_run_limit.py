# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A late adjudication an issue has no agent runs left to pay for.

The road here reads the candidate worktree BEFORE it asks whether the run
happened, and for a good reason: a run the shutdown sweep killed can have
changed the candidate on its way out, and a contaminated candidate is a thing
an operator has to be told about. A launch that never started is the case that
reasoning does not cover -- it changed nothing, so a candidate that has moved
moved under something else, and the refusal's own park is the one that has to
stand.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import (
    run_ledger_values as _run_ledger_values,
    run_limit_values as _run_limit_values,
)
from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from tests.workflow.fixtures import KEY_AWAITING_HUMAN, KEY_PARK_REASON
from tests.workflow.stages.decomposition.late_run_support import adjudicate
from tests.workflow.stages.decomposition.late_settlement_support import (
    MOVED_CANDIDATE,
    SPLIT_RUN,
)
from tests.workflow.stages.decomposition.late_test_support import (
    LATE_ISSUE_NUMBER,
    seeded_late_issue,
)

# The allowance this issue records for itself, already spent to the last run.
_ALLOWANCE = 4


class SpentLedgerLateAdjudicationTest(unittest.TestCase):
    """No late generation is adjudicated on a run the issue cannot pay for."""

    def setUp(self) -> None:
        seeded = seeded_late_issue(**{
            _run_ledger_values.AGENT_RUN_ALLOWANCE: _ALLOWANCE,
            _run_ledger_values.AGENT_RUNS_USED: _ALLOWANCE,
        })
        self.github = seeded[0]
        self.issue = seeded[1]

    def test_a_spent_ledger_adjudicates_nothing(self) -> None:
        outcome, spawn = adjudicate(self.github, self.issue, SPLIT_RUN)

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.DEFERRED)
        self._assert_parked_on_the_ledger()

    def test_a_moved_candidate_is_not_its_doing(self) -> None:
        # The candidate moved under something this launch never ran, so a
        # `late_worktree_mutated` park would replace the refusal's own with a
        # reason about a process that did not exist.
        outcome, spawn = adjudicate(
            self.github, self.issue, SPLIT_RUN, worktree=MOVED_CANDIDATE,
        )

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.DEFERRED)
        self._assert_parked_on_the_ledger()

    def _assert_parked_on_the_ledger(self) -> None:
        pinned = self.github.pinned_data(LATE_ISSUE_NUMBER)
        self.assertTrue(pinned.get(KEY_AWAITING_HUMAN))
        self.assertEqual(
            pinned.get(KEY_PARK_REASON), _run_limit_values.PARK_AGENT_RUN_LIMIT,
        )
        self.assertEqual(pinned.get(_run_ledger_values.AGENT_RUNS_USED), _ALLOWANCE)


if __name__ == "__main__":
    unittest.main()
