# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A change request handed to `workflow:fixing` whose developer launch never reported back.

The handoff's write records the persisted verdict as handed, ahead of the
relabel, and only the writes behind the developer's run drop it. A tick that
stops anywhere in between leaves the next one the feedback to hand over: the
developer is launched once and no second reviewer is spent, and only feedback
whose anchor never landed is posted again. A launch the ledger shows settled
is not run again, and one that started and left no trace parks for the
operator's retry, which replays the posted feedback to one developer.
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

HANDED_BACK = ((_world.ISSUE, LABEL_FIXING), (_world.ISSUE, LABEL_VALIDATING))


def _hands_the_verdict_over(state) -> bool:
    """Whether a pinned write carries the waiting verdict as handed."""
    return (state.get(_world.RETURNED_VERDICT) or {}).get("handed") is not None


# Each request the handoff makes before its launch, the one that fails, and
# how many feedback posts the pull request carries once the next tick hands
# the request over: feedback whose anchor never landed is posted again.
_UNLANDED = (
    ("the handoff's write", ("write_pinned_state", _hands_the_verdict_over), 2),
    ("its relabel", ("set_workflow_label", lambda label: label == LABEL_FIXING), 1),
)


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


class _FailsOnce:
    """One client request that fails the first time `fails` says what it was asked is the one."""

    def __init__(self, request, fails) -> None:
        self._request = request
        self._fails = fails
        self._failed = False

    def __call__(self, issue, asked):
        if not self._failed and self._fails(asked):
            self._failed = True
            raise ConnectionError("GitHub refused the request")
        return self._request(issue, asked)


class UnlandedHandoffTest(_world.ReviewVerdictWorld, unittest.TestCase):
    """A handoff whose write or relabel failed is finished on `validating` by one developer."""

    def test_the_next_tick_hands_it_over(self) -> None:
        for name, failure, posts in _UNLANDED:
            with self.subTest(name):
                self.setUp()
                self._fails_the_handoff(*failure)
                self.assertEqual(self.github.workflow_label(self.issue), LABEL_VALIDATING)

                fixed = self.dispatched(_developer(), dirty_files=(), push_branch=True, head_shas=FIX_HEAD_SHAS)

                spawned = fixed[_world.RUN_AGENT]
                self.assertEqual(
                    (
                        spawned.call_count,
                        _world.REQUESTED in spawned.call_args.args[1],
                        len(_read.feedback_posts(self)),
                        tuple(self.github.label_history),
                        self.pinned()[_world.RETURNED_VERDICT],
                    ),
                    (1, True, posts, HANDED_BACK, None),
                )

    def _fails_the_handoff(self, request: str, fails) -> None:
        """Return the change request over a client whose `request` fails once, where `fails` says."""
        failing = _FailsOnce(getattr(self.github, request), fails)
        with patch.object(self.github, request, failing), self.assertRaises(ConnectionError):
            self.returns(REQUESTING)


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
