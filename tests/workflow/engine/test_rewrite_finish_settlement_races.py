# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Another finish's settlement under the dormant evidence phase's own writes, told by what moved beside it.

The retirement case (`receipt_retirement_support`) and the captured case
(`rewrite_captured_test_support.CapturedEvidenceCase`), the evidence phase
asked directly over a finish held to the dormant settled-evidence policy.
A settlement another finish makes of a newer transaction just as the phase
lands the invalidation the configuration owes the settled run moves the
evidence records alone: that refusal is no movement under the newer
transaction, whose settlement stays current under either policy. A
settlement another finish makes of the captured run, with a later review
handed over just as the phase's own settlement edit reads the comment and
put back before that edit answers, moved the run's binding all the same: the
comment the edit read names it, and the settlement adopted is invalidated
whole despite the restoration. Nothing runs.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator.workflow.engine import (
    rewrite_finish_settlement as _settlement_step,
    rewrite_finish_writes as _writes,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from tests.workflow.engine import (
    receipt_retirement_support as retirement,
    rewrite_captured_test_support as captured_support,
    rewrite_finish_evidence_test_support as finish_support,
    rewrite_finish_readings as readings,
    rewrite_settled_moves as settled_moves,
    settled_finish_support as settled,
    verification_evidence_test_support as support,
    verification_record_test_support as record_support,
)
from tests.workflow.interleaving import _RacesTheStep

# Why a record a newer settlement replaced as current retired, as history spells it.
_SUPERSEDED = _records.Retirement.SUPERSEDED.value

# The report and review records a later review moves, as the pinned comment spells them.
_REPORT_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")


def _settles(case, pending) -> None:
    """Post `pending`'s artifact and settle it over the comment as it stands, as another finish would; once."""
    state = case.gh.read_pinned_state(case.issue)
    if _record_state.read_pending_evidence(state) != pending:
        return
    posted = case.gh.publish_verification_artifact(case.pull_request, pending.artifact)
    case.gh.write_pinned_state(case.issue, _settlement.settled_state(
        state, pending, posted.landed_id, finish_support.REVIEWING,
    ))


class _MovesUnderTheEdit:
    """The strict edit, its first call made just as another finish settles the run and a later review is handed over.

    The report and review records are put back right behind that edit's own
    reading of the comment, so it answers over a comment that moved and
    leaves one that reads as it did before the review.
    """

    def __init__(self, case) -> None:
        self._case = case
        self._edit = case.gh.edit_pinned_state
        self._walk = case.gh._pinned_comment
        self._owed = True
        self.kept: dict = {}

    def __call__(self, issue, state, **options):
        if not self._owed:
            return self._edit(issue, state, **options)
        self._owed = False
        pinned = readings.pinned(self._case)
        self.kept = {key: pinned.get(key) for key in _REPORT_RECORDS}
        _settles(self._case, self._case.captured)
        settled_moves.reviews_again(self._case)
        with patch.object(self._case.gh, "_pinned_comment", self._walks):
            return self._edit(issue, state, **options)

    def _walks(self, *located):
        """The edit's walk to the comment, the report and review records put back right behind it."""
        found = self._walk(*located)
        restored = self._case.gh.read_pinned_state(self._case.issue)
        for key, kept in self.kept.items():
            restored.set(key, kept)
        self._case.gh.write_pinned_state(self._case.issue, restored)
        return found


class EvidenceOnlyRefusalTest(retirement.RetirementCase, unittest.TestCase):
    """A refusal of the phase's own write over the evidence records alone moves nothing a binding rests on."""

    def test_the_newer_settlement_is_kept(self) -> None:
        # The configuration moved past the settled run, and a newer
        # transaction of the head is recorded under the configuration in
        # place now. Another finish settles it just as the phase lands the
        # invalidation the run is owed, refusing that write over the evidence
        # records alone: the newer settlement stays current under either
        # policy, the run superseded by it, and nothing runs.
        for held in (True, False):
            with self.subTest(held=held):
                self.setUp()
                settled_moves.reconfigures(self)
                newer = self._records_under_the_new_configuration()
                finish = self.dormant() if held else self.landed()
                lands = _RacesTheStep(_writes.lands, partial(_settles, self, newer))

                with patch.object(_writes, "lands", lands):
                    self.assertEqual(self.asks(_settlement_step.resolves, finish), FinishOutcome.REFUSED)

                self._assert_current(newer)

    def _assert_current(self, newer) -> None:
        """`newer` settled current, nothing pending, the run superseded by it, and nothing run."""
        pending, current, history = self.records()
        self.assertEqual((pending, current.receipt), (None, newer.receipt))
        self.assertEqual(history[-1], (self.settled.receipt, _SUPERSEDED))
        self.assertEqual(self.verify.call_count, 0)

    def _records_under_the_new_configuration(self):
        """Another road's newer transaction of the head, bound to the configuration in place now; it."""
        state = self.gh.read_pinned_state(self.issue)
        binding = replace(self.settled.binding, context_revision=_proof.configured_context_revision())
        newer = _record_state.mint_pending_evidence(state, support.ISSUE_NUMBER, binding, (record_support.ran(),))
        self.assertTrue(_record_state.record_pending_evidence(state, newer))
        self.gh.write_pinned_state(self.issue, state)
        return newer


class RestoredUnderTheEditTest(captured_support.CapturedEvidenceCase, unittest.TestCase):
    """Binding movement the settlement edit read is movement, however soon it was put back."""

    def test_the_adopted_run_is_retired_whole(self) -> None:
        # Another finish settles the captured run and a later review is
        # handed over just as the phase's settlement edit reads the comment,
        # and the review is put back before that edit answers: the comment it
        # read moved the run's binding, so the settlement adopted is
        # invalidated whole, its revision and binding kept, with the report
        # and review records as they were put back and nothing run.
        edits = _MovesUnderTheEdit(self)

        with patch.object(self.gh, "edit_pinned_state", edits):
            self.asks(_settlement_step.resolves, settled.dormant(self.landed()))

        pinned = readings.pinned(self)
        current, history = self.records()[1:]
        self.assertIsNone(current)
        self.assertEqual(history[-1], (self.captured.receipt, readings.INVALIDATED))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual(entry.revision, self.captured.revision)
        self.assertEqual(entry.binding, self.captured.binding)
        self.assertEqual({key: pinned.get(key) for key in _REPORT_RECORDS}, edits.kept)
        self.assertEqual(self.verify.call_count, 0)


if __name__ == "__main__":
    unittest.main()
