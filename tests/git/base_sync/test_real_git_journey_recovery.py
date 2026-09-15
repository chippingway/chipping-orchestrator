# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The adjudicated rebase journey, lost at every moment it makes durable.

Each case runs the real refresh up to one durable boundary, lets the process
die there, and runs the next real refresh over whatever that left on disk and
on the pinned comment. Every one of them has to come back to the finish an
unbroken tick makes: the verdict and the receipt on the replay, the reviewer
routed to it, and nobody asked to measure or adjudicate the change again.
"""
from __future__ import annotations

import unittest

from tests.git.base_sync import journey_push_support as windows
from tests.git.base_sync.journey_adjudication_support import adjudicates_once
from tests.git.base_sync.journey_assertions import (
    CLEAN_REBASE,
    KEY_PENDING_PUSH_SHA,
    KEY_PENDING_REWRITE_SHA,
    RECOVERY_PUSHED,
    RECOVERY_RELABELLED,
    JourneyAssertions,
)
from tests.git.base_sync.journey_git_support import OversizedJourneyRealGitFixture


class _InterruptedJourney(JourneyAssertions, OversizedJourneyRealGitFixture):
    """The journey up to the base advance, for one tick to be lost over."""

    def setUp(self) -> None:
        super().setUp()
        self.accepted = self._commits_an_oversized_candidate()
        adjudicates_once(self, self.accepted)
        self.adjudication = self._issue_comments()
        self._advance_base(conflicting=False)

    def _finishes(self, *methods: str) -> None:
        """Run the next refresh and hold it to the finish an unbroken tick makes."""
        pusher = self._refreshes()

        replayed = self._wt_head()
        self.assertNotEqual(replayed, self.accepted)
        self.assertIn(pusher.revision, ("", replayed))
        self._assert_rotated_onto(replayed, self.accepted)
        self._assert_rebased_by(*methods)
        self._assert_reviewable()
        self._assert_decided_once()


class InterruptedBeforePublicationTest(_InterruptedJourney, unittest.TestCase):
    """Lost before the replay reached the remote: the recovery publishes it."""

    def test_a_crash_before_the_rebase(self) -> None:
        # The anchor and the terms are down and git never ran, so the checkout
        # is still on the anchor: the attempt is dropped and rebased afresh.
        self._refreshes(windows.BEFORE_THE_REBASE)
        self._finishes(CLEAN_REBASE)

    def test_a_crash_before_the_record(self) -> None:
        # `git rebase` replayed the branch and nothing wrote which commit that
        # produced, so the checkout diverges from the pull request and no id
        # names it. Read by the divergence alone that replay would be reset;
        # what vouches for it is what it contributes.
        self._refreshes(windows.BEFORE_THE_RECORD)
        durable = self._durable()
        self.assertNotEqual(self._wt_head(), self.accepted)
        self.assertEqual(
            (durable.get(KEY_PENDING_PUSH_SHA), durable.get(KEY_PENDING_REWRITE_SHA)),
            (self.accepted, None),
        )
        self._finishes(RECOVERY_PUSHED)

    def test_a_crash_after_the_record(self) -> None:
        # The replay is recorded and no permission was asked, so the recovery
        # re-derives the evidence and the permit rules on it before its push.
        self._refreshes(windows.AFTER_THE_RECORD)
        self._finishes(RECOVERY_PUSHED)

    def test_a_crash_before_the_push(self) -> None:
        # The permission is durable and the remote is still on the lease, so
        # the recovery reissues the push on that permit alone.
        self._refreshes(windows.BEFORE_THE_PUSH)
        self._finishes(RECOVERY_PUSHED)


class InterruptedAfterPublicationTest(_InterruptedJourney, unittest.TestCase):
    """Lost once the replay was on the remote: the recovery only finishes."""

    def test_a_crash_before_the_receipt(self) -> None:
        # The push landed and its answer never came back, so the permission is
        # still outstanding over a head the pull request carries. The leased
        # no-op receipts it and rotates the verdict without measuring.
        self._refreshes(windows.BEFORE_THE_RECEIPT)
        self._finishes(RECOVERY_RELABELLED)

    def test_a_crash_before_the_report(self) -> None:
        # The receipt landed and the record the sinks are owed did not; the
        # proof it is made from is kept, so the recovery reports it once.
        self._refreshes(windows.BEFORE_THE_REPORT)
        self._finishes(RECOVERY_RELABELLED)

    def test_a_crash_before_the_notice(self) -> None:
        # Everything durable landed and nothing was announced, so the recovery
        # announces and routes it.
        self._refreshes(windows.BEFORE_THE_NOTICE)
        self._finishes(RECOVERY_RELABELLED)

    def test_a_crash_before_the_mark(self) -> None:
        # The one window the checkpoint cannot close: the notice and the event
        # are out and nothing records it, so they are said again rather than
        # lost, and the durable state is right either way.
        self._refreshes(windows.BEFORE_THE_MARK)
        self._finishes(CLEAN_REBASE, RECOVERY_RELABELLED)

    def test_a_crash_at_the_relabel(self) -> None:
        # The mark says the finish announced itself, so the recovery owes the
        # route and the write and says nothing twice.
        self._refreshes(windows.AT_THE_RELABEL)
        self._finishes(CLEAN_REBASE)

    def test_a_crash_after_the_relabel(self) -> None:
        # The reviewer was routed and the clearing write was lost.
        self._refreshes(windows.AFTER_THE_RELABEL)
        self._finishes(CLEAN_REBASE)


if __name__ == "__main__":
    unittest.main()
