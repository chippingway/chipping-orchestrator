# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run whose abandonment is read moving keeps that abandonment, however its first write fails.

A finish recorded its run for the landed head and died posting its artifact,
before it announced anything, and the checkout was reset onto the anchor
before the next recovery. That snapshot is movement under the run, and the road
it chooses resets and clears the attempt -- so the run is abandoned first. Where the abandonment's own write
over the comment read again does not land -- that comment would not read, or
another road moved a record under the write -- it is staged on the tick's own
reading instead and lands there, so the movement is kept: with both heads put
back, a later recovery and the dispatcher's reconciliation settle nothing.
Only a comment that takes no write at all leaves the run unabandoned, and then
the recovery takes no road: nothing is reset, cleared, or parked, and the
attempt's anchor keeps the reconciliation off the run.

A fetch that fails ends in the git owner's abort, whose reset takes the
checkout off the landed head itself: the run is abandoned on the state that
abort's park writes, so it goes in the very write that releases the attempt --
whatever a comment read of the abandonment's own would have answered, and
whether or not the attempt's record names its replay yet, since the receipt
the finish put on the attempt beside the run is what says it is the finish's --
or, where that write does not land, neither goes and the attempt still guards
the run. The park's notice goes out ahead of that write, so it says the write
drops the attempt rather than that it is gone, whether the write is then
refused or lands with its answer lost. Nothing runs, pushes, or announces
again, and no developer is launched.
"""
from __future__ import annotations

import hashlib
import subprocess
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git import branch_transport
from orchestrator.github.pinned_state import PinnedEdit
from orchestrator.workflow.engine import verification_durable
from orchestrator.workflow.engine.review_subjects import REVIEW_SUBJECT
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)
from tests.workflow.interleaving import _RacesPastTheStep

_DURABLE_READ = "durable_comment"

# A fetch of the pull request's branch that failed.
_UNFETCHED = subprocess.CompletedProcess([], 1, "", "unread remote")

# The comment read again for the abandonment answering as one nobody could read.
_UNREAD = (None, verification_durable._UNREAD)

# A requirements revision no reviewer was handed, for a review subject another road moves.
_ELSEWHERE = hashlib.sha256(b"requirements another road recorded").hexdigest()


def _moves_the_subject(case: support.VerificationRecoveryCase) -> None:
    """Move the review subject on `case`'s pinned comment, as another road's write would."""
    moved = case.gh.read_pinned_state(case.issue)
    moved.set(REVIEW_SUBJECT, {**moved.get(REVIEW_SUBJECT), "requirements": _ELSEWHERE})
    case.gh.write_pinned_state(case.issue, moved)


def _unreadable(*_called, **_options):
    """The comment read again for an abandonment, answering as one nobody could read."""
    return _UNREAD


def _unnames_the_replay(case: support.VerificationRecoveryCase) -> None:
    """Blank the replay the attempt's record names, as the window before git's result is recorded leaves it."""
    unnamed = case.gh.read_pinned_state(case.issue)
    unnamed.set(readings.KEY_REWRITE_SHA, None)
    case.gh.write_pinned_state(case.issue, unnamed)


def _puts_the_remote_on(case: support.VerificationRecoveryCase, head: str) -> None:
    """Point `case`'s remote branch at `head`."""
    case._git("update-ref", f"refs/heads/{git_support.BRANCH}", head, cwd=case._remote)


def _puts_the_checkout_on(case: support.VerificationRecoveryCase, head: str) -> None:
    """Reset `case`'s checkout onto `head`."""
    case._git("reset", "--quiet", "--hard", head, cwd=case._wt)


# How the abandonment's write fails: the comment nobody could read again, or a
# record another road moved between that reading and the write.
_UNLANDED = (
    ("the comment would not read again", lambda _case, _original: _unreadable),
    (
        "another road moved a record under the write",
        lambda case, original: _RacesPastTheStep(original, partial(_moves_the_subject, case)),
    ),
)


# The attempt's record of its replay as the abort finds it, beside how it got
# that way: named, or not yet named -- which the receipt the finish put on the
# attempt with the run answers for all the same.
_REPLAYS = (("named", None), ("not yet named", _unnames_the_replay))


# How the write recording an abort's park goes wrong, beside whether it landed
# first: refused outright, or landed with its answer lost.
_UNCONFIRMED = (("refused", False), ("landed, its answer lost", True))

_AWAITING = "awaiting_human"

# What the notice says of the attempt a landed reset releases.
_RELEASED_BY_THE_WRITE = "is dropped by the pinned-state write that records this park, and still stands"


def _answers_the_park(edit, lands: bool, issue, state, **options) -> PinnedEdit:
    """`edit`, the client's strict edit, answering the park's record as refused -- or, where it `lands`, as lost.

    The park's record is the edit flagging the issue awaiting a human over a
    comment that does not; every other edit is answered as it always is.
    """
    if not state.get(_AWAITING) or options["over"].get(_AWAITING):
        return edit(issue, state, **options)
    if not lands:
        return PinnedEdit.MOVED
    edit(issue, state, **options)
    return PinnedEdit.UNCONFIRMED


class UnlandedAbandonmentTest(support.CapturedRunCase, unittest.TestCase):
    """A recovery holds, with its attempt standing, until the abandonment it owes lands."""

    def test_a_failed_write_falls_back(self) -> None:
        # The abandonment's write over the comment read again fails, so it is
        # landed over the tick's own reading: the run is abandoned and the
        # road of a checkout back on the anchor taken. With both heads put
        # back on the landed head, a later recovery and the reconciliation
        # settle nothing.
        for failure, failing in _UNLANDED:
            with self.subTest(failure=failure):
                head, captured = self._recovers_off_the_landing(failing)
                self._assert_released(captured)
                _puts_the_remote_on(self, head)
                _puts_the_checkout_on(self, head)

                self.recovers()
                self.reconciles()

                self._assert_released(captured)

    def test_an_unwritable_comment_holds(self) -> None:
        # No write to the comment lands at all, so the run cannot be
        # abandoned: nothing is cleared or parked, and the reconciliation
        # leaves the run to the attempt still standing, even with the
        # checkout put back on the landed head.
        head, captured = self._recovers_off_the_landing(
            lambda _case, original: original, edit=PinnedEdit.MOVED,
        )

        self.assertFalse(readings.pinned(self).get(_AWAITING))
        self.assert_held(captured)
        _puts_the_checkout_on(self, head)
        self.reconciles()
        self.assertEqual(readings.pinned_records(self)[:2], (captured, None))

    def test_a_reset_carries_its_abandonment(self) -> None:
        # The fetch fails, so the abort resets the checkout onto the anchor:
        # the run is abandoned in the write that releases the attempt, even
        # where the comment would not read again for an abandonment of its
        # own, and whether or not the attempt's record names its replay yet.
        # Put back on the landed head, the checkout settles nothing.
        for replay, unnames in _REPLAYS:
            with self.subTest(replay=replay):
                self.setUp()
                head, captured = self.captures()
                if unnames is not None:
                    unnames(self)
                with (
                    patch.object(branch_transport, "_authed_fetch", return_value=_UNFETCHED),
                    patch.object(verification_durable, _DURABLE_READ, side_effect=_unreadable),
                ):
                    self.recovers()

                self.assertEqual(self._wt_head(), self.anchor)
                self._assert_released(captured)
                _puts_the_checkout_on(self, head)
                self.reconciles()
                self._assert_released(captured)

    def test_an_unconfirmed_park_keeps_its_word(self) -> None:
        # The fetch fails and the abort's reset lands, and the write recording
        # its park is refused, or lands with its answer lost. The notice posted
        # ahead of that write says the write drops the attempt, never that it
        # is gone. Refused, neither the abandonment nor the release is
        # written, so the attempt still guards the run -- the reconciliation
        # leaves it be even with the checkout put back -- and landed, both
        # went together.
        for unconfirmed, lands in _UNCONFIRMED:
            with self.subTest(write=unconfirmed):
                head, captured, notice = self._parks_unconfirmed(lands=lands)

                self.assertIn(_RELEASED_BY_THE_WRITE, notice)
                if lands:
                    self._assert_released(captured)
                else:
                    self.assert_held(captured)
                    _puts_the_checkout_on(self, head)
                    self.reconciles()
                    self.assertEqual(readings.pinned_records(self)[:2], (captured, None))

    def _parks_unconfirmed(self, *, lands: bool) -> tuple:
        """A fresh case's captured run, recovered behind a failed fetch with its park's write going wrong.

        The write lands and loses its answer where `lands` says, and is refused
        outright otherwise. The head, the run, and the notice the park posted.
        """
        self.setUp()
        head, captured = self.captures()
        edit = partial(_answers_the_park, self.gh.edit_pinned_state, lands)
        with (
            patch.object(branch_transport, "_authed_fetch", return_value=_UNFETCHED),
            patch.object(self.gh, "edit_pinned_state", side_effect=edit),
        ):
            self.recovers()
        return head, captured, self.gh.posted_comments[-1][1]

    def _recovers_off_the_landing(self, failing, edit: PinnedEdit | None = None) -> tuple:
        """A fresh case's captured run, its checkout reset onto the anchor, recovered over the reading `failing` gives.

        `edit` is what every strict edit of the comment answers meanwhile,
        where one is given. The head, and the run.
        """
        self.setUp()
        head, captured = self.captures()
        _puts_the_checkout_on(self, self.anchor)
        reread = failing(self, verification_durable.durable_comment)
        edits = self.gh.edit_pinned_state if edit is None else (lambda *_called, **_options: edit)
        with (
            patch.object(verification_durable, _DURABLE_READ, side_effect=reread),
            patch.object(self.gh, "edit_pinned_state", side_effect=edits),
        ):
            self.recovers()
        return head, captured

    def _assert_released(self, captured) -> None:
        """`captured` abandoned and the attempt cleared, with nothing announced, pushed, launched, or run again."""
        recorded = readings.pinned_records(self)
        attempt = readings.pinned(self)[readings.KEY_PENDING_PUSH]
        self.assertEqual(
            (recorded[0], recorded[2][-1], attempt),
            (None, (captured.receipt, readings.ABANDONED), None),
        )
        said = (support.announced(self), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(said, ([], 0, 0))
        self.assertEqual(self.runs(), 1)


if __name__ == "__main__":
    unittest.main()
