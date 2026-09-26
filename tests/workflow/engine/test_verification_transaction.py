# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the evidence reconciliation settles, and how every crash window replays.

The crash windows are the point of the transaction, so each is written as the
place a process can die: after GitHub accepted an artifact whose response never
came back, after the artifact landed and before the settling write, and after
the settlement landed with the record somehow still standing. Each is replayed
by running the reconciliation again over the comment the first run persisted,
and each has to end with one artifact on the thread, one current record, and
the transaction's receipt as the handoff.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.github.verification_evidence import EvidenceSource
from orchestrator.workflow.engine import (
    verification_record_fields as _fields,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import verification_evidence_test_support as support

_GITHUB_LOG = "orchestrator.github"

_WARNING = "WARNING"

_FAILED = 1


def _history(case) -> list[tuple]:
    """Each retired record by receipt and why it was retired, oldest first."""
    return [
        (entry.receipt, entry.retired)
        for entry in _settlement.read_evidence_history(case.state)
    ]


class SettledEvidenceTest(unittest.TestCase, support.VerificationEvidenceCase):
    """A proved transaction publishes once, becomes current, and keeps the earlier as history."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)

    def test_a_proved_transaction_settles(self) -> None:
        pending = self.record()

        self.assertFalse(self.reconcile())

        current = _settlement.read_current_evidence(self.state)
        self.assertEqual(
            [(found.receipt, found.content_revision) for found in self.artifacts()],
            [(pending.receipt, current.content_revision)],
        )
        self.assertEqual(
            (current.binding, current.passed), (pending.binding, True),
        )
        self.assertEqual(
            _settlement.read_evidence_handoff(self.state),
            _records.EvidenceHandoff(
                receipt=pending.receipt,
                pr_number=support.PR_NUMBER,
                revision=pending.revision,
                target_head=support.TESTED_SHA,
                settled_under=support.LABEL_VALIDATING,
            ),
        )
        self.assertIsNone(self.state.get(_records.PENDING_EVIDENCE))
        # Tracked as ours, so the artifact never reads back as a human's feedback.
        self.assertIn(current.comment_id, self.state.get(support.LEDGER))

    def test_a_settled_issue_owes_nothing(self) -> None:
        self.record()
        self.reconcile()
        writes = self.gh.write_state_calls

        self.assertFalse(self.reconcile())

        self.assertEqual(len(self.artifacts()), 1)
        self.assertEqual(self.gh.write_state_calls, writes)

    def test_later_evidence_supersedes(self) -> None:
        # A reviewer's account of a failed command is evidence too, and stays
        # actionable as the current record; the passing run before it is
        # history, not relabelled.
        first = self.record()
        self.reconcile()
        second = self.record(
            self.binding(source=EvidenceSource.REVIEWER_REPORTED), exit_status=_FAILED,
        )

        self.reconcile()

        current = _settlement.read_current_evidence(self.state)
        self.assertEqual(
            [found.artifact_revision for found in self.artifacts()],
            [first.revision, second.revision],
        )
        self.assertEqual((current.receipt, current.passed), (second.receipt, False))
        self.assertEqual(
            _history(self), [(first.receipt, _records.Retirement.SUPERSEDED)],
        )


class ReplayedEvidenceTest(unittest.TestCase, support.VerificationEvidenceCase):
    """Every window a process can die in replays to one artifact and one settlement."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.pending = self.record()

    def test_an_accepted_post_whose_response_was_lost(self) -> None:
        self.gh.report_failures.lost.add(support.PR_NUMBER)
        with self.assertLogs(_GITHUB_LOG, _WARNING):
            held = self.reconcile()
        self.gh.report_failures.lost.clear()

        replayed = self.reconcile()

        self.assertEqual((held, replayed), (True, False))
        self.assertEqual(len(self.artifacts()), 1)
        self.assertEqual(
            _settlement.read_current_evidence(self.state).receipt,
            self.pending.receipt,
        )

    def test_a_settling_write_that_never_landed(self) -> None:
        with patch.object(
            self.gh, "write_pinned_state", side_effect=RuntimeError("write lost"),
        ), self.assertRaises(RuntimeError):
            self.reconcile()

        self.assertFalse(self.reconcile())

        self.assertEqual(len(self.artifacts()), 1)
        self.assertEqual(
            _settlement.read_evidence_handoff(self.state).receipt,
            self.pending.receipt,
        )

    def test_a_record_its_own_handoff_settled(self) -> None:
        # The settlement landed; a record standing beside its own handoff is
        # dropped rather than published a second time or moved into history.
        self.reconcile()
        self.state.set(_records.PENDING_EVIDENCE, _fields.pending_object(self.pending))
        self.gh.write_pinned_state(self.issue, self.state)

        self.assertFalse(self.reconcile())

        self.assertEqual(len(self.artifacts()), 1)
        self.assertIsNone(self.state.get(_records.PENDING_EVIDENCE))
        self.assertEqual(_history(self), [])


class RetiredEvidenceTest(unittest.TestCase, support.VerificationEvidenceCase):
    """What can never settle is retired, never published and never parked."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)

    def test_an_ended_pull_request_abandons_it(self) -> None:
        pending = self.record()
        self.pull_request.state = "closed"

        with self.assertLogs(support.WORKFLOW_LOG, "INFO"):
            self.assertFalse(self.reconcile())

        self.assertEqual(
            _history(self), [(pending.receipt, _records.Retirement.ABANDONED)],
        )
        self.assertEqual(self.artifacts(), [])
        self.assertFalse(_record_state.carries_pending_evidence(self.state))

    def test_an_unreadable_record_is_dropped(self) -> None:
        self.state.set(_records.PENDING_EVIDENCE, {"receipt": "issue-7-verification-1"})
        self.gh.write_pinned_state(self.issue, self.state)

        with self.assertLogs(support.WORKFLOW_LOG, "ERROR"):
            self.assertFalse(self.reconcile())

        self.assertIsNone(self.state.get(_records.PENDING_EVIDENCE))
        self.assertFalse(self.state.get("awaiting_human"))
        self.assertEqual(self.artifacts(), [])

    def test_evidence_older_than_settled_is_abandoned(self) -> None:
        # Recorded, then overtaken before its tick by a later one that settled
        # -- a restored comment is the only way to reach it -- so publishing it
        # now would put an older run over a newer one.
        stale = self.record()
        restored = self.gh.pinned_data(support.ISSUE_NUMBER)[_records.PENDING_EVIDENCE]
        newer = self.record()
        self.reconcile()
        self.state.set(_records.PENDING_EVIDENCE, restored)
        self.gh.write_pinned_state(self.issue, self.state)

        with self.assertLogs(support.WORKFLOW_LOG, "INFO"):
            self.assertFalse(self.reconcile())

        self.assertEqual(
            _history(self)[-1], (stale.receipt, _records.Retirement.ABANDONED),
        )
        self.assertEqual(
            _settlement.read_current_evidence(self.state).receipt, newer.receipt,
        )
        self.assertEqual(len(self.artifacts()), 1)


if __name__ == "__main__":
    unittest.main()
