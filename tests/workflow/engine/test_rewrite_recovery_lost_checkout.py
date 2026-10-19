# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A settled run stays retired for good once a recovery finds its checkout gone from disk.

The real-git finish case (`rewrite_verification_recovery_support`), issue #7's reviewed run settled under the anchor and
its finish killed unannounced, loses its checkout under the landed road, the quiet hold, or a standing stranded park:
ahead of the proof, as it is asked, behind an issue read, or as the landed road reads its candidate, the base tip the
reset blanked perhaps written back behind. The reset and the retirement land in separate writes, so the head put back
(label and reply too, for the park) routes with nothing current, nothing remade, pushed, or launched. A run written back
with its attempt behind a quiet hold's retirement is retired again; a road retiring it just ahead, pinning another
attempt or a newer run, holds the tick over what it wrote, the checkout unreset. A git request of the hold, gate, or
abort finding it gone is recorded alike; a retirement a full comment or usage write refuses is asked again whole.
"""
from __future__ import annotations

import copy
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git import commands
from orchestrator.git.base_sync import attempts as _attempts, rewrite_facts
from orchestrator.git.worktrees import creation
from orchestrator.github.pinned_state import PinnedEdit
from orchestrator.workflow.engine import (
    base_refresh,
    rewrite_landing_retirement as _retirement,
    verification_durable as _durable,
    verification_settlement_state as _settlement,
)
from tests.support.fakes import FakeLabel
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_evidence_test_support as fixtures,
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
    settled_finish_support as settled_support,
)

# A label the refresh does not drive, under which the dispatcher's hold strands the attempt.
_UNDRIVEN = "workflow:resolving_conflict"

_READS = "_reads_the_checkout"

_PROVES = "retires_unproved"

_EDITS = "edit_pinned_state"

_CURRENT = "verification_evidence_current"

# The usage total, and what crowds a retirement over the restored tip: a full comment, or a usage write once or always.
_USAGE_TOTAL = "issue_total_tokens"

_FULL, _USAGE, _EVERY = "full", "usage", "every"

# The roads whose git request ahead of any proof finds the checkout gone: the hold, the gate, the uncounted lag's abort.
_DISPATCHER, _REFRESH, _ABORT = "dispatcher", "refresh", "abort"


def _moves_past(case, live, *read, **options):
    """`live`, the checkout's reading, taken past a stray commit made on `case`'s checkout."""
    case._git(*support.STRAY_COMMIT, cwd=case._wt)
    return live(*read, **options)


def _vanishes_ahead(case, live, *asked, **options):
    """`live`, a call, asked once `case`'s checkout is gone from disk."""
    if case._wt.is_dir():
        case._wt.rename(case._away)
    return live(*asked, **options)


def _vanishes_behind(case, live, *asked, **options):
    """`live`, a call, its answer handed back once `case`'s checkout is gone from disk."""
    answered = live(*asked, **options)
    if case._wt.is_dir():
        case._wt.rename(case._away)
    return answered


class _LostCheckoutCase(guarded.GuardedRecoveryCase):
    """The finish case whose checkout a recovery finds gone from disk, put back once that recovery answered."""

    def setUp(self) -> None:
        super().setUp()
        self._away = self._wt.parent / "checkout-away"
        self._tips: list = []
        self._crowds = None

    def settles(self) -> None:
        """Land a reviewed rebase, settle its run, and kill its finish, the head and the run kept for the case."""
        self._run = self.settles_then_dies()

    def strands_then(self, answers, again) -> None:
        """Settle and kill the finish, strand the attempt by `answers`, `again` it, and reply under the label."""
        self.settles()
        self.issue.labels = [FakeLabel(_UNDRIVEN)]
        answers()
        again(answers)
        self.issue.labels = [FakeLabel(git_support.REVIEWING)]
        self.continues()

    def loses_the_checkout_down(self, road: str) -> None:
        """Answer the case down `road`, the checkout gone right ahead of the git request reading or resetting it."""
        answers = partial(guarded.answers_a_held_anchor, self) if road == _DISPATCHER else self.recovers
        if road == _REFRESH:
            self.unstarts()
        verb = "reset" if road == _ABORT else "rev-parse"
        request = handoff.Boundary("ahead of the request", "_git_hardened", lambda asked, *_args, **_kw: asked == verb)
        gone = request.racing(
            commands._git_hardened, partial(self._wt.rename, self._away), lambda: None,
        )
        counts = (lambda *_args: None) if road == _ABORT else base_refresh._worktree_behind_base
        with (
            patch.object(commands, "_git_hardened", gone),
            patch.object(base_refresh, "_worktree_behind_base", counts),
        ):
            answers()

    def unstarts(self) -> None:
        """Leave the attempt as one that never left its anchor, the checkout back on it, under an undriven label."""
        unstarted = self.gh.read_pinned_state(self.issue)
        unstarted.set(readings.KEY_REWRITE_SHA, None)
        self.gh.write_pinned_state(self.issue, unstarted)
        self._git("reset", "--quiet", "--hard", self.anchor, cwd=self._wt)
        self.issue.labels = [FakeLabel(_UNDRIVEN)]

    def crowds_the_retirement(self, issue, staged, over: dict) -> None:
        """Once the tip is written back, have a usage write land right ahead of the edit retiring the run."""
        if self._crowds not in {_USAGE, _EVERY} or self._tips:
            return
        if over.get(_CURRENT) and staged.get(_CURRENT) is None:
            self._crowds = None if self._crowds == _USAGE else self._crowds
            spent = self.gh.read_pinned_state(issue)
            spent.set(_USAGE_TOTAL, (spent.get(_USAGE_TOTAL) or 0) + 1)
            self.gh.write_pinned_state(issue, spent)

    def assert_retired(self, *, routes: bool = True) -> None:
        """The run invalidated whole while the checkout is away, and still once it is back on the head -- and routed."""
        head, settled = self._run
        self.assertFalse(self._wt.is_dir())
        self.assert_invalidated(settled)
        self._away.rename(self._wt)
        self._git("reset", "--quiet", "--hard", head, cwd=self._wt)
        self.issue.labels = [FakeLabel(git_support.REVIEWING)]
        self.recovers()
        records = readings.pinned_records(self)
        self.assertIsNone(records[1])
        self.assertIn((settled.receipt, readings.INVALIDATED), records[2])
        if routes:
            self.assert_routed(head)


class RestoredTipTest(_LostCheckoutCase, unittest.TestCase):
    """The retirement a checkout gone from disk lands outlives the base tip written back behind its blank."""

    def test_a_vanishing_candidate(self) -> None:
        # The landed road reads the checkout committed past the head; it goes from disk right behind that reading.
        for crowds in (None, _USAGE):
            with self.subTest(crowds=crowds):
                self.setUp()
                self.settles()
                self._crowds = crowds
                reads = partial(_vanishes_behind, self, partial(_moves_past, self, getattr(rewrite_facts, _READS)))
                with patch.object(rewrite_facts, _READS, reads):
                    self._races(self.recovers)
                self.assert_retired()

    def test_a_quiet_hold(self) -> None:
        # Under a driven stage, a full comment, or a usage write refusing every time, keeps the run until room is made.
        for crowds in (None, _FULL, _USAGE, _EVERY):
            with self.subTest(crowds=crowds):
                self.setUp()
                self.settles()
                self._crowds = crowds
                self._wt.rename(self._away)
                self._races(self._holds_unrestored)
                if crowds in {_FULL, _EVERY}:
                    self.assertEqual(readings.pinned_records(self)[1], self._run[1])
                    standing = self.pinned_fields(readings.KEY_PENDING_PUSH, readings.KEY_REWRITE_BASE)
                    self.assertEqual(standing, (self.anchor, None))
                    moves.makes_room(self)
                    self._holds_unrestored()
                self.assert_retired()

    def test_a_standing_park(self) -> None:
        # The dispatcher's hold of a stage the refresh does not drive finds its stranded park already standing.
        self.strands_then(partial(guarded.answers_a_held_anchor, self), self._races_away)
        self.assert_retired()

    def _holds_unrestored(self) -> None:
        """The dispatcher's quiet hold over a checkout it cannot bring back."""
        with patch.object(creation, "_ensure_pr_worktree", side_effect=RuntimeError("not brought back")):
            guarded.answers_a_held_anchor(self)

    def _races_away(self, recovery) -> None:
        """Run `recovery` with the checkout gone from disk, the base tip written back behind its blank."""
        self._wt.rename(self._away)
        self._races(recovery)

    def _races(self, recovery) -> None:
        """Run `recovery`, the base tip another road writes back right behind the edit that first blanks it."""
        self._tips.append(self.pinned_fields(readings.KEY_REWRITE_BASE)[0])
        with patch.object(self.gh, "edit_pinned_state", partial(self._puts_back_behind, self.gh.edit_pinned_state)):
            recovery()
        self.assertEqual(self._tips, [])
        self.assertNotEqual(self._crowds, _USAGE, "no usage write raced the retirement")

    def _puts_back_behind(self, live, issue, staged, **options):
        """`live`, the pinned-comment edit, the tip held written back right behind the first to blank it, crowded."""
        self.crowds_the_retirement(issue, staged, options["over"])
        answered = live(issue, staged, **options)
        tip = readings.KEY_REWRITE_BASE
        read = options["over"].get(tip)
        blanks = read is not None and staged.get(tip) is None
        if answered is PinnedEdit.EDITED and blanks and self._tips:
            if self._crowds == _FULL:
                moves.fills_the_comment(self, left=len(self._tips[0]) - 2)
            state = self.gh.read_pinned_state(issue)
            state.set(tip, self._tips.pop())
            self.gh.write_pinned_state(issue, state)
        return answered


class MidRoadCheckoutTest(_LostCheckoutCase, unittest.TestCase):
    """A checkout gone from disk after a recovery's caller found it on disk still has its run retired."""

    def test_a_moved_candidate(self) -> None:
        # The landed road reads the checkout committed past the head; it goes as that movement's proof is asked.
        self.settles()
        with patch.object(rewrite_facts, _READS, partial(_moves_past, self, getattr(rewrite_facts, _READS))):
            self._vanishes_in_the_proof(self.recovers)
        self.assert_retired()

    def test_a_candidate_being_read(self) -> None:
        # The landed road's own git request reading the checkout as its candidate finds it gone, outside any proof.
        self.settles()
        with patch.object(rewrite_facts, _READS, partial(_vanishes_ahead, self, getattr(rewrite_facts, _READS))):
            self.recovers()
        self.assert_retired()

    def test_a_quiet_hold(self) -> None:
        # The dispatcher holds a stage the refresh drives over a checkout on disk, gone as the hold's proof is asked.
        self.settles()
        self._vanishes_in_the_proof(partial(guarded.answers_a_held_anchor, self))
        self.assert_retired()

    def test_a_standing_park(self) -> None:
        # The hold, or the refresh's eligibility gate, finds its stranded park standing; the checkout goes as it proves.
        answerers = {"dispatcher": partial(guarded.answers_a_held_anchor, self), "refresh": self.recovers}
        for answerer, answers in answerers.items():
            with self.subTest(answerer=answerer):
                self.setUp()
                self.strands_then(answers, self._vanishes_in_the_proof)
                self.assert_retired()

    def test_a_request_inside_the_proof(self) -> None:
        # The quiet hold's checkout goes right behind one of its proof's issue reads, missing for its next git request.
        self.settles()
        with patch.object(self.gh, "get_issue", partial(_vanishes_behind, self, self.gh.get_issue)):
            guarded.answers_a_held_anchor(self)
        self.assert_retired()

    def test_a_git_request_ahead_of_any_proof(self) -> None:
        # The hold or the gate over an undriven unstarted attempt reads HEAD, or the abort resets it, and finds it gone.
        for road in (_DISPATCHER, _REFRESH, _ABORT):
            with self.subTest(road=road):
                self.setUp()
                self.settles()
                self.loses_the_checkout_down(road)
                self.assert_retired(routes=road != _REFRESH)

    def _vanishes_in_the_proof(self, recovery) -> None:
        """Run `recovery`, the checkout gone from disk right as the recovery's proof is first asked over it."""
        with patch.object(_retirement, _PROVES, partial(_vanishes_ahead, self, getattr(_retirement, _PROVES))):
            recovery()


class RacedRetirementTest(_LostCheckoutCase, unittest.TestCase):
    """A run retired over a checkout gone from disk, another road writing right ahead of that retirement or behind."""

    def test_a_run_written_back_behind(self) -> None:
        # The run and attempt written back behind an unrestored hold's retirement retire again, the comment read afresh.
        self.settles()
        self._written = copy.deepcopy(readings.pinned(self))
        self._wt.rename(self._away)
        unavailable = RuntimeError("the checkout could not be brought back")
        with (
            patch.object(creation, "_ensure_pr_worktree", side_effect=unavailable),
            patch.object(self.gh, _EDITS, partial(self._writes_back_behind, self.gh.edit_pinned_state)),
        ):
            guarded.answers_a_held_anchor(self)
        self.assertIsNone(self._written)
        self.assert_retired()

    def test_another_road_retires_the_run_ahead(self) -> None:
        # The fetch fails and the checkout goes behind the reset's blank; ahead of the retirement, or its third try past
        # two usage writes, another road pins a fresh attempt or a newer run, the checkout back: what it wrote stands.
        races = (
            ("attempt", self._replaces_the_attempt),
            ("successor", partial(settled_support.records_a_newer_run, settles=True)),
            ("last", partial(self._replaces_the_attempt, spends=2)),
        )
        for race, writes in races:
            with self.subTest(race=race):
                self.setUp()
                self.settles()
                self._onto = self.pinned_fields(readings.KEY_REWRITE_BASE)[0]
                self._blanked = False
                self._written = None
                self._spent = 0
                edits = partial(self._races_the_retirement, writes, self.gh.edit_pinned_state)
                with (
                    patch("orchestrator.git.branch_transport._authed_fetch", guarded.unfetched),
                    patch.object(self.gh, _EDITS, edits),
                ):
                    self.recovers()
                self._assert_held_as_written(race)

    def _assert_held_as_written(self, race: str) -> None:
        """What another road wrote ahead of the retirement standing as it wrote it, the checkout left on the head."""
        self.assertTrue(self._blanked and self._written)
        self.assertEqual(self._wt_head(), self._run[0], "the checkout was reset over what another road wrote")
        if race == "successor":
            current = readings.pinned_records(self)[1]
            self.assertEqual(current.receipt, self._written.receipt)
            self.assertEqual(self.pinned_fields(readings.KEY_PENDING_PUSH), (self.anchor,))
        else:
            pinned = self.pinned_fields(*self._written)
            self.assertEqual(pinned, tuple(self._written.values()))
        self.assert_made_once()

    def _writes_back_behind(self, live, issue, staged, **options):
        """`live`, the pinned-comment edit, the run and its attempt written back right behind the first to retire it."""
        answered = live(issue, staged, **options)
        if answered is PinnedEdit.EDITED and self._retires(staged, **options) and self._written:
            state = self.gh.read_pinned_state(issue)
            for field in (*readings.ATTEMPT_KEYS, *_durable._EVIDENCE_RECORDS):
                state.set(field, self._written.get(field))
            self.gh.write_pinned_state(issue, state)
            self._written = None
        return answered

    def _races_the_retirement(self, writes, live, issue, staged, **options):
        """`live`, the pinned-comment edit: the checkout gone behind the reset's blank, `writes` ahead of the run's."""
        if self._blanked and self._written is None and self._retires(staged, **options):
            self._written = writes(self)
            if self._written is not None:
                self._away.rename(self._wt)
        answered = live(issue, staged, **options)
        tip = readings.KEY_REWRITE_BASE
        blanks = options["over"].get(tip) is not None
        blanks = blanks and staged.get(tip) is None
        if answered is PinnedEdit.EDITED and blanks and not self._blanked:
            self._blanked = True
            self._wt.rename(self._away)
        return answered

    def _retires(self, staged, *, over: dict, **_options) -> bool:
        """Whether a pinned-comment edit retires the run the comment it is decided on carries current."""
        return bool(over.get(_CURRENT)) and not staged.get(_CURRENT)

    def _replaces_the_attempt(self, _case, spends: int = 0) -> dict | None:
        """Retire the run and pin another attempt, as another road would; it, or None for its first `spends` calls."""
        state = self.gh.read_pinned_state(self.issue)
        if self._spent < spends:
            self._spent += 1
            state.set(_USAGE_TOTAL, (state.get(_USAGE_TOTAL) or 0) + 1)
            self.gh.write_pinned_state(self.issue, state)
            return None
        replacement = fixtures.attempt_record(
            self._run[0], None, git_support.PR_NUMBER, git_support.REVIEWING, self._onto,
        )
        self.assertTrue(_settlement.retire_current_evidence(state))
        _attempts._clears_the_attempt(state)
        for key, member in replacement.items():
            state.set(key, member)
        self.gh.write_pinned_state(self.issue, state)
        return replacement

if __name__ == "__main__":
    unittest.main()
