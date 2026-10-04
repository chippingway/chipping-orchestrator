# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One writer per repository issue on this host, contended between processes.

Every holder below is a separate interpreter, because the claim exists for the
process whose scheduler this one cannot read: a second poller on the same host.
"""
from __future__ import annotations

import errno
import fcntl
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import config
from orchestrator.scheduler import claim_notes, writer_claims
from tests.scheduler.writer_claim_helpers import RETIRED_CYCLE, SharedNamespaceCase, descriptors_on
from tests.support.writer_claim_processes import HELD, REFUSED, RELEASED

# The repository's numeric id, and another repository's.
_REPO_ID = 42
_OTHER_REPO_ID = 43
_ISSUE = 7
_OTHER_ISSUE = 8
_SCHEDULER_LOG = "orchestrator.scheduler"

# What a holder process does with the claim once it reports: keeps it until
# told, keeps it having noted the late cycle its hold retires, or lets it go
# at once.
_HOLD = "hold"
_RETIRE = "retire"
_TRY = "try"


class ProcessContentionTest(SharedNamespaceCase):
    """A key another process holds is refused here, and nothing else is."""

    def test_a_held_key_is_refused_until_let_go(self) -> None:
        holder = self.other_process(_REPO_ID, _ISSUE, _HOLD)
        self.assertEqual(holder.said(), HELD)

        with self.assertLogs(_SCHEDULER_LOG) as logged:
            self.assertFalse(self.granted_here(_REPO_ID, _ISSUE))
            self.assertIn(f"repo_id={_REPO_ID} issue=#{_ISSUE} reason=held_elsewhere", logged.output[0])
        # Different keys stay independent: another issue of this repository,
        # and the same issue number in another repository.
        self.assertTrue(self.granted_here(_REPO_ID, _OTHER_ISSUE))
        self.assertTrue(self.granted_here(_OTHER_REPO_ID, _ISSUE))

        self.assertEqual(holder.let_go(), 0)
        self.assertTrue(self.granted_here(_REPO_ID, _ISSUE))

    def test_holding_here_refuses_another_process(self) -> None:
        with writer_claims.issue_writer(_REPO_ID, _ISSUE) as held:
            self.assertTrue(held)
            contender = self.other_process(_REPO_ID, _ISSUE, _TRY)
            self.assertEqual(contender.said(), REFUSED)
            self.assertEqual(contender.exited(), 0)
        retry = self.other_process(_REPO_ID, _ISSUE, _TRY)
        self.assertEqual(retry.said(), HELD)


class ThreadSharingTest(SharedNamespaceCase):
    """Inside one process: one writer per key, and the receipt let in beside it."""

    def test_a_second_writer_here_is_refused(self) -> None:
        with writer_claims.issue_writer(_REPO_ID, _ISSUE) as held:
            self.assertTrue(held)
            with self.assertLogs(_SCHEDULER_LOG) as logged:
                self.assertFalse(_on_another_thread(self.granted_here, _REPO_ID, _ISSUE))
                self.assertIn("reason=held_here", logged.output[0])
            self.assertTrue(_on_another_thread(self.granted_here, _REPO_ID, _OTHER_ISSUE))
        self.assertTrue(_on_another_thread(self.granted_here, _REPO_ID, _ISSUE))

    def test_alongside_keeps_the_lock_to_the_last(self) -> None:
        claim_file = writer_claims.claim_path(_REPO_ID, _ISSUE)
        with writer_claims.issue_writer(_REPO_ID, _ISSUE) as writer:
            self.assertTrue(writer)
            with writer_claims.issue_writer(_REPO_ID, _ISSUE, alongside=True) as beside:
                self.assertTrue(beside, "a holder alongside joins this process's writer")
                self.assertEqual(descriptors_on(claim_file), 1, "one file description per key")
        # The other way round: a holder alongside keeps no writer here out,
        # and keeps the lock against other processes once the writer leaves.
        with writer_claims.issue_writer(_REPO_ID, _ISSUE, alongside=True) as beside:
            self.assertTrue(beside)
            self.assertTrue(self.granted_here(_REPO_ID, _ISSUE))
            self.assertEqual(self.other_process(_REPO_ID, _ISSUE, _TRY).said(), REFUSED)
        self.assertEqual(descriptors_on(claim_file), 0)
        self.assertEqual(self.other_process(_REPO_ID, _ISSUE, _TRY).said(), HELD)

    def test_alongside_is_refused_by_another_process(self) -> None:
        holder = self.other_process(_REPO_ID, _ISSUE, _HOLD)
        self.assertEqual(holder.said(), HELD)
        with writer_claims.issue_writer(_REPO_ID, _ISSUE, alongside=True) as beside:
            self.assertFalse(beside)
        self.assertEqual(holder.let_go(), 0)


class ProcessReleaseTest(SharedNamespaceCase):
    """Every way a holder ends gives the claim back, and leaves its file."""

    def test_a_killed_holder_holds_nothing(self) -> None:
        holder = self.other_process(_REPO_ID, _ISSUE, _HOLD)
        self.assertEqual(holder.said(), HELD)
        claim_file = writer_claims.claim_path(_REPO_ID, _ISSUE)
        inode = claim_file.stat().st_ino

        holder.killed()

        self.assertTrue(self.granted_here(_REPO_ID, _ISSUE))
        # Never unlinked: a lock lives on the inode, so a file recreated under
        # the same path would let two processes each hold "the" claim.
        self.assertEqual(claim_file.stat().st_ino, inode)

    def test_a_raising_body_releases_a_live_holder(self) -> None:
        holder = self.other_process(_REPO_ID, _ISSUE, "raise")
        self.assertEqual(holder.said(), HELD)
        self.assertEqual(holder.said(), RELEASED)

        # The holder is still running; only the exception ended its claim.
        self.assertTrue(self.granted_here(_REPO_ID, _ISSUE))
        self.assertEqual(holder.let_go(), 0)

    def test_every_exit_closes_the_descriptor(self) -> None:
        claim_file = writer_claims.claim_path(_REPO_ID, _ISSUE)
        with self.assertRaises(RuntimeError), writer_claims.issue_writer(_REPO_ID, _ISSUE) as held:
            self.assertTrue(held)
            self.assertEqual(descriptors_on(claim_file), 1)
            raise RuntimeError("the body failed")
        self.assertEqual(descriptors_on(claim_file), 0)

        holder = self.other_process(_REPO_ID, _ISSUE, _HOLD)
        self.assertEqual(holder.said(), HELD)
        with writer_claims.issue_writer(_REPO_ID, _ISSUE) as held:
            self.assertFalse(held)
            self.assertEqual(descriptors_on(claim_file), 0)


class HoldNotesTest(SharedNamespaceCase):
    """What a hold tells the pollers it refuses, and what the next holder finds."""

    def test_a_retirement_note_ends_with_its_hold(self) -> None:
        holder = self.other_process(_REPO_ID, _ISSUE, _RETIRE)
        self.assertEqual(holder.said(), HELD)

        with self.assertLogs(_SCHEDULER_LOG):
            self.assertFalse(self.granted_here(_REPO_ID, _ISSUE))
        self.assertEqual(claim_notes.noted_retirement(_REPO_ID, _ISSUE), RETIRED_CYCLE)
        self.assertIsNone(claim_notes.noted_retirement(_REPO_ID, _OTHER_ISSUE), "a key nobody noted on")

        self.assertEqual(holder.let_go(), 0)
        with writer_claims.issue_writer(_REPO_ID, _ISSUE) as held:
            self.assertTrue(held)
            self.assertIsNone(
                claim_notes.noted_retirement(_REPO_ID, _ISSUE), "a note is its own hold's, and ends with it",
            )

    def test_only_a_holding_writer_notes(self) -> None:
        claim_notes.note_retirement(_REPO_ID, _ISSUE, RETIRED_CYCLE)
        with writer_claims.issue_writer(_REPO_ID, _ISSUE, alongside=True) as beside:
            self.assertTrue(beside)
            claim_notes.note_retirement(_REPO_ID, _ISSUE, RETIRED_CYCLE)
        self.assertIsNone(claim_notes.noted_retirement(_REPO_ID, _ISSUE))

        with writer_claims.issue_writer(_REPO_ID, _ISSUE) as held:
            self.assertTrue(held)
            claim_notes.note_retirement(_REPO_ID, _ISSUE, RETIRED_CYCLE)
            self.assertEqual(claim_notes.noted_retirement(_REPO_ID, _ISSUE), RETIRED_CYCLE)

    def test_only_other_pollers_holds_are_counted(self) -> None:
        for _ in range(2):
            self.assertTrue(self.granted_here(_REPO_ID, _ISSUE))
        self.assertEqual(claim_notes.foreign_holds(_REPO_ID, _ISSUE), 0, "this process's own holds")

        for counted in (1, 2):
            self.assertEqual(self.other_process(_REPO_ID, _ISSUE, _TRY).said(), HELD)
            self.assertEqual(claim_notes.foreign_holds(_REPO_ID, _ISSUE), counted - 1, "found only by taking it")
            self.assertTrue(self.granted_here(_REPO_ID, _ISSUE))
            self.assertTrue(self.granted_here(_REPO_ID, _ISSUE))
            self.assertEqual(claim_notes.foreign_holds(_REPO_ID, _ISSUE), counted)
        self.assertEqual(claim_notes.foreign_holds(_REPO_ID, _OTHER_ISSUE), 0, "counted per key")


class NamespaceTest(SharedNamespaceCase):
    """Where the claims live, and what a claim that cannot be worked does."""

    def test_claims_live_under_the_checkout_root(self) -> None:
        claim_file = writer_claims.claim_path(_REPO_ID, _ISSUE)

        self.assertEqual(claim_file.parent, config.WORKTREES_DIR / ".issue-writer-claims")
        self.assertNotEqual(claim_file, writer_claims.claim_path(_REPO_ID, _OTHER_ISSUE))
        self.assertNotEqual(claim_file, writer_claims.claim_path(_OTHER_REPO_ID, _ISSUE))

    def test_an_unopenable_namespace_withholds(self) -> None:
        # A file where the namespace directory belongs: nothing can be
        # coordinated on, and that is answered as a refusal rather than as
        # leave to write the issue uncoordinated.
        (self.root / ".issue-writer-claims").write_text("", encoding="utf-8")

        with self.assertLogs(_SCHEDULER_LOG, level="WARNING") as logged:
            self.assertFalse(self.granted_here(_REPO_ID, _ISSUE))
            self.assertIn("reason=unusable", logged.output[0])

    def test_a_broken_lock_withholds_the_issue(self) -> None:
        # A lock table with no room is not a holder, so it is never waited out
        # or mistaken for contention -- and never treated as granted either.
        broken = OSError(errno.ENOLCK, "no locks available")
        claim_file = writer_claims.claim_path(_REPO_ID, _ISSUE)
        with (
            patch.object(fcntl, "flock", side_effect=broken),
            self.assertLogs(_SCHEDULER_LOG, level="WARNING") as logged,
        ):
            self.assertFalse(self.granted_here(_REPO_ID, _ISSUE))
            self.assertIn("reason=unusable", logged.output[0])
        self.assertEqual(descriptors_on(claim_file), 0)


def _on_another_thread(asked, *args):
    """What `asked` answers when a thread other than this one asks it."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asked, *args).result()


if __name__ == "__main__":
    unittest.main()
