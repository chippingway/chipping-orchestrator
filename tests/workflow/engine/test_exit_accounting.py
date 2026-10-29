# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Every exit the tracked spawn returns is accounted on its issue once, before anything above can discard it.

Each case goes through `_run_agent_tracked`, the boundary every invoked
process returns through. What it has to show: the accounting lands as the run
returns -- a held, failed, or timed-out exit's as much as a finished one's --
and only the accounting does, laid back onto the caller as the comment's, so
the disposition's own write behind it neither counts the run again nor puts
the totals back; and one that neither landed nor read back covered leaves the
result unaccounted and the caller's state withheld, so nothing that depends on
it follows until a later reading settles it.
"""
from __future__ import annotations

import json
import unittest

from orchestrator.agents.models import ToolLifecycle
from orchestrator.github.pinned_state import PinnedState
from orchestrator.observability.usage import protocol as _protocol
from orchestrator.workflow.engine import report_commits as _report_commits, usage_checkpoint as _usage_checkpoint
from tests.workflow.engine import run_circuit_test_support as support
from tests.workflow.fixtures import AGENT_RUN_ACCOUNTING_KEYS, accounted

# A field the caller staged before the spawn, which is its own write's to make.
_STAGED = "dev_session_id"
_STAGED_SESSION = "staged-before-the-spawn"

# A command an Antigravity run left running when it stopped.
_ACTIVE_STEP = ToolLifecycle(step_index=1, tool_name="run_command", state="ACTIVE")

# A counter a hand edit spelled as nothing its writers write.
_DAMAGED_TOKENS = "lots"

# Exits whose disposition a stage withholds or parks, each of which still ran:
# a shutdown kill, a timeout, a failure, and an Antigravity run that stopped
# with a command still active.
_HELD_EXITS = (
    ("a shutdown kill", support.agent_result(interrupted=True, exit_code=support.INTERRUPTED_EXIT_CODE)),
    ("a timeout", support.agent_result(timed_out=True, exit_code=-1)),
    ("a failure", support.agent_result(exit_code=1, last_message="")),
    ("an incomplete run", support.agent_result(exit_code=1, unfinished_steps=(_ACTIVE_STEP,))),
)

# The write a stage's disposition lands behind the run: its own staged field,
# decided on nothing the accounting moves.
_DISPOSITION = _report_commits.ReportWrite(owned=frozenset((_STAGED,)), decided_on=frozenset())


class ExitAccountingTest(unittest.TestCase):
    """What the tracked spawn lands of each exit, and what it hands its caller."""

    def test_an_exit_is_accounted_as_it_returns(self) -> None:
        # The accounting lands alone -- not the field the caller staged -- and
        # is laid back onto the caller with the reading it was synced with, so
        # a whole-state write or a guarded commit behind it keeps one count
        # and lands what the caller staged.
        for settles in (_writes_whole, _commits):
            with self.subTest(settles.__name__):
                launch = support.seeded()
                launch.state.set(_STAGED, _STAGED_SESSION)

                support.run_launch(launch)
                landed = launch.durable
                laid_back = _laid_back(launch.state)
                settles(launch)

                self.assertEqual((launch.answer.unaccounted, _STAGED in landed), (False, False))
                self.assertEqual(laid_back, (_accounting(landed), _accounting(landed)))
                self.assertEqual(accounted(launch.durable), (1, 1))
                self.assertEqual(launch.durable[_STAGED], _STAGED_SESSION)

    def test_each_held_exit_is_accounted_once(self) -> None:
        # Whatever a stage makes of the exit, it ran: its usage is counted once,
        # and nothing of its disposition rides the accounting.
        for name, outcome in _HELD_EXITS:
            with self.subTest(name):
                launch = support.run_launch(support.seeded(), outcome=outcome, backend=_protocol.AGY)

                self.assertFalse(launch.answer.unaccounted)
                self.assertEqual(accounted(launch.durable), (1, 1))

    def test_an_unconfirmed_accounting_is_held(self) -> None:
        # The edit landed and its response was lost: nothing can say it landed
        # until a later reading, so the result is unaccounted and the caller's
        # state is kept out of the whole-state write that would put the count
        # back. A restart reading the receipt adds nothing.
        launch = support.seeded()
        launch.gh.pinned_failures.lost.add(support.ISSUE_NUMBER)

        support.run_launch(launch)
        launch.gh.write_pinned_state(launch.issue, launch.state)
        launch.gh.pinned_failures.lost.clear()
        restarted = launch.gh.read_pinned_state(launch.issue)
        read_back = _usage_checkpoint.checkpoint(launch.gh, launch.issue, restarted, launch.answer)

        self.assertEqual((launch.answer.unaccounted, launch.state.withheld), (True, True))
        self.assertIs(read_back.status, _usage_checkpoint.AccountingStatus.COVERED)
        self.assertEqual(accounted(launch.durable), (1, 1))

    def test_a_refused_accounting_is_held(self) -> None:
        # A counter a hand edit damaged refuses the accounting with nothing
        # written: the charge the launch paid stands, and the result is held.
        launch = support.run_launch(support.seeded(issue_total_tokens=_DAMAGED_TOKENS))

        self.assertEqual((launch.answer.unaccounted, launch.state.withheld), (True, True))
        self.assertEqual(launch.spent, 1)
        self.assertEqual(accounted(launch.durable), (0, 0))
        self.assertEqual(launch.durable["issue_total_tokens"], _DAMAGED_TOKENS)

    def test_a_launch_never_made_owes_nothing(self) -> None:
        # The circuit turned the launch away: no process, no exit, and nothing
        # held -- the refusal is what the caller reads.
        launch = support.run_launch(support.seeded(), allowance=1)
        refused = support.run_launch(launch, allowance=1).answer

        self.assertEqual((refused.invoked, refused.unaccounted), (False, False))
        self.assertEqual(launch.invocations, 1)
        self.assertEqual(accounted(launch.durable), (1, 1))


def _accounting(record: dict) -> dict:
    """The accounting fields `record` carries."""
    return {field: record.get(field) for field in AGENT_RUN_ACCOUNTING_KEYS}


def _laid_back(state: PinnedState) -> tuple[dict, dict]:
    """The accounting `state` carries, and the accounting the reading it was synced with carries."""
    return _accounting(state.state_data), _accounting(json.loads(state.synced))


def _writes_whole(launch: support.Launch) -> None:
    """The disposition written whole from the caller's state."""
    launch.gh.write_pinned_state(launch.issue, launch.state)


def _commits(launch: support.Launch) -> None:
    """The disposition landed through a guarded commit over the caller's synced reading."""
    commit = _report_commits.ReportCommit(launch.gh, launch.issue, launch.state)
    commit.lands(launch.state, _DISPOSITION)


if __name__ == "__main__":
    unittest.main()
