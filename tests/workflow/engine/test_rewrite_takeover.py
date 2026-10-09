# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An unpublished auto-rebase replay handed to the late generation adjudicating it.

A handoff proves, off the pinned record alone, that the attempt and the live
generation describe one replay -- the candidate, the pull request, the head it
was leased against, and the stage -- and then retires the attempt in the very
write that has the generation take the replay over, leaving the frozen pair,
the measurement, and every unrelated record as they were. Evidence of other
work, or evidence short of what the proof needs, is left standing for the
recovery that answers it; a handoff already made writes nothing again.
"""
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine.rewrite_takeover import TakeoverOutcome
from orchestrator.workflow.late_split import state as _late_state
from tests.workflow.engine import rewrite_takeover_test_support as support

# The attempt as a handoff leaves it: every member blanked rather than removed.
_RETIRED = dict.fromkeys(support.ATTEMPT_KEYS)

# Two whole records describing different work, each as one field moves it.
_UNRELATED = (
    ("another candidate", {"late_candidate_sha": support.OTHER}),
    ("another pull request", {"late_published_pr_number": support.PR_NUMBER + 1}),
    ("another frozen head", {"late_published_sha": support.OTHER}),
    ("another stage", {"late_source_stage": "workflow:validating"}),
    ("an announced landing", {support.KEY_ANNOUNCED: support.REPLAY}),
)

# A record that cannot show what the proof needs, on either side -- a
# generation late adjudication itself would refuse among them, since a replay
# handed to one is retired into an owner nobody can publish it from.
_INCOMPLETE = (
    ("an attempt still in flight", {support.KEY_REWRITE_SHA: None}),
    ("terms missing under a replay", {support.KEY_REWRITE_STAGE: None}),
    ("an anchor that is no commit", {support.KEY_PENDING_PUSH: "a1a1"}),
    ("an unmeasured candidate", {"late_additions": None}),
    ("a candidate under its ceiling", {"late_additions": 12}),
    ("a cancelled cycle", {"late_cancelled": True}),
    ("no measurement base", {"late_base_sha": None}),
    ("a partial publication group", {"late_source_stage": None}),
    ("no current issue", {"late_current_issue": None}),
    ("another issue's generation", {"late_current_issue": support.ISSUE + 1}),
    ("no root issue", {"late_root_issue": None}),
)


def _owns(record: dict) -> bool:
    """Whether the generation `record` carries owns its candidate as a taken-over replay."""
    generation = _late_state.read_late_generation(PinnedState(data=record))
    return generation.publication.replayed_as(generation.candidate_sha)


class HandoffTest(unittest.TestCase):
    """A proved pair moves the replay to the generation in one write; anything else moves nothing."""

    def test_a_proved_pair_is_handed_over(self) -> None:
        world = support.TakeoverWorld.seeded(**support.STANDING)
        state = world.github.read_pinned_state(world.issue)

        outcome = support._takeover.takes_over(world.github, world.issue, state)

        durable = world.pinned()
        self.assertEqual(outcome, TakeoverOutcome.TAKEN_OVER)
        self.assertEqual(world.standing(support.ATTEMPT_KEYS), _RETIRED)
        self.assertEqual(durable[support.KEY_REPLAY], support.REPLAY)
        self.assertTrue(_owns(durable))
        # The frozen pair, the measurement, and the publication are as the gate
        # froze them, and the park and round the rebase left are not the
        # handoff's to touch; the label stays on the adjudication.
        self.assertEqual(support.late_group(durable), dict(support.GENERATION))
        self.assertEqual(world.standing(support.STANDING), dict(support.STANDING))
        label = world.github.workflow_label(world.issue)
        self.assertEqual((label, state.data), (support.LABEL_DECOMPOSING, durable))

    def test_a_repeated_handoff_writes_nothing(self) -> None:
        world = support.TakeoverWorld.seeded()
        self.assertEqual(world.takes_over(), TakeoverOutcome.TAKEN_OVER)
        handed = (world.pinned(), world.github.write_state_calls)

        self.assertEqual(world.takes_over(), TakeoverOutcome.OWNED)

        self.assertEqual((world.pinned(), world.github.write_state_calls), handed)

    def test_an_unconfirmed_handoff_is_owned_after(self) -> None:
        # The write landed and its answer was lost: unconfirmed is not refused,
        # and the comment read again is what says the handoff stands.
        world = support.TakeoverWorld.seeded()
        world.github.pinned_failures.lost.add(support.ISSUE)

        self.assertEqual(world.takes_over(), TakeoverOutcome.UNCONFIRMED)
        landed = world.standing((support.KEY_REPLAY, support.KEY_PENDING_PUSH))
        self.assertEqual(landed, {support.KEY_REPLAY: support.REPLAY, support.KEY_PENDING_PUSH: None})

        world.github.pinned_failures.lost.discard(support.ISSUE)
        self.assertEqual(world.takes_over(), TakeoverOutcome.OWNED)

    def test_unrelated_evidence_is_left_standing(self) -> None:
        for case, moved in _UNRELATED:
            with self.subTest(case):
                self._left_standing(moved, TakeoverOutcome.UNRELATED)

    def test_incomplete_evidence_is_left_standing(self) -> None:
        for case, moved in _INCOMPLETE:
            with self.subTest(case):
                self._left_standing(moved, TakeoverOutcome.INCOMPLETE)

    def test_nothing_is_handed_without_both_owners(self) -> None:
        # No attempt to hand over, an attempt with no generation to take it,
        # and a replay owned by a generation recorded against another issue,
        # which adjudication here would refuse.
        no_generation = dict.fromkeys(support.GENERATION)
        foreign_owner = {
            **_RETIRED, support.KEY_REPLAY: support.REPLAY, "late_current_issue": support.ISSUE + 1,
        }
        for case, pinned in (
            ("no attempt", _RETIRED), ("no generation", no_generation), ("another issue's owner", foreign_owner),
        ):
            with self.subTest(case):
                self._left_standing(pinned, TakeoverOutcome.ABSENT)

    def _left_standing(self, pinned: dict, expected: TakeoverOutcome) -> None:
        """Hand over a world seeded with `pinned`; nothing written, and `expected` answered."""
        world = support.TakeoverWorld.seeded(**pinned)
        seeded = world.pinned()

        self.assertEqual(world.takes_over(), expected)

        self.assertEqual((world.pinned(), world.github.write_state_calls), (seeded, 0))


class GuardedHandoffTest(unittest.TestCase):
    """The handoff lands over the comment read afresh, decided on both records it was proved on."""

    def test_a_moved_record_refuses_the_handoff(self) -> None:
        # Another road ends the cycle, re-anchors the attempt, or freezes
        # another candidate after the handoff read the comment: the attempt
        # stays standing under that road's write, and the tick's state is
        # withheld from every whole-state write behind it.
        for moved in (
            {"late_cancelled": True},
            {support.KEY_PENDING_PUSH: support.OTHER},
            {"late_candidate_sha": support.OTHER},
        ):
            with self.subTest(moved=sorted(moved)):
                world = support.TakeoverWorld.seeded()
                state = world.github.read_pinned_state(world.issue)
                world.another_road(**moved)
                written = world.pinned()

                self.assertEqual(
                    (support._takeover.takes_over(world.github, world.issue, state), state.withheld),
                    (TakeoverOutcome.REFUSED, True),
                )
                self.assertEqual(world.pinned(), written)

    def test_what_nobody_decided_on_is_kept(self) -> None:
        world = support.TakeoverWorld.seeded()
        state = world.github.read_pinned_state(world.issue)
        world.another_road(a_field_no_binary_writes_yet="kept", review_round=5)

        self.assertEqual(
            support._takeover.takes_over(world.github, world.issue, state), TakeoverOutcome.TAKEN_OVER,
        )

        durable = world.pinned()
        self.assertEqual(
            (durable["a_field_no_binary_writes_yet"], durable["review_round"], durable[support.KEY_REPLAY]),
            ("kept", 5, support.REPLAY),
        )
