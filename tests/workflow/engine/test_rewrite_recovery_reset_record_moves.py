# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Movement a dormant reset record reads under the run, retired before the reset goes on, whatever git answers.

The guarded recovery case (`guarded_recovery_support`), its run settled or captured and its finish killed unannounced,
the next fetch failing as another road moves the run's report, the git owner's abort handed the dormant recorder. Git
refuses the abort's reset behind its record's blank: the run is retired whole first, so neither tip nor report put back
revives it; every write behind the blank refused, the next recovery reads the blank and invalidates it. A tip read blank
and put back refuses the record, so no reset goes unrecorded; a gone checkout's lost-answer record, under the
dispatcher's stranded park, retires the run in its own write; an attempt pinned behind is kept.
"""
from __future__ import annotations

import subprocess
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git import branch_transport, commands
from orchestrator.git.base_sync import attempts as _attempts, persistence
from orchestrator.github.pinned_state import PinnedEdit
from orchestrator.workflow.engine import rewrite_recovery_parks as _parks
from tests.support.fakes import FakeLabel
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_evidence_test_support as fixtures,
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    settled_finish_support as settled,
)

# The report record the run is bound to, the revision another road moves it to, and the seams a case stands in for.
_REPORT = "developer_report_current"
_REVISION = "revision"

# The current record a settled run stands in, which the write invalidating it drops.
_CURRENT = "verification_evidence_current"
_FETCHES = "_authed_fetch"
_EDITS = "edit_pinned_state"
_OVER = "over"
_GIT = "_git_hardened"
_RESET = "reset"

# The run's current record and its base tip, and that tip and the run's report, as another road takes them off and
# puts them back.
_RUN_AND_TIP = (_CURRENT, readings.KEY_REWRITE_BASE)
_TIP_AND_REPORT = (readings.KEY_REWRITE_BASE, _REPORT)

# Where the checkout goes, and a label the refresh does not drive, stranding the attempt.
_AWAY = "checkout-away"
_UNDRIVEN = "workflow:resolving_conflict"


def _writes(case, fields: dict, *, clears: bool = False) -> None:
    """Write each of `fields` onto `case`'s comment, its attempt cleared first where `clears`, as another road would."""
    state = case.gh.read_pinned_state(case.issue)
    if clears:
        _attempts._clears_the_attempt(state)
    for key, field_value in fields.items():
        state.set(key, field_value)
    case.gh.write_pinned_state(case.issue, state)


def _refuses_the_reset(live, asked: list, verb: str, *args, **options) -> subprocess.CompletedProcess:
    """`live`, the hardened git call, refusing every reset, noted in `asked`, and running every other command."""
    if verb == _RESET:
        asked.append(verb)
        return subprocess.CompletedProcess([verb, *args], 1, "", "reset refused")
    return live(verb, *args, **options)


def _notes_the_reset(live, asked: list, verb: str, *args, **options) -> subprocess.CompletedProcess:
    """`live`, the hardened git call, run as it is, every reset noted in `asked`."""
    if verb == _RESET:
        asked.append(verb)
    return live(verb, *args, **options)


class RecordedMoveTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """What a landed reset record read moving is retired before a reset git refuses puts the base tip back."""

    def test_a_refused_reset_revives_nothing(self) -> None:
        # Captured or settled, the run retires whole first, the attempt kept on its anchor for the refused reset's park.
        for captures in (False, True):
            with self.subTest(captured=captures):
                self.setUp()
                run = (self.captures() if captures else self.settles_then_dies())[1]
                self._recovers_over_a_moved_report()
                if captures:
                    self.assert_abandoned(run)
                else:
                    self.assert_invalidated(run)
                self.assertEqual(self.pinned_fields(readings.KEY_PENDING_PUSH), (self.anchor,))

    def test_an_unlanded_retirement_keeps_the_blank(self) -> None:
        # Every write behind the blank refused, nothing lands; with writes landing, the next recovery reads the blank.
        settled = self.settles_then_dies()[1]
        self._recovers_over_a_moved_report(refusing=True)
        standing = self.pinned_fields(guarded.AWAITING, readings.KEY_REWRITE_BASE)
        self.assertEqual((standing, self._resets), ((None, None), []))
        self.assertEqual(readings.pinned_records(self)[1], settled)
        self.gh.pinned_failures.refused.discard(git_support.ISSUE)
        with patch.object(branch_transport, _FETCHES, guarded.unfetched):
            self.recovers()
        self.assert_invalidated(settled)
        self.assert_released()

    def _recovers_over_a_moved_report(self, *, refusing: bool = False) -> None:
        """A recovery over a failed fetch and a refused reset, the report moved behind the fetch, back behind the blank;
        `refusing` has GitHub refuse every pinned-comment write behind the blank."""
        self._held = [self.pinned_fields(_REPORT)[0]]
        self._taken = False
        self._refusing = refusing
        self._resets = []
        with (
            patch.object(branch_transport, _FETCHES, self._moves_the_report),
            patch.object(self.gh, _EDITS, partial(self._puts_the_report_back, self.gh.edit_pinned_state)),
            patch.object(commands, _GIT, partial(_refuses_the_reset, getattr(commands, _GIT), self._resets)),
        ):
            self.recovers()
        self.assertEqual((self._taken, self._held), (True, []))

    def _moves_the_report(self, spec, ref: str, **options):
        """The branch's fetch, failing, the report written at another revision behind it the first time."""
        fetched = guarded.unfetched(spec, ref, **options)
        if "issue-7" in ref and not self._taken:
            self._taken = True
            report = self._held[0]
            self._writes_the_report({**report, _REVISION: report[_REVISION] + 1})
        return fetched

    def _puts_the_report_back(self, live, issue, staged, **options):
        """`live`, the pinned-comment edit, the report written back right behind the edit blanking the base tip."""
        answered = live(issue, staged, **options)
        read = options[_OVER].get(readings.KEY_REWRITE_BASE)
        if read and not staged.get(readings.KEY_REWRITE_BASE) and self._held:
            self._writes_the_report(self._held.pop())
            if self._refusing:
                self.gh.pinned_failures.refused.add(issue.number)
        return answered

    def _writes_the_report(self, report) -> None:
        """Write `report` as the run's report record, as another road would."""
        state = self.gh.read_pinned_state(self.issue)
        state.set(_REPORT, report)
        self.gh.write_pinned_state(self.issue, state)


class BlankTipTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A base tip the tick read blank is held to the comment read afresh before the reset goes on."""

    def test_a_tip_put_back_holds_the_reset(self) -> None:
        # The tip read blank, put back as the fetch fails, refuses the record and the reset; the next tick makes both.
        settled = self.settles_then_dies()[1]
        self._tip = [self.pinned_fields(readings.KEY_REWRITE_BASE)[0]]
        self._writes_the_tip(None)
        resets: list = []
        with (
            patch.object(branch_transport, _FETCHES, self._puts_the_tip_back),
            patch.object(commands, _GIT, partial(_notes_the_reset, getattr(commands, _GIT), resets)),
        ):
            self.recovers()
            self.assertEqual((resets, self._tip), ([], []))
            self.assertIsNotNone(self.pinned_fields(readings.KEY_REWRITE_BASE)[0])
            self.recovers()
        self.assertEqual(resets, [_RESET])
        self.assert_invalidated(settled)
        self.assert_released()

    def test_a_tip_put_back_behind_the_blank_holds(self) -> None:
        # Another road puts the tip back right behind the reset record's blank: the record reads it afresh and holds
        # the reset, the run, captured or settled, left on the landed head it was proved over and the tick's state
        # withheld, so no reset moves the checkout off evidence nothing records moved.
        for captures in (False, True):
            with self.subTest(captured=captures):
                self.setUp()
                head = (self.captures() if captures else self.settles_then_dies())[0]
                context = guarded.recovery_context(self)
                self._tip = [self.pinned_fields(readings.KEY_REWRITE_BASE)[0]]
                puts_back = partial(self._puts_the_tip_back_behind, self.gh.edit_pinned_state)
                with patch.object(self.gh, _EDITS, puts_back):
                    self.assertIsNone(persistence._resets(context, self.anchor))
                held = (self._tip, self._wt_head(), context.state.withheld)
                self.assertEqual(held, ([], head, True))

    def test_a_successor_behind_the_proof_holds(self) -> None:
        # The reset's record reads the run's report moved and retires the run; right behind that retirement another
        # road settles a newer run on its binding and puts the tip and the report back: the record reads the comment
        # once more behind its proof and holds the reset, the checkout left on the head and the tick's state withheld.
        self._run = self.settles_then_dies()
        context = guarded.recovery_context(self)
        held_back = self.pinned_fields(*_TIP_AND_REPORT)
        self._tip = [dict(zip(_TIP_AND_REPORT, held_back, strict=True))]
        report = held_back[1]
        _writes(self, {_REPORT: {**report, _REVISION: report[_REVISION] + 1}})
        settles = partial(self._settles_behind_the_retirement, self.gh.edit_pinned_state)
        with patch.object(self.gh, _EDITS, settles):
            self.assertIsNone(persistence._resets(context, self.anchor))
        held = (self._tip, self._wt_head(), context.state.withheld)
        self.assertEqual(held, ([], self._run[0], True))

    def _settles_behind_the_retirement(self, live, issue, staged, **options):
        """`live`, the pinned-comment edit, a newer run settled and the fields held put back behind the run retired."""
        answered = live(issue, staged, **options)
        retires = options[_OVER].get(_CURRENT) and not staged.get(_CURRENT)
        if retires and self._tip:
            settled.records_a_newer_run(self, settles=True, binding=self._run[1].binding)
            _writes(self, self._tip.pop())
        return answered

    def _puts_the_tip_back_behind(self, live, issue, staged, **options):
        """`live`, the pinned-comment edit, the tip held written back right behind the first edit blanking it."""
        answered = live(issue, staged, **options)
        tip = readings.KEY_REWRITE_BASE
        blanks = options[_OVER].get(tip) and not staged.get(tip)
        if blanks and self._tip:
            self._writes_the_tip(self._tip.pop())
        return answered

    def _puts_the_tip_back(self, spec, ref: str, **options):
        """The branch's fetch, failing, the tip held written back behind it the first time."""
        fetched = guarded.unfetched(spec, ref, **options)
        if "issue-7" in ref and self._tip:
            self._writes_the_tip(self._tip.pop())
        return fetched

    def _writes_the_tip(self, tip) -> None:
        """Write `tip` as the attempt's base tip, as another road would."""
        state = self.gh.read_pinned_state(self.issue)
        state.set(readings.KEY_REWRITE_BASE, tip)
        self.gh.write_pinned_state(self.issue, state)


class GoneCheckoutTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A reset's record that did not land over a checkout gone from disk still retires what it read moving."""

    def test_an_unlanded_record_retires_the_run(self) -> None:
        # With the report moved and the checkout gone, the hold's reset record reads the move and loses its answer, the
        # report put back; the run, settled or captured, is retired in a write of its own.
        for captures in (False, True):
            with self.subTest(captured=captures):
                self.setUp()
                head, run = self.captures() if captures else self.settles_then_dies()
                away = self._strands_over_a_moved_report()
                if captures:
                    self.assert_abandoned(run)
                else:
                    self.assert_invalidated(run)
                away.rename(self._wt)
                self.issue.labels = [FakeLabel(git_support.REVIEWING)]
                self.recovers()
                self.assert_recovered(head)
                self.assertEqual(readings.pinned_records(self)[:2], (None, None))

    def test_a_run_put_back_behind_the_blank(self) -> None:
        # The tick reads no run current over a checkout gone, and another road puts the run and its base tip back right
        # behind the reset record's blank: the retirement reads the comment afresh and retires the run whole, and with
        # that blank undone the proof holds, the tick's state withheld.
        run = self.settles_then_dies()[1]
        written = dict(zip(_RUN_AND_TIP, self.pinned_fields(*_RUN_AND_TIP), strict=True))
        answered = self._proves_over_nothing_held(partial(_writes, self, written))
        self.assertEqual(answered, (False, True))
        records = readings.pinned_records(self)
        self.assertIsNone(records[1])
        self.assertIn((run.receipt, readings.INVALIDATED), records[2])

    def test_an_attempt_pinned_behind_the_blank_holds(self) -> None:
        # Another road pins a fresh attempt right behind that blank instead: the retirement reads it afresh and holds,
        # the tick's state withheld, so nothing it carries is written back over that attempt.
        head = self.settles_then_dies()[0]
        pinned = fixtures.attempt_record(head, "", git_support.PR_NUMBER, git_support.REVIEWING)
        answered = self._proves_over_nothing_held(partial(_writes, self, pinned, clears=True))
        self.assertEqual(answered, (False, True))
        standing = readings.pinned(self)
        self.assertEqual({key: standing.get(key) for key in pinned}, pinned)

    def _proves_over_nothing_held(self, behind) -> tuple[bool, bool]:
        """Prove over the run taken off and the checkout gone, `behind` made right behind the reset record's blank; the
        proof's answer, and whether the tick's state is withheld."""
        _writes(self, {_CURRENT: None})
        context = guarded.recovery_context(self)
        self._wt.rename(self._wt.parent / _AWAY)
        self._behind = [behind]
        makes = partial(self._makes_behind_the_blank, self.gh.edit_pinned_state)
        with patch.object(self.gh, _EDITS, makes):
            proved = _parks.proves_before_a_park(context)
        self.assertEqual(self._behind, [])
        return proved, context.state.withheld

    def _makes_behind_the_blank(self, live, issue, staged, **options):
        """`live`, the pinned-comment edit, what is held behind made right behind the first edit blanking the tip."""
        answered = live(issue, staged, **options)
        tip = readings.KEY_REWRITE_BASE
        read = options[_OVER].get(tip)
        if read and not staged.get(tip) and self._behind:
            self._behind.pop()()
        return answered

    def _strands_over_a_moved_report(self):
        """Move the report and the checkout away, and hold the anchor, the first record's answer lost; where it went."""
        report = self.pinned_fields(_REPORT)[0]
        self._held = [report]
        state = self.gh.read_pinned_state(self.issue)
        state.set(_REPORT, {**report, _REVISION: report[_REVISION] + 1})
        self.gh.write_pinned_state(self.issue, state)
        away = self._wt.parent / _AWAY
        self._wt.rename(away)
        self.issue.labels = [FakeLabel(_UNDRIVEN)]
        with patch.object(self.gh, _EDITS, partial(self._answers_lost_once, self.gh.edit_pinned_state)):
            guarded.answers_a_held_anchor(self)
        self.assertEqual(self._held, [])
        return away

    def _answers_lost_once(self, live, issue, staged, **options):
        """`live`, the pinned-comment edit, its first answer lost unsent behind the report held written back."""
        if not self._held:
            return live(issue, staged, **options)
        state = self.gh.read_pinned_state(issue)
        state.set(_REPORT, self._held.pop())
        self.gh.write_pinned_state(issue, state)
        return PinnedEdit.UNCONFIRMED


class ReplacedAttemptTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """An attempt another road pins while the reset's record retires what it read moving is kept, nothing reset."""

    def test_a_replacement_holds_the_reset(self) -> None:
        # The report taken off, the reset's record invalidates the run; an attempt pinned right behind holds the reset.
        head = self.settles_then_dies()[0]
        self._pinned = fixtures.attempt_record(head, "", git_support.PR_NUMBER, git_support.REVIEWING)
        self._taken = False
        self._replaced = False
        resets: list = []
        with (
            patch.object(branch_transport, _FETCHES, self._takes_the_report_off),
            patch.object(self.gh, _EDITS, partial(self._replaces_behind, self.gh.edit_pinned_state)),
            patch.object(commands, _GIT, partial(_notes_the_reset, getattr(commands, _GIT), resets)),
        ):
            self.recovers()
        pinned = readings.pinned(self)
        self.assertEqual((self._replaced, resets), (True, []))
        standing = {key: pinned.get(key) for key in self._pinned}
        self.assertEqual(standing, self._pinned)

    def test_a_replacement_behind_the_blank_holds(self) -> None:
        # The checkout on disk and nothing read moving, another road pins an attempt right behind the reset record's
        # blank: the record reads the comment afresh and holds the reset, the checkout left on the landed head and
        # the tick's state withheld, so writing it whole puts nothing back over that attempt.
        head = self.settles_then_dies()[0]
        self._pinned = fixtures.attempt_record(head, "", git_support.PR_NUMBER, git_support.REVIEWING)
        self._replaced = False
        context = guarded.recovery_context(self)
        replaces = partial(self._replaces_behind_the_blank, self.gh.edit_pinned_state)
        with patch.object(self.gh, _EDITS, replaces):
            self.assertIsNone(persistence._resets(context, self.anchor))
        self.gh.write_pinned_state(self.issue, context.state)
        self.assertEqual((self._replaced, self._wt_head()), (True, head))
        standing = self.pinned_fields(*self._pinned)
        self.assertEqual(standing, tuple(self._pinned.values()))

    def _takes_the_report_off(self, spec, ref: str, **options):
        """The branch's fetch, failing, the run's report taken off the comment behind it the first time."""
        fetched = guarded.unfetched(spec, ref, **options)
        if "issue-7" in ref and not self._taken:
            self._taken = True
            state = self.gh.read_pinned_state(self.issue)
            state.set(_REPORT, None)
            self.gh.write_pinned_state(self.issue, state)
        return fetched

    def _replaces_behind_the_blank(self, live, issue, staged, **options):
        """`live`, the pinned-comment edit, another road's attempt pinned right behind the first that blanks the tip."""
        answered = live(issue, staged, **options)
        tip = readings.KEY_REWRITE_BASE
        blanks = options[_OVER].get(tip) and not staged.get(tip)
        if blanks and not self._replaced:
            self._replaced = True
            _writes(self, self._pinned, clears=True)
        return answered

    def _replaces_behind(self, live, issue, staged, **options):
        """`live`, the pinned-comment edit, another road's attempt pinned right behind the first that drops the run."""
        answered = live(issue, staged, **options)
        current = staged.get(_CURRENT)
        if answered is PinnedEdit.EDITED and current is None and not self._replaced:
            self._replaced = True
            state = self.gh.read_pinned_state(issue)
            _attempts._clears_the_attempt(state)
            for key, pinned in self._pinned.items():
                state.set(key, pinned)
            self.gh.write_pinned_state(issue, state)
        return answered



if __name__ == "__main__":
    unittest.main()
