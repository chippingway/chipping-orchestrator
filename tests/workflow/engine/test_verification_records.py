# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The evidence records' round trip: safe absences, refusals, revisions, and history.

An issue that predates these records carries none of their keys, and has to
read back as owing nothing, holding nothing, and having retired nothing -- with
a reconciliation that writes nothing over it. A record is accepted only where
it reads back identically and publishes, a later one abandons the earlier into
history rather than forgetting a receipt that may already be on the thread,
and the history index stays bounded without a later revision ever reusing one
it evicted.
"""
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import MAX_PINNED_BODY
from orchestrator.github.verification_evidence import VerifiedCommand
from orchestrator.workflow.engine import (
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import verification_evidence_test_support as support

# Past what one comment holds, so its artifact could never be posted.
_OVERSIZED_TRANSCRIPT = "x" * (MAX_PINNED_BODY + 1)

# More settlements than the history index keeps, and how many it keeps.
_SETTLEMENTS = 7

_HISTORY_KEPT = 5


def _retired(case) -> list[tuple]:
    """Each retired record by receipt and why it was retired, oldest first."""
    return [
        (entry.receipt, entry.retired)
        for entry in _settlement.read_evidence_history(case.state)
    ]


class AbsentRecordsTest(unittest.TestCase, support.VerificationEvidenceCase):
    """An issue that recorded no evidence owes, holds, and writes nothing."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)

    def test_an_issue_without_the_keys_owes_nothing(self) -> None:
        self.gh.write_pinned_state(self.issue, self.state)
        writes = self.gh.write_state_calls

        self.assertFalse(self.reconcile())

        self.assertFalse(_record_state.carries_pending_evidence(self.state))
        self.assertEqual(
            (
                _record_state.read_pending_evidence(self.state),
                _settlement.read_current_evidence(self.state),
                _settlement.read_evidence_history(self.state),
                _settlement.read_evidence_handoff(self.state),
            ),
            (None, None, (), None),
        )
        self.assertEqual(self.gh.write_state_calls, writes)

    def test_damage_reads_as_nothing_to_rely_on(self) -> None:
        self.state.set(_records.CURRENT_EVIDENCE, {"receipt": "issue-7-verification-1"})
        self.state.set(_records.EVIDENCE_HISTORY, {"not": "a list"})

        self.assertIsNone(_settlement.read_current_evidence(self.state))
        self.assertIsNone(_settlement.read_evidence_history(self.state))
        # Retiring what nobody can read clears it and indexes nothing.
        self.assertTrue(_settlement.retire_current_evidence(self.state))
        self.assertIsNone(self.state.get(_records.CURRENT_EVIDENCE))


class RecordingTest(unittest.TestCase, support.VerificationEvidenceCase):
    """A record is accepted only where it reads back and its artifact can be posted."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)

    def test_an_unpublishable_record_is_refused(self) -> None:
        # A review subject about another pull request reads back as damage,
        # and a transcript past one comment is an artifact nobody can post.
        target = self.binding().target
        foreign = dict(target.subject, pr=support.PR_NUMBER + 1)
        refused = (
            self.minted(self.binding(target=_records.EvidenceTarget(target.publication, foreign))),
            self.minted(self.binding(), _OVERSIZED_TRANSCRIPT),
        )
        before = dict(self.state.data)

        for pending in refused:
            self.assertFalse(_record_state.record_pending_evidence(self.state, pending))

        self.assertEqual(self.state.data, before)

    def minted(
        self, binding: _records.EvidenceBinding, output: str = "12 passed",
    ) -> _records.PendingEvidence:
        """A transaction for `binding` whose one command printed `output`."""
        ran = VerifiedCommand(command=support.SUITE, exit_status=0, output=output)
        return _record_state.mint_pending_evidence(
            self.state, support.ISSUE_NUMBER, binding, (ran,),
        )

    def test_a_later_record_abandons_the_earlier(self) -> None:
        first = self.record()
        again = _record_state.record_pending_evidence(self.state, first)
        second = self.record()

        self.assertTrue(again)
        self.assertEqual(second.revision, first.revision + 1)
        self.assertNotEqual(second.receipt, first.receipt)
        self.assertEqual(_retired(self), [(first.receipt, _records.Retirement.ABANDONED)])
        self.assertEqual(_record_state.read_pending_evidence(self.state), second)


class HistoryTest(unittest.TestCase, support.VerificationEvidenceCase):
    """Current evidence retires into a bounded history; revisions never repeat."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)

    def test_an_invalidation_keeps_it_whole(self) -> None:
        settled = self.record()
        self.reconcile()

        self.assertTrue(_settlement.retire_current_evidence(self.state))

        # Kept whole: the report revision and digest and the complete review
        # subject survive, though the artifact names only the subject's head.
        self.assertIsNone(_settlement.read_current_evidence(self.state))
        self.assertEqual(
            [
                (entry.receipt, entry.retired, entry.binding)
                for entry in _settlement.read_evidence_history(self.state)
            ],
            [(settled.receipt, _records.Retirement.INVALIDATED, settled.binding)],
        )
        self.assertEqual(
            settled.binding.target.subject, self.subject.recorded(),
        )
        self.assertFalse(_settlement.retire_current_evidence(self.state))

    def test_history_is_bounded_and_revisions_move_on(self) -> None:
        for _ in range(_SETTLEMENTS):
            self.record()
            self.reconcile()

        following = _record_state.mint_pending_evidence(
            self.state, support.ISSUE_NUMBER, self.binding(), (),
        )
        self.assertEqual(
            [entry.revision for entry in _settlement.read_evidence_history(self.state)],
            list(range(_SETTLEMENTS - _HISTORY_KEPT, _SETTLEMENTS)),
        )
        self.assertEqual(
            _settlement.read_current_evidence(self.state).revision, _SETTLEMENTS,
        )
        self.assertEqual(following.revision, _SETTLEMENTS + 1)


if __name__ == "__main__":
    unittest.main()
