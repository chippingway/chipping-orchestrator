# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed rewrite routed with no evidence current for its head, and the base advancing under its final steps.

Direct finishes held to the dormant settled-evidence policy
(`settled_route_support`): issue #7's head rebased with nothing run for it,
then the base advances while the notice is posted or the relabel made. Behind
the relabel the head is held to the base tip its replay was made onto, so the
route holds with the attempt standing, and once the checkout has fetched that
base the next finish continues the head to the caller's rebase, announced
once. A base tip blanked to record movement, or missing from a legacy
attempt, holds the route against the base the finish counted instead -- and
so does a base advanced on the remote while the local base ref is rewound
under the head.
"""
from __future__ import annotations

import unittest
from collections.abc import Callable
from functools import partial
from itertools import product
from typing import NamedTuple
from unittest.mock import patch

from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
    settled_route_support as route,
)


def _hands_the_reviewer(case: route.SettledRouteCase) -> str:
    """Rebase and push the branch over a base that changed it, with no reviewer handed the head; that head."""
    git_support.advances_the_base(case)
    return case.rebases_by_hand()


def _advances_over_a_rewound_ref(case: route.SettledRouteCase) -> None:
    """Advance `case`'s base on the remote, and rewind the checkout's own base ref to the commit before the one counted.

    The head stands over that earlier commit, so the local count reads the base
    rewound under it rather than advanced, and leaves the remote unasked.
    """
    spec = case._spec
    base = f"refs/remotes/{spec.remote_name}/{spec.base_branch}"
    earlier = case._git("rev-parse", f"{base}~1", cwd=case._wt).strip()
    support.advances_the_base_again(case)
    case._git("update-ref", base, earlier, cwd=case._wt)


def _defers_the_evidence(case: route.SettledRouteCase) -> str:
    """Rebase and push the branch over a base that moved and came back, its tree the tested one; that head."""
    git_support.advances_the_base(case, net=False)
    return case.rebases_by_hand()


class _Route(NamedTuple):
    """How a head with no evidence current for it is landed, and whether the anchor's run stays current beside it."""

    name: str
    lands: Callable
    deferred: bool


_ROUTES = (
    _Route("the fresh reviewer's responsibility handed off", _hands_the_reviewer, deferred=False),
    _Route("the replaced head's evidence deferred", _defers_the_evidence, deferred=True),
)

# The final steps the base advances under.
_STEPS = (handoff.BEFORE_THE_ANNOUNCEMENT, handoff.BEFORE_THE_RELABEL)

_EDITED_BODY = "Also cover a base that moved twice."


class _Blank(NamedTuple):
    """Where a finish of a head whose base tip was blanked dies, the step the base then advances under, and a receipt.

    `receipted` False drops the attempt's evidence receipt once the tip is
    blanked, as an attempt recorded before that member existed carries none.
    `moves` is how the base advances: on the remote alone, or with the
    checkout's own base ref rewound under the head besides.
    """

    died: handoff.Boundary
    step: handoff.Boundary
    receipted: bool
    moves: Callable = support.advances_the_base_again


_BLANKS = (
    _Blank(handoff.BEFORE_THE_ANNOUNCEMENT, handoff.BEFORE_THE_ANNOUNCEMENT, receipted=True),
    _Blank(handoff.BEFORE_THE_ANNOUNCEMENT, handoff.BEFORE_THE_RELABEL, receipted=True),
    _Blank(handoff.BEFORE_THE_RELABEL, handoff.BEFORE_THE_RELABEL, receipted=False),
    _Blank(
        handoff.BEFORE_THE_ANNOUNCEMENT, handoff.BEFORE_THE_RELABEL, receipted=True, moves=_advances_over_a_rewound_ref,
    ),
)

# Each final step the base of a legacy attempt advances under, and how: on the
# remote alone, or -- while the relabel is made -- with the checkout's own base
# ref rewound under the head besides.
_LEGACY_MOVES = (
    *((step, support.advances_the_base_again) for step in _STEPS),
    (handoff.BEFORE_THE_RELABEL, _advances_over_a_rewound_ref),
)


class UnprovedRouteMoveTest(route.SettledRouteCase, unittest.TestCase):
    """A head no evidence answers for is held to its base behind the relabel, and continued where the base moved."""

    def test_a_moved_base_holds_the_route(self) -> None:
        # The route is held with the attempt standing and the anchor's run as
        # the landing left it; the next finish continues the head.
        for landing, step in product(_ROUTES, _STEPS):
            with self.subTest(route=landing.name, step=step.name):
                self.setUp()
                head = landing.lands(self)
                self._moving(step, partial(self.finalizes, head, FinishRoad.PUBLICATION))

                self.assertEqual(readings.pinned(self)[readings.KEY_PENDING_PUSH], self.anchor)
                standing = self.source.receipt if landing.deferred else None
                self.assertEqual(self._current(), standing)

                self._assert_continued(head)

    def test_a_blanked_tip_still_holds_the_route(self) -> None:
        # The run's base tip was blanked over movement nobody could record
        # otherwise; the finish that then invalidates it still holds the route
        # where the base advanced under its final steps, and the next one
        # continues the head.
        for blank in _BLANKS:
            named = {"died": blank.died.name, "step": blank.step.name}
            with self.subTest(receipted=blank.receipted, moves=blank.moves.__name__, **named):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                self._blanks_the_tip(head, blank)
                self._moving(blank.step, partial(self.finalizes, head), blank.moves)

                self.assertEqual(readings.pinned(self)[readings.KEY_PENDING_PUSH], self.anchor)
                self.assertIsNone(self._current())

                self._assert_continued(head, ran=1)

    def test_a_legacy_attempt_holds_the_route(self) -> None:
        # The attempt records no base tip at all, so nothing proves which base
        # the head was replayed onto; the finish still holds the route where
        # the base advanced under its final steps, read against the base the
        # tick counted the head against -- a local base ref rewound under the
        # head meanwhile included, which reads the base no longer that count.
        for step, moves in _LEGACY_MOVES:
            with self.subTest(step=step.name, moves=moves.__name__):
                self.setUp()
                head = _hands_the_reviewer(self)
                git_support.pins_the_attempt(self, head)
                state = self.gh.read_pinned_state(self.issue)
                state.data.pop(readings.KEY_REWRITE_BASE)
                self.gh.write_pinned_state(self.issue, state)
                self._moving(step, partial(self.finalizes, head), moves)

                self.assertEqual(readings.pinned(self)[readings.KEY_PENDING_PUSH], self.anchor)

                self._assert_continued(head)

    def _blanks_the_tip(self, head: str, blank: _Blank) -> None:
        """Kill `head`'s finish where `blank` says, its run settled, and have the next finish record movement.

        The issue is edited under the run on a comment filled to its limit,
        so that finish blanks the base tip rather than invalidate the run;
        the body is then put back and room made, and the receipt dropped
        where `blank` carries none.
        """
        publishes = partial(self.finalizes, head, FinishRoad.PUBLICATION)
        handoff.dies_at(self.gh, blank.died, publishes)
        written = self.issue.body
        self.issue.body = _EDITED_BODY
        finish_moves.fills_the_comment(self)
        self.assertEqual(self.finalizes(head), FinishOutcome.HELD)
        self.assertIsNone(readings.pinned(self)[readings.KEY_REWRITE_BASE])
        self.issue.body = written
        finish_moves.makes_room(self)
        if not blank.receipted:
            state = self.gh.read_pinned_state(self.issue)
            state.set(readings.KEY_EVIDENCE_RECEIPT, None)
            self.gh.write_pinned_state(self.issue, state)

    def _moving(self, step: handoff.Boundary, finishing, moves: Callable = support.advances_the_base_again) -> None:
        """`finishing` HELD, the base advanced again by `moves` behind the call of the client's step `step` picks."""
        live = getattr(self.gh, step.step)
        moving = step.moving(live, partial(moves, self))
        with patch.object(self.gh, step.step, moving):
            self.assertEqual(finishing(), FinishOutcome.HELD)

    def _current(self) -> str | None:
        """The receipt of the evidence current now, or None."""
        current = readings.pinned_records(self)[1]
        return None if current is None else current.receipt

    def _assert_continued(self, head: str, *, ran: int = 0) -> None:
        """The next finish, over the base the checkout fetched, continues `head` said once; `ran` runs, no push."""
        self._git("fetch", "--quiet", "origin", cwd=self._wt)
        self.assertEqual(self.finalizes(head), FinishOutcome.CONTINUED)
        said = (support.announced(self), len(readings.notices(self)))
        self.assertEqual(said, ([head], 1))
        self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)
        self.assert_made(ran)


if __name__ == "__main__":
    unittest.main()
