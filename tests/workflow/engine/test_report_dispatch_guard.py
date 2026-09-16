# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where the report reconciliation sits among the guards ahead of every handler.

Two orderings decide whether a report is ever published on an issue nobody
wants, and neither is visible from the reconciliation's own unit tests.

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

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import (
    dispatch_guards as _dispatch_guards,
    issue_processing as _issue_processing,
    report_record_state as _record_state,
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


class DispatchOrderingTest(unittest.TestCase, support.ReportTransactionCase):
    """The guard runs behind the pause screen and ahead of no terminal."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)
        self.record()
        self.gh.write_pinned_state(self.issue, self.state)

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
