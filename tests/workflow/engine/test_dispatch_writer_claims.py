# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a tick does with an issue another poller on this host is writing.

Nothing it would need the claim for: no refetch, no recovery, no receipt, no
handler, no write, and no evaluation record, on every dispatch mode a tick can
take -- while every other issue in the same tick is dispatched as ever. What it
does keep is a close it read, in this process's latch and nowhere else, scoped
to the cycle one read of the record says that close ends, so a human reopening
the issue before the claim comes back cannot take the reading away. The claim
is the repository's numeric id and the issue number, so a spec
configured under another name, and a poller that fetched the repository before
it was renamed, meet the same holder.
"""
from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from orchestrator.scheduler import writer_claims
from tests.support.writer_claims import claimable, held_elsewhere, unusable_namespace
from tests.workflow.engine import cleanup_deferral_support as _deferral
from tests.workflow.engine.contended_close_support import ticked_on
from tests.workflow.engine.renamed_poller_support import RenamedRepositoryCase
from tests.workflow.engine.writer_claim_test_support import (
    ALL_ISSUES,
    DISPATCH_MODES,
    FAMILY_PARENT,
    HELD_ISSUES,
    WAITING_CHILD,
    HeldIssuesCase,
    StandInHandler,
    WriterClaimDispatchCase,
)
from tests.workflow.fixtures import LABEL_READY

# The two ways a claim is refused without anyone in this process holding it:
# another poller holding it, and a namespace nothing can be locked in.
_HELD_ELSEWHERE = "held elsewhere"
_UNUSABLE = "unusable"

_REFUSED_IN_EVERY_MODE = tuple(
    (refusal, mode)
    for refusal in (_HELD_ELSEWHERE, _UNUSABLE)
    for mode in DISPATCH_MODES
)

_KEY_AWAITING_HUMAN = "awaiting_human"


class ContendedDispatchTest(HeldIssuesCase):
    """A held issue is skipped whole, and retried once it is let go."""

    def test_held_issues_are_skipped_then_retried(self) -> None:
        for mode, limit, scheduled in DISPATCH_MODES:
            with self.subTest(mode=mode):
                self.seeded()
                held = held_elsewhere(self.github.repo_id, *HELD_ISSUES)
                self.ticked_while_held(held, limit=limit, scheduled=scheduled)
                self.ticked_once_released(limit=limit, scheduled=scheduled)

    def test_a_raising_handler_gives_its_claim_back(self) -> None:
        for mode, limit, scheduled in DISPATCH_MODES:
            with self.subTest(mode=mode):
                self.seeded()

                self.ticked(StandInHandler(*ALL_ISSUES), limit=limit, scheduled=scheduled)

                for issue_number in ALL_ISSUES:
                    self.assertTrue(claimable(self.github.repo_id, issue_number), f"#{issue_number} still claimed")
                retry = StandInHandler()
                self.ticked(retry, limit=limit, scheduled=scheduled)
                self.assertEqual(set(retry.ran), set(ALL_ISSUES))


class RenamedRepositoryTest(RenamedRepositoryCase):
    """A claim held under the name a repository had is held under the name it has.

    Each poller names the repository as GitHub answered when it fetched it, so
    a poller started before a rename and one started after it name it two ways
    for as long as both run -- and this one's spec a third. The id each keys
    its claims on is one.
    """

    def test_a_held_issue_is_skipped_then_retried(self) -> None:
        for mode, limit, scheduled in DISPATCH_MODES:
            with self.subTest(mode=mode):
                self.seeded()
                held = self.held_before_the_rename(*HELD_ISSUES)
                self.ticked_while_held(held, limit=limit, scheduled=scheduled)
                self.ticked_once_released(limit=limit, scheduled=scheduled)

    def test_a_held_child_is_not_released(self) -> None:
        self.seeded_family()

        with self.held_before_the_rename(WAITING_CHILD):
            self.ticked(StandInHandler(), limit=1, scheduled=False)

        self.assertEqual(self.github.label_history, [], "a parent's walk meets the same holder")


class ContendedFamilyWriteTest(WriterClaimDispatchCase):
    """A parent's handler writes a child only under the child's own claim."""

    def test_a_held_child_is_released_by_a_later_walk(self) -> None:
        for mode, limit, scheduled in DISPATCH_MODES:
            with self.subTest(mode=mode):
                self.seeded_family()

                with held_elsewhere(self.github.repo_id, WAITING_CHILD):
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
        for mode, limit, scheduled in DISPATCH_MODES:
            with self.subTest(mode=mode):
                comments = list(self.github.posted_comments)
                record = self.github.pinned_data(_deferral.OWNER_NUMBER)

                with held_elsewhere(self.github.repo_id, _deferral.OWNER_NUMBER):
                    ticked_on(self, limit, scheduled=scheduled)

                self.assertEqual(self._observed(_deferral.REPO_SLUG), self.owed)
                self.assertEqual(self.github.posted_comments, comments)
                self.assertEqual(self.github.pinned_data(_deferral.OWNER_NUMBER), record)
                self.assertFalse(self._cancelled())

    def test_a_released_owner_is_swept_next_tick(self) -> None:
        with held_elsewhere(self.github.repo_id, _deferral.OWNER_NUMBER):
            ticked_on(self, 4, scheduled=True)

        ticked_on(self, 4, scheduled=True)

        self.assertTrue(self._cancelled())
        self.assertEqual(self._observed(_deferral.REPO_SLUG), frozenset())
        self.stage.assert_not_called()


class ContendedFreshCloseTest(_deferral.DeferralCase, unittest.TestCase):
    """A close first read while the owner's claim is refused is latched, and nothing more.

    The owner is a closed umbrella still holding a snapshot ref, and no earlier
    tick has seen it closed. Whatever refuses the claim -- another poller
    holding it, or a namespace nothing can be locked in -- the poll may not
    post the receipt that would make the close durable, since that is the
    holder's. It reads the record once, for the cycle the close ends, and the
    latch scoped to that cycle is what is left, and what outlives a human
    reopening the issue.
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
                ticked_on(self, limit, scheduled=scheduled)

                self.assertTrue(self._cancelled(), "the reopened owner's cycle is still ended")
                self.stage.assert_not_called()
                self.assertEqual(self._observed(_deferral.REPO_SLUG), frozenset())

    def test_a_refused_submit_writes_nothing(self) -> None:
        # A worker of this process is running the owner, so the scheduler
        # refuses the submit, and another poller holds the claim besides: the
        # refusal's own recovery reads and writes nothing, past the one read
        # the enumeration took for the cycle it keeps.
        reads = Mock(wraps=self.github.read_pinned_state)
        with (
            held_elsewhere(self.github.repo_id, _deferral.OWNER_NUMBER),
            patch.object(self.github, "read_pinned_state", reads),
        ):
            self._tick_a_worker_held(self._scheduler())

        self.assertEqual(reads.call_count, 1)
        self.assertEqual(_deferral.receipts_on(self.github), [])
        self.assertEqual(self._observed(_deferral.REPO_SLUG), self.owed)

    def test_a_receipt_lands_beside_our_own_writer(self) -> None:
        # The worker running the owner holds its claim in THIS process, and the
        # receipt is a comment built to land beside that worker, so the poll
        # writes it as it always has.
        with writer_claims.issue_writer(self.github.repo_id, _deferral.OWNER_NUMBER) as held:
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
        record = self.github.pinned_data(_deferral.OWNER_NUMBER)
        reads = Mock(wraps=self.github.read_pinned_state)
        with _refused(refusal, self.github), patch.object(self.github, "read_pinned_state", reads):
            ticked_on(self, limit, scheduled=scheduled)

        self.assertEqual(reads.call_count, 1, "the record is read once, for the cycle the close ends")
        self.assertEqual(self.github.pinned_data(_deferral.OWNER_NUMBER), record, "and not written")
        self.assertEqual(_deferral.receipts_on(self.github), [], "the close is not written down")
        self.assertEqual(self._observed(_deferral.REPO_SLUG), self.owed, "but it is latched")


def _refused(refusal: str, github):
    """The refusal a case names, as the block it holds over the owner."""
    if refusal == _HELD_ELSEWHERE:
        return held_elsewhere(github.repo_id, _deferral.OWNER_NUMBER)
    return unusable_namespace()


if __name__ == "__main__":
    unittest.main()
