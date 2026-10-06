# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A change request is handed over only where the pinned comment has room for it beside its developer's charge.

The handoff is prepared before its feedback is posted, and its commit behind
the post asks the same room of the candidate it sends -- the request at its
widest handoff, its post's ledger entry counted once, and the charge and start
of the developer it owes. A comment another road filled before the post posts
nothing; one it filled while the post went out takes no handoff, the one post
left for a later tick to take; one left with just that room takes the
handoff. Whatever waits is handed over once room is freed, in the tick its
reviewer returned or on a later one: one post, one developer.

The other writes that refuse the handoff's commit are in
`test_review_handoff_commits.py`.
"""
from __future__ import annotations

import operator
import unittest
from functools import partial

from orchestrator.workflow.stages.validating import review_verdicts as _verdicts
from tests.workflow.fixtures import LABEL_FIXING, LABEL_VALIDATING
from tests.workflow.stages.validating import (
    review_handoff_test_support as _support,
    review_park_test_support as _parked,
    review_verdict_test_support as _world,
    review_write_test_support as _roads,
)

HANDED_BACK = ((_world.ISSUE, LABEL_FIXING), (_world.ISSUE, LABEL_VALIDATING))

# The field another road's notes fill the pinned comment with.
_NOTES = "operator_notes"

# How far short of the comment's ceiling another road's notes leave it while
# the feedback is posted: room for the handoff's own write, and none for the
# developer's charge beside it.
_SHORT_OF_THE_CHARGE = 150


def _left(case) -> tuple:
    """How many feedback posts `case`'s pull request carries, every relabel, and which verdict waits."""
    waiting = case.waiting()
    return (
        len(case.feedback_posts()),
        tuple(case.github.label_history),
        None if waiting is None else waiting["verdict"],
    )


class HandoffRoomTest(_support.HandoffWorld, unittest.TestCase):
    """The handoff is taken with room for its developer's charge, before its post and behind it, or not at all."""

    def test_a_full_comment_posts_nothing(self) -> None:
        # Another road fills the pinned comment once the request is
        # persisted, leaving no room for it at its handoff beside its
        # developer's charge. The handoff is prepared before its feedback is
        # posted, so nothing is posted, written, relabelled, or launched, in
        # the tick its reviewer returned or on a later one; once that room is
        # freed, a later tick posts once and hands the request to its one
        # developer.
        for fresh in (True, False):
            with self.subTest(fresh=fresh):
                self.setUp()
                decision = self.seeds()
                _parked.fills_to(self, spare=0)
                filled = self.pinned()

                held = self.hands_over(decision if fresh else None).call_count
                left = (held, self.pinned() == filled, _left(self))
                _roads.Writes({_NOTES: ""})(self)

                self.assertEqual(
                    (left, self.hands_over().call_count, _left(self)),
                    ((0, True, (0, (), _verdicts.CHANGES_REQUESTED)), 1, (1, HANDED_BACK, None)),
                )

    def test_filling_behind_the_post_takes_nothing(self) -> None:
        # Another road fills the pinned comment while the feedback is posted,
        # right ahead of the commit handing the request over, leaving room for
        # that commit but none for the developer's charge beside it. The
        # commit is refused -- in the tick its reviewer returned, or on a
        # later one -- with the comment as that road left it, behind the one
        # post, and nothing relabelled or launched; once that room is freed, a
        # later tick takes that post and hands the request to its one
        # developer.
        fills = partial(_roads.leaves, partial(_parked.fills_to, spare=_SHORT_OF_THE_CHARGE))
        for fresh in (True, False):
            with self.subTest(fresh=fresh):
                self.setUp()
                decision = self.seeds()
                with _roads.AnotherRoadAhead(self, bool, fills).patched():
                    held = self.hands_over(decision if fresh else None).call_count
                left = (held, self.pinned() == self.left_behind, _left(self))
                _roads.Writes({_NOTES: ""})(self)

                self.assertEqual(
                    (left, self.hands_over().call_count, _left(self)),
                    ((0, True, (1, (), _verdicts.CHANGES_REQUESTED)), 1, (1, HANDED_BACK, None)),
                )

    def test_just_the_room_takes_the_handoff(self) -> None:
        # Another road fills the pinned comment to exactly the room the
        # request needs at its widest handoff beside its developer's charge.
        # The commit behind the post asks that same room of the candidate it
        # sends, the post's ledger entry counted once, so it lands -- in the
        # tick its reviewer returned, or on a later one -- beside that one
        # post, and the request is handed to its one developer.
        for fresh in (True, False):
            with self.subTest(fresh=fresh):
                self.setUp()
                decision = self.seeds()
                _parked.fills_to(self, spare=0, handing=True)
                relabel = _world.AnotherRoadBehind(
                    self, "set_workflow_label", partial(operator.eq, LABEL_FIXING), _support.HandoffWorld.remembers,
                )

                with relabel.patched():
                    ran = self.hands_over(decision if fresh else None)

                posted = [said.id for said in self.feedback_posts()]
                self.assertEqual(
                    (ran.call_count, posted, self.remembered[_support.ANCHOR]),
                    (1, posted[:1], posted[0]),
                )


if __name__ == "__main__":
    unittest.main()
