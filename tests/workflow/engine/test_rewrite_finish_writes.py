# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed base rewrite's finish, held to the guarded commits it writes through.

Each write of a finish lands over the comment read afresh, so another road's
move of a record it was decided on refuses it with nothing behind it made --
no notice, no event, no relabel, no retirement -- and leaves that road's write
exactly as it stands, while a field nobody decided on is kept as the fresh
comment carries it. An edit nobody confirmed stops the finish too, and the next
one picks up from what it left.
"""
from __future__ import annotations

import unittest
from functools import partial
from types import MappingProxyType

from orchestrator.workflow.engine import rewrite_finish as _finish
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from tests.workflow.engine import rewrite_finish_effects_support as effects, rewrite_finish_test_support as support
from tests.workflow.interleaving import _RacesPastTheStep

_ROUTED = (support.LABEL_VALIDATING,)

# A park another road records while a finish runs.
_ANOTHER_PARK = "agent_timeout"

# A round another road spends while a finish runs.
_ANOTHER_ROUND = 4

# A pull request the issue does not pin.
_ANOTHER_PR = 43

# A field no binary reads, which another road writes while a finish runs.
_UNKNOWN = "a_field_no_binary_writes_yet"

# Each record a finish is decided on, as another road moves it after the finish read the comment.
_MOVED = (
    {support.KEY_PENDING_PUSH: support.OTHER},
    {support.KEY_REWRITE_DEBT: support.owed(support.OTHER, support.ANCHOR)},
    {support.KEY_AWAITING_HUMAN: True, support.KEY_PARK_REASON: _ANOTHER_PARK},
    {support.KEY_REVIEW_ROUND: _ANOTHER_ROUND},
    {support.KEY_PR: _ANOTHER_PR},
    {"developer_report_current": {"revision": 9}},
)

# The attempt as a finish leaves it: every member blanked rather than removed.
_RETIRED = MappingProxyType(dict.fromkeys(support.ATTEMPT_KEYS))


class GuardedWriteTest(unittest.TestCase):
    """Another road's move of what a finish was decided on stops it; what nobody decided on is kept."""

    def test_a_moved_record_stops_the_finish(self) -> None:
        for moved in _MOVED:
            with self.subTest(moved=sorted(moved)):
                world = support.FinishWorld.seeded()
                finish = world.finish()
                world.another_road(**moved)
                written = world.pinned()

                outcome = _finish.finalizes(finish)

                # Nothing said, routed, or written over that road's record, and
                # no whole-state write puts the tick's reading back over it.
                self.assertEqual(
                    (outcome, world.said(), world.relabels(), world.pinned(), finish.state.withheld),
                    (FinishOutcome.REFUSED, ([], []), (), written, True),
                )

    def test_what_nobody_decided_on_is_kept(self) -> None:
        world = support.FinishWorld.seeded(**{support.KEY_LEDGER: [5]})
        finish = world.finish()
        world.another_road(**{_UNKNOWN: "kept", support.KEY_LEDGER: [5, 6]})

        self.assertEqual(_finish.finalizes(finish), FinishOutcome.ROUTED)

        # The notice's entry joins the ledger beside the one another road added.
        durable = world.pinned()
        ledger = durable[support.KEY_LEDGER]
        self.assertEqual(durable[_UNKNOWN], "kept")
        self.assertEqual(ledger[:2], [5, 6])
        self.assertEqual(len(ledger), 3)
        retired = (support.owed(), None, None, 0)
        self.assertEqual(support.checkpoint(durable), retired)

    def test_an_unconfirmed_mark_is_said_once(self) -> None:
        world = support.FinishWorld.seeded()
        lost = world.github.pinned_failures.lost
        lost.add(support.ISSUE)

        # Said, and the mark landed with its answer lost: nothing behind it is made.
        self.assertEqual(world.finalizes(), FinishOutcome.UNCONFIRMED)
        self.assertEqual(
            (world.relabels(), support.checkpoint(world.pinned())),
            ((), (support.owed(), support.LANDED, support.ANCHOR, 0)),
        )

        lost.discard(support.ISSUE)
        self.assertEqual(world.finalizes(support.FOUND), FinishOutcome.ROUTED)
        notices, events = world.said()
        self.assertEqual(
            (len(notices), events, world.relabels()),
            (1, [effects.rebased("auto_clean_rebase")], _ROUTED),
        )
        self.assertIsNone(world.pinned()[support.KEY_PENDING_PUSH])

    def test_a_refused_retirement_relabels_nothing(self) -> None:
        # Another road parks the issue the instant the announcement lands: the
        # retirement is prepared before the relabel, so nothing is routed over
        # that park, and the park is kept as that road wrote it.
        world = support.FinishWorld.seeded()
        parks = partial(world.another_road, **{
            support.KEY_AWAITING_HUMAN: True, support.KEY_PARK_REASON: _ANOTHER_PARK,
        })
        world.github._send_pinned_edit = _RacesPastTheStep(world.github._send_pinned_edit, parks)

        self.assertEqual(world.finalizes(), FinishOutcome.REFUSED)

        durable = world.pinned()
        notices, events = world.said()
        self.assertEqual(world.relabels(), ())
        self.assertEqual((len(notices), len(events)), (1, 1))
        self.assertEqual(
            (support.checkpoint(durable)[1:3], durable[support.KEY_PARK_REASON]),
            ((support.LANDED, support.ANCHOR), _ANOTHER_PARK),
        )

    def test_a_refused_route_is_resumed_by_the_next(self) -> None:
        world = support.FinishWorld.seeded()
        relabel = world.github.set_workflow_label
        spends = partial(world.another_road, **{support.KEY_REVIEW_ROUND: _ANOTHER_ROUND})
        world.github.set_workflow_label = _RacesPastTheStep(relabel, spends)

        # Refused behind its relabel: the anchor and the mark still stand,
        # which is what brings the next finish back to the route alone.
        self.assertEqual(world.finalizes(), FinishOutcome.REFUSED)
        self.assertEqual(
            (world.relabels(), support.checkpoint(world.pinned())),
            (_ROUTED, (support.owed(), support.LANDED, support.ANCHOR, _ANOTHER_ROUND)),
        )

        world.github.set_workflow_label = relabel
        self.assertEqual(world.finalizes(support.FOUND), FinishOutcome.ROUTED)
        notices, events = world.said()
        self.assertEqual((len(notices), len(events)), (1, 1))
        self.assertEqual(world.relabels(), _ROUTED)
        self.assertEqual(support.attempt(world.pinned()), _RETIRED)


if __name__ == "__main__":
    unittest.main()
