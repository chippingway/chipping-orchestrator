# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where the report reconciliation sits among the guards ahead of every handler.

Three orderings decide whether a report is published, on which world, and on an
issue anybody still wants -- and none of them is visible from the
reconciliation's own unit tests.

The first is the PLACE in the guard chain, which is pinned here by call order
rather than by outcome, and over the WHOLE chain rather than over the guards
either side of it. Ahead of the outstanding-publication reconciliation the guard
would read a candidate mid-gate as one whose code was never published and stand
down on every tick; between that reconciliation and the auto-rebase anchor asked
behind it, it would publish onto a pull request carrying a replay no recovery
has finalized; behind the reuse guard or the handler it would let a reviewer be
spawned over a report nobody published. Every one of those failures leaves every
other assertion in this file passing, so the order itself is what is asserted.

A PAUSED issue never reaches the guard at all: the hard-skip screen is one
level up, in `_process_issue`, and returns before the routing that runs the
dispatch guards. An operator applying the label is entitled to expect that
nothing at all happens, publication included.

A CLOSED issue reaches the guard and is handed straight back. The stage
terminal that drains one runs BEHIND every dispatch guard, so a human closing
an issue whose pull request is still open would otherwise get a report
published and a handoff recorded on the way to `rejected`. The control case
beside it is what makes the refusal meaningful: the same world with the issue
open does publish.
"""
from __future__ import annotations

import contextlib
import importlib
import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import (
    dispatch_guards as _dispatch_guards,
    issue_processing as _issue_processing,
    report_record_state as _record_state,
    report_records as _records,
    report_transaction as _report_transaction,
    stage_targets as _stage_targets,
)
from tests.support.github.models import FakeLabel
from tests.workflow.engine import report_transaction_test_support as support
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_DONE,
    LABEL_REJECTED,
    LABEL_VALIDATING,
)

_PAUSED = "paused"

# A park a stage takes and a stage answers, standing for every reason that is
# not this owner's own.
_AGENT_TIMEOUT = "agent_timeout"

# The stage-owned guards this one has to run between, named by the owner each
# is read off and the step it stands for. Resolved when the case runs, exactly
# as the dispatcher resolves them, so a stage owner that moves takes this table
# with it rather than leaving it passing against a module nothing calls.
_STAGE_CHAIN = (
    ("adjudication", _stage_targets._LATE_RELABEL_OWNER, "_holds_the_label"),
    ("publication", _stage_targets._LATE_RECONCILE_OWNER, "_reconciles_published_work"),
    ("reuse", _stage_targets._LATE_REUSE_OWNER, "_refuses_reuse"),
)

# The auto-rebase anchor, which belongs to this module rather than to a stage
# and is asked TWICE -- once ahead of the publication reconciliation and once
# behind it, because the late claim that released it may be the very record
# that reconciliation spends. Recorded under one step name, so the sequence a
# case asserts carries both calls and a guard moved between them is seen.
_RECOVERY = "recovery"

# Every step the dispatcher takes on a live `validating` issue, in the order it
# has to take them. Spelled once because it is the whole of what this module
# protects: each neighbour stands aside, so where each was called is all there
# is left to observe.
_REQUIRED_ORDER = (
    "adjudication", _RECOVERY, "publication", _RECOVERY, "report", "reuse", "handler",
)


class _Recorder:
    """One guard stood aside, recording that the dispatcher reached it."""

    def __init__(self, called: list[str], step: str, answer=False) -> None:
        self._called = called
        self._step = step
        self._answer = answer

    def __call__(self, *_args, **_kwargs):
        """Record this step and stand aside with the answer it was given."""
        self._called.append(self._step)
        return self._answer


@contextlib.contextmanager
def _stood_aside(called: list[str]):
    """Stand every neighbouring guard and the handler aside, in call order.

    Each owner is resolved when the case runs, exactly as the dispatcher
    resolves it, so a stage owner that moves takes this with it rather than
    leaving the assertion passing against a module nothing calls.
    """
    with contextlib.ExitStack() as chain:
        for step, owner, guard in _STAGE_CHAIN:
            chain.enter_context(patch.object(
                importlib.import_module(owner), guard, _Recorder(called, step),
            ))
        chain.enter_context(patch.object(
            _dispatch_guards, "_anchor_holds_the_tick",
            _Recorder(called, _RECOVERY),
        ))
        chain.enter_context(patch.object(
            _report_transaction, "_reconciles_pending_report",
            _Recorder(called, "report"),
        ))
        chain.enter_context(patch.object(
            _stage_targets, "_call_handler", _Recorder(called, "handler", None),
        ))
        yield


class DispatchOrderingTest(unittest.TestCase, support.ReportTransactionCase):
    """The guard runs behind the pause screen and ahead of no terminal."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)
        self.record()
        self.gh.write_pinned_state(self.issue, self.state)

    def test_the_guard_runs_in_the_required_place(self) -> None:
        # The required place in the chain, asserted as an order rather than as
        # an outcome: every neighbour stands aside, so what is left to observe
        # is where each one was called.
        #
        # Both recovery checks are in that sequence, and the second is what
        # this owner has to stay behind: a pair the size gate froze on an
        # interrupted rebase's own head is settled by the reconciliation above,
        # which leaves the anchor still pinned -- so a report published between
        # the two would go onto a pull request carrying an unfinalized replay.
        called: list[str] = []

        with self._seams(), _stood_aside(called):
            _issue_processing._process_issue(self.gh, _TEST_SPEC, self.issue)

        self.assertEqual(tuple(called), _REQUIRED_ORDER)

    def test_an_open_issue_publishes(self) -> None:
        # The control the two refusals below are read against: reached by the
        # real dispatch chain, this world settles.
        with self._seams():
            _dispatch_guards._pinned_state_refuses(
                self.gh, _TEST_SPEC, self.issue, LABEL_VALIDATING,
            )

        self.assertEqual(len(support.report_comments(self)), 1)

    def test_a_closed_issue_publishes_nothing(self) -> None:
        self.issue.closed = True

        with self._seams():
            refused = _dispatch_guards._pinned_state_refuses(
                self.gh, _TEST_SPEC, self.issue, LABEL_VALIDATING,
            )

        self.assertFalse(refused)
        self.assertEqual(support.report_comments(self), [])
        self.assertIsNotNone(
            _record_state.read_pending_report(self.gh.read_pinned_state(self.issue)),
        )

    def test_a_terminal_label_publishes_nothing(self) -> None:
        # A terminal label resolves to no handler at all, so the no-op behind
        # this guard protects nothing: an OPEN issue somebody has already
        # marked finished would otherwise publish a report and record a
        # handoff on its way to that no-op.
        for ended in (LABEL_DONE, LABEL_REJECTED):
            with self.subTest(label=ended):
                self.setUp()

                with self._seams():
                    refused = _dispatch_guards._pinned_state_refuses(
                        self.gh, _TEST_SPEC, self.issue, ended,
                    )

                self.assertFalse(refused)
                self.assertEqual(support.report_comments(self), [])
                self.assertIsNotNone(_record_state.read_pending_report(
                    self.gh.read_pinned_state(self.issue),
                ))

    def test_a_paused_issue_never_reaches_the_guard(self) -> None:
        self.issue.labels.append(FakeLabel(_PAUSED))

        with self._seams(), patch.object(
            _stage_targets, "_call_handler",
        ) as dispatched:
            _issue_processing._process_issue(self.gh, _TEST_SPEC, self.issue)
            dispatched.assert_not_called()

        self.assertEqual(support.report_comments(self), [])


class ForeignParkRecoveryTest(unittest.TestCase, support.ReportTransactionCase):
    """A park another route holds is answered through this guard, not behind it.

    The collision a unit test cannot see. This guard would park an unreadable
    record, and the pinned park flags are single -- so a record damaged on an
    issue a stage has already parked is one this owner may not write over. Held
    in front of the handler instead, the guard deadlocks what it is waiting
    for: the awaiting-human branch that answers a transient park runs BEHIND
    this guard, so it never runs, the foreign park never clears,
    `awaiting_human` stays set, and the next tick holds for the same reason.
    Both parks then stand for the life of the issue and neither the damage nor
    the recovery is ever announced.

    So it is driven through `_process_issue` twice: once with the foreign park
    standing, where the handler has to be reached, and once after the stage's
    own recovery has taken that park down, where the damage has to be
    announced. Either dispatch alone would pass over the deadlock.
    """

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)
        # A record a hand edit truncated, on an issue a stage has already
        # parked waiting for a human.
        self.state.set(_records.PENDING_REPORT, {"receipt": support.RECEIPT})
        self.state.set(support.AWAITING_HUMAN, True)
        self.state.set(support.PARK_REASON, _AGENT_TIMEOUT)
        self.gh.write_pinned_state(self.issue, self.state)

    def test_the_foreign_park_reaches_its_handler(self) -> None:
        notices = len(self.gh.posted_comments)

        self.assertEqual(self._dispatched(), 1)

        standing = self.gh.read_pinned_state(self.issue)
        self.assertEqual(standing.get(support.PARK_REASON), _AGENT_TIMEOUT)
        self.assertEqual(len(self.gh.posted_comments), notices)

    def test_the_damage_follows_the_recovery(self) -> None:
        # The tick after the foreign park goes is this owner's: the handler is
        # held and the damage is announced, which is what standing down in
        # front of it was waiting for rather than giving up on.
        notices = len(self.gh.posted_comments)
        self._dispatched()
        self._recovers()

        self.assertEqual(self._dispatched(), 0)

        held = self.gh.read_pinned_state(self.issue)
        self.assertEqual(held.get(support.PARK_REASON), support.PARK_DAMAGED)
        self.assertEqual(len(self.gh.posted_comments), notices + 1)
        self.assertTrue(_record_state.carries_pending_report(held))

    def _dispatched(self) -> int:
        """One real dispatch, answering with how many handlers it reached."""
        with self._seams(), patch.object(
            _stage_targets, "_call_handler",
        ) as dispatched:
            _issue_processing._process_issue(self.gh, _TEST_SPEC, self.issue)
            return dispatched.call_count

    def _recovers(self) -> None:
        """What a stage's awaiting-human branch does with a transient park."""
        standing = self.gh.read_pinned_state(self.issue)
        standing.set(support.AWAITING_HUMAN, False)
        standing.set(support.PARK_REASON, None)
        self.gh.write_pinned_state(self.issue, standing)


if __name__ == "__main__":
    unittest.main()
