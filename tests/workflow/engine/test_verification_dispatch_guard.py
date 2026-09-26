# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The evidence reconciliation behind the guards every dispatch already passes.

Its place in the chain -- directly behind the developer-report transaction and
ahead of the reuse guard and the handler -- is pinned with the rest of that
chain in `test_report_dispatch_guard.py`. What is pinned here is what it does
from there. Reached through the real chain on a live issue, it settles. And it
stands aside, publishing and dropping nothing, on every issue the dispatcher
would hand it that is not live work: closed, labelled `done` or `rejected`,
held by a hard-skip control label, or carrying no workflow label at all -- so a
reopen or a relabel finds the record exactly as it was.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import (
    dispatch_guards as _dispatch_guards,
    verification_record_state as _record_state,
    verification_settlement_state as _settlement,
)
from tests.support.github.models import FakeLabel
from tests.workflow.engine import verification_evidence_test_support as support
from tests.workflow.fixtures import _TEST_SPEC, LABEL_DONE, LABEL_REJECTED

_PAUSED = "paused"


def _closes(case) -> None:
    case.issue.closed = True


def _labels_done(case) -> None:
    case.label = LABEL_DONE


def _labels_rejected(case) -> None:
    case.label = LABEL_REJECTED


def _pauses(case) -> None:
    case.issue.labels.append(FakeLabel(_PAUSED))


def _unlabels(case) -> None:
    case.label = None


class EvidenceDispatchTest(unittest.TestCase, support.VerificationEvidenceCase):
    """Live work settles through the chain; anything else is left as it stands."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.pending = self.record()

    def test_the_real_chain_settles_live_work(self) -> None:
        with self.seams():
            refused = _dispatch_guards._pinned_state_refuses(
                self.gh, _TEST_SPEC, self.issue, self.label,
            )

        persisted = self.gh.read_pinned_state(self.issue)
        self.assertFalse(refused)
        self.assertEqual(len(self.artifacts()), 1)
        self.assertEqual(
            _settlement.read_current_evidence(persisted).receipt, self.pending.receipt,
        )

    def test_work_that_is_not_live_is_left_alone(self) -> None:
        for moves in (_closes, _labels_done, _labels_rejected, _pauses, _unlabels):
            with self.subTest(move=moves.__name__):
                self.setUp()
                moves(self)
                writes = self.gh.write_state_calls

                with self.assertLogs(support.WORKFLOW_LOG, "INFO"):
                    self.assertFalse(self.reconcile())

                self.assertEqual(self.artifacts(), [])
                self.assertEqual(self.gh.write_state_calls, writes)
                self.assertEqual(
                    _record_state.read_pending_evidence(self.state), self.pending,
                )


if __name__ == "__main__":
    unittest.main()
