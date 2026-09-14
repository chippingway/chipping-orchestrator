# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What still refuses a developer or reviewer launch ahead of the ledger.

The lifetime ledger is the backstop under the caps that were already there,
not a replacement for any of them, and the order matters in one direction: a
cap that fired only AFTER the charge would spend a run on work nothing ever
ran. So each case here drives a real handler over an issue whose own cap is
spent and pins the same facts -- no process, no charge standing, and a spend
the tick did not move.

The session budget refuses something narrower. It does not turn the tick away;
it retires the transcript the resume would have replayed, and what reaches the
boundary is one fresh spawn rather than a resume. Its sibling below is the
other half of that accounting: the single retry a poisoned session earns is
not a licence a spawn with no transcript also gets, so a fresh launch that
comes back poisoned is charged once and asks for nothing more.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.config import settings as config
from orchestrator.workflow.engine import (
    retry_values as _retry_values,
    run_ledger_values as _run_ledger_values,
)
from tests.workflow.engine import charged_run_roads as roads, charged_run_test_support as support
from tests.workflow.fixtures import (
    KEY_AWAITING_HUMAN,
    KEY_PARK_REASON,
    _agent,
    _iso_hours_ago,
    _PatchedWorkflowMixin,
)

_REVIEW_CAP = "review_cap"

_CONFLICT_CAP = "conflict_cap"

# A window the cap is measured inside, so what refuses the spawn is the budget
# being spent rather than the clock having moved past it.
_WINDOW_HOURS = 1

_RESUME_BUDGET = 3

_RESUME_SESSION_ID = "resume_session_id"

_MAX_RESUMES = "DEV_SESSION_MAX_RESUMES"


class CappedLaunchTest(unittest.TestCase, _PatchedWorkflowMixin):
    """Every cap that already refused work still refuses it first."""

    def test_a_spent_retry_budget_charges_no_run(self) -> None:
        driven = roads.IMPLEMENTING_FRESH.drive(
            self,
            roads.IMPLEMENTING_FRESH.agent_result,
            retry_count=config.MAX_RETRIES_PER_DAY,
            retry_window_start=_iso_hours_ago(_WINDOW_HOURS),
        )

        self._assert_refused_ahead_of_the_charge(
            driven, _retry_values.PARK_RETRY_CAP,
        )

    def test_a_spent_review_cap_charges_no_run(self) -> None:
        driven = roads.VALIDATING.drive(
            self,
            roads.VALIDATING.agent_result,
            review_round=config.MAX_REVIEW_ROUNDS,
        )

        self._assert_refused_ahead_of_the_charge(driven, _REVIEW_CAP)

    def test_a_spent_conflict_cap_charges_no_run(self) -> None:
        driven = roads.CONFLICT.drive(
            self,
            roads.CONFLICT.agent_result,
            conflict_round=config.MAX_CONFLICT_ROUNDS,
        )

        self._assert_refused_ahead_of_the_charge(driven, _CONFLICT_CAP)

    def test_a_spent_resume_budget_spawns_fresh(self) -> None:
        # The transcript is retired before the boundary is asked, so what the
        # ledger records is one launch -- and it is the fresh spawn, not the
        # resume the budget just refused.
        with patch.object(config, _MAX_RESUMES, _RESUME_BUDGET):
            driven = roads.IMPLEMENTING_RESUME.drive(
                self,
                roads.IMPLEMENTING_RESUME.agent_result,
                dev_resume_count=_RESUME_BUDGET,
            )

        spawn_call = driven.mocks[support.RUN_AGENT].call_args
        self.assertEqual(driven.spawns, 1)
        self.assertIsNone(spawn_call.kwargs.get(_RESUME_SESSION_ID))
        self.assertEqual(driven.spent, support.SPENT_BEFORE + 1)

    def test_a_poisoned_fresh_spawn_buys_no_retry(self) -> None:
        # The retry exists to recover a transcript that cannot be replayed. A
        # launch with none to begin with has nothing to recover, so the
        # poisoned marker earns it no second process and no second charge.
        driven = roads.IMPLEMENTING_RESUME.drive(
            self,
            _agent(
                session_id=None,
                last_message="",
                stderr=support.POISONED_STDERR,
            ),
            dev_session_id=None,
        )

        self.assertEqual(driven.spawns, 1)
        self.assertEqual(driven.spent, support.SPENT_BEFORE + 1)

    def _assert_refused_ahead_of_the_charge(self, driven, park_reason) -> None:
        """No process, no charge, and the cap's own park saying why."""
        driven.mocks[support.RUN_AGENT].assert_not_called()
        pinned = driven.github.pinned_data(driven.number)
        self.assertEqual(
            pinned.get(_run_ledger_values.AGENT_RUNS_USED), support.SPENT_BEFORE,
        )
        self.assertNotIn(_run_ledger_values.AGENT_RUN_RESERVATION, pinned)
        self.assertTrue(pinned.get(KEY_AWAITING_HUMAN))
        self.assertEqual(pinned.get(KEY_PARK_REASON), park_reason)


if __name__ == "__main__":
    unittest.main()
