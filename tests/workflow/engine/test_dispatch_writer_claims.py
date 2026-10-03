# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a tick does with an issue another poller on this host is writing.

Nothing it would need the claim for: no refetch, no pinned read, no recovery,
no receipt, no handler, and no evaluation record, on every dispatch mode a tick
can take -- while every other issue in the same tick is dispatched as ever. What
it does keep is a close it read, in this process's latch and nowhere else, so a
human reopening the issue before the claim comes back cannot take the reading
away. The claim is the repository's canonical name and the issue number, so a
spec configured under another name meets the same holder.
"""
from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from orchestrator.scheduler import writer_claims
from tests.support.writer_claims import claimable, held_elsewhere, unusable_namespace
from tests.workflow.engine import cleanup_deferral_support as _deferral
from tests.workflow.engine.writer_claim_test_support import (
    FAMILY_PARENT,
    FREE_ISSUES,
    HELD_CLOSED,
    HELD_ISSUES,
    WAITING_CHILD,
    StandInHandler,
    WriterClaimDispatchCase,
)
from tests.workflow.fixtures import LABEL_READY

# Each way a tick can execute its issues, as (name, `parallel_limit`, whether
# the scheduler takes the dispatch over): the sequential loop, the bounded
# in-tick pool, and the scheduler's fan-out submits and family bucket.
_DISPATCH_MODES = (
    ("sequential", 1, False),
    ("pool", 2, False),
    ("scheduler", 4, True),
)

_ALL_ISSUES = HELD_ISSUES | FREE_ISSUES

# The two ways a claim is refused without anyone in this process holding it:
# another poller holding it, and a namespace nothing can be locked in.
_HELD_ELSEWHERE = "held elsewhere"
_UNUSABLE = "unusable"

_REFUSED_IN_EVERY_MODE = tuple(
    (refusal, mode)
    for refusal in (_HELD_ELSEWHERE, _UNUSABLE)
    for mode in _DISPATCH_MODES
)

_KEY_AWAITING_HUMAN = "awaiting_human"


class ContendedDispatchTest(WriterClaimDispatchCase):
    """A held issue is skipped whole, and retried once it is let go."""

    def test_held_issues_are_skipped_then_retried(self) -> None:
        for mode, limit, scheduled in _DISPATCH_MODES:
            with self.subTest(mode=mode):
                self.seeded()
                self._ticked_while_held(limit, scheduled=scheduled)
                self._ticked_once_released(limit, scheduled=scheduled)

    def test_a_raising_handler_gives_its_claim_back(self) -> None:
        for mode, limit, scheduled in _DISPATCH_MODES:
            with self.subTest(mode=mode):
                self.seeded()

                self.ticked(StandInHandler(*_ALL_ISSUES), limit=limit, scheduled=scheduled)

                for issue_number in _ALL_ISSUES:
                    self.assertTrue(claimable(self.github.repo_slug, issue_number), f"#{issue_number} still claimed")
                retry = StandInHandler()
                self.ticked(retry, limit=limit, scheduled=scheduled)
                self.assertEqual(set(retry.ran), set(_ALL_ISSUES))

    def _ticked_while_held(self, limit: int, *, scheduled: bool) -> None:
        """A tick over the held issues, held under the name GitHub answers.

        The spec is configured under another name, which keys no claim at all.
        """
        stand_in = StandInHandler()
        with held_elsewhere(self.github.repo_slug, *HELD_ISSUES):
            self.ticked(stand_in, limit=limit, scheduled=scheduled)

        self.assertEqual(set(stand_in.ran), set(FREE_ISSUES), "only the free issues run")
        self.assertEqual(self.written_issues(), set(FREE_ISSUES), "nothing is written on a held one")
        self.assertEqual(self.evaluated_issues(), set(FREE_ISSUES), "nothing is accounted for one")
        self.assertEqual(self._observed(_deferral.REPO_SLUG), {HELD_CLOSED}, "the close it read is kept")

    def _ticked_once_released(self, limit: int, *, scheduled: bool) -> None:
        """The ticks after the holder lets go.

        The kept close is swept first, under the claim, and found to end
        nothing; the issue's own handler runs on the tick after that.
        """
        swept = StandInHandler()
        self.ticked(swept, limit=limit, scheduled=scheduled)

        self.assertEqual(set(swept.ran), set(_ALL_ISSUES - {HELD_CLOSED}))
        self.assertEqual(self._observed(_deferral.REPO_SLUG), frozenset())

        retry = StandInHandler()
        self.ticked(retry, limit=limit, scheduled=scheduled)

        self.assertEqual(set(retry.ran), set(_ALL_ISSUES), "a released issue runs again")
        self.assertEqual(self.written_issues(), set(_ALL_ISSUES))


class ContendedFamilyWriteTest(WriterClaimDispatchCase):
    """A parent's handler writes a child only under the child's own claim."""

    def test_a_held_child_is_released_by_a_later_walk(self) -> None:
        for mode, limit, scheduled in _DISPATCH_MODES:
            with self.subTest(mode=mode):
                self.seeded_family()

                with held_elsewhere(self.github.repo_slug, WAITING_CHILD):
                    self.ticked(StandInHandler(), limit=limit, scheduled=scheduled)

                self.assertEqual(self.github.label_history, [], "the held child is not released")
                self.assertFalse(self.github.pinned_data(FAMILY_PARENT).get(_KEY_AWAITING_HUMAN), "nothing parks")

                self.ticked(StandInHandler(), limit=limit, scheduled=scheduled)

                # Released, and picked up on the same tick from there.
                self.assertEqual(self.github.label_history[0], (WAITING_CHILD, LABEL_READY))


class ContendedCleanupTest(_deferral.DeferralCase, unittest.TestCase):
    """A close owed to a held owner stays owed, and is swept once it is free.

    The owner is a closed umbrella still holding a snapshot ref, whose close an
    earlier tick observed and wrote down while a worker held it. What a later
    tick owes it is a cleanup pass -- the recovery route, not a stage -- and
    that pass reads the record and writes on the strength of it, so it is a
    writer like any other.
    """

    def setUp(self) -> None:
        super().setUp()
        self._tick_a_worker_held(self._scheduler())
        self.owed = frozenset((_deferral.OWNER_NUMBER,))
        self.assertEqual(self._observed(_deferral.REPO_SLUG), self.owed)

    def test_a_held_owner_keeps_its_observation(self) -> None:
        for mode, limit, scheduled in _DISPATCH_MODES:
            with self.subTest(mode=mode):
                comments = list(self.github.posted_comments)
                record = self.github.pinned_data(_deferral.OWNER_NUMBER)

                with held_elsewhere(self.github.repo_slug, _deferral.OWNER_NUMBER):
                    _ticked_on(self, limit, scheduled=scheduled)

                self.assertEqual(self._observed(_deferral.REPO_SLUG), self.owed)
                self.assertEqual(self.github.posted_comments, comments)
                self.assertEqual(self.github.pinned_data(_deferral.OWNER_NUMBER), record)
                self.assertFalse(self._cancelled())

    def test_a_released_owner_is_swept_next_tick(self) -> None:
        with held_elsewhere(self.github.repo_slug, _deferral.OWNER_NUMBER):
            _ticked_on(self, 4, scheduled=True)

        _ticked_on(self, 4, scheduled=True)

        self.assertTrue(self._cancelled())
        self.assertEqual(self._observed(_deferral.REPO_SLUG), frozenset())
        self.stage.assert_not_called()


class ContendedFreshCloseTest(_deferral.DeferralCase, unittest.TestCase):
    """A close first read while the owner's claim is refused is latched, and nothing more.

    The owner is a closed umbrella still holding a snapshot ref, and no earlier
    tick has seen it closed. Whatever refuses the claim -- another poller
    holding it, or a namespace nothing can be locked in -- the poll may neither
    read the record that says whether the close is owed nor post the receipt
    that would make it durable, since both are the holder's. The latch is what
    is left, and it is what outlives a human reopening the issue.
    """

    def setUp(self) -> None:
        super().setUp()
        self.owed = frozenset((_deferral.OWNER_NUMBER,))

    def test_a_refused_claim_keeps_the_close(self) -> None:
        for refusal, (mode, limit, scheduled) in _REFUSED_IN_EVERY_MODE:
            with self.subTest(refusal=refusal, mode=mode):
                self._seeded_owner()
                self._ticked_refused(refusal, limit, scheduled=scheduled)

                self._reopened()
                _ticked_on(self, limit, scheduled=scheduled)

                self.assertTrue(self._cancelled(), "the reopened owner's cycle is still ended")
                self.stage.assert_not_called()
                self.assertEqual(self._observed(_deferral.REPO_SLUG), frozenset())

    def test_a_refused_submit_writes_nothing(self) -> None:
        # A worker of this process is running the owner, so the scheduler
        # refuses the submit, and another poller holds the claim besides: the
        # refusal's own recovery reads and writes nothing either.
        reads = Mock(wraps=self.github.read_pinned_state)
        with (
            held_elsewhere(self.github.repo_slug, _deferral.OWNER_NUMBER),
            patch.object(self.github, "read_pinned_state", reads),
        ):
            self._tick_a_worker_held(self._scheduler())

        self.assertEqual(reads.call_count, 0)
        self.assertEqual(_deferral.receipts_on(self.github), [])
        self.assertEqual(self._observed(_deferral.REPO_SLUG), self.owed)

    def test_a_receipt_lands_beside_our_own_writer(self) -> None:
        # The worker running the owner holds its claim in THIS process, and the
        # receipt is a comment built to land beside that worker, so the poll
        # writes it as it always has.
        with writer_claims.issue_writer(self.github.repo_slug, _deferral.OWNER_NUMBER) as held:
            self.assertTrue(held)
            self._tick_a_worker_held(self._scheduler())

        self.assertEqual(len(_deferral.receipts_on(self.github)), 1)
        self.assertEqual(self._observed(_deferral.REPO_SLUG), self.owed)

    def _seeded_owner(self) -> None:
        """The closed owner afresh, in a process that has observed nothing."""
        self.github = _deferral.owner_holding_a_ref()
        self._fresh_process()
        self.stage.reset_mock()

    def _ticked_refused(self, refusal: str, limit: int, *, scheduled: bool) -> None:
        """A tick that first reads the close with the owner's claim refused."""
        reads = Mock(wraps=self.github.read_pinned_state)
        with _refused(refusal, self.github), patch.object(self.github, "read_pinned_state", reads):
            _ticked_on(self, limit, scheduled=scheduled)

        self.assertEqual(reads.call_count, 0, "the record is not read")
        self.assertEqual(_deferral.receipts_on(self.github), [], "the close is not written down")
        self.assertEqual(self._observed(_deferral.REPO_SLUG), self.owed, "but it is latched")


def _refused(refusal: str, github):
    """The refusal a case names, as the block it holds over the owner."""
    if refusal == _HELD_ELSEWHERE:
        return held_elsewhere(github.repo_slug, _deferral.OWNER_NUMBER)
    return unusable_namespace()


def _ticked_on(case: _deferral.DeferralCase, limit: int, *, scheduled: bool) -> None:
    """One tick over the case's owner, through the mode the arguments name."""
    if scheduled:
        case._ticked(case._scheduler())
        return
    _deferral.ticked_directly(case, limit)


if __name__ == "__main__":
    unittest.main()
