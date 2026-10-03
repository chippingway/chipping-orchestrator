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
from unittest.mock import patch

from orchestrator import config
from orchestrator.scheduler import writer_claims
from tests.scheduler.writer_claim_helpers import (
    HELD,
    REFUSED,
    RELEASED,
    SharedNamespaceCase,
    descriptors_on,
)

_SLUG = "acme/widget"
_ISSUE = 7
_OTHER_ISSUE = 8
_SCHEDULER_LOG = "orchestrator.scheduler"


class ProcessContentionTest(SharedNamespaceCase):
    """A key another process holds is refused here, and nothing else is."""

    def test_a_held_key_is_refused_until_let_go(self) -> None:
        holder = self.other_process(_SLUG, _ISSUE, "hold")
        self.assertEqual(holder.said(), HELD)

        with self.assertLogs(_SCHEDULER_LOG) as logged:
            self.assertFalse(self.granted_here(_SLUG, _ISSUE))
            self.assertIn("reason=held_elsewhere", logged.output[0])
        # The identity is the repository's, which GitHub names
        # case-insensitively, so another spelling of it is the same key.
        self.assertFalse(self.granted_here("Acme/Widget", _ISSUE))
        # Different keys stay independent: another issue of this repository,
        # and the same issue number in another repository.
        self.assertTrue(self.granted_here(_SLUG, _OTHER_ISSUE))
        self.assertTrue(self.granted_here("acme/gadget", _ISSUE))

        self.assertEqual(holder.let_go(), 0)
        self.assertTrue(self.granted_here(_SLUG, _ISSUE))

    def test_holding_here_refuses_another_process(self) -> None:
        with writer_claims.issue_writer(_SLUG, _ISSUE) as held:
            self.assertTrue(held)
            contender = self.other_process(_SLUG, _ISSUE, "try")
            self.assertEqual(contender.said(), REFUSED)
            self.assertEqual(contender.exited(), 0)
        retry = self.other_process(_SLUG, _ISSUE, "try")
        self.assertEqual(retry.said(), HELD)


class ProcessReleaseTest(SharedNamespaceCase):
    """Every way a holder ends gives the claim back, and leaves its file."""

    def test_a_killed_holder_holds_nothing(self) -> None:
        holder = self.other_process(_SLUG, _ISSUE, "hold")
        self.assertEqual(holder.said(), HELD)
        claim_file = writer_claims.claim_path(_SLUG, _ISSUE)
        inode = claim_file.stat().st_ino

        holder.killed()

        self.assertTrue(self.granted_here(_SLUG, _ISSUE))
        # Never unlinked: a lock lives on the inode, so a file recreated under
        # the same path would let two processes each hold "the" claim.
        self.assertEqual(claim_file.stat().st_ino, inode)

    def test_a_raising_body_releases_a_live_holder(self) -> None:
        holder = self.other_process(_SLUG, _ISSUE, "raise")
        self.assertEqual(holder.said(), HELD)
        self.assertEqual(holder.said(), RELEASED)

        # The holder is still running; only the exception ended its claim.
        self.assertTrue(self.granted_here(_SLUG, _ISSUE))
        self.assertEqual(holder.let_go(), 0)

    def test_every_exit_closes_the_descriptor(self) -> None:
        claim_file = writer_claims.claim_path(_SLUG, _ISSUE)
        with self.assertRaises(RuntimeError), writer_claims.issue_writer(_SLUG, _ISSUE) as held:
            self.assertTrue(held)
            self.assertEqual(descriptors_on(claim_file), 1)
            raise RuntimeError("the body failed")
        self.assertEqual(descriptors_on(claim_file), 0)

        holder = self.other_process(_SLUG, _ISSUE, "hold")
        self.assertEqual(holder.said(), HELD)
        with writer_claims.issue_writer(_SLUG, _ISSUE) as held:
            self.assertFalse(held)
            self.assertEqual(descriptors_on(claim_file), 0)


class NamespaceTest(SharedNamespaceCase):
    """Where the claims live, and what a claim that cannot be worked does."""

    def test_claims_live_under_the_checkout_root(self) -> None:
        claim_file = writer_claims.claim_path(_SLUG, _ISSUE)

        self.assertEqual(claim_file.parent, config.WORKTREES_DIR / ".issue-writer-claims")
        self.assertEqual(claim_file, writer_claims.claim_path("ACME/Widget", _ISSUE))
        self.assertNotEqual(claim_file, writer_claims.claim_path(_SLUG, _OTHER_ISSUE))

    def test_an_unopenable_namespace_withholds(self) -> None:
        # A file where the namespace directory belongs: nothing can be
        # coordinated on, and that is answered as a refusal rather than as
        # leave to write the issue uncoordinated.
        (self.root / ".issue-writer-claims").write_text("", encoding="utf-8")

        with self.assertLogs(_SCHEDULER_LOG, level="WARNING") as logged:
            self.assertFalse(self.granted_here(_SLUG, _ISSUE))
            self.assertIn("reason=unusable", logged.output[0])

    def test_a_broken_lock_withholds_the_issue(self) -> None:
        # A lock table with no room is not a holder, so it is never waited out
        # or mistaken for contention -- and never treated as granted either.
        broken = OSError(errno.ENOLCK, "no locks available")
        claim_file = writer_claims.claim_path(_SLUG, _ISSUE)
        with (
            patch.object(fcntl, "flock", side_effect=broken),
            self.assertLogs(_SCHEDULER_LOG, level="WARNING") as logged,
        ):
            self.assertFalse(self.granted_here(_SLUG, _ISSUE))
            self.assertIn("reason=unusable", logged.output[0])
        self.assertEqual(descriptors_on(claim_file), 0)


if __name__ == "__main__":
    unittest.main()
