# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A current record's write that did not land is still finished by the next admitted dispatch, once.

The admission every dispatch takes its record through refuses only what it
cannot read as current, so a current record whose developer-report settlement
was refused, or sent and never confirmed, is admitted again and read back:
the pull request carries one report, the handoff is recorded, and the
lifetime runs the record has spent stay spent. Driven through the sequential
poll's own entry, so each pass decides on the record read under the issue's
writer claim; the stage handler behind the guards is stood aside and counted.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import (
    dispatch as _dispatch,
    report_settlement_state as _settlement,
    run_ledger_values as _run_ledger_values,
    stage_targets as _stage_targets,
)
from tests.workflow.engine import (
    report_commit_test_support as commit_support,
    report_transaction_test_support as support,
)
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.observation_support import ObservedCloseCase, read_now

# The lifetime runs the record has spent, against an allowance with room left.
_CHARGED = 2
_RUN_ALLOWANCE = 10

# The request a published report goes out as.
_POST = "publish_developer_report"

_FOREIGN_PARK_REASON = "agent_timeout"

# A park another road takes while the report is being posted.
_FOREIGN_PARK = MappingProxyType({support.PARK_REASON: _FOREIGN_PARK_REASON, support.AWAITING_HUMAN: True})


class CurrentRecordRecoveryTest(ObservedCloseCase, unittest.TestCase, support.ReportTransactionCase):
    """A settlement that did not land is finished by the next dispatch, with one report and no refund."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)
        self._fresh_process()
        allowance = patch.object(config, "MAX_AGENT_RUNS_PER_ISSUE", _RUN_ALLOWANCE)
        allowance.start()
        self.addCleanup(allowance.stop)
        self.state.set(_run_ledger_values.AGENT_RUNS_USED, _CHARGED)
        self.record()
        commit_support.pinned((self.gh, self.issue), self.state)

    def test_an_unconfirmed_settlement_is_read_back(self) -> None:
        # GitHub took the settlement and its answer never came back, so the
        # first pass holds; the next reads the comment back, finds nothing
        # owed, and goes on to the handler writing nothing again.
        self.gh.pinned_failures.lost.add(support.ISSUE_NUMBER)
        self.assertEqual(self._dispatched(), 0)
        self.gh.pinned_failures.lost.discard(support.ISSUE_NUMBER)
        written = self.gh.write_state_calls

        self.assertEqual(self._dispatched(), 1)

        self.assertEqual(self.gh.write_state_calls, written)
        self._assert_settled_once()

    def test_a_refused_settlement_is_finished_once(self) -> None:
        # A park another road took while the report was being posted moved the
        # comment, so the settlement was refused with nothing written over it.
        # The next pass finds the report by its receipt and settles it,
        # posting nothing again and leaving that park standing.
        with commit_support.behind(self.gh, self.issue, _POST, **_FOREIGN_PARK):
            self.assertEqual(self._dispatched(), 0)

        self.assertEqual(self._dispatched(), 1)

        self._assert_settled_once()
        self.assertEqual(self.gh.pinned_data(support.ISSUE_NUMBER)[support.PARK_REASON], _FOREIGN_PARK_REASON)

    def _dispatched(self) -> int:
        """One sequential pass over the issue, answering how many handlers it reached."""
        with self._seams(), patch.object(_stage_targets, "_call_handler") as dispatched:
            _dispatch._process_polled_issue(self.gh, _TEST_SPEC, self.issue, read_at=read_now())
            return dispatched.call_count

    def _assert_settled_once(self) -> None:
        """One report on the pull request, its handoff recorded, and the lifetime charge where it was."""
        support.assert_one_report(self)
        settled = self.gh.read_pinned_state(self.issue)
        self.assertEqual(
            (_settlement.read_handoff(settled).receipt, settled.get(_run_ledger_values.AGENT_RUNS_USED)),
            (support.RECEIPT, _CHARGED),
        )


if __name__ == "__main__":
    unittest.main()
