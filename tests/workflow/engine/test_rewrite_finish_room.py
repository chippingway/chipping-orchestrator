# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed base rewrite's debt at the limit of what the pinned comment holds.

The room the debt needs is measured on the whole write that announces it and
on the comment as it stands, and a debt with no room parks the landing with
the push and the attempt kept, until a reply once room is made finishes the
route; a comment with no room for that park either is left exactly as it is,
and since it is only full, not moved, the tick's state is not withheld from
the writes behind it. Each write past that measurement is measured again over
the comment as another road has since left it -- the announcement with its
notice's ledger entry reserved over the ledger that comment carries, and the
park over the round its room depended on -- so neither posts or files anything
for a record that could not follow it.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from types import MappingProxyType

from orchestrator import config
from orchestrator.workflow.engine import report_record_values as _record_values, rewrite_finish as _finish
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from tests.workflow.engine import rewrite_finish_effects_support as effects, rewrite_finish_test_support as support

_FOUND = (
    ":mag: Recovered an interrupted auto-rebase for PR #42; the new head `b2b2b2b2` was already "
    "published before the orchestrator restart. Routing `workflow:fixing` -> `workflow:validating` "
    "so the reviewer re-runs against the rewritten branch."
)

_UNRECORDED = (
    f"{config.HITL_MENTIONS} PR #42 now stands on `{support.LANDED}`, which the orchestrator's auto "
    f"rebase pushed over `{support.ANCHOR}`, and the report debt that head is owed does not fit on "
    "this issue's pinned state comment. Routed to `workflow:validating` without it, the reviewer "
    "would be handed the report of the head it replaced, so the route stops here with the push kept "
    "and nothing routed. Remove records this issue no longer needs from the pinned state comment, "
    "then reply on this issue with anything to finish the route."
)

_ROUTED = (support.LABEL_VALIDATING,)

# A pull request the issue does not pin.
_ANOTHER_PR = 43

# A round wider than everything the announcement adds, so the announcement that
# resets it is the narrower write: the comment as it stands is what has no room.
_WIDE_ROUND_DIGITS = 200
_WIDE_ROUND = int("9" * _WIDE_ROUND_DIGITS)

# Room past the debt alone, and well short of the announcement it rides.
_SHORT_OF_THE_ANNOUNCEMENT = 10

# Room past the announcement, and short of the ledger entry its notice adds.
_SHORT_OF_AN_ENTRY = 3

# Room short of the debt, and of the park that would hold the route for it.
_NO_ROOM_FOR_THE_PARK = 20

# Each comment a debt has no room on: what it carries, and how far past the
# debt alone its room reaches.
_NO_ROOM = (
    ("room for the debt alone", {}, _SHORT_OF_THE_ANNOUNCEMENT),
    ("a round wider than the announcement", {support.KEY_REVIEW_ROUND: _WIDE_ROUND}, -1),
)

# What a debt park leaves: its flags beside the attempt, no debt or mark, the
# replay still recorded; nothing said or routed; and its notice on the issue,
# read as the watermark.
_PARKED = (
    (support.PARK_UNRECORDED_DEBT, True, (None, None, support.ANCHOR), support.LANDED),
    (([], []), ()),
    (True, True),
)

# The announcement a publication's checkpoint lands, beside its notice's entry.
_ANNOUNCED = MappingProxyType({
    support.KEY_REWRITE_DEBT: support.owed(),
    support.KEY_REVIEW_ROUND: 0,
    support.KEY_ANNOUNCED: support.LANDED,
})

# The widest id a comment is recorded at, which a reservation over the tick's
# ledger takes and another road can record first.
_WIDEST_ID = _record_values.MAX_RECORDED_NUMBER


def _held(world: support.FinishWorld) -> tuple:
    """What a debt park left: its flags and the attempt it kept, what was said and routed, and its notice."""
    durable = world.pinned()
    notice = world.issue.comments[-1]
    kept = (
        durable[support.KEY_PARK_REASON],
        durable[support.KEY_AWAITING_HUMAN],
        support.checkpoint(durable)[:3],
        durable[support.KEY_REWRITE_SHA],
    )
    noticed = (
        notice.body.startswith(_UNRECORDED),
        durable[support.KEY_WATERMARK] == notice.id,
    )
    return kept, (world.said(), world.relabels()), noticed


class DebtRoomTest(unittest.TestCase):
    """A debt the pinned comment has no room for parks the landing, and a reply after room is made finishes it."""

    def test_a_debt_without_room_parks_the_landing(self) -> None:
        for case, pinned, short in _NO_ROOM:
            with self.subTest(case):
                world = self._parked(short, **pinned)

                self.assertEqual(_held(world), _PARKED)

    def test_room_and_a_reply_finish_the_route(self) -> None:
        world = self._parked(_SHORT_OF_THE_ANNOUNCEMENT)
        effects.makes_room(world)
        reply = effects.replies(world)

        answered = replace(support.FOUND, retry=reply)
        self.assertEqual(world.finalizes(answered), FinishOutcome.ROUTED)

        self.assertEqual(
            world.said(), ([effects.posted(_FOUND)], [effects.rebased("crash_recovery_relabel_only")]),
        )
        self.assertEqual(world.relabels(), _ROUTED)
        durable = world.pinned()
        self.assertEqual(
            (
                durable[support.KEY_REWRITE_DEBT], durable[support.KEY_AWAITING_HUMAN],
                durable[support.KEY_PARK_REASON], durable[support.KEY_WATERMARK],
                durable[support.KEY_PENDING_PUSH],
            ),
            (support.owed(), False, None, reply, None),
        )

    def test_an_uncarried_claim_is_left_standing(self) -> None:
        # Another pull request's claim is no debt this landing proves, so the
        # route goes on and leaves it exactly as it is.
        claim = support.owed(pr=_ANOTHER_PR)
        world = support.FinishWorld.seeded(**{support.KEY_REWRITE_DEBT: claim})

        self.assertEqual(world.finalizes(), FinishOutcome.ROUTED)

        self.assertEqual(world.pinned()[support.KEY_REWRITE_DEBT], claim)
        self.assertEqual(world.relabels(), _ROUTED)

    def test_a_park_with_no_room_posts_nothing(self) -> None:
        # The comment has no room for the park either, so no park notice is
        # posted or event filed for a record that could not follow it. The
        # comment is simply too full and moved nothing, so the tick's state is
        # not withheld from the writes behind the finish.
        world = support.FinishWorld.seeded()
        effects.leaves(world, _NO_ROOM_FOR_THE_PARK)
        full = world.pinned()
        finish = world.finish()

        self.assertEqual(_finish.finalizes(finish), FinishOutcome.REFUSED)

        github = world.github
        self.assertEqual((github.posted_comments, github.recorded_events), ([], []))
        self.assertEqual(github.posted_pr_comments, [])
        self.assertEqual(world.pinned(), full)
        self.assertFalse(finish.state.withheld)

    def _parked(self, short: int, **pinned: object) -> support.FinishWorld:
        """A publication finishing over a comment `short` past the room its debt alone needs; parked."""
        world = support.FinishWorld.seeded(**pinned)
        effects.leaves(world, effects.room_for(world) + short)

        self.assertEqual(world.finalizes(), FinishOutcome.PARKED)
        return world


class RoomMovedMeanwhileTest(unittest.TestCase):
    """Room another road changed after the finish read the comment is measured as that comment now stands."""

    def test_a_notice_entry_is_reserved_afresh(self) -> None:
        # Another road records the very id a reservation over the tick's ledger
        # would take, and fills the comment to within less than a notice's
        # entry of the announcement. Reserved over the ledger the comment now
        # carries, the entry has no room, so nothing is said for a mark that
        # could not follow it.
        world = support.FinishWorld.seeded(**{support.KEY_LEDGER: [5]})
        finish = world.finish()
        world.another_road(**{support.KEY_LEDGER: [5, _WIDEST_ID]})
        announcing = effects.room_for(world, **_ANNOUNCED)
        effects.leaves(world, announcing + _SHORT_OF_AN_ENTRY)

        self.assertEqual(_finish.finalizes(finish), FinishOutcome.REFUSED)

        self.assertEqual(world.said(), ([], []))
        self.assertEqual(world.relabels(), ())
        durable = world.pinned()
        self.assertIsNone(durable.get(support.KEY_ANNOUNCED))
        self.assertEqual(durable[support.KEY_PENDING_PUSH], support.ANCHOR)

    def test_a_park_whose_round_moved_posts_nothing(self) -> None:
        # The comment as the finish read it had no room for the debt beside a
        # wide round; another road resets that round before the park, which
        # leaves room the park was never measured on, so no park is posted,
        # filed, or recorded over it.
        world = support.FinishWorld.seeded(**{support.KEY_REVIEW_ROUND: _WIDE_ROUND})
        effects.leaves(world, effects.room_for(world) - 1)
        finish = world.finish()
        world.another_road(**{support.KEY_REVIEW_ROUND: 0})

        self.assertEqual(_finish.finalizes(finish), FinishOutcome.REFUSED)

        github = world.github
        self.assertEqual(github.posted_comments, [])
        self.assertEqual(github.recorded_events, [])
        self.assertEqual(github.posted_pr_comments, [])
        durable = world.pinned()
        self.assertEqual(
            (durable.get(support.KEY_PARK_REASON), durable.get(support.KEY_AWAITING_HUMAN)), (None, None),
        )


if __name__ == "__main__":
    unittest.main()
