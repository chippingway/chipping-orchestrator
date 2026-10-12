# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed rewrite routed with no evidence current for its head, and the base advancing under its final steps.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
head rebased and pushed with no reviewer handed it, so nothing is run or
recorded for it -- the fresh reviewer owes its evidence, the anchor's settled
run invalidated where the rebase moved the tree, or left standing on the
replaced head's review, deferred, where the base moved and came back so the
rebased head carries the tested tree. Then the base advances again while the
announcement's notice is posted, or while the relabel is made. Behind the
relabel the head is held to the base tip its replay was made onto once more,
which reads it: the route is held with the attempt standing rather than
retired over a head the base left behind, so no handler is released onto it,
and the next tick continues the head to another rebase it routes -- each head
announced once, nothing run, and no developer launched.

So is a head whose run a finish settled and a later tick read moving -- the
requirements edited on a comment with no room to invalidate it -- which blanks
the base tip its replay was recorded as made onto: with the requirements put
back and room made, the next finish invalidates the run, and a base that
advances while its notice is posted or its relabel made still holds the route,
read against the base the finish counted the head against.
"""
from __future__ import annotations

import unittest
from functools import partial
from itertools import product
from typing import NamedTuple
from unittest.mock import patch

from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
)


def _hands_the_reviewer(case: support.CapturedRunCase) -> str:
    """Rebase and push the branch over a base that changed it, with no reviewer handed the head; that head."""
    git_support.advances_the_base(case)
    return case.rebases_by_hand()


def _defers_the_evidence(case: support.CapturedRunCase) -> str:
    """Rebase and push the branch over a base that moved and came back, its tree the tested one; that head."""
    git_support.advances_the_base(case, net=False)
    return case.rebases_by_hand()


class _Route(NamedTuple):
    """How a head with no evidence current for it is landed, and whether the anchor's run stays current beside it."""

    name: str
    lands: object
    deferred: bool


_ROUTES = (
    _Route("the fresh reviewer's responsibility handed off", _hands_the_reviewer, deferred=False),
    _Route("the replaced head's evidence deferred", _defers_the_evidence, deferred=True),
)

# The final steps the base advances under.
_STEPS = (handoff.BEFORE_THE_ANNOUNCEMENT, handoff.BEFORE_THE_RELABEL)

_EDITED_BODY = "Also cover a base that moved twice."


class UnprovedRouteMoveTest(support.CapturedRunCase, unittest.TestCase):
    """A head no evidence answers for is held to its base behind the relabel, and continued where the base moved."""

    def test_a_moved_base_holds_the_route(self) -> None:
        # The route is held with the attempt standing and the anchor's run as
        # the landing left it; the next tick rebases the head once more and
        # routes what it published, each head said once.
        for route, step in product(_ROUTES, _STEPS):
            with self.subTest(route=route.name, step=step.name):
                self.setUp()
                head = route.lands(self)
                self._moving(step, partial(self.finishes, head))

                self.assertEqual(readings.pinned(self)[readings.KEY_PENDING_PUSH], self.anchor)
                standing = self.source.receipt if route.deferred else None
                self.assertEqual(self._current(), standing)
                self.recovers()

                self._assert_continued(head)

    def test_a_blanked_tip_still_holds_the_route(self) -> None:
        # The run's base tip was blanked over movement nobody could record
        # otherwise; the finish that then invalidates it still holds the route
        # where the base advanced under its final steps, and the next tick
        # continues the head to another rebase.
        for step in _STEPS:
            with self.subTest(step=step.name):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                self._blanks_the_tip(head)
                self._moving(step, self.recovers)

                pinned = readings.pinned(self)
                self.assertEqual(pinned[readings.KEY_PENDING_PUSH], self.anchor)
                self.assertIsNone(self._current())
                self.recovers()

                self._assert_continued(head, ran=1)

    def _blanks_the_tip(self, head: str) -> None:
        """Kill `head`'s finish before its announcement, its run settled, and have the next tick record movement.

        The issue is edited under the run on a comment filled to its limit,
        so the tick blanks the base tip rather than invalidate the run; the
        body is then put back and room made.
        """
        handoff.dies_at(self.gh, handoff.BEFORE_THE_ANNOUNCEMENT, partial(self.finishes, head))
        written = self.issue.body
        self.issue.body = _EDITED_BODY
        finish_moves.fills_the_comment(self)
        self.recovers()
        self.assertIsNone(readings.pinned(self)[readings.KEY_REWRITE_BASE])
        self.issue.body = written
        finish_moves.makes_room(self)

    def _moving(self, step: handoff.Boundary, finishing) -> None:
        """Run `finishing` with the base advanced again behind the call of the client's step `step` picks."""
        live = getattr(self.gh, step.step)
        moving = step.moving(live, partial(support.advances_the_base_again, self))
        with patch.object(self.gh, step.step, moving):
            finishing()

    def _current(self) -> str | None:
        """The receipt of the evidence current now, or None."""
        current = readings.pinned_records(self)[1]
        return None if current is None else current.receipt

    def _assert_continued(self, head: str, *, ran: int = 0) -> None:
        """`head` and the head its continuation pushed each announced once, the attempt retired, `ran` runs."""
        said = (support.announced(self), len(readings.notices(self)))
        self.assertEqual(said, ([head, git_support.remote_head(self)], 2))
        self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (ran, 1, 0))


if __name__ == "__main__":
    unittest.main()
