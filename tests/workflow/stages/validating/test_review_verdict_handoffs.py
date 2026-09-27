# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A change request handed to `workflow:fixing` whose developer launch never reported back.

The handoff's write records the persisted verdict as handed, ahead of the
relabel, and only the writes behind the developer's run drop it. A tick that
stops anywhere in between leaves the next one the feedback to hand over: the
developer is launched once and no second reviewer is spent, and only feedback
whose anchor never landed is posted again. What the launch left is read off
the ledger's charge of that very launch: a reservation that never spawned is
spent by the one developer it was taken for, a started launch whose commit is
on the branch is not run again, one that left no trace parks for the
operator's retry -- which replays the posted feedback to one developer -- and
another road's charge is no launch of this developer at all.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from tests.workflow import published_reports as _published_reports
from tests.workflow.fixtures import LABEL_FIXING, LABEL_VALIDATING
from tests.workflow.stages.validating import review_verdict_readings as _read, review_verdict_test_support as _world
from tests.workflow.stages.validating.validating_review_test_support import FIX_HEAD_SHAS

# A reviewer asking for the change, with nothing declared beside it.
REQUESTING = f"{_world.REQUESTED}\n\nVERDICT: CHANGES_REQUESTED"

RESERVATION = "agent_run_reservation"

ANCHOR = "pending_fix_reviewer_comment_id"

RELABEL = "set_workflow_label"

LATER_REPORT = "Covered the empty configuration as well; the suite passes."

FINGERPRINT = "agent_run_fingerprint"

STARTED = "started"

# A launch no road of this issue's handoff names: another role's, run by an
# operator who moved the issue off `fixing` and back.
ANOTHER_LAUNCH = "0123456789abcdef" * 4

# A developer process that stopped mid-run, leaving nothing written behind it.
DIED = RuntimeError("the developer process died")

# A commit the developer made that the pull request has not got, and the
# publication that carries it there.
STRANDED = MappingProxyType({
    "branch_ahead_behind": (1, 0),
    "head_shas": FIX_HEAD_SHAS[-1:],
})

PUSH = "_push_branch"

# The one agent a handed change request is owed, as its spawn names it.
DEVELOPER = ("developer",)

# Who took a reservation standing behind the developer's own launch: another
# road, or a retry under this launch's own fingerprint.
_LATER_RESERVATIONS = (
    ("another road's", lambda _case: ANOTHER_LAUNCH),
    ("this launch's own", lambda case: case.pinned()[FINGERPRINT]),
)

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
    ("its relabel", (RELABEL, lambda label: label == LABEL_FIXING), 1),
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

                fixed = self.dispatched(_world.developer(), dirty_files=(), push_branch=True, head_shas=FIX_HEAD_SHAS)

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

    def test_a_report_behind_a_recovered_relabel(self) -> None:
        # The relabel failed, and a later report settles while the next tick's
        # recovery takes it: the request is about words the pull request no
        # longer carries, so no developer is launched, the later report is
        # kept rather than written back over, and no anchor is left to replay.
        self._fails_the_handoff(RELABEL, lambda label: label == LABEL_FIXING)
        relabelling = _world.AnotherRoadBehind(
            self,
            RELABEL,
            lambda label: label == LABEL_FIXING,
            lambda case: _published_reports.republishes_the_report(case.github, case.issue, LATER_REPORT),
        )

        with patch.object(self.github, RELABEL, relabelling):
            ran = self.dispatched(_world.developer())

        pinned = self.pinned()
        self.assertEqual(
            (
                ran[_world.RUN_AGENT].call_count,
                pinned[_world.RETURNED_VERDICT],
                pinned.get(ANCHOR),
                _read.current_report_revision(self),
            ),
            (0, None, None, 2),
        )

    def _fails_the_handoff(self, request: str, fails) -> None:
        """Return the change request over a client whose `request` fails once, where `fails` says."""
        failing = _FailsOnce(getattr(self.github, request), fails)
        with patch.object(self.github, request, failing), self.assertRaises(ConnectionError):
            self.returns(REQUESTING)


class _FixingTicks(_world.ReviewVerdictWorld):
    """`fixing` ticks over a change request handed there, whose developer launch stopped somewhere."""

    def _fixing(self, *agents, **run_options) -> dict:
        """One `fixing` tick, whose spawns return `agents` unless a `run_agent` says otherwise."""
        run_options.setdefault("run_agent", list(agents))
        run_options.setdefault("dirty_files", ())
        run_options.setdefault("head_shas", FIX_HEAD_SHAS)
        return self._run_fixing(self.github, self.issue, **run_options)

    def _charged(self) -> int:
        """The lifetime agent-run count the issue carries now."""
        return self.pinned()[_world.AGENT_RUNS_USED]

    def _charges(self, fingerprint: str, phase: str) -> None:
        """One more charge on the ledger, under `fingerprint`, standing at `phase`."""
        state = self.github.read_pinned_state(self.issue)
        state.set(_world.AGENT_RUNS_USED, self._charged() + 1)
        state.set(RESERVATION, phase)
        state.set(FINGERPRINT, fingerprint)
        self.github.write_pinned_state(self.issue, state)


class HandedChangeRequestTest(_FixingTicks, unittest.TestCase):
    """A change request relabelled to `fixing` whose developer was never charged."""

    def setUp(self) -> None:
        super().setUp()
        with patch.object(self.github, "read_pinned_state", _RefusesTheLaunchRead(self.github)):
            self.returns(REQUESTING)

    def test_fixing_launches_the_one_developer(self) -> None:
        pinned = self.pinned()
        self.assertEqual(
            (self.github.workflow_label(self.issue), pinned[_world.RETURNED_VERDICT]["handed"]),
            (LABEL_FIXING, self._charged()),
        )

        fixed = self._fixing(_world.developer())

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

    def test_an_unanchored_request_is_anchored_again(self) -> None:
        # The anchor the handoff wrote is gone, so nothing could replay the
        # feedback to a retry: it is posted again and recorded before the
        # developer is launched, and when that launch dies the operator's
        # retry replays it to one developer.
        state = self.github.read_pinned_state(self.issue)
        state.data.pop(ANCHOR)
        self.github.write_pinned_state(self.issue, state)

        with self.assertRaises(RuntimeError):
            self._fixing(run_agent=MagicMock(side_effect=DIED))
        anchored = self.pinned().get(ANCHOR)
        parked = self._fixing()
        _world.replies(self, "/orchestrator continue")
        fixed = self._fixing(_world.developer())

        spawned = fixed[_world.RUN_AGENT]
        self.assertEqual(
            (
                len(_read.feedback_posts(self)),
                anchored is not None,
                parked[_world.RUN_AGENT].call_count,
                spawned.call_count,
                _world.REQUESTED in spawned.call_args.args[1],
            ),
            (2, True, 0, 1, True),
        )

    def test_a_stale_request_keeps_a_later_report(self) -> None:
        # The head was pushed, and a later report settles while recovery reads
        # the subject: the request is dropped, but over the comment read again,
        # so the drop's write keeps the later report rather than restoring the
        # one the request was about.
        _world.pushes(self)
        behind = _world.AnotherRoadBehind(
            self,
            "reread_report_location",
            lambda _location: True,
            lambda case: _published_reports.republishes_the_report(case.github, case.issue, LATER_REPORT),
        )

        with patch.object(self.github, "reread_report_location", behind):
            ran = self._fixing()

        pinned = self.pinned()
        self.assertEqual(
            (
                ran[_world.RUN_AGENT].call_count,
                pinned[_world.RETURNED_VERDICT],
                pinned.get(ANCHOR),
                _read.current_report_revision(self),
            ),
            (0, None, None, 2),
        )

    def test_another_roads_charge_is_no_launch(self) -> None:
        # The one charge past the handoff names another role's launch and
        # started: it says nothing about this developer, who is still owed
        # and launched once, rather than parked as a launch that never ended.
        self._charges(ANOTHER_LAUNCH, STARTED)

        fixed = self._fixing(_world.developer())

        self.assertEqual(
            (
                fixed[_world.RUN_AGENT].call_count,
                _read.spawned_roles(self),
                self.pinned().get(_world.PARK_REASON),
                self.pinned()[_world.RETURNED_VERDICT],
                self.github.label_history[-1],
            ),
            (1, DEVELOPER, None, None, (_world.ISSUE, LABEL_VALIDATING)),
        )


class InterruptedLaunchTest(_FixingTicks, unittest.TestCase):
    """A change request whose developer launch was charged and never reported back."""

    def test_a_reserved_charge_is_spent_once(self) -> None:
        # The charge's STARTED write was refused, so the launch reserved its
        # run and spawned nothing. The next tick's developer is that very
        # launch, spawned under the reservation rather than charged again.
        refusing = _FailsOnce(
            self.github.write_pinned_state, lambda state: state.get(RESERVATION) == STARTED,
        )
        with patch.object(self.github, "write_pinned_state", refusing):
            self.returns(REQUESTING)
        charged = self._charged()
        self.assertEqual(
            (self.pinned()[RESERVATION], _read.spawned_roles(self)),
            ("reserved", ()),
        )

        fixed = self._fixing(_world.developer())

        self.assertEqual(
            (
                fixed[_world.RUN_AGENT].call_count,
                _read.spawned_roles(self),
                self._charged(),
                self.pinned()[_world.RETURNED_VERDICT],
            ),
            (1, DEVELOPER, charged, None),
        )

    def test_a_started_launch_that_committed_stands(self) -> None:
        # The developer ran and committed, and the process died before
        # anything was written behind it: the commit the pull request has not
        # got is that run's work, which the stage's own bounce publishes, and
        # no second developer is paid for.
        with self.assertRaises(RuntimeError):
            self.returns(REQUESTING, run_agent=MagicMock(side_effect=DIED))
        charged = self._charged()

        bounced = self._fixing(**STRANDED)

        self.assertEqual(
            (
                bounced[_world.RUN_AGENT].call_count,
                _read.spawned_roles(self),
                self._charged(),
                self.pinned()[_world.RETURNED_VERDICT],
                bounced[PUSH].call_count,
                self.github.label_history[-1],
            ),
            (0, DEVELOPER, charged, None, 1, (_world.ISSUE, LABEL_VALIDATING)),
        )

    def test_a_later_reservation_parks_the_handoff(self) -> None:
        # The developer's launch started and died, and a later charge stands
        # reserved behind it: that reservation says nothing about the run
        # before it, so no second developer is launched or charged, and the
        # handoff parks for the operator.
        for name, fingerprint in _LATER_RESERVATIONS:
            with self.subTest(name):
                self.setUp()
                with self.assertRaises(RuntimeError):
                    self.returns(REQUESTING, run_agent=MagicMock(side_effect=DIED))
                self._charges(fingerprint(self), "reserved")
                charged = self._charged()

                parked = self._fixing(_world.developer())

                self.assertEqual(
                    (
                        parked[_world.RUN_AGENT].call_count,
                        _read.spawned_roles(self),
                        self._charged(),
                        self.pinned()[_world.PARK_REASON],
                        self.pinned()[_world.RETURNED_VERDICT],
                    ),
                    (0, DEVELOPER, charged, EXECUTION_FAILED, None),
                )

    def test_a_push_behind_an_unfinished_launch(self) -> None:
        # The launch started and died, and a push moved the head since: the
        # feedback is about a head the pull request no longer carries, so no
        # park keeps it for a retry to replay -- the verdict and its anchor
        # are dropped, no developer is launched on it, and whatever the
        # stage's own road makes of the moved checkout is its own.
        with self.assertRaises(RuntimeError):
            self.returns(REQUESTING, run_agent=MagicMock(side_effect=DIED))
        _world.pushes(self)

        ran = self._fixing()

        pinned = self.pinned()
        self.assertEqual(
            (ran[_world.RUN_AGENT].call_count, pinned[_world.RETURNED_VERDICT], pinned.get(ANCHOR)),
            (0, None, None),
        )
        self.assertNotEqual(pinned.get(_world.PARK_REASON), EXECUTION_FAILED)

    def test_an_unfinished_launch_parks_for_one_retry(self) -> None:
        # STARTED goes down before the spawn, and nothing on the branch says a
        # developer ran: nothing is paid for twice, and the issue is not
        # bounced to a second reviewer. The operator's retry replays the
        # posted feedback to one fresh developer session.
        with self.assertRaises(RuntimeError):
            self.returns(REQUESTING, run_agent=MagicMock(side_effect=DIED))

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

        _world.replies(self, "/orchestrator continue")
        fixed = self._fixing(_world.developer())

        spawned = fixed[_world.RUN_AGENT]
        self.assertEqual(
            (spawned.call_count, _world.REQUESTED in spawned.call_args.args[1]),
            (1, True),
        )


if __name__ == "__main__":
    unittest.main()
