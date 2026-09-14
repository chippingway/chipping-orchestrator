# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where a hand relabel is caught: the label becoming a handler call."""
from __future__ import annotations

import importlib
import unittest
from unittest.mock import Mock, patch

from orchestrator.workflow.engine import (
    dispatch_guards as _dispatch_guards,
    issue_processing as _issue_processing,
    stage_targets as _stage_targets,
)
from orchestrator.workflow.stages.decomposition import (
    late_reuse as _late_reuse,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.stages.decomposition.late_content_support import late_issue
from tests.workflow.stages.decomposition.late_published_support import (
    published_generation,
)
from tests.workflow.stages.decomposition.late_relabel_support import (
    CANCELLED_GENERATION,
    SETTLED_GENERATIONS,
    relabelled,
)
from tests.workflow.stages.decomposition.late_test_support import KEYS

# What the dispatcher would hand a relabelled issue to. `ready` is the label a
# human reaches for to wave a candidate through, and its handler lives on the
# `blocked` owner -- so this is the module a coerced dispatch lands on.
READY_OWNER, READY_HANDLER = _stage_targets._STAGE_HANDLER_TARGETS[
    WorkflowLabel.READY
]

_WORKFLOW_LOG = "orchestrator.workflow"

READ_PINNED_STATE = "read_pinned_state"

# The last of the two questions the dispatcher asks that one read, and the one
# a `decomposing` issue either reaches or is proved not to need.
REFUSES_REUSE = "_refuses_reuse"

SET_WORKFLOW_LABEL = "set_workflow_label"

# What a record nothing can read parks under, and the two ways a hand edit
# leaves the marker: gone, and there as a value no reader will type.
PARK_MEASUREMENT_FAILED = "late_measurement_failed"
MARKER_GONE = None
NOT_A_FLAG = "yes"


class DispatchRefusalTest(unittest.TestCase):
    """A live adjudication may not reach the handler its label names."""

    def test_a_relabelled_generation_is_refused(self) -> None:
        # Nothing refuses the human's own label write, so the coercion is only
        # stoppable here: dispatching `ready` would hand the candidate to the
        # implementing handoff with no verdict on it.
        github, issue = late_issue()
        relabelled(issue, WorkflowLabel.READY)

        dispatched = self._route(github, issue)

        dispatched.assert_not_called()
        self.assertEqual(
            github.workflow_label(issue), WorkflowLabel.DECOMPOSING,
        )

    def test_a_settled_generation_routes_as_before(self) -> None:
        # A record no gate keyed to size holds is free to be routed --
        # unless it is CANCELLED, which is its own ending under whatever
        # label a human moved it to.
        for label, generation in SETTLED_GENERATIONS:
            with self.subTest(generation=label):
                github, issue = late_issue(generation=generation)
                relabelled(issue, WorkflowLabel.READY)

                dispatched = self._route(github, issue)

                dispatched.assert_called_once_with(github, _TEST_SPEC, issue)

    def test_a_cancelled_cycle_is_refused_here_too(self) -> None:
        # Every label names a handler that would ACT on the issue, so a
        # cancelled cycle wearing one is refused whatever it says. `ready` is
        # one the cycle's own decomposer writes as its ordinary outcome, so
        # the ending that outcome interrupted is written from there rather
        # than left for a label nothing would move.
        github, issue = late_issue(generation=CANCELLED_GENERATION)
        relabelled(issue, WorkflowLabel.READY)

        with self.assertLogs(_WORKFLOW_LOG):
            dispatched = self._route(github, issue)

        dispatched.assert_not_called()
        self.assertEqual(
            github.label_history, [(issue.number, WorkflowLabel.REJECTED)],
        )

    def test_a_failed_repair_still_refuses(self) -> None:
        # The refusal is the safety property and the relabel is the repair, so
        # a label write that cannot land must not hand the issue to the very
        # handler this exists to keep it away from.
        github, issue = late_issue()
        relabelled(issue, WorkflowLabel.READY)

        with patch.object(
            github, SET_WORKFLOW_LABEL, side_effect=RuntimeError("nope"),
        ):
            dispatched = self._route(github, issue)

        dispatched.assert_not_called()
        self.assertEqual(github.workflow_label(issue), WorkflowLabel.READY)

    def test_an_unreadable_state_refuses(self) -> None:
        # The costs are not symmetric. Failing open publishes an unadjudicated
        # candidate -- the handler behind this reads the same pinned comment,
        # and a first read that failed transiently is followed by a second
        # that may well succeed. Failing closed costs one tick of one issue.
        github, issue = late_issue()
        relabelled(issue, WorkflowLabel.READY)

        with patch.object(
            github, READ_PINNED_STATE, side_effect=RuntimeError("blip"),
        ):
            dispatched = self._route(github, issue)

        dispatched.assert_not_called()

    def _route(self, github, issue):
        """Route one issue the way a tick does, reporting the handler call."""
        dispatched = Mock()
        label = github.workflow_label(issue)
        owner = importlib.import_module(READY_OWNER)
        with patch.object(owner, READY_HANDLER, dispatched):
            _issue_processing._route_issue_to_handler(github, _TEST_SPEC, issue, label)
        return dispatched


class AdjudicatedLabelTest(unittest.TestCase):
    """The label the dispatcher's guards step aside for, and what proves it.

    `workflow:decomposing` is where an adjudication spends every one of its own
    ticks, and an issue in one is working from its own candidate rather than an
    ancestor's snapshot. What decides that is the record, not the label.
    """

    def test_the_label_it_pins_is_asked_no_more(self) -> None:
        # The ordinary case, and the reason the step-aside exists at all:
        # neither question the read answers is about an issue under
        # adjudication, and the handler behind it reads state of its own.
        held, asked = self._guarded(*late_issue())

        self.assertFalse(held)
        asked.assert_not_called()

    def test_the_label_alone_is_no_bypass(self) -> None:
        # What the label cannot say on its own. A child of a split closed while
        # it was being decomposed comes back with `decomposing` exactly where
        # it was and no generation of its own -- so an issue with nothing live
        # on it is asked the reuse question like any other.
        for label, generation in SETTLED_GENERATIONS:
            with self.subTest(generation=label):
                held, asked = self._guarded(
                    *late_issue(generation=generation),
                )

                self.assertFalse(held)
                asked.assert_called_once()

    def test_a_cancelled_cycle_is_held_before_it(self) -> None:
        # The one settled record the label does not free, and the one asked
        # AHEAD of the reuse question rather than past it. That question can
        # hold a dispatch indefinitely -- an ancestor's ref nobody can reach
        # is answered by holding, tick after tick -- and an owner of its own
        # cancelled cycle nested under one would never reconcile what it owes.
        held, asked = self._guarded(
            *late_issue(generation=CANCELLED_GENERATION),
        )

        self.assertTrue(held)
        asked.assert_not_called()

    def _guarded(self, github, issue):
        """Ask the guards, holding the reuse question the read ends in."""
        asked = Mock(return_value=False)
        with patch.object(_late_reuse, REFUSES_REUSE, asked):
            held = _dispatch_guards._pinned_state_refuses(
                github, _TEST_SPEC, issue, WorkflowLabel.DECOMPOSING,
            )
        return held, asked


class HalfPublishedAdjudicationTest(unittest.TestCase):
    """An adjudication whose publication group is only part of one.

    The group is the whole of what this mode settles by -- which pull request
    the verdict was taken over, which head to pin the push it licenses to, and
    which stage to hand the issue back to -- and none of it can be re-derived
    from anywhere else. Every field beside the marker is read fail-closed, so
    a marker a hand edit took leaves the record reading as a candidate nothing
    had published: a `single` then skips the proof that the pull request is
    still the one the reading was about, pushes nothing, routes the issue to
    `implementing`, and retires the frozen evidence behind it.
    """

    def test_a_partial_group_holds_the_adjudication(self) -> None:
        for marker in (MARKER_GONE, NOT_A_FLAG):
            with self.subTest(marker=marker):
                half = self._half_published(marker)

                self.assertTrue(self._refuses(half))
                pinned = self._pinned(half)
                self.assertTrue(pinned[KEYS.awaiting])
                self.assertEqual(
                    pinned[KEYS.park_reason], PARK_MEASUREMENT_FAILED,
                )

    def test_the_frozen_evidence_is_left_standing(self) -> None:
        # The park writes the pinned comment, and what it writes leaves the
        # group exactly as it found it: what the record names is a human's to
        # put back, and a settlement taken over half of it is what the refusal
        # exists to stop.
        entered = published_generation()
        half = self._half_published(MARKER_GONE)

        self._refuses(half)

        pinned = self._pinned(half)
        self.assertEqual(pinned[KEYS.candidate_sha], entered.candidate_sha)
        self.assertEqual(
            pinned[KEYS.published_pr_number], entered.publication.published_pr_number,
        )

    def test_a_whole_group_is_adjudicated_as_before(self) -> None:
        # What says the refusal is about the damage rather than about the
        # adjudication being asked a question no record passes.
        whole = late_issue(generation=published_generation())

        self.assertFalse(self._refuses(whole))
        self.assertNotIn(KEYS.awaiting, self._pinned(whole))

    def _half_published(self, marker):
        """A post-publication adjudication whose marker a hand edit took."""
        seeded = late_issue(generation=published_generation())
        pinned = self._pinned(seeded)
        pinned[KEYS.post_publication] = marker
        seeded[0].seed_state(seeded[1].number, **pinned)
        return seeded

    def _pinned(self, seeded) -> dict:
        """What this issue's pinned comment carries."""
        return seeded[0].pinned_data(seeded[1].number)

    def _refuses(self, seeded) -> bool:
        """Whether the dispatcher's own read stops this adjudication."""
        return _dispatch_guards._pinned_state_refuses(
            seeded[0], _TEST_SPEC, seeded[1], WorkflowLabel.DECOMPOSING,
        )
