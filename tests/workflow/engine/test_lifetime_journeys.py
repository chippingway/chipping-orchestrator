# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How many agent processes one issue can start before something stops it.

The owners under the lifetime ledger each answer for their own step, and none
of them answers this: the number an operator sets is a number of PROCESSES,
and what turns it into one is every stage the issue walks, every tick it
takes, and the dispatcher that holds it once the runs are gone. So each case
here walks a real issue through a real loop under a small allowance and counts
what the runner was actually asked to start.

The count is read as the sum of what each tick spawned rather than off one
long-lived mock, because that is the reading a restarted process would take:
nothing carries the total between ticks but the issue's own pinned comment,
and each tick here builds its own patch set over it.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import run_grant_request as _run_grant_request, run_ledger as _run_ledger
from tests.support.fakes import FakeGitHubClient
from tests.workflow.engine import (
    lifetime_comments as _lifetime_comments,
    lifetime_journeys as journeys,
    lifetime_models as _lifetime_models,
    lifetime_test_support as support,
)
from tests.workflow.fixtures import LABEL_VALIDATING, _PatchedWorkflowMixin

# What a human buys the issue when the walk has stopped it, and how many ticks
# it takes to prove that is all they bought.
_GRANTED_RUNS = 2

_ADD_RUNS = f"/orchestrator add-agent-runs {_GRANTED_RUNS}"

# The deployment-wide ceiling, as the setting an operator writes it in.
_RUNS_PER_ISSUE = "MAX_AGENT_RUNS_PER_ISSUE"

# The counter a rebase and a recovered conflict both put back to nothing.
_REVIEW_ROUND = "review_round"


class LifetimeJourneyTest(unittest.TestCase, _PatchedWorkflowMixin):
    """No loop an issue can sit in spends more runs than it was allowed."""

    def test_every_journey_stops_at_the_total(self) -> None:
        for journey in journeys.JOURNEYS:
            with self.subTest(journey=journey.name):
                walked = self._walked(journey)

                self.assertEqual(walked.total, _lifetime_models.ALLOWANCE)
                self.assertEqual(walked.spent, _lifetime_models.ALLOWANCE)

    def test_every_journey_parks_and_says_so_once(self) -> None:
        # The park is durable and the sentence under it is said once per park
        # rather than once per tick, so the ticks past the ceiling add nothing
        # to the thread -- which is what a human waiting on one comment sees.
        for journey in journeys.JOURNEYS:
            with self.subTest(journey=journey.name):
                walked = self._walked(journey)

                self.assertTrue(walked.parked)
                self.assertEqual(len(walked.notices), 1)
                self.assertIn(
                    f"({_lifetime_models.ALLOWANCE}/{_lifetime_models.ALLOWANCE} runs)",
                    walked.notices[0],
                )

    def test_the_setting_bounds_an_issue_of_its_own(self) -> None:
        # Nearly every issue carries no allowance of its own, and what holds
        # those is the deployment's setting -- read live, on every launch. So
        # the walk under it stops at the number an operator actually
        # configured rather than at one a fixture wrote onto the issue.
        journey = journeys.ROTATED_SESSIONS
        with patch.object(config, _RUNS_PER_ISSUE, _lifetime_models.ALLOWANCE):
            walked = support.walk(
                self,
                journey,
                seeded_on=support.seeded(journey, allowance=None),
            )

        self.assertEqual(walked.total, _lifetime_models.ALLOWANCE)
        self.assertTrue(walked.parked)
        self.assertNotIn(_run_ledger.AGENT_RUN_ALLOWANCE, walked.pinned)

    def test_the_total_is_the_pinned_comment(self) -> None:
        # A restarted orchestrator knows what the issue's own comment says and
        # nothing more. Rebuilt from exactly that, the process still refuses
        # the next launch -- the ceiling is not a counter the tick loop holds.
        journey = journeys.ROTATED_SESSIONS
        walked = self._walked(journey)

        restarted = FakeGitHubClient()
        restarted.add_issue(walked.issue)
        restarted.seed_state(walked.issue.number, **walked.pinned)
        resumed = support.walk(
            self, journey, 1, seeded_on=(restarted, walked.issue),
        )

        self.assertEqual(resumed.total, 0)
        self.assertEqual(resumed.spent, _lifetime_models.ALLOWANCE)

    def test_an_extension_buys_exactly_what_it_asks(self) -> None:
        # What the command widens is what the issue may still spend, so the
        # walk goes on for exactly the granted runs and stops on the same
        # park again -- the runs already spent are not returned by it.
        journey = journeys.ROTATED_SESSIONS
        walked = self._walked(journey)
        _lifetime_comments.said(walked.issue, _ADD_RUNS)

        bought = support.walk(
            self,
            journey,
            _GRANTED_RUNS + _lifetime_models.REFUSED_TICKS,
            seeded_on=(walked.github, walked.issue),
        )

        self.assertEqual(bought.total, _GRANTED_RUNS)
        self.assertEqual(bought.spent, _lifetime_models.ALLOWANCE + _GRANTED_RUNS)
        self.assertEqual(
            bought.pinned.get(_run_ledger.AGENT_RUN_ALLOWANCE),
            _lifetime_models.ALLOWANCE + _GRANTED_RUNS,
        )
        self.assertTrue(bought.parked)

    def test_no_command_buys_more_than_its_bound(self) -> None:
        # The bound is a property of the command rather than of the
        # deployment, so a request past it buys nothing at all and the walk
        # stays exactly where the ceiling left it.
        journey = journeys.ROTATED_SESSIONS
        walked = self._walked(journey)
        past_the_bound = _run_grant_request.MAX_RUNS_PER_COMMAND + 1
        _lifetime_comments.said(
            walked.issue, f"/orchestrator add-agent-runs {past_the_bound}",
        )

        refused = support.walk(
            self, journey, 1, seeded_on=(walked.github, walked.issue),
        )

        self.assertEqual(refused.total, 0)
        self.assertEqual(refused.spent, _lifetime_models.ALLOWANCE)
        self.assertTrue(refused.parked)

    def _walked(self, journey) -> _lifetime_models.Walk:
        """One journey walked until its allowance stops it, and past that."""
        return support.walk(self, journey)


class ResetRoundTest(unittest.TestCase, _PatchedWorkflowMixin):
    """The counter these loops reset, and the one they cannot."""

    def test_a_spent_round_is_put_back_by_the_tick(self) -> None:
        # Each of these legs is entered on a round the reviewer has already
        # spent, and the tick itself is what puts it back. That is the only
        # form of the claim worth making: a leg that staged the reset would be
        # asserting on its own fixture, and a loop whose round never moves is
        # not the loop these journeys are about.
        for journey in journeys.RESET_JOURNEYS:
            with self.subTest(journey=journey.name):
                entered = journey.legs[0].staged[_REVIEW_ROUND]

                walked = support.walk(self, journey, 1)

                self.assertEqual(entered, journeys.ROUNDS_SPENT)
                self.assertEqual(walked.rounds[0], 0)

    def test_a_base_sync_resets_and_spends_nothing(self) -> None:
        # The refresh is not a stage and starts no agent: it rebases the
        # branch onto the base that moved, force-pushes it, hands the issue
        # back to the reviewer, and puts the round counter back -- and the
        # ledger it did all that under is exactly where it found it. So a
        # deployment whose base moves every day buys no agent runs by it.
        walked = support.walk(self, journeys.SYNCED_BASE, 1)

        self.assertEqual(walked.total, 0)
        self.assertEqual(walked.rounds[0], 0)
        self.assertIn(
            (walked.issue.number, LABEL_VALIDATING),
            walked.github.label_history,
        )
        self.assertEqual(walked.spent, 0)
        self.assertEqual(
            walked.pinned.get(_run_ledger.AGENT_RUN_ALLOWANCE),
            _lifetime_models.ALLOWANCE,
        )


if __name__ == "__main__":
    unittest.main()
