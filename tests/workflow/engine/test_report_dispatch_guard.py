# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where the report reconciliation sits among the guards ahead of every handler.

Three orderings decide whether a report is published, on which world, and on an
issue anybody still wants -- and none of them is visible from the
reconciliation's own unit tests.

The first is the PLACE in the guard chain, which is pinned here by call order
rather than by outcome. Ahead of the outstanding-publication reconciliation the
guard would read a candidate mid-gate as one whose code was never published and
stand down on every tick; behind the reuse guard or the handler it would let a
reviewer be spawned over a report nobody published. Both failures leave every
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

# The guards this one has to run between, named by the owner each is read off
# and the step it stands for. Resolved when the case runs, exactly as the
# dispatcher resolves them, so a stage owner that moves takes this table with
# it rather than leaving it passing against a module nothing calls.
_CHAIN = (
    ("adjudication", _stage_targets._LATE_RELABEL_OWNER, "_holds_the_label"),
    ("publication", _stage_targets._LATE_RECONCILE_OWNER, "_reconciles_published_work"),
    ("reuse", _stage_targets._LATE_REUSE_OWNER, "_refuses_reuse"),
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
        for step, owner, guard in _CHAIN:
            chain.enter_context(patch.object(
                importlib.import_module(owner), guard, _Recorder(called, step),
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
        called: list[str] = []

        with self._seams(), _stood_aside(called):
            _issue_processing._process_issue(self.gh, _TEST_SPEC, self.issue)

        self.assertEqual(
            called,
            ["adjudication", "publication", "report", "reuse", "handler"],
        )

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


if __name__ == "__main__":
    unittest.main()
