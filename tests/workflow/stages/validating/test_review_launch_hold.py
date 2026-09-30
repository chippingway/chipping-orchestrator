# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A handed change request's developer is launched only over what still stands where the run circuit starts it.

The handoff's last reading is requests old by the time the circuit charges the
launch, and the charge is a write old by the time it is started. Another road
starting the developer the request owes, charging a run of its own over the
reservation, pushing, clearing the feedback anchor, or pinning another comment
in place of the one the handoff read in either window is seen on the circuit's
own readings, and nobody is launched over it: nothing it wrote is written
back, and the next entry retires, drops, holds, or replays the request as what
moved says. Any other run charged before the charge -- a reviewer's -- is no
such move, and the one developer is launched.

The handoff up to the circuit is in `test_review_handoffs.py`.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from tests.workflow.stages.validating import (
    review_handoff_test_support as _support,
    review_verdict_test_support as _world,
)

# Two fields nothing the launch stands on watches: the per-issue run
# allowance, and the usage total every road's run adds up into.
ALLOWANCE = "agent_run_allowance"

TOKENS = "issue_total_tokens"

GRANTED = 100

FOLDED = 1000

# The phases a charge stands in: taken ahead of the spawn, and let through to it.
RESERVED = "reserved"

STARTED = "started"


def _grants_and_folds(case) -> None:
    """Another road granting `case`'s issue a wider run allowance and folding a run's tokens into its usage total.

    What the total reads once folded is kept as `case.folded`.
    """
    state = case.github.read_pinned_state(case.issue)
    case.folded = (state.get(TOKENS) or 0) + FOLDED
    state.set(ALLOWANCE, GRANTED)
    state.set(TOKENS, case.folded)
    case.github.write_pinned_state(case.issue, state)


def _replaces_the_comment(case) -> None:
    """Another road pinning a new comment in place of `case`'s pinned comment, carrying the very same record."""
    state = case.github.read_pinned_state(case.issue)
    state.comment_id = None
    case.github.write_pinned_state(case.issue, state)


def _behind_the_hold(case, _issue) -> bool:
    """Whether a reading of the comment is the first behind the relabel: the one the launch is last held to."""
    return bool(case.github.label_history)


def _behind_the_charge(_case, state) -> bool:
    """Whether a pinned-comment write is the run circuit's charge, reserved and not yet started."""
    return state.get(_support.RESERVATION) == RESERVED


# The two requests between the handoff's last reading and the developer's
# start, as the client spells each, and which of its calls is the one.
_BEHIND_THE_HOLD = ("read_pinned_state", _behind_the_hold)

_BEHIND_THE_CHARGE = ("write_pinned_state", _behind_the_charge)

# Behind which request another road does what, and then: the developers this
# tick launches, the runs charged meanwhile, the phase the charge standing
# last is left in, the developers a later tick -- holding no decision --
# launches, whether the request still waits, and whether the anchor still
# names the feedback post.
_AT_THE_CIRCUIT = (
    ("the owed start behind the hold", _BEHIND_THE_HOLD, _support.charges_a_run, (0, 1, STARTED, 0, False, True)),
    ("an unrelated run behind the hold", _BEHIND_THE_HOLD, partial(_support.charges_a_run, owed=False),
     (1, 2, STARTED, 0, False, False)),
    ("a push behind the hold", _BEHIND_THE_HOLD, _world.pushes, (0, 1, RESERVED, 0, False, False)),
    ("the anchor cleared behind the hold", _BEHIND_THE_HOLD, partial(_support.moves_the_anchor, to="nowhere"),
     (0, 0, None, 0, True, False)),
    ("the owed start behind the charge", _BEHIND_THE_CHARGE, _support.charges_a_run,
     (0, 2, STARTED, 0, False, True)),
    ("an unrelated run behind the charge", _BEHIND_THE_CHARGE, partial(_support.charges_a_run, owed=False),
     (0, 2, STARTED, 1, False, False)),
    ("a push behind the charge", _BEHIND_THE_CHARGE, _world.pushes, (0, 1, RESERVED, 0, False, False)),
    ("the anchor cleared behind the charge", _BEHIND_THE_CHARGE, partial(_support.moves_the_anchor, to="nowhere"),
     (0, 1, RESERVED, 0, True, False)),
    ("the comment replaced behind the hold", _BEHIND_THE_HOLD, _replaces_the_comment, (0, 0, None, 1, False, False)),
    ("the comment replaced behind the charge", _BEHIND_THE_CHARGE, _replaces_the_comment,
     (0, 1, RESERVED, 1, False, False)),
)


class LaunchBoundaryTest(_support.HandoffWorld, unittest.TestCase):
    """What moves between the handoff's last reading and the developer's start launches nobody over it."""

    def test_the_circuit_holds_the_launch(self) -> None:
        # The owed developer's start seen on the circuit's reading -- before
        # the charge or behind it -- launches nobody and writes nothing over
        # it, so the count and the start another road wrote stand, and a later
        # tick retires the request with its anchor kept for that developer's
        # replay. A push, behind the hold or behind the charge, is seen where
        # the subject is resolved again behind the charge, and a cleared anchor
        # on the reading the circuit next writes from: either launches nobody,
        # a refusal behind the charge leaving this launch's own charge standing
        # reserved and a cleared anchor seen before it charging nothing, and a
        # later tick drops the request with its anchor over the push and holds
        # it handed over the cleared anchor. Another road's run charged over
        # the reservation leaves no charge of this launch's own to start, and a
        # later tick, replaying the handoff, launches the one developer. So
        # does a later tick over a comment another road pinned in place of the
        # one the handoff read, where the circuit launched nobody: the run's
        # writes, made through the id the handoff holds, would land on a
        # comment nobody reads. Feedback is posted once.
        for name, behind, road, expected in _AT_THE_CIRCUIT:
            with self.subTest(name):
                self.setUp()
                self.assertEqual(
                    (
                        *self._hands_over_behind(*behind, road),
                        self.hands_over().call_count,
                        self.waiting() is not None,
                        self.pinned().get(_support.ANCHOR) == self.feedback_posts()[0].id,
                        len(self.feedback_posts()),
                    ),
                    (*expected, 1),
                )

    def test_what_the_circuit_accepts_is_kept(self) -> None:
        # Another road grants the issue a wider run allowance and folds a
        # run's tokens into its usage total -- fields nothing the launch
        # stands on watches -- behind the handoff's last reading, or behind
        # the charge. The circuit's readings carry both and the launch still
        # stands on them, so the one developer is launched, and the writes
        # behind that run keep the grant and the fold, the fold counted once
        # though two readings carried it, rather than putting back the comment
        # the handoff read.
        for request, when in (_BEHIND_THE_HOLD, _BEHIND_THE_CHARGE):
            with self.subTest(request=request):
                self.setUp()
                launched = self._hands_over_behind(request, when, _grants_and_folds)
                kept = self.pinned()
                self.assertEqual(
                    (*launched, kept.get(ALLOWANCE), kept.get(TOKENS)),
                    (1, 1, STARTED, GRANTED, self.folded),
                )

    def _hands_over_behind(self, request: str, when, road) -> tuple:
        """Hand a fresh request over while another road does `road` behind the client's `request` that `when` names.

        What that tick leaves: the developers it launched, the runs charged
        meanwhile, by either road, and the phase the charge standing last is
        left in.
        """
        decision = self.seeds()
        used = self.pinned()[_world.AGENT_RUNS_USED]
        another_road = _world.AnotherRoadBehind(self, request, partial(when, self), road)
        with patch.object(self.github, request, another_road):
            launched = self.hands_over(decision).call_count
        left = self.pinned()
        return launched, left[_world.AGENT_RUNS_USED] - used, left.get(_support.RESERVATION)


if __name__ == "__main__":
    unittest.main()
