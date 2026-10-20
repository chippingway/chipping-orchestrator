# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run's refusal survives whatever the readings beside it came to, and a comment with no room for it.

The last word behind a recovery's proof takes every reading and lets none mask
another, so movement read beside a base nobody could read still abandons the
captured run while the unread base holds the route. And where the pinned
comment has no room for the abandonment, the write that only shrinks it -- the
run dropped and the base tip its replay was recorded as made onto blanked --
refuses the run for good -- the dispatcher's stranded park over a checkout gone
from disk among them, which keeps the attempt. A recovery that leaves without finishing the landing,
because the checkout left the head its fetch found or the remote branch is
observed off it, abandons the run on its way out, over the movement it read
and with nothing read again for it, so a checkout back on the head by the
next tick revives nothing. Either way, putting back what
moved and making room routes the head with nothing run, recorded, pushed, or
announced again. An abandonment refused over an evidence record moved by no
write of the recovery's stops the recovery there, the comment left as it moved.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git.base_sync import replay_evidence, rewrite_facts
from orchestrator.git.base_sync.rewrite_handoffs import _BaseStanding
from orchestrator.workflow.engine import dispatch_guards, verification_records
from tests.support.fakes import FakeLabel
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as moves,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)

_BASE_READING = "_standing_on_the_remote_base"

_CLASSIFIED = "_made_for_another_publication"

# The evidence floor the comment comes to carry by no write of the recovery's.
_MOVED_FLOOR = 99

# What moves while a base reading comes back unread, beside what puts it back.
_BESIDE_AN_UNREAD_BASE = (
    (
        "the issue body was edited",
        lambda case: setattr(case.issue, "body", "Also cover an unread base."),
        lambda case, body: setattr(case.issue, "body", body),
    ),
    (
        "another command was configured",
        lambda case: case.configures("echo another"),
        lambda case, _body: case.configures(support.CONFIGURED),
    ),
)


def _answered(standing: _BaseStanding, move, *_args) -> _BaseStanding:
    """A base reading that comes back as `standing`, `move` made while it was taken."""
    move()
    return standing


def _moves_behind(original, move, *args):
    """Answer `original` -- the recovery's classification of what its fetch found -- then make `move`."""
    answered = original(*args)
    move()
    return answered


def _behind_the_classification(move):
    """A patch making `move` each time a recovery has classified what its fetch found, before it reads the landing."""
    original = getattr(replay_evidence, _CLASSIFIED)
    return patch.object(replay_evidence, _CLASSIFIED, side_effect=partial(_moves_behind, original, move))


def _moves_off_the_landing(case: support.CapturedRunCase, moved: list) -> None:
    """Put `case`'s remote branch on the anchor and raise its comment's evidence floor, kept on `moved` as it reads."""
    case._git("update-ref", f"refs/heads/{git_support.BRANCH}", case.anchor, cwd=case._remote)
    state = case.gh.read_pinned_state(case.issue)
    state.set(verification_records.REVISION_FLOOR, _MOVED_FLOOR)
    case.gh.write_pinned_state(case.issue, state)
    moved.append(readings.pinned(case))


class SurvivingRefusalTest(support.CapturedRunCase, unittest.TestCase):
    """A captured run something was read moving under is never routed, whatever read beside it or fit after it."""

    def test_movement_beside_an_unread_base_abandons(self) -> None:
        # The base cannot be read again, which holds the route, and the
        # requirements or the configuration are read moving in the same last
        # word, which abandons the run. Put back, they route the head with the
        # run still abandoned and nothing run again.
        for moved, moves_it, restores in _BESIDE_AN_UNREAD_BASE:
            with self.subTest(moved=moved):
                head, captured = self._holds_beside_an_unread_base(moves_it, restores)

                self.recovers()

                self.assert_abandoned(captured)
                self.assert_recovered(head)

    def test_no_room_to_abandon_still_refuses(self) -> None:
        # The base is read elsewhere over a comment with no room for the
        # run's history entry: the run is dropped instead, and the base tip
        # it rests on with it, holding the route. Once room is made and the
        # base reads where it was, the head is routed with nothing recorded,
        # since no base can be proved for it any more. A command that prints
        # nothing leaves a transcript smaller than the entry abandoning it.
        self.configures("true")
        head, _captured = self.captures()
        moves.fills_the_comment(self)
        moved = partial(_answered, _BaseStanding.MOVED, lambda: None)
        with patch.object(rewrite_facts, _BASE_READING, side_effect=moved):
            self.recovers()

        self.assert_held(None)
        self.assertEqual(
            (readings.pinned(self)[readings.KEY_REWRITE_BASE], self.runs()),
            (None, 1),
        )
        moves.makes_room(self)
        self.recovers()
        self.assertEqual(
            (readings.pinned_records(self), self.runs()),
            (git_support.nothing_recorded(self), 1),
        )
        self.assert_recovered(head)

    def test_a_checkout_left_early_abandons(self) -> None:
        # The recovery's fetch finds the remote and the checkout on the landed
        # head, and the checkout commits past it before the landing is read:
        # the recovery finishes nothing, and abandons the run captured for
        # that head on its way out, over the movement it read. Put back on
        # the head, the next recovery routes it with the run still abandoned
        # and nothing run again.
        head, captured = self._leaves_early()

        self.recovers()

        self.assert_abandoned(captured)
        self.assert_recovered(head)

    def test_a_remote_observed_off_the_head_abandons(self) -> None:
        # The recovery's fetch finds the remote and the checkout on the landed
        # head, and the remote branch is put back on the anchor before the
        # landing is observed: the observation finds no landing to finish, and
        # the run captured for the head is abandoned before the recovery
        # leaves. With the branch back on the head, the next recovery routes
        # it with the run still abandoned and nothing run, pushed, or
        # announced again.
        head, captured = self.captures()
        branch = f"refs/heads/{git_support.BRANCH}"
        with _behind_the_classification(partial(self._git, "update-ref", branch, self.anchor, cwd=self._remote)):
            self.recovers()

        self.assert_held(None)
        self.assert_abandoned(captured)
        self._git("update-ref", branch, head, cwd=self._remote)
        self.recovers()
        self.assert_abandoned(captured)
        self.assert_recovered(head)

    def test_a_moved_record_stops_the_observation(self) -> None:
        # Behind the classification the remote branch is put back on the
        # anchor and, by no write of the recovery's, the comment comes to
        # carry another evidence floor -- an invariant failure under the issue
        # writer claim. The abandonment the observation owes is refused over
        # that floor, so the recovery goes no further: the comment stands
        # exactly as it moved, the run still pending beside the anchor, and
        # nothing is relabelled, pushed, or announced.
        _head, captured = self.captures()
        moved: list = []
        with _behind_the_classification(partial(_moves_off_the_landing, self, moved)):
            self.recovers()

        self.assertEqual(readings.pinned(self), moved[-1])
        self.assert_held(captured)
        self.assertEqual(support.announced(self), [])
        self.pushes.assert_not_called()

    def _holds_beside_an_unread_base(self, moves_it, restores) -> tuple:
        """A fresh case's captured run, held over an unread base `moves_it` moved beside; then put back.

        The head and the run, once the recovery held the route and abandoned
        the run, and `restores` put back what moved.
        """
        self.setUp()
        head, captured = self.captures()
        body = self.issue.body
        unread = partial(_answered, _BaseStanding.UNREAD, partial(moves_it, self))
        with patch.object(rewrite_facts, _BASE_READING, side_effect=unread):
            self.recovers()
        self.assert_held(None)
        self.assert_abandoned(captured)
        restores(self, body)
        return head, captured

    def _leaves_early(self) -> tuple:
        """A captured run, its checkout committing past the head behind the recovery's classification.

        Put back on the head once that recovery held the route and abandoned
        the run. The head and the run.
        """
        head, captured = self.captures()
        with _behind_the_classification(partial(self._git, *support.STRAY_COMMIT, cwd=self._wt)):
            self.recovers()
        self.assert_held(None)
        self.assert_abandoned(captured)
        self._git("reset", "--quiet", "--hard", head, cwd=self._wt)
        return head, captured


class StrandedNoRoomTest(support.CapturedRunCase, unittest.TestCase):
    """A run the dispatcher's stranded park drops for want of room is refused for good, never run again."""

    def test_no_room_over_a_missing_checkout_refuses(self) -> None:
        # The issue is relabelled out of the stages the refresh drives with its
        # checkout gone from disk, over a comment with no room for the run's
        # history entry: the dispatcher's stranded park drops the run and the
        # base tip it rests on, keeping the attempt. With the checkout back,
        # room made, the label restored, and a continue, the recovery routes
        # the head with nothing run, recorded, pushed, or announced again.
        head = self._strands_over_no_room()

        pinned = readings.pinned(self)
        self.assertIsNone(readings.records(pinned)[0])
        self.assertIsNone(pinned[readings.KEY_REWRITE_BASE])
        self.assertEqual(pinned[readings.KEY_PENDING_PUSH], self.anchor)
        moves.makes_room(self)
        self.issue.labels = [FakeLabel(git_support.REVIEWING)]
        self.continues()
        self.recovers()
        self.assertEqual(
            (readings.pinned_records(self), self.runs()),
            (git_support.nothing_recorded(self), 1),
        )
        self.assert_recovered(head)

    def _strands_over_no_room(self) -> str:
        """A run captured for the landed head, stranded by the dispatcher over no checkout and no room; the head.

        The checkout is back on disk once the park was taken. A command that
        prints nothing leaves a transcript smaller than the entry abandoning it.
        """
        self.configures("true")
        head = self.captures()[0]
        moves.fills_the_comment(self)
        away = self._wt.parent / "checkout-away"
        self._wt.rename(away)
        self.issue.labels = [FakeLabel("workflow:resolving_conflict")]
        label = self.gh.workflow_label(self.issue)
        state = self.gh.read_pinned_state(self.issue)
        dispatch_guards._anchor_holds_the_tick(self.gh, self._spec, self.issue, label, state)
        away.rename(self._wt)
        return head


if __name__ == "__main__":
    unittest.main()
