# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run whose landing is read moving is abandoned before any road, and nothing is taken until that lands.

A finish recorded its run for the landed head and died posting its artifact,
before it announced anything, and the checkout was reset onto the anchor
before the next recovery. That snapshot is movement under the run, and the road
it chooses resets and clears the attempt -- so the run is abandoned first, as
the attempt's checkpoint over the reading the tick last confirmed. Where that
write does not land -- the comment would not read for it, or no edit of it
lands -- the recovery takes no road: nothing is reset, cleared, or parked, and
the attempt's anchor keeps the reconciliation off the run, until a later tick
lands the abandonment and takes the road; with both heads put back, a later
recovery and the dispatcher's reconciliation then settle nothing.

A fetch that fails ends in the git owner's abort, whose reset takes the
checkout off the landed head itself: the run is abandoned on the state that
abort's park writes, so it goes in the very write that releases the attempt --
whether or not the attempt's record names its replay yet, since the receipt
the finish put on the attempt beside the run is what says it is the finish's --
or, where that write does not land, neither goes and the attempt still guards
the run. The park's notice goes out ahead of that write, so it says the write
drops the attempt rather than that it is gone, whether the write is then
refused or lands with its answer lost -- either of which the next tick, reading
the comment afresh, finds as it then stands. Nothing runs, pushes, or announces
again, and no developer is launched.
"""
from __future__ import annotations

import subprocess
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git import branch_transport
from orchestrator.github.pinned_state import PinnedEdit
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)
from tests.workflow.interleaving import _RacesPastTheStep

_FETCH = "_authed_fetch"

# A fetch of the pull request's branch that failed.
_UNFETCHED = subprocess.CompletedProcess([], 1, "", "unread remote")

# What the recovery logs where the abandonment's checkpoint could not read the comment it lands over.
_UNREAD_CHECKPOINT = "the write abandoning the evidence captured for the landing came back unreadable"


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


def _unread_behind_the_fetch(case: support.VerificationRecoveryCase):
    """A patch leaving the comment's next read unanswered once the recovery has fetched the pull request's branch."""
    unread = partial(case.gh.pinned_failures.unanswered_once.add, case.issue.number)
    return patch.object(branch_transport, _FETCH, _RacesPastTheStep(getattr(branch_transport, _FETCH), unread))


def _refuses_every_edit(case: support.VerificationRecoveryCase):
    """A patch answering every strict edit of `case`'s comment as one that found it moved."""
    return patch.object(case.gh, "edit_pinned_state", return_value=PinnedEdit.MOVED)


# The attempt's record of its replay as the abort finds it, beside how it got
# that way: named, or not yet named -- which the receipt the finish put on the
# attempt with the run answers for all the same.
_REPLAYS = (("named", None), ("not yet named", _unnames_the_replay))


# How the write recording an abort's park goes wrong, beside whether it landed
# first: refused outright, or landed with its answer lost -- each as the client
# answers the strict edit that record lands through.
_UNCONFIRMED = (("refused", False), ("landed, its answer lost", True))

# What the notice says of the attempt a landed reset releases.
_RELEASED_BY_THE_WRITE = "is dropped by the pinned-state write that records this park, and still stands"


class UnlandedAbandonmentTest(support.CapturedRunCase, unittest.TestCase):
    """A recovery holds, with its attempt standing, until the abandonment it owes lands."""

    def test_an_unread_comment_holds_the_road(self) -> None:
        # The comment does not answer the read the abandonment's checkpoint
        # lands over, so the run is not abandoned and the recovery takes no
        # road: nothing is reset, cleared, parked, or posted. The next tick
        # lands the abandonment and takes the road of a checkout back on the
        # anchor; with both heads put back on the landed head, a later
        # recovery and the reconciliation settle nothing.
        with self.assertLogs("orchestrator.base_sync") as logged:
            head, captured = self._recovers_off_the_landing(_unread_behind_the_fetch)
            self.assertIn(_UNREAD_CHECKPOINT, "\n".join(logged.output))

        self.assert_held(captured)
        self.recovers()
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
        head, captured = self._recovers_off_the_landing(_refuses_every_edit)

        self.assertFalse(readings.pinned(self).get("awaiting_human"))
        self.assert_held(captured)
        _puts_the_checkout_on(self, head)
        self.reconciles()
        self.assertEqual(readings.pinned_records(self)[:2], (captured, None))

    def test_a_reset_carries_its_abandonment(self) -> None:
        # The fetch fails, so the abort resets the checkout onto the anchor:
        # the run is abandoned in the write that releases the attempt, whether
        # or not the attempt's record names its replay yet. Put back on the
        # landed head, the checkout settles nothing.
        for replay, unnames in _REPLAYS:
            with self.subTest(replay=replay):
                self.setUp()
                head, captured = self.captures()
                if unnames is not None:
                    unnames(self)
                with patch.object(branch_transport, _FETCH, return_value=_UNFETCHED):
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
        failing = self.gh.pinned_failures.lost if lands else self.gh.pinned_failures.refused
        failing.add(self.issue.number)
        with patch.object(branch_transport, _FETCH, return_value=_UNFETCHED):
            self.recovers()
        failing.discard(self.issue.number)
        return head, captured, self.gh.posted_comments[-1][1]

    def _recovers_off_the_landing(self, failing) -> tuple:
        """A fresh case's captured run, its checkout reset onto the anchor, recovered inside `failing(self)`.

        The head, and the run.
        """
        self.setUp()
        head, captured = self.captures()
        _puts_the_checkout_on(self, self.anchor)
        with failing(self):
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
