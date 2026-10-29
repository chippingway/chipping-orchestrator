# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The identity a tracked run stamps on the result of each process it starts.

Every case goes through `_run_agent_tracked`, the one boundary a process is
started from: a process is identified by the charge it was started under and a
random nonce, never by its request, so two runs of an identical request -- with
no session id between them -- are two invocations, each accounted once.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import usage_checkpoint as _usage_checkpoint
from tests.workflow.engine import (
    run_circuit_test_support as support,
    usage_checkpoint_test_support as _accounting,
)

# The workflow cycle a record names, one no reader can name, and the charge a
# reservation an earlier tick left standing was taken at.
_CYCLE = "late_cycle_id"
_LATE_CYCLE = 4
_DAMAGED_CYCLE = "damaged"
_STANDING_COUNT = 6

# Two launches of one request, and what accounting each twice comes to.
_LAUNCHES = range(2)
_ACCOUNTED_TWICE = (
    _accounting.STATUS.ACCOUNTED,
    _accounting.STATUS.ACCOUNTED,
    _accounting.STATUS.COVERED,
    _accounting.STATUS.COVERED,
)

# The meter two unpriced runs leave: two exits, no tokens, and no cost.
_TWO_UNPRICED_RUNS = (2, 0, None, ["no-usage"])


class InvocationIdentityTest(unittest.TestCase):
    """Each process is identified by the charge it was started under, never by its request."""

    def test_identical_launches_are_two_invocations(self) -> None:
        # One request launched twice -- the same role, stage, command, and
        # prompt, and the same session-less result -- is one logical launch
        # and two processes.
        launch = support.seeded(**{_CYCLE: _LATE_CYCLE})

        identities = [
            support.run_launch(launch, outcome=support.agent_result(session_id=None)).answer.invocation
            for _ in _LAUNCHES
        ]

        self.assertEqual([identity.ordinal for identity in identities], [1, 2])
        self.assertNotEqual(identities[0].nonce, identities[1].nonce)
        self.assertEqual(
            {(identity.repo, identity.issue, identity.comment, identity.cycle) for identity in identities},
            {(launch.gh.repo_slug, support.ISSUE_NUMBER, launch.state.comment_id, _LATE_CYCLE)},
        )
        self.assertEqual(launch.durable[support.FINGERPRINT], support.fingerprint())

    def test_a_reused_charge_names_its_process(self) -> None:
        # A charge an earlier tick reserved and never started is the one this
        # process is started under, so it is identified by that count.
        launch = support.run_launch(support.seeded(**{
            support.USED: _STANDING_COUNT,
            support.RESERVATION: support.RESERVED,
            support.FINGERPRINT: support.fingerprint(),
        }))

        self.assertEqual((launch.spent, launch.answer.invocation.ordinal), (_STANDING_COUNT, _STANDING_COUNT))

    def test_a_damaged_cycle_names_no_cycle(self) -> None:
        # A record whose cycle identity no reader can name charges a process
        # that belongs to no cycle -- not the absent one -- so nothing of it
        # is accounted while that identity stays damaged.
        launch = support.run_launch(support.seeded(**{_CYCLE: _DAMAGED_CYCLE}))

        outcome = _usage_checkpoint.checkpoint(launch.gh, launch.issue, launch.state, launch.answer)

        self.assertIsNone(launch.answer.invocation.cycle)
        self.assertIs(outcome.status, _accounting.STATUS.REFUSED)
        self.assertIs(outcome.refusal, _accounting.REFUSAL.DAMAGED)

    def test_identical_runs_are_each_counted_once(self) -> None:
        # The same parsed usage from two runs of one request: only the
        # identity each was started under tells them apart, so the meter
        # counts two exits, and settling each again adds nothing.
        launch = support.seeded()
        answers = [support.run_launch(launch).answer for _ in _LAUNCHES]

        outcomes = tuple(
            _usage_checkpoint.checkpoint(launch.gh, launch.issue, launch.state, answer).status
            for answer in (*answers, *answers)
        )

        self.assertEqual(outcomes, _ACCOUNTED_TWICE)
        self.assertEqual(_accounting.counted(launch.durable), _TWO_UNPRICED_RUNS)


if __name__ == "__main__":
    unittest.main()
