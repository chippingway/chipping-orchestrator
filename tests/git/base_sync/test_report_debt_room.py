# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report debt a landed rebase owes, at the limit of what the pinned comment holds.

A debt the pinned comment has no room for is not one a finish may route past:
the reviewer would be handed the report of the head the push replaced. So the
room is measured on the whole write the debt rides -- the announcement, with
the notice's ledger entry, the reset round, and the mark -- and a finish short
of it announces nothing and routes nothing, parking with the attempt standing
until somebody makes room and replies. Every write a tick makes stays within
the limit either way.
"""

from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import MagicMock, patch

from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from tests.git.base_sync.refresh_scenarios import PUSH_PATCH, _clean_rebase_scenario, _landed_recovery_scenario
from tests.git.base_sync.refresh_test_support import (
    AFTER_SHA,
    BEFORE_SHA,
    ISSUE,
    LABEL_VALIDATING,
    PR_NUMBER,
    _pending_attempt,
    _SyncWorktreeWithBaseFixture,
)
from tests.git.base_sync.report_debt_test_support import (
    KEY_REWRITE_DEBT,
    DurableAtTheRelabel,
    owed,
    settles_a_report_of,
    stands_on,
)
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeUser

KEY_PARK_REASON = "park_reason"
KEY_AWAITING_HUMAN = "awaiting_human"
KEY_REVIEW_ROUND = "review_round"

# The attempt a landed push is finished from, which a hold keeps standing.
KEY_PENDING_PUSH_SHA = "pending_auto_base_rebase_push_sha"
KEY_PENDING_REWRITE_SHA = "pending_auto_base_rebase_rewrite_sha"

# The mark a finish leaves between its announcement and its clear.
KEY_ANNOUNCED_SHA = "pending_auto_base_rebase_announced_sha"

PARK_UNRECORDED_DEBT = "auto_base_rebase_unrecorded_debt"

EVENT_BASE_REBASED = "base_rebased"

HUMAN_LOGIN = "human"

DIED = "the process died before the tick returned"

# A pinned key nothing reads, standing in for whatever else fills the comment.
_FILLER = "room_filler"

# Room enough for everything this fixture writes.
_AMPLE = 4096

# A comment id as wide as the widest a comment is recorded at. Every id the
# ticks mint lands past it, so the ledger entry a finish reserves for its notice
# is exactly as wide as the one the notice takes, and the room a finish
# measures is the room its write needs.
_WIDEST_ID = 1_000_000_000_000_000_000

# Rounds a reviewer has spent on the head a recovery finishes: wider than the 0
# the finish resets the round to.
_SPENT_ROUNDS = 10

# A round wider than the mark and the notice's ledger entry together, so the
# announcement that resets it is narrower than the comment standing now.
_WIDE_ROUND_DIGITS = 200
_WIDE_ROUND = int("9" * _WIDE_ROUND_DIGITS)

# How far below the room a finish's widest write needs the sweep reaches, and
# its stride: past everything the announcement puts down beside the debt, and
# short of where the park it holds with would not fit either.
_BELOW = 160
_STRIDE = 4


def _rooms_around(needed: int) -> list[int]:
    """The rooms a boundary sweep finishes with: from well short of `needed` to just past it."""
    swept = range(needed - _BELOW, needed + 2 * _STRIDE, _STRIDE)
    return sorted({*swept, needed - 1, needed})


def _announced(github) -> tuple[int, int]:
    """How many `base_rebased` events and pull-request notices the issue has had."""
    events = [
        recorded for recorded in github.recorded_events
        if recorded.get("event") == EVENT_BASE_REBASED
    ]
    return len(events), len(github.posted_pr_comments)


def _debt_room(github) -> int:
    """The room the landed head's debt alone takes on the comment as it stands."""
    durable = github.pinned_data(ISSUE)
    owing = {**durable, KEY_REWRITE_DEBT: owed(BEFORE_SHA, AFTER_SHA)}
    return len(pinned_state_body(owing)) - len(pinned_state_body(durable))


class _Writes:
    """A pinned-state writer that remembers the widest comment it was asked to write, whole or as a guarded edit."""

    def __init__(self, github) -> None:
        self._write = github.write_pinned_state
        self._edit = github._send_pinned_edit
        self.widest = 0

    def __call__(self, issue, state):
        """Measure the comment this write renders, then write it."""
        self.widest = max(self.widest, len(pinned_state_body(state.data)))
        return self._write(issue, state)

    def edits(self, issue, body: str):
        """Measure the comment a guarded edit sends, then send it."""
        self.widest = max(self.widest, len(body))
        return self._edit(issue, body)


class _RoomFixture(_SyncWorktreeWithBaseFixture):
    """PR #42 over a settled report of the anchor, on a pinned comment filled to a chosen room."""

    def _reported(self, **state) -> None:
        """Seed the issue afresh, its pull request on the anchor and its report of it settled.

        Every comment id minted past this is as wide as `_WIDEST_ID`.
        """
        self.gh = FakeGitHubClient()
        self._seed_pr_issue(**state)
        settles_a_report_of(self.gh, BEFORE_SHA)
        pull = self.gh.pulls[PR_NUMBER]
        pull.issue_comments.append(FakeComment(
            id=_WIDEST_ID, body="an earlier comment", user=FakeUser(HUMAN_LOGIN),
        ))

    def _leaves(self, room: int) -> None:
        """Fill the pinned comment until `room` characters are left under the limit."""
        pinned = self._pinned()
        pinned[_FILLER] = ""
        short = MAX_PINNED_BODY - room - len(pinned_state_body(pinned))
        pinned[_FILLER] = "x" * short

    def _pinned(self) -> dict:
        """The pinned comment's payload as the client holds it, for a case to edit in place."""
        return self.gh._pinned[ISSUE].data

    def _ticks(self, scenario) -> tuple[int, list]:
        """Run `scenario`; the widest write it made, and what was durable at each relabel."""
        writes = _Writes(self.gh)
        relabel = DurableAtTheRelabel(self.gh)
        with patch.object(self.gh, "write_pinned_state", writes), patch.object(
            self.gh, "_send_pinned_edit", writes.edits,
        ), patch.object(self.gh, "set_workflow_label", relabel):
            scenario.run(self)
        return writes.widest, relabel.seen

    def _assert_held(self, announced: tuple[int, int]) -> None:
        """Parked with the push kept and the attempt standing, nothing routed, and nothing said past `announced`."""
        durable = self.gh.pinned_data(ISSUE)
        self.assertEqual(
            (
                durable.get(KEY_PARK_REASON), durable.get(KEY_PENDING_PUSH_SHA),
                durable.get(KEY_PENDING_REWRITE_SHA), durable.get(KEY_REWRITE_DEBT),
            ),
            (PARK_UNRECORDED_DEBT, BEFORE_SHA, AFTER_SHA, None),
        )
        self.assertNotIn((ISSUE, LABEL_VALIDATING), self.gh.label_history)
        self.assertEqual(_announced(self.gh), announced)

    def _assert_within(self, ticked, fits: bool, announced: tuple[int, int]) -> None:
        """A finish wrote nothing past the limit, routing with its debt where its write `fits` and holding where not.

        `ticked` is what `_ticks` answered, and `announced` what was said
        before the finish ran.
        """
        widest, seen = ticked
        self.assertLessEqual(widest, MAX_PINNED_BODY)
        self.assertEqual((ISSUE, LABEL_VALIDATING) in self.gh.label_history, fits)
        if not fits:
            self._assert_held(announced)
        self.assertEqual(
            [(at.get(KEY_REWRITE_DEBT), at.get(KEY_PENDING_PUSH_SHA)) for at in seen],
            [(owed(BEFORE_SHA, AFTER_SHA), BEFORE_SHA)] if fits else [],
        )

    def _finishes_once_there_is_room(self) -> None:
        """Make room and reply, and hold the tick after to the finish the debt was owed.

        The debt is durable beside the anchor when the reviewer is routed, the
        reply is spent with the park it answered, and the head the pull
        request already carries is finished without being pushed again.
        """
        self._pinned().pop(_FILLER)
        stands_on(self.gh, AFTER_SHA)
        self._add_comment(self.gh._next_comment_id(), "made room, please retry", HUMAN_LOGIN)
        scenario = _landed_recovery_scenario(AFTER_SHA)

        self._assert_within(self._ticks(scenario), True, (0, 0))
        scenario[PUSH_PATCH].assert_not_called()
        durable = self.gh.pinned_data(ISSUE)
        self.assertEqual(
            (durable.get(KEY_AWAITING_HUMAN), durable.get(KEY_PARK_REASON), durable.get(KEY_PENDING_PUSH_SHA)),
            (False, None, None),
        )


class RoomAtTheLandingTest(_RoomFixture, unittest.TestCase):
    """The tick whose push lands measures its debt on the announcement it rides."""

    def test_every_write_fits_across_the_boundary(self) -> None:
        # Below the room the landing's widest write needs, the debt alone may
        # still fit while the announcement it rides would not. The finish
        # routes exactly where that write fits, with its debt durable at the
        # relabel, holds everywhere short of it with nothing routed or
        # announced, and writes nothing past the limit either way.
        needed = self._room_the_landing_needs()
        for room in _rooms_around(needed):
            with self.subTest(room=room):
                self._assert_within(self._lands_with(room), room >= needed, (0, 0))

    def test_room_and_a_reply_finish_the_route(self) -> None:
        self._lands_with(self._room_the_landing_needs() - 1)

        self._finishes_once_there_is_room()

        self.assertEqual(_announced(self.gh), (1, 1))

    def _lands_with(self, room: int) -> tuple[int, list]:
        """One clean rebase whose push lands on a comment with `room` left."""
        self._reported()
        self._leaves(room)
        return self._ticks(_clean_rebase_scenario())

    def _room_the_landing_needs(self) -> int:
        """The room the widest write of a landing that routes takes, over the comment it started from.

        Measured on a landing given plenty, so it is what the writes really
        carried rather than what anything here reserves for them.
        """
        widest, _seen = self._lands_with(_AMPLE)
        return widest - (MAX_PINNED_BODY - _AMPLE)


class RoomInTheRecoveryTest(_RoomFixture, unittest.TestCase):
    """A recovery finishing a landed head holds on the same room, and a reply finishes it."""

    def test_a_recovery_writes_within_the_limit(self) -> None:
        # A push lost before its mark, over rounds a reviewer already spent:
        # the recovery's announcement resets that round ahead of its mark, so
        # the write it measured is the write that goes out. It routes exactly
        # where that write fits and holds everywhere short of it, having said
        # nothing past what the lost tick said.
        needed = self._room_the_recovery_needs()
        for room in _rooms_around(needed):
            with self.subTest(room=room):
                self._assert_within(self._recovers_with(room), room >= needed, (1, 1))

    def test_a_recovery_holds_until_there_is_room(self) -> None:
        for road, left, announced, finished in (
            # The push landed and its answer was lost before anything was said:
            # the landing is held with nothing said, and the reply's finish
            # says it once.
            (
                "lost before its announcement",
                partial(self._reported, **_pending_attempt(AFTER_SHA)), (0, 0), (1, 1),
            ),
            # The push landed and the tick died before its mark, having said so
            # once; the finish that the reply brings says it again.
            ("lost before its mark", self._lost_before_the_mark, (1, 1), (2, 2)),
            # An earlier build announced it and put no debt beside its mark,
            # so nothing is said again either way.
            ("announced without its debt", self._announced_without_its_debt, (0, 0), (0, 0)),
        ):
            with self.subTest(road):
                left()
                stands_on(self.gh, AFTER_SHA)
                self._leaves(_debt_room(self.gh) - 1)
                scenario = _landed_recovery_scenario(AFTER_SHA)

                self.assertLessEqual(self._ticks(scenario)[0], MAX_PINNED_BODY)
                self._assert_held(announced)
                scenario[PUSH_PATCH].assert_not_called()
                self._finishes_once_there_is_room()
                self.assertEqual(_announced(self.gh), finished)

    def test_a_round_wider_than_the_mark_holds(self) -> None:
        # The announcement resets the round, so over a round wider than the
        # mark and the notice's entry together it is the narrower of the two
        # writes, and it has room for the debt the comment standing now has
        # none for. That is no room for the debt at all: the recovery holds
        # rather than route a head with nothing recorded, and a reply after
        # room is made finishes it.
        self._lost_before_the_mark(**{KEY_REVIEW_ROUND: _WIDE_ROUND})
        stands_on(self.gh, AFTER_SHA)
        self._leaves(_debt_room(self.gh) - 1)

        widest = self._ticks(_landed_recovery_scenario(AFTER_SHA))[0]

        self.assertLessEqual(widest, MAX_PINNED_BODY)
        self._assert_held((1, 1))
        self._finishes_once_there_is_room()

    def _recovers_with(self, room: int) -> tuple[int, list]:
        """The recovery of a push lost before its mark, over spent rounds, on a comment with `room` left."""
        self._lost_before_the_mark(**{KEY_REVIEW_ROUND: _SPENT_ROUNDS})
        stands_on(self.gh, AFTER_SHA)
        self._leaves(room)
        return self._ticks(_landed_recovery_scenario(AFTER_SHA))

    def _room_the_recovery_needs(self) -> int:
        """The room the widest write of a recovery that routes takes, over the comment it started from."""
        widest, _seen = self._recovers_with(_AMPLE)
        return widest - (MAX_PINNED_BODY - _AMPLE)

    def _lost_before_the_mark(self, **state) -> None:
        # The mark lands through the guarded edit of the pinned comment, the
        # first the finish makes past its notice and its event.
        self._reported(**state)
        with patch.object(
            self.gh, "edit_pinned_state", MagicMock(side_effect=RuntimeError(DIED)),
        ), self.assertRaises(RuntimeError):
            _clean_rebase_scenario().run(self)

    def _announced_without_its_debt(self) -> None:
        self._reported(**_pending_attempt(AFTER_SHA), **{KEY_ANNOUNCED_SHA: AFTER_SHA})


if __name__ == "__main__":
    unittest.main()
