# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Every stage road that spawns an agent stops at a spent lifetime ledger.

The charge is taken at one boundary, but what makes it worth anything is that
each road actually goes through that boundary with the issue it is spending.
So these cases drive the real handlers rather than the boundary: a stage wired
to spawn without naming its budget is one that would run an agent here, and no
assertion about the circuit alone would notice.

What is asserted is the same on every road: no process is invoked, the issue
is durably parked on `agent_run_limit` with the sentence that explains it, and
the spend is exactly what the ledger already carried -- a refusal charges
nothing, because nothing ran.

Every road is driven twice, over a clean checkout and over one that is not.
The second world is the one that matters: several roads read the worktree
BEFORE they ask whether the run happened, on purpose -- what a killed run left
on disk is an operator's to see -- and a launch that never started would
otherwise be blamed for whatever an earlier one left there, replacing the park
the refusal had just recorded with a reason about a process that never existed.

The late adjudicator is the one spawning road not driven from here: it is not
a dispatched handler and runs inside a harness of its own, so its case lives
beside it in `tests/workflow/stages/decomposition/test_late_run_limit.py`.
"""
from __future__ import annotations

import unittest
from functools import partial

from orchestrator.workflow.engine import (
    run_ledger_values as _run_ledger_values,
    run_limit_values as _run_limit_values,
)
from tests.support.fakes import FakeGitHubClient
from tests.workflow.engine import spent_ledger_test_support as support
from tests.workflow.fixtures import (
    _TEST_SPEC,
    KEY_AWAITING_HUMAN,
    KEY_PARK_REASON,
    _agent,
    _PatchedWorkflowMixin,
)


class SpentLedgerSpawnTest(unittest.TestCase, _PatchedWorkflowMixin):
    """No road spends a run the issue no longer has."""

    def test_no_road_reaches_a_process(self) -> None:
        for road in support.ROADS:
            with self.subTest(role=road.role):
                self._assert_refused(road)

    def test_no_road_blames_a_refusal_for_the_tree(self) -> None:
        # The same refusal, over a checkout carrying what an earlier run left.
        # A road that read the tree before asking whether this run happened
        # would park on that reading and overwrite the park the refusal took.
        for road in support.ROADS:
            with self.subTest(role=road.role):
                self._assert_refused(road, **road.unclean)

    def _assert_refused(self, road: support.SpawningRoad, **world) -> None:
        gh, issue = support.spent_issue(road)

        mocks = self._run(
            partial(road.run_stage, gh, _TEST_SPEC, issue),
            run_agent=_agent(last_message="never asked"),
            **world,
        )

        mocks[support.RUN_AGENT].assert_not_called()
        self._assert_parked_on_the_ledger(gh, road)

    def _assert_parked_on_the_ledger(
        self, gh: FakeGitHubClient, road: support.SpawningRoad,
    ) -> None:
        """The park, its sentence, and a spend the refusal did not move."""
        parked = gh.pinned_data(road.number)
        self.assertTrue(parked.get(KEY_AWAITING_HUMAN))
        self.assertEqual(
            parked.get(KEY_PARK_REASON), _run_limit_values.PARK_AGENT_RUN_LIMIT,
        )
        self.assertEqual(
            parked.get(_run_ledger_values.AGENT_RUNS_USED), support.ALLOWANCE,
        )
        self.assertNotIn(_run_ledger_values.AGENT_RUN_RESERVATION, parked)
        self.assertTrue(any(
            f"{support.ALLOWANCE}/{support.ALLOWANCE} runs" in body
            for _, body in gh.posted_comments
        ))


if __name__ == "__main__":
    unittest.main()
