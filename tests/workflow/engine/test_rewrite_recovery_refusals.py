# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run's refusal survives whatever the readings beside it came to, and a comment with no room for it.

The last word behind a recovery's proof takes every reading and lets none mask
another, so movement read beside a base nobody could read still abandons the
captured run while the unread base holds the route. And where the pinned
comment has no room for the abandonment, the write that only shrinks it -- the
run dropped and the base tip its replay was recorded as made onto blanked --
refuses the run for good. A recovery that leaves without finishing the landing,
because the checkout left the head its fetch found or the remote branch is
observed off it, abandons the run on its way out, even where the checkout is
back on the head before anything reads it again. Either way, putting back what
moved and making room routes the head with nothing run, recorded, pushed, or
announced again.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git import branch_transport
from orchestrator.git.base_sync import replay_evidence, rewrite_facts
from orchestrator.git.base_sync.rewrite_handoffs import _BaseStanding
from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)
from tests.workflow.interleaving import _RacesPastTheStep

_BASE_READING = "_standing_on_the_remote_base"

# A key nothing reads, standing in for whatever else fills the comment.
_FILLER = "room_filler"

_STRAY_COMMIT = (
    "-c", "user.name=stray", "-c", "user.email=stray@example.invalid",
    "commit", "--quiet", "--allow-empty", "-m", "stray",
)

_CLASSIFIED = "_made_for_another_publication"

_REMOTE_READ = "_remote_branch_read"

_CONFIGURED = f"test -f feature.py && echo '{git_support.CHECKED}'"

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
        lambda case, _body: case.configures(_CONFIGURED),
    ),
)


def _captures(case: support.VerificationRecoveryCase) -> tuple:
    """Land a reviewed rebase whose finish records its run and dies at the relabel; the head, and that run."""
    head = case.lands_a_reviewed_rebase()
    case.dies_routing(partial(case.finishes, head))
    case.assertEqual(case.runs(), 1)
    return head, readings.pinned_records(case)[0]


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


def _fills_the_comment(case: support.VerificationRecoveryCase) -> None:
    """Fill `case`'s pinned comment to its limit, as another road's records would."""
    filled = case.gh.read_pinned_state(case.issue)
    filled.set(_FILLER, "")
    room = MAX_PINNED_BODY - len(pinned_state_body(filled.data))
    filled.set(_FILLER, "x" * room)
    case.gh.write_pinned_state(case.issue, filled)


def _makes_room(case: support.VerificationRecoveryCase) -> None:
    """Take the filler back off `case`'s pinned comment, as a human making room does."""
    emptied = case.gh.read_pinned_state(case.issue)
    emptied.data.pop(_FILLER)
    case.gh.write_pinned_state(case.issue, emptied)


class SurvivingRefusalTest(support.VerificationRecoveryCase, unittest.TestCase):
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

                self._assert_abandoned(captured)
                self.assert_recovered(head)

    def test_no_room_to_abandon_still_refuses(self) -> None:
        # The base is read elsewhere over a comment with no room for the
        # run's history entry: the run is dropped instead, and the base tip
        # it rests on with it, holding the route. Once room is made and the
        # base reads where it was, the head is routed with nothing recorded,
        # since no base can be proved for it any more. A command that prints
        # nothing leaves a transcript smaller than the entry abandoning it.
        self.configures("true")
        head, _captured = _captures(self)
        _fills_the_comment(self)
        moved = partial(_answered, _BaseStanding.MOVED, lambda: None)
        with patch.object(rewrite_facts, _BASE_READING, side_effect=moved):
            self.recovers()

        self.assert_held(None)
        self.assertEqual(
            (readings.pinned(self)[readings.KEY_REWRITE_BASE], self.runs()),
            (None, 1),
        )
        _makes_room(self)
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
        # that head on its way out -- even where the checkout is put back on
        # the head while that abandonment reads the remote branch, ahead of
        # reading the checkout again. Back on the head, the next recovery
        # routes it with the run still abandoned and nothing run again.
        for put_back_mid_read in (False, True):
            with self.subTest(put_back_mid_read=put_back_mid_read):
                head, captured = self._leaves_early(put_back_mid_read=put_back_mid_read)

                self.recovers()

                self._assert_abandoned(captured)
                self.assert_recovered(head)

    def test_a_remote_observed_off_the_head_abandons(self) -> None:
        # The recovery's fetch finds the remote and the checkout on the landed
        # head, and the remote branch is put back on the anchor before the
        # landing is observed: the observation finds no landing to finish, and
        # the run captured for the head is abandoned before the recovery
        # leaves. With the branch back on the head, the next recovery routes
        # it with the run still abandoned and nothing run, pushed, or
        # announced again.
        head, captured = _captures(self)
        branch = f"refs/heads/{git_support.BRANCH}"
        with _behind_the_classification(partial(self._git, "update-ref", branch, self.anchor, cwd=self._remote)):
            self.recovers()

        self.assert_held(None)
        self._assert_abandoned(captured)
        self._git("update-ref", branch, head, cwd=self._remote)
        self.recovers()
        self._assert_abandoned(captured)
        self.assert_recovered(head)

    def _holds_beside_an_unread_base(self, moves_it, restores) -> tuple:
        """A fresh case's captured run, held over an unread base `moves_it` moved beside; then put back.

        The head and the run, once the recovery held the route and abandoned
        the run, and `restores` put back what moved.
        """
        self.setUp()
        head, captured = _captures(self)
        body = self.issue.body
        unread = partial(_answered, _BaseStanding.UNREAD, partial(moves_it, self))
        with patch.object(rewrite_facts, _BASE_READING, side_effect=unread):
            self.recovers()
        self.assert_held(None)
        self._assert_abandoned(captured)
        restores(self, body)
        return head, captured

    def _leaves_early(self, *, put_back_mid_read: bool) -> tuple:
        """A fresh case's captured run, its checkout committing past the head behind the recovery's classification.

        Put back on the head after that recovery -- or, `put_back_mid_read`,
        while it reads the remote branch on its way out. The head and the run,
        once the recovery held the route and abandoned the run.
        """
        self.setUp()
        head, captured = _captures(self)
        put_back = partial(self._git, "reset", "--quiet", "--hard", head, cwd=self._wt)
        reads = getattr(branch_transport, _REMOTE_READ)
        if put_back_mid_read:
            reads = _RacesPastTheStep(reads, put_back)
        with (
            _behind_the_classification(partial(self._git, *_STRAY_COMMIT, cwd=self._wt)),
            patch.object(branch_transport, _REMOTE_READ, reads),
        ):
            self.recovers()
        self.assert_held(None)
        self._assert_abandoned(captured)
        put_back()
        return head, captured

    def _assert_abandoned(self, captured) -> None:
        """Nothing pending or current, the settled evidence invalidated and `captured` abandoned, and no second run."""
        retired = (*git_support.invalidated(self), (captured.receipt, readings.ABANDONED))
        self.assertEqual(
            (readings.pinned_records(self), self.runs()),
            ((None, None, retired), 1),
        )


if __name__ == "__main__":
    unittest.main()
