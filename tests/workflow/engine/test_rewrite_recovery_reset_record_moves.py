# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Movement a reset's own record reads under the run, retired before the reset goes on, whatever git answers.

The guarded recovery case (`guarded_recovery_support`), its run settled or captured and its finish killed unannounced,
the next fetch failing as another road moves the run's report. Git refuses the abort's reset behind its record's blank:
the run is retired whole first, so neither tip nor report put back revives it; every write behind the blank refused,
the next recovery reads the blank and invalidates it. A tip read blank and put back refuses the record, so no reset goes
unrecorded; a gone checkout's lost-answer record retires the run in its own write; an attempt pinned behind is kept.
"""
from __future__ import annotations

import subprocess
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git import branch_transport, commands
from orchestrator.git.base_sync import attempts as _attempts
from orchestrator.github.pinned_state import PinnedEdit
from tests.support.fakes import FakeLabel
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_evidence_test_support as fixtures,
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
)

# The report record the run is bound to, the revision another road moves it to, and the seams a case stands in for.
_REPORT = "developer_report_current"
_REVISION = "revision"

# The current record a settled run stands in, which the write invalidating it drops.
_CURRENT = "verification_evidence_current"
_FETCHES = "_authed_fetch"
_GIT = "_git_hardened"

# Where the checkout goes, a HEAD naming no commit, and a label the refresh does not drive, stranding the attempt.
_AWAY = "checkout-away"
_MISSING_HEAD = "ffffffffffffffffffffffffffffffffffffffff\n"
_UNDRIVEN = "workflow:resolving_conflict"


def _refuses_the_reset(live, asked: list, verb: str, *args, **options) -> subprocess.CompletedProcess:
    """`live`, the hardened git call, refusing every reset, noted in `asked`, and running every other command."""
    if verb == "reset":
        asked.append(verb)
        return subprocess.CompletedProcess([verb, *args], 1, "", "reset refused")
    return live(verb, *args, **options)


def _notes_the_reset(live, asked: list, verb: str, *args, **options) -> subprocess.CompletedProcess:
    """`live`, the hardened git call, run as it is, every reset noted in `asked`."""
    if verb == "reset":
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
            patch.object(self.gh, "edit_pinned_state", partial(self._puts_the_report_back, self.gh.edit_pinned_state)),
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
        read = options["over"].get(readings.KEY_REWRITE_BASE)
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
        self.assertEqual(resets, ["reset"])
        self.assert_invalidated(settled)
        self.assert_released()

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
                self.assert_routed(head)

    def test_a_loss_the_skip_selection_reads(self) -> None:
        # The refresh's skip selection reads HEAD for a decided commit and finds the checkout gone, back as that failure
        # unwinds: the run, captured or settled, is still retired whole before anything routes the head.
        for captures in (False, True):
            with self.subTest(captured=captures):
                self.setUp()
                run = (self.captures() if captures else self.settles_then_dies())[1]
                decided = self.gh.read_pinned_state(self.issue)
                decided.set("implementing_published_sha", self.anchor)
                self.gh.write_pinned_state(self.issue, decided)
                self.issue.labels = [FakeLabel("workflow:implementing")]
                self._held = []
                with patch.object(commands, _GIT, partial(self._gone_at_the_head, commands._git_hardened)):
                    self.recovers()
                (self.assert_abandoned if captures else self.assert_invalidated)(run)

    def test_a_parked_head_off_the_replay(self) -> None:
        # Under a standing park the dispatcher reads HEAD naming a missing commit and releases the handler: that read
        # still retires the run, captured or settled, so HEAD put back and a reply route nothing current.
        for captures in (False, True):
            with self.subTest(captured=captures):
                self.setUp()
                run = (self.captures() if captures else self.settles_then_dies())[1]
                self._parks_over_a_missing_head()
                (self.assert_abandoned if captures else self.assert_invalidated)(run)
                self.continues()
                self.recovers()
                self.assertEqual(readings.pinned_records(self)[:2], (None, None))

    def _parks_over_a_missing_head(self) -> None:
        """Stand a recovery park, and have the dispatcher hold the anchor over HEAD naming no commit, put back."""
        parked = self.gh.read_pinned_state(self.issue)
        parked.set(guarded.AWAITING, True)
        parked.set("park_reason", "auto_base_rebase_push_failed")
        parked.set("last_action_comment_id", self.gh.latest_comment_id(self.issue))
        self.gh.write_pinned_state(self.issue, parked)
        named = self._git("rev-parse", "--git-path", "HEAD", cwd=self._wt).strip()
        head = self._wt / named
        original = head.read_bytes()
        head.write_text(_MISSING_HEAD)
        guarded.answers_a_held_anchor(self)
        head.write_bytes(original)

    def _gone_at_the_head(self, live, verb, *asked, **options):
        """`live`, the hardened git call, the checkout away for its first `rev-parse` there, back as that unwinds."""
        if self._held or verb != "rev-parse" or options.get("cwd") != self._wt:
            return live(verb, *asked, **options)
        self._held.append(self._wt.with_name(_AWAY))
        self._wt.rename(self._held[0])
        try:
            return live(verb, *asked, **options)
        except FileNotFoundError:
            self._held[0].rename(self._wt)
            raise

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
        with patch.object(self.gh, "edit_pinned_state", partial(self._answers_lost_once, self.gh.edit_pinned_state)):
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
            patch.object(self.gh, "edit_pinned_state", partial(self._replaces_behind, self.gh.edit_pinned_state)),
            patch.object(commands, _GIT, partial(_notes_the_reset, getattr(commands, _GIT), resets)),
        ):
            self.recovers()
        pinned = readings.pinned(self)
        self.assertEqual((self._replaced, resets), (True, []))
        standing = {key: pinned.get(key) for key in self._pinned}
        self.assertEqual(standing, self._pinned)

    def _takes_the_report_off(self, spec, ref: str, **options):
        """The branch's fetch, failing, the run's report taken off the comment behind it the first time."""
        fetched = guarded.unfetched(spec, ref, **options)
        if "issue-7" in ref and not self._taken:
            self._taken = True
            state = self.gh.read_pinned_state(self.issue)
            state.set(_REPORT, None)
            self.gh.write_pinned_state(self.issue, state)
        return fetched

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



class OwedLossTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A checkout loss no write could record stays owed, so the next poll retires the run before its road goes on."""

    def test_a_loss_every_write_refused(self) -> None:
        # The hold finds the checkout gone with every write refused, and it is back before the refresh's next poll:
        # that poll still retires the run, captured or settled, before anything routes it.
        for captures in (False, True):
            with self.subTest(captured=captures):
                self.setUp()
                run = (self.captures() if captures else self.settles_then_dies())[1]
                away = self._wt.with_name(_AWAY)
                self._wt.rename(away)
                with patch.object(self.gh.pinned_failures, "refused", {self.issue.number}):
                    guarded.answers_a_held_anchor(self)
                away.rename(self._wt)
                self.recovers()
                retired = (run.receipt, readings.ABANDONED if captures else readings.INVALIDATED)
                self.assertIn(retired, readings.pinned_records(self)[2])

if __name__ == "__main__":
    unittest.main()
