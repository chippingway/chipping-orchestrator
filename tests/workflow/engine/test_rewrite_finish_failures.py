# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The notice of a configured verification a landed base rewrite's head failed, kept until the pull request carries it.

A failing run records no evidence, so its notice is the failure's whole
account. It is recorded on the pinned comment, with the invalidation, before
it is posted, and the route waits for the pull request to carry it: a post
GitHub refused, or one whose answer was lost, holds the route with the record
standing, and so does an evidence write nobody confirmed. The next finish --
the recovery of the push it finds standing -- runs nothing again: it finds the
notice where a lost answer left it, or posts the one it recorded, once, and
routes only on a base it can still read where the head was counted against it.
"""
from __future__ import annotations

import unittest

from orchestrator.git.base_sync.rewrite_handoffs import _BaseStanding
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from tests.workflow.engine import (
    rewrite_evidence_test_support as rewrite_support,
    rewrite_finish_evidence_test_support as finish_support,
    rewrite_finish_moves as moves,
    rewrite_finish_readings as readings,
    verification_evidence_test_support as support,
)

REBASED = support.REBASED_SHA

FOUND = finish_support.FOUND

# Where the base stands as a later finish takes up a recorded failure, and what
# that finish comes to: gone elsewhere or unread holds, and a base the head was
# not replayed onto routes, since this route records nothing anyway.
_STANDINGS = (
    (_BaseStanding.MOVED, FinishOutcome.HELD),
    (_BaseStanding.UNREAD, FinishOutcome.HELD),
    (_BaseStanding.DROPPED, FinishOutcome.ROUTED),
)


class FailureNoticeTest(unittest.TestCase, finish_support.RewriteFinishCase):
    """A failure notice is posted once whatever its post or its record's write came to."""

    def setUp(self) -> None:
        finish_support.RewriteFinishCase.setUp(self)
        self.attempts(REBASED)
        self.rewrites(REBASED)
        self.exits[support.SUITE] = rewrite_support.FAILED_EXIT
        self.outputs[support.SUITE] = rewrite_support.FAILED_OUTPUT

    def test_a_refused_post_is_made_next_time(self) -> None:
        posts = moves.FailingPosts(self, lands=False)

        self.assertEqual(self.finishes(REBASED), FinishOutcome.HELD)

        self._assert_held_with_the_record(posted=0)
        posts.failing = False
        self._assert_routed_once()

    def test_a_lost_answer_is_found_where_it_landed(self) -> None:
        posts = moves.FailingPosts(self, lands=True)

        self.assertEqual(self.finishes(REBASED), FinishOutcome.HELD)

        self._assert_held_with_the_record(posted=1)
        posts.failing = False
        self._assert_routed_once()

    def test_an_unconfirmed_record_posts_once(self) -> None:
        # The write recording the failure lands and its answer is lost, so
        # nothing is posted behind it. The next finish finds the record and
        # posts the notice it holds, with no second run.
        self.during = moves.loses_answers

        self.assertEqual(self.finishes(REBASED), FinishOutcome.UNCONFIRMED)

        self.gh.pinned_failures.lost.clear()
        self._assert_held_with_the_record(posted=0)
        self._assert_routed_once()

    def test_a_recorded_failure_waits_on_the_base(self) -> None:
        # The notice lands and its answer is lost, so nothing routes. Each
        # later finish finds the notice where it landed and runs nothing
        # again, and is held to the base before it routes.
        posts = moves.FailingPosts(self, lands=True)
        self.assertEqual(self.finishes(REBASED), FinishOutcome.HELD)
        posts.failing = False

        for standing, outcome in _STANDINGS:
            with self.subTest(standing=standing):
                self.world.base = standing

                self.assertEqual(self.finishes(REBASED, FOUND), outcome)

        noticed = len(readings.notices(self))
        self.assertEqual(
            (len(self.handed), noticed, readings.relabels(self)),
            (1, 2, readings.ROUTED),
        )

    def _assert_held_with_the_record(self, *, posted: int) -> None:
        """Nothing routed or retired, the invalidation and the failure's notice recorded, `posted` notices out."""
        held = readings.pinned(self)
        self.assertEqual(
            (readings.relabels(self), held[readings.KEY_PENDING_PUSH], readings.records(held)),
            ((), support.TESTED_SHA, (None, None, self.invalidated())),
        )
        self.assertEqual(readings.failure(held)["head"], REBASED)
        self.assertEqual(len(readings.notices(self)), 1 + posted)

    def _assert_routed_once(self) -> None:
        """The next finish routes behind one failure notice, run once, entered in the ledger, its record cleared."""
        self.assertEqual(self.finishes(REBASED, FOUND), FinishOutcome.ROUTED)
        posted = [comment for comment in self.pull_request.issue_comments if comment.body.startswith(":x:")]
        pinned = readings.pinned(self)
        self.assertEqual(
            (len(posted), len(self.handed), readings.relabels(self)),
            (1, 1, readings.ROUTED),
        )
        self.assertIn(posted[0].id, pinned[support.LEDGER])
        self.assertEqual(
            (readings.failure(pinned), readings.attempt(pinned)),
            (None, readings.RETIRED),
        )


if __name__ == "__main__":
    unittest.main()
