# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A change request handed to `workflow:fixing` whose developer launch never reported back.

The relabel's write records the persisted verdict as handed, and only the
writes behind the developer's run drop it. A process that stops between the
two leaves `fixing` the feedback to hand over: the developer is launched once,
nothing is posted twice, and no second reviewer is spent. A launch the ledger
shows settled is not run again, and one that started and left no trace parks
for the operator's retry, which replays the posted feedback to one developer.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.fixtures import LABEL_FIXING, LABEL_VALIDATING, _agent, _reported
from tests.workflow.stages.validating import review_verdict_readings as _read, review_verdict_test_support as _world
from tests.workflow.stages.validating.validating_review_test_support import FIX_HEAD_SHAS

# A reviewer asking for the change, with nothing declared beside it.
REQUESTING = f"{_world.REQUESTED}\n\nVERDICT: CHANGES_REQUESTED"

RESERVATION = "agent_run_reservation"

EXECUTION_FAILED = "agent_execution_failed"

# Ticks on `fixing` with nothing new on the thread, which a park waits through.
QUIET_TICKS = 2


class _RefusesTheLaunchRead:
    """A pinned-comment read that fails once, the first time the issue carries `workflow:fixing`.

    That read is the developer launch's charge, so failing it is a process
    stopping between the relabel's write and the spawn.
    """

    def __init__(self, github) -> None:
        self._github = github
        self._read = github.read_pinned_state
        self._failed = False

    def __call__(self, issue):
        if not self._failed and self._github.workflow_label(issue) == LABEL_FIXING:
            self._failed = True
            raise ConnectionError("the pinned comment could not be read")
        return self._read(issue)


class HandedChangeRequestTest(_world.ReviewVerdictWorld, unittest.TestCase):
    """A handed change request stays owed to its one developer until that developer is launched."""

    def setUp(self) -> None:
        super().setUp()
        with patch.object(self.github, "read_pinned_state", _RefusesTheLaunchRead(self.github)):
            self.returns(REQUESTING)

    def test_fixing_launches_the_one_developer(self) -> None:
        pinned = self.pinned()
        self.assertEqual(
            (self.github.workflow_label(self.issue), pinned[_world.RETURNED_VERDICT]["handed"]),
            (LABEL_FIXING, pinned[_world.AGENT_RUNS_USED]),
        )

        fixed = self._fixing(_developer())

        self.assertEqual(
            (
                fixed[_world.RUN_AGENT].call_count,
                _world.REQUESTED in fixed[_world.RUN_AGENT].call_args.args[1],
                len(_read.feedback_posts(self)),
                self.pinned()[_world.RETURNED_VERDICT],
                self.github.label_history[-1],
            ),
            (1, True, 1, None, (_world.ISSUE, LABEL_VALIDATING)),
        )

    def test_a_launched_developer_is_not_rerun(self) -> None:
        # A charge past the handoff whose phase a returned run's write settled.
        self._charges_a_launch(phase=None)

        fixed = self._fixing()

        self.assertEqual(
            (fixed[_world.RUN_AGENT].call_count, self.pinned()[_world.RETURNED_VERDICT]),
            (0, None),
        )

    def test_an_unfinished_launch_parks_for_one_retry(self) -> None:
        # STARTED goes down before the spawn, and nothing on the branch says a
        # developer ran: nothing is paid for twice, and the issue is not
        # bounced to a second reviewer. The operator's retry replays the
        # posted feedback to one fresh developer session.
        self._charges_a_launch(phase="started")

        quiet = [self._fixing() for _ in range(QUIET_TICKS)]
        pinned = self.pinned()
        self.assertEqual(
            (
                {ran[_world.RUN_AGENT].call_count for ran in quiet},
                pinned[_world.PARK_REASON],
                pinned[_world.RETURNED_VERDICT],
                self.github.workflow_label(self.issue),
            ),
            ({0}, EXECUTION_FAILED, None, LABEL_FIXING),
        )

        self.issue.comments.append(FakeComment(
            id=self.github._next_comment_id(self.issue),
            body="/orchestrator continue",
            user=FakeUser(self.issue.user.login),
        ))
        fixed = self._fixing(_developer())

        spawned = fixed[_world.RUN_AGENT]
        self.assertEqual(
            (spawned.call_count, _world.REQUESTED in spawned.call_args.args[1]),
            (1, True),
        )

    def _fixing(self, *agents) -> dict:
        """One `fixing` tick, whose spawns return `agents`."""
        return self._run_fixing(
            self.github, self.issue, run_agent=list(agents), dirty_files=(), head_shas=FIX_HEAD_SHAS,
        )

    def _charges_a_launch(self, *, phase: str | None) -> None:
        """Charge one launch past the handoff, its reservation left at `phase`."""
        state = self.github.read_pinned_state(self.issue)
        state.set(_world.AGENT_RUNS_USED, state.get(_world.AGENT_RUNS_USED) + 1)
        state.set(RESERVATION, phase)
        self.github.write_pinned_state(self.issue, state)


def _developer():
    """The developer run a handed change request is answered by."""
    return _agent(session_id=_world.DEV_SESSION, last_message=_reported("fixed"))


if __name__ == "__main__":
    unittest.main()
