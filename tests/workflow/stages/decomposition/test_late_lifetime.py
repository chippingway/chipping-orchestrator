# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How many candidates one issue can have adjudicated before it runs out.

The adjudicator is the one road to an agent that is not a dispatched handler,
so the journeys that walk an issue's whole lifetime cannot drive it and this
is where its half of that coverage lives. What it adds is a loop the other
roads do not have: a developer resumed with guidance commits again, the gate
measures again, and a fresh generation is frozen over the new commit -- which
is an adjudication per candidate, with nothing in the late domain that counts
how many an issue has had.

The lifetime ledger is what counts them, and the second subject here is the
one way an issue gets a fresh domain record without getting fresh runs: an
authorized restart projects a new cycle over the old pinned comment, and the
allowance and the spend are on the list of things it carries across.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.config import settings as config
from orchestrator.workflow.engine import (
    dispatch as _dispatch,
    run_ledger_values as _run_ledger_values,
    run_limit as _run_limit,
)
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from tests.workflow.fixtures import (
    _TEST_SPEC,
    KEY_AWAITING_HUMAN,
    KEY_PARK_REASON,
    _agent,
    _PatchedWorkflowMixin,
)
from tests.workflow.stages.decomposition import late_restart_support as _restart_fixtures
from tests.workflow.stages.decomposition.late_run_support import adjudicate, agent_reply
from tests.workflow.stages.decomposition.late_seam_support import WorktreeSeed
from tests.workflow.stages.decomposition.late_test_support import (
    CYCLE_ID,
    KEYS,
    LATE_ISSUE_NUMBER,
    SHA_LENGTH,
    SINGLE_REPLY,
    late_generation,
    seeded_late_issue,
)

# Small enough that a whole lifetime of adjudications fits in a handful of
# rounds, and large enough that the walk before the ceiling is a walk.
_ALLOWANCE = 3

# How many rounds are driven past the last one the issue can pay for: one to
# meet the refusal, and one that has to add nothing to the thread.
_REFUSED_ROUNDS = 2

# How many rounds a whole sequence drives, and the day's spawn budget pinned
# one wider than that. Every adjudication is charged to that budget too, and
# it is bounded by a setting the environment can carry -- so left alone it
# would be what stopped the sequence on any host configured tighter than this
# is long, and these cases would be measuring the wrong cap. What it refuses
# ahead of the lifetime ledger is `test_capped_launches.py`'s subject.
_ROUNDS_DRIVEN = _ALLOWANCE + _REFUSED_ROUNDS

_RETRY_ALLOWANCE = _ROUNDS_DRIVEN + 1

_RETRIES_PER_DAY = "MAX_RETRIES_PER_DAY"

_RUN_LIMIT_PHRASE = "lifetime agent-run allowance"

_RUN_AGENT = "run_agent"


def _candidate_sha(round_number: int) -> str:
    """The commit the developer left the checkout on for this round."""
    return format(round_number + 1, f"0{SHA_LENGTH}x")


class RepeatedAdjudicationTest(unittest.TestCase):
    """One candidate after another, and the ledger that ends the sequence."""

    def setUp(self) -> None:
        held = patch.object(config, _RETRIES_PER_DAY, _RETRY_ALLOWANCE)
        held.start()
        self.addCleanup(held.stop)
        seeded = seeded_late_issue(**{
            _run_ledger_values.AGENT_RUN_ALLOWANCE: _ALLOWANCE,
            _run_ledger_values.AGENT_RUNS_USED: 0,
        })
        self.github = seeded[0]
        self.issue = seeded[1]

    def test_the_sequence_stops_at_the_total(self) -> None:
        adjudicated = self._rounds(_ROUNDS_DRIVEN)

        self.assertEqual(sum(adjudicated), _ALLOWANCE)
        self.assertEqual(
            self._pinned().get(_run_ledger_values.AGENT_RUNS_USED), _ALLOWANCE,
        )

    def test_a_refused_round_decides_nothing(self) -> None:
        # A refusal is not a verdict: the generation is left exactly as the
        # gate froze it, the issue stops, and the sentence explaining it is
        # said once however many more rounds reach the same refusal.
        self._rounds(_ALLOWANCE)
        deferred = [
            self._round(_ALLOWANCE + extra) for extra in range(_REFUSED_ROUNDS)
        ]

        for outcome, spawn in deferred:
            self.assertEqual(outcome.disposition, _LateDisposition.DEFERRED)
            spawn.assert_not_called()
        pinned = self._pinned()
        self.assertEqual(
            pinned.get(KEYS.candidate_sha),
            _candidate_sha(_ALLOWANCE + _REFUSED_ROUNDS - 1),
        )
        self.assertTrue(pinned.get(KEY_AWAITING_HUMAN))
        self.assertEqual(
            pinned.get(KEY_PARK_REASON), _run_limit.PARK_AGENT_RUN_LIMIT,
        )
        self.assertEqual(len(self._notices()), 1)

    def _rounds(self, rounds: int) -> list[int]:
        """Drive `rounds` adjudications, and report what each one spawned."""
        return [
            self._round(number)[1].call_count for number in range(rounds)
        ]

    def _round(self, number: int):
        """Freeze one fresh candidate over this issue, and adjudicate it.

        A new cycle over a new commit is what the gate leaves behind when a
        resumed developer commits again: the domain record is replaced whole,
        and nothing in it remembers how many of them there have been.
        """
        candidate = _candidate_sha(number)
        state = self.github.read_pinned_state(self.issue)
        _late_state.write_late_generation(state, late_generation(
            cycle_id=CYCLE_ID + number, candidate_sha=candidate,
        ))
        self.github.write_pinned_state(self.issue, state)
        return adjudicate(
            self.github,
            self.issue,
            agent_reply(SINGLE_REPLY),
            worktree=WorktreeSeed(head=candidate),
        )

    def _pinned(self) -> dict:
        return self.github.pinned_data(LATE_ISSUE_NUMBER)

    def _notices(self) -> list[str]:
        return [
            body for _, body in self.github.posted_comments
            if _RUN_LIMIT_PHRASE in body
        ]


class RestartedCycleTest(
    _restart_fixtures.RestartCase, _PatchedWorkflowMixin, unittest.TestCase,
):
    """A fresh cycle is not a fresh lifetime."""

    def test_the_restarted_issue_keeps_what_it_spent(self) -> None:
        # The projection is a whitelist of facts about the ISSUE, and what it
        # has spent is one of them. Handed back instead, a cancelled cycle
        # would be the way to buy another lifetime.
        self._seed(**self._spent_ledger())

        self._reported_route()

        pinned = self._pinned()
        self.assertEqual(
            pinned.get(_run_ledger_values.AGENT_RUN_ALLOWANCE), _ALLOWANCE,
        )
        self.assertEqual(
            pinned.get(_run_ledger_values.AGENT_RUNS_USED), _ALLOWANCE,
        )

    def test_the_fresh_cycle_reaches_no_agent(self) -> None:
        # What the retained count is worth: the first spawn of the cycle an
        # operator just authorized is refused, and the issue stops on the park
        # that says so rather than decomposing itself all over again.
        self._seed(**self._spent_ledger())
        self._reported_route()

        mocks = self._dispatched()

        mocks[_RUN_AGENT].assert_not_called()
        pinned = self._pinned()
        self.assertTrue(pinned.get(KEY_AWAITING_HUMAN))
        self.assertEqual(
            pinned.get(KEY_PARK_REASON), _run_limit.PARK_AGENT_RUN_LIMIT,
        )

    def _spent_ledger(self) -> dict:
        return {
            _run_ledger_values.AGENT_RUN_ALLOWANCE: _ALLOWANCE,
            _run_ledger_values.AGENT_RUNS_USED: _ALLOWANCE,
        }

    def _dispatched(self) -> dict:
        """The tick after the restart, on the label the restart applied."""
        return self._run(
            lambda: _dispatch._route_issue_to_handler(
                self.github,
                _TEST_SPEC,
                self.issue,
                self.github.workflow_label(self.issue),
            ),
            run_agent=_agent(last_message="never asked"),
        )


if __name__ == "__main__":
    unittest.main()
