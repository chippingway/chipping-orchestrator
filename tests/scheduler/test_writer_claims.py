# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One writer per repository issue on this host, contended between processes.

Every holder below is a separate interpreter, because the claim exists for the
process whose scheduler this one cannot read: a second poller on the same host.
"""
from __future__ import annotations

import errno
import fcntl
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import DEFAULT, patch

from orchestrator import config
from orchestrator.scheduler import claim_notes, writer_claims
from tests.scheduler.writer_claim_helpers import (
    CUT_CYCLE,
    LOCKED,
    RETIRED_CYCLE,
    SharedNamespaceCase,
    descriptors_on,
)
from tests.support.writer_claim_processes import HELD, REFUSED, RELEASED, OtherProcess

# The repository's numeric id, and another repository's.
_REPO_ID = 42
_OTHER_REPO_ID = 43
_ISSUE = 7
_OTHER_ISSUE = 8
_SCHEDULER_LOG = "orchestrator.scheduler"
_ENCODING = "utf-8"

# What a holder process does with the claim once it reports: keeps it until
# told, keeps it having noted the late cycle its hold retires, or lets it go
# at once -- and the two that run out of room on the claim file mid-record.
_HOLD = "hold"
_RETIRE = "retire"
_TRY = "try"
_CUT_NOTE = "cut-note"
_CUT_RELEASE = "cut-release"
_PAUSED = "paused"


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

    def test_an_unstamped_release_still_lets_go(self) -> None:
        # A release stamp the disk refuses costs a later reading its tie to
        # the record, never the lock. The signature before it lands.
        claim_file = writer_claims.claim_path(_REPO_ID, _ISSUE)
        refused_stamp = [DEFAULT, OSError(errno.ENOSPC, "no space")]
        with (
            self.assertLogs(_SCHEDULER_LOG, level="WARNING") as logged,
            patch.object(writer_claims.os, "write", wraps=os.write, side_effect=refused_stamp),
        ):
            self.assertTrue(self.granted_here(_REPO_ID, _ISSUE))
            self.assertIn("was not stamped", logged.output[0])
        self.assertEqual(descriptors_on(claim_file), 0)
        self.assertEqual(self.other_process(_REPO_ID, _ISSUE, _TRY).said(), HELD)

    def test_a_cut_short_release_is_no_stamp(self) -> None:
        # Only `released=` and one digit of the stamp land. Taken back, the
        # hold reads as one that died holding the claim -- as late as it can
        # be -- and never as a moment before the reading it came after.
        read_at = claim_notes.moment()
        holder = self.other_process(_REPO_ID, _OTHER_ISSUE, _CUT_RELEASE)
        self.assertEqual(holder.said(), HELD)
        self.assertEqual(holder.exited(), 0)
        left = writer_claims.claim_path(_REPO_ID, _OTHER_ISSUE).read_text(encoding=_ENCODING)
        self.assertNotIn(writer_claims.RELEASED_LINE, left, "no part of the stamp stays behind")

        self.assertTrue(self.granted_here(_REPO_ID, _OTHER_ISSUE))
        self.assertFalse(claim_notes.undisturbed_since(_REPO_ID, _OTHER_ISSUE, read_at))


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

    def test_a_cut_short_note_is_no_note(self) -> None:
        # Only `retiring-cycle=` and the first digit of the cycle land. Taken
        # back, the hold notes no cycle -- least of all that digit's -- and
        # what it writes afterwards is whole: its release stamp still says
        # when it ended.
        holder = self.other_process(_REPO_ID, _OTHER_ISSUE, _CUT_NOTE)
        self.assertEqual(holder.said(), HELD)
        self.assertGreater(CUT_CYCLE, 9)
        self.assertIsNone(claim_notes.noted_retirement(_REPO_ID, _OTHER_ISSUE))

        self.assertEqual(holder.let_go(), 0)
        read_at = claim_notes.moment()
        self.assertTrue(self.granted_here(_REPO_ID, _OTHER_ISSUE))
        self.assertTrue(claim_notes.undisturbed_since(_REPO_ID, _OTHER_ISSUE, read_at), "a whole stamp behind the note")

    def test_only_a_standing_holds_note_is_read(self) -> None:
        # A note is read off a file a hold signed and has not stamped as let
        # go. One no hold signed is nobody's, and one whose hold stamped its
        # release belongs to a hold that is over.
        claim_file = writer_claims.claim_path(_REPO_ID, _OTHER_ISSUE)
        claim_file.parent.mkdir()
        signed = f"{writer_claims.HOLDER_LINE}standing\n"
        note = f"{claim_notes._RETIRING}{RETIRED_CYCLE}\n"
        for left, noted in (
            (note, None),
            (f"{signed}{note}{writer_claims.RELEASED_LINE}1\n", None),
            (f"{signed}{note}", RETIRED_CYCLE),
        ):
            with self.subTest(left=left):
                claim_file.write_text(left, encoding=_ENCODING)
                self.assertEqual(claim_notes.noted_retirement(_REPO_ID, _OTHER_ISSUE), noted)

    def test_no_note_outlives_a_released_hold(self) -> None:
        # The hold before noted a retirement and ended; the next holder has
        # the lock and has not yet read or emptied the file. A process that
        # holder refuses reads no note of a hold that let go. One killed
        # holding the claim stamped nothing, and was the last hold to write
        # the issue, so its note is read until the next holder empties it.
        for issue_number, ending, noted in (
            (_ISSUE, OtherProcess.let_go, None),
            (_OTHER_ISSUE, OtherProcess.killed, RETIRED_CYCLE),
        ):
            with self.subTest(ending=ending.__name__):
                retiring = self.other_process(_REPO_ID, issue_number, _RETIRE)
                self.assertEqual(retiring.said(), HELD)
                ending(retiring)
                paused = self.other_process(_REPO_ID, issue_number, _PAUSED)
                self.assertEqual(paused.said(), LOCKED)

                with self.assertLogs(_SCHEDULER_LOG):
                    self.assertFalse(self.granted_here(_REPO_ID, issue_number))
                self.assertEqual(claim_notes.noted_retirement(_REPO_ID, issue_number), noted)
                self.assertEqual(paused.let_go(), 0)


class HoldTimesTest(SharedNamespaceCase):
    """When another poller last held a key, as this process finds it by taking the key."""

    def test_own_holds_disturb_no_reading(self) -> None:
        # The first claim finds a file nobody has signed, which proves nobody
        # held the key before it no more than an emptied one would.
        self.assertTrue(self.granted_here(_REPO_ID, _ISSUE))
        read_at = claim_notes.moment()
        for _ in range(2):
            self.assertTrue(self.granted_here(_REPO_ID, _ISSUE))
        self.assertTrue(claim_notes.undisturbed_since(_REPO_ID, _ISSUE, read_at))

    def test_a_later_hold_is_found_by_any_claim_here(self) -> None:
        read_at = claim_notes.moment()
        self.held_and_let_go(_REPO_ID, _ISSUE)
        self.assertTrue(claim_notes.undisturbed_since(_REPO_ID, _ISSUE, read_at), "found only by taking it")

        # Taken and let go by another thread first: the hold is found then,
        # and a reading older than it stays disturbed for the pass after.
        self.assertTrue(_on_another_thread(self.granted_here, _REPO_ID, _ISSUE))
        self.assertTrue(self.granted_here(_REPO_ID, _ISSUE))
        self.assertFalse(claim_notes.undisturbed_since(_REPO_ID, _ISSUE, read_at))
        self.assertTrue(claim_notes.undisturbed_since(_REPO_ID, _ISSUE, claim_notes.moment()), "a later reading")
        self.assertTrue(claim_notes.undisturbed_since(_REPO_ID, _OTHER_ISSUE, read_at), "found per key")

    def test_a_predecessors_hold_is_older(self) -> None:
        # A poller restarted over the namespace the one before it used: that
        # process held the key and exited, its token is still on the file, and
        # it ended before anything this process read.
        self.held_and_let_go(_REPO_ID, _ISSUE)
        read_at = claim_notes.moment()

        self.assertTrue(self.granted_here(_REPO_ID, _ISSUE))
        self.assertTrue(claim_notes.undisturbed_since(_REPO_ID, _ISSUE, read_at))

    def test_a_hold_standing_at_the_reading_disturbs(self) -> None:
        holder = self.other_process(_REPO_ID, _ISSUE, _HOLD)
        self.assertEqual(holder.said(), HELD)
        read_at = claim_notes.moment()
        self.assertEqual(holder.let_go(), 0)

        self.assertTrue(self.granted_here(_REPO_ID, _ISSUE))
        self.assertFalse(claim_notes.undisturbed_since(_REPO_ID, _ISSUE, read_at))

    def test_a_killed_hold_ends_when_found(self) -> None:
        # It said nothing of when it ended, so all that is known is that it
        # had by the time this process took the key.
        holder = self.other_process(_REPO_ID, _ISSUE, _HOLD)
        self.assertEqual(holder.said(), HELD)
        holder.killed()
        read_at = claim_notes.moment()

        self.assertTrue(self.granted_here(_REPO_ID, _ISSUE))
        self.assertFalse(claim_notes.undisturbed_since(_REPO_ID, _ISSUE, read_at))
        self.assertTrue(claim_notes.undisturbed_since(_REPO_ID, _ISSUE, claim_notes.moment()))

    def test_what_a_found_file_says(self) -> None:
        # What another hold left, as the next acquisition finds it. A whole
        # stamp later than the clock reads now was taken before the host last
        # started, so it is older than any process on it. A stamp or a
        # signature cut short, or a file nobody signed, says only that a hold
        # may have been there: it ended no sooner than it is found.
        claim_file = writer_claims.claim_path(_REPO_ID, _ISSUE)
        claim_file.parent.mkdir()
        released = 2 * claim_notes.moment()
        for left, undisturbed in (
            (f"{writer_claims.HOLDER_LINE}before-boot\n{writer_claims.RELEASED_LINE}{released}\n", True),
            (f"{writer_claims.HOLDER_LINE}cut-short\n{writer_claims.RELEASED_LINE}1", False),
            (writer_claims.HOLDER_LINE[:3], False),
            ("", False),
        ):
            with self.subTest(left=left):
                claim_file.write_text(left, encoding=_ENCODING)
                read_at = claim_notes.moment()

                self.assertTrue(self.granted_here(_REPO_ID, _ISSUE))
                self.assertIs(claim_notes.undisturbed_since(_REPO_ID, _ISSUE, read_at), undisturbed)

    def test_holds_between_open_and_lock_disturb(self) -> None:
        # This process opens the file, creating it, and before it locks it
        # another process takes the key and lets go, then a third empties the
        # file and cannot sign it. The empty file this process then finds is
        # no proof that nobody held the key, so a reading taken before those
        # holds is disturbed.
        read_at = claim_notes.moment()
        interleaved = self.held_first(_REPO_ID, _OTHER_ISSUE)
        with patch.object(fcntl, "flock", wraps=fcntl.flock, side_effect=interleaved):
            self.assertTrue(self.granted_here(_REPO_ID, _OTHER_ISSUE))
        self.assertFalse(claim_notes.undisturbed_since(_REPO_ID, _OTHER_ISSUE, read_at))


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
        # leave to write the issue uncoordinated -- here, and in a process
        # that resolves the same root from its own environment.
        (self.root / ".issue-writer-claims").write_text("", encoding=_ENCODING)

        with self.assertLogs(_SCHEDULER_LOG, level="WARNING") as logged:
            self.assertFalse(self.granted_here(_REPO_ID, _ISSUE))
            self.assertIn("reason=unusable", logged.output[0])
        self.assertEqual(self.other_process(_REPO_ID, _ISSUE, _TRY).said(), REFUSED)

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
