# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A successor another road settles right behind a recovery proof's invalidation of the run, proved on its own.

The guarded recovery case (`guarded_recovery_support`): issue #7's run
settled and its finish killed before its announcement, the recovery context
read off the comment handed straight to the proof before a park or the
guarded park (`rewrite_recovery_parks`), as a recovery road does.

- Over a reset already recorded by blanking the base tip, a newer run settled
  right behind the run's invalidation, the tip put back behind the next
  reading, is invalidated whole -- before a park, and before a raised
  notice's error goes on.
- With the tip staged back behind a reset git refused, the run the tick holds
  stands, and a newer run settled beside the comment's blank is invalidated.
- Behind a mark's invalidation, a newer run settled as the issue's
  requirements move is taken in by the recheck and invalidated by its own
  proof.

Nothing is run again, pushed, or launched.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.github.pinned_state import PinnedEdit
from orchestrator.workflow.engine import (
    rewrite_recovery_parks as _parks,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_readings as readings,
    settled_finish_support as settled_support,
)

# A requirement added to the issue body, which moves every binding taken under the requirements before it.
_ADDED_REQUIREMENT = "\n\n- Also cover a base the reset recorded."

# The park a case hands the guarded park directly.
_PARKS = partial(_parks.lands_a_park, message="The auto rebase needs a human.", reason="auto_base_rebase_push_failed")


class _SettlesBehindTheInvalidation:
    """A newer run settled right behind the write invalidating `run`, carrying its binding, kept as `successor`.

    `tip`, where given, is the base tip the attempt recorded before the reset
    blanked it, put back right behind the next reading of the comment;
    `edits_the_issue` moves the issue's requirements beside the newer run.
    """

    def __init__(self, case, run, *, tip: str | None = None, edits_the_issue: bool = False) -> None:
        self._case = case
        self.run = run
        self.tip = tip
        self._edits_the_issue = edits_the_issue
        self._read = case.gh.read_pinned_state
        self._edit = case.gh.edit_pinned_state
        self._restores = False
        self.successor = None

    def reads(self, issue):
        """The comment, read; the first reading behind the newer run has the tip put back right behind it."""
        read = self._read(issue)
        if self._restores:
            self._restores = False
            restored = self._read(issue)
            restored.set(readings.KEY_REWRITE_BASE, self.tip)
            self._case.gh.write_pinned_state(issue, restored)
        return read

    def edits(self, issue, staged, **options):
        """The strict edit; the first landing with nothing current has the newer run settled right behind it."""
        edited = self._edit(issue, staged, **options)
        invalidates = staged.get(_records.CURRENT_EVIDENCE) is None
        if edited is PinnedEdit.EDITED and self.successor is None and invalidates:
            self.successor = settled_support.records_a_newer_run(self._case, settles=True, binding=self.run.binding)
            self._restores = self.tip is not None
            if self._edits_the_issue:
                self._case.issue.body += _ADDED_REQUIREMENT
        return edited


class AdoptedSuccessorTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A successor settled right behind the run's invalidation is proved on its own receipt, however clean it reads."""

    def test_a_successor_before_a_park(self) -> None:
        # The proof invalidates the run over the recorded blank, and the recheck behind takes in the newer
        # run settled right behind that write, read beside the blank: it is invalidated whole.
        races, context = self._races()
        with self._racing(races):
            _parks.proves_before_a_park(context)

        self._assert_retired(races.successor)

    def test_a_successor_behind_a_raised_notice(self) -> None:
        # The park's notice raises, and the proof taken before that error goes on meets the same race.
        races, context = self._races()
        posts = patch.object(self.gh, "comment", side_effect=RuntimeError("GitHub did not answer the notice's post"))
        with self._racing(races), posts:
            self.assertRaises(RuntimeError, _PARKS, context)

        self._assert_retired(races.successor)

    def test_a_tip_staged_back(self) -> None:
        # The tip is staged back behind a reset git refused, the comment still blank: alone, the run the
        # tick holds stands for the park; a newer run settled beside that blank is invalidated whole.
        for settles in (False, True):
            with self.subTest(successor=settles):
                self.setUp()
                races, context = self._races()
                context.state.set(readings.KEY_REWRITE_BASE, races.tip)
                successor = None
                if settles:
                    successor = settled_support.records_a_newer_run(self, settles=True, binding=races.run.binding)
                self.assertTrue(_parks.proves_before_a_park(context))

                if successor is not None:
                    self._assert_retired(successor)
                    continue
                self.assertEqual(readings.pinned_records(self)[1].receipt, races.run.receipt)

    def test_a_successor_under_moved_requirements(self) -> None:
        # A mark moves the run, and a newer run settles right behind its invalidation as the issue's
        # requirements move: the recheck takes it in, and its own proof invalidates it whole.
        races, context = self._races(marked=True)
        with self._racing(races):
            _parks.proves_before_a_park(context)

        self._assert_retired(races.successor)

    def _races(self, *, marked: bool = False) -> tuple:
        """The race over a settled run moved -- by a recorded reset, or by a mark -- and the context read behind."""
        run = self.settles_then_dies()[1]
        tip = guarded.recovery_context(self).state.get(readings.KEY_REWRITE_BASE)
        if marked:
            state = self.gh.read_pinned_state(self.issue)
            state.set(_records.EVIDENCE_HANDOFF, {"moved": run.receipt})
            self.gh.write_pinned_state(self.issue, state)
            races = _SettlesBehindTheInvalidation(self, run, edits_the_issue=True)
        else:
            self.assertTrue(_parks.records_the_reset(guarded.recovery_context(self)))
            races = _SettlesBehindTheInvalidation(self, run, tip=tip)
        return races, guarded.recovery_context(self)

    def _racing(self, races: _SettlesBehindTheInvalidation):
        """The client's readings and strict edits of the comment answered through `races`."""
        return patch.multiple(self.gh, read_pinned_state=races.reads, edit_pinned_state=races.edits)

    def _assert_retired(self, successor) -> None:
        """`successor` invalidated whole into history under its own receipt, its revision and binding kept."""
        self.assertIsNotNone(successor)
        pending, current, retired = readings.pinned_records(self)
        self.assertEqual((pending, current), (None, None))
        self.assertEqual(retired[-1], (successor.receipt, readings.INVALIDATED))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (successor.revision, successor.binding))


if __name__ == "__main__":
    unittest.main()
