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
whole despite the restoration -- as it is where another proof blanked the
attempt's base tip there to record movement, and that tip was put back, and
where that finish marked movement in the run's handoff place or spent a
revision past it on the floor, and the records its settlement left were put
back: the edit read only evidence records moving, but moving to movement
recorded under the run. With that finish's announcement of the landing in
the review's place, the edit read only the evidence records and the attempt's
members moved, neither a record any binding rests on, so the settlement
adopted stays current. Nothing runs.
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

# The attempt members another finish's announcement of the landing moves.
_ANNOUNCEMENT = (readings.KEY_ANNOUNCED, readings.KEY_ANNOUNCED_EVENT)

# The client's strict edit of the pinned comment, which a case makes another finish's moves under.
_EDIT = "edit_pinned_state"


def _blanks_the_base_tip(case) -> None:
    """Another readiness proof blanking the attempt's base tip, recording movement read under the run."""
    settled_moves.writes_over(case, readings.KEY_REWRITE_BASE, None)


def _marks_the_run(case) -> None:
    """Another finish's mark of movement read under the settled run, written in its handoff's place."""
    settled_moves.writes_over(case, _records.EVIDENCE_HANDOFF, {"moved": case.captured.receipt})


def _spends_past_the_run(case) -> None:
    """Another finish's revision spent past the settled run on the floor, recording movement read under it."""
    settled_moves.writes_over(case, readings.KEY_REVISION_FLOOR, case.captured.revision + 1)


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
    """The strict edit, its first call made just as another finish settles the run and makes `move` beside it.

    The records `keys` names are put back exactly as the settlement left them
    -- one missing then removed -- right behind that edit's own reading of
    the comment, so it answers over a comment that moved and leaves one that
    reads as the settlement left it before `move`. `settled` is the run as
    that settlement made it current.
    """

    def __init__(self, case, move, keys: tuple[str, ...]) -> None:
        self._case = case
        self._move = move
        self._keys = keys
        self._edit = case.gh.edit_pinned_state
        self._walk = case.gh._pinned_comment
        self._owed = True
        self.kept: dict = {}
        self.settled = None

    def __call__(self, issue, state, **options):
        if not self._owed:
            return self._edit(issue, state, **options)
        self._owed = False
        _settles(self._case, self._case.captured)
        self.settled = self._case.records()[1]
        self.kept = self.left()
        self._move(self._case)
        with patch.object(self._case.gh, "_pinned_comment", self._walks):
            return self._edit(issue, state, **options)

    def left(self) -> dict:
        """The records `keys` names, as the comment carries them now."""
        pinned = readings.pinned(self._case)
        return {key: pinned[key] for key in self._keys if key in pinned}

    def _walks(self, *located):
        """The edit's walk to the comment, the records `keys` names put back right behind it."""
        found = self._walk(*located)
        restored = self._case.gh.read_pinned_state(self._case.issue)
        for key in self._keys:
            restored.data.pop(key, None)
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
        edits = _MovesUnderTheEdit(self, settled_moves.reviews_again, _REPORT_RECORDS)

        with patch.object(self.gh, _EDIT, edits):
            self.asks(_settlement_step.resolves, settled.dormant(self.landed()))

        self._assert_retired(edits)

    def test_a_restored_base_tip_blank_is_movement(self) -> None:
        # Another finish settles the captured run and another proof blanks
        # the attempt's base tip -- the movement it read under the run,
        # recorded where nothing else had room -- just as the phase's
        # settlement edit reads the comment, and the tip is put back before
        # that edit answers: the mark that edit read is movement, so the
        # settlement adopted is invalidated whole all the same.
        edits = _MovesUnderTheEdit(self, _blanks_the_base_tip, (readings.KEY_REWRITE_BASE,))

        with patch.object(self.gh, _EDIT, edits):
            self.asks(_settlement_step.resolves, settled.dormant(self.landed()))

        self._assert_retired(edits)

    def test_a_restored_movement_mark_is_movement(self) -> None:
        # Another finish settles the captured run and marks movement it read
        # under it in its handoff's place just as the phase's settlement edit
        # reads the comment, and the settlement's handoff is put back before
        # that edit answers: the edit read only an evidence record move, but
        # one recording movement under the run, so the settlement adopted is
        # invalidated whole all the same.
        edits = _MovesUnderTheEdit(self, _marks_the_run, (_records.EVIDENCE_HANDOFF,))

        with patch.object(self.gh, _EDIT, edits):
            self.asks(_settlement_step.resolves, settled.dormant(self.landed()))

        self._assert_retired(edits)

    def test_a_restored_spent_revision_is_movement(self) -> None:
        # Another finish settles the captured run and spends a revision past
        # it on the floor just as the phase's settlement edit reads the
        # comment, and the floor is put back before that edit answers: the
        # revision that edit read outranks the run, so the settlement adopted
        # is invalidated whole all the same.
        edits = _MovesUnderTheEdit(self, _spends_past_the_run, (readings.KEY_REVISION_FLOOR,))

        with patch.object(self.gh, _EDIT, edits):
            self.asks(_settlement_step.resolves, settled.dormant(self.landed()))

        self._assert_retired(edits)

    def test_a_restored_announcement_moves_nothing(self) -> None:
        # Another finish settles the captured run and announces the landing
        # just as the phase's settlement edit reads the comment, and the
        # announcement is put back before that edit answers: the comment it
        # read moved the evidence records and the attempt's announcement
        # members alone, which no binding rests on, so the settlement adopted
        # stays current as that finish made it, its run posted once and
        # nothing run, with the announcement as it was put back.
        edits = _MovesUnderTheEdit(self, retirement.announces, _ANNOUNCEMENT)

        with patch.object(self.gh, _EDIT, edits):
            self.asks(_settlement_step.resolves, settled.dormant(self.landed()))

        pending, current = self.records()[:2]
        self.assertEqual((pending, current.receipt), (None, self.captured.receipt))
        self.assertEqual(edits.left(), edits.kept)
        receipts = [found.receipt for found in support.posted_artifacts(self)]
        self.assertEqual(receipts.count(self.captured.receipt), 1)
        self.assertEqual(self.verify.call_count, 0)

    def _assert_retired(self, edits: _MovesUnderTheEdit) -> None:
        """The settlement adopted invalidated whole, its provenance kept and its run posted once; `edits` put back.

        Its history entry is the run exactly as that settlement made it
        current -- receipt, revision, binding, transcript, verdict, and
        artifact -- and nothing ran, launched, or relabelled.
        """
        current, history = self.records()[1:]
        self.assertIsNone(current)
        self.assertEqual(history[-1], (self.captured.receipt, readings.INVALIDATED))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual(entry, _records.HistoricalEvidence.of(edits.settled, _records.Retirement.INVALIDATED))
        self.assertEqual(edits.left(), edits.kept)
        receipts = [found.receipt for found in support.posted_artifacts(self)]
        self.assertEqual(receipts.count(self.captured.receipt), 1)
        ran = (self.verify.call_count, self.developer.call_count, readings.relabels(self))
        self.assertEqual(ran, (0, 0, ()))


if __name__ == "__main__":
    unittest.main()
