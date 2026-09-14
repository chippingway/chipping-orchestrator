# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where a cancelled cycle may be dispatched from, which is nowhere labelled.

Every workflow label names a handler that ACTS on the issue rather than
settling it -- one spawns the decomposer, one publishes a candidate, one
resumes a developer -- so a cancelled cycle wearing any of them is refused
whatever it says. A human who relabels such an owner is asking for work on a
cycle a close already ended, and that is the one thing the mark forbids.

Where the TERMINAL lands is a narrower question. The transition graph answers
for every label a workflow wrote: each state a late cycle can be interrupted
on declares the edge to `rejected`, and one that does not is refused and said
out loud rather than relabelled out from under whoever put the issue there.
The two the cycle's own decomposer leaves behind are the exception -- `ready`
and `blocked` are its ordinary outcome, a close observed inside that run lands
ahead of it, and neither label is one anything would ever come back to. The
unlabeled state is the exception in the other direction: it is the restart
handshake itself, and re-applying a terminal there would undo it.
"""
from __future__ import annotations

import unittest

from orchestrator.github.labels import PAUSED_LABEL
from orchestrator.workflow.late_split.phases import LatePhase
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeLabel
from tests.workflow.fixtures import _PatchedWorkflowMixin
from tests.workflow.stages.decomposition.late_cleanup_support import (
    PARENT_NUMBER,
    OwnerSeed,
    SeededUmbrella,
    split_umbrella,
)
from tests.workflow.stages.decomposition.late_route_support import (
    routed_owner,
)

_WORKFLOW_LOG = "orchestrator.workflow"

_KEY_CANCELLED = "late_cancelled"

_RETIRED = ((PARENT_NUMBER, WorkflowLabel.REJECTED),)

# Stage labels a late cycle can be interrupted on, each declaring the edge to
# `rejected` the terminal is written over.
_RETIRABLE_LABELS = (
    WorkflowLabel.VALIDATING,
    WorkflowLabel.IN_REVIEW,
    WorkflowLabel.FIXING,
)

# The two a decomposition run writes as its ordinary outcome, which a close
# observed inside that run lands ahead of. Neither declares the edge and
# neither is swept while closed, so the terminal is written from both.
_AGENT_OUTCOME_LABELS = (WorkflowLabel.READY, WorkflowLabel.BLOCKED)


class CancelledUnderAnyLabelTest(_PatchedWorkflowMixin, unittest.TestCase):
    """A cancelled cycle is refused wherever the issue has been moved to.

    Every label names a handler that would ACT on the issue rather than settle
    it, so none of them is a state a cancelled cycle may be dispatched from.
    Where the terminal lands is narrower: the states a late cycle can be
    interrupted on declare the edge to `rejected`, the two its own decomposer
    writes as an ordinary outcome earn it because nothing else would ever
    reach them, and an operator's own conversation label is refused and said
    out loud instead.
    """

    def test_a_stage_label_is_refused_and_retired(self) -> None:
        for label in _RETIRABLE_LABELS:
            with self.subTest(label=label):
                seeded = _cancelled_on(label)

                with self.assertLogs(_WORKFLOW_LOG):
                    dispatched = routed_owner(self, seeded, label)

                dispatched.assert_not_called()
                self.assertEqual(
                    tuple(seeded.github.label_history), _RETIRED,
                )

    def test_an_agent_outcome_is_refused_and_retired(self) -> None:
        # The two labels a decomposer spawned before the close writes as its
        # ordinary outcome. A close observed inside that run lands ahead of
        # it, and neither label is swept while closed nor declares the edge --
        # so an ending refused there is one nothing would ever finish.
        for label in _AGENT_OUTCOME_LABELS:
            with self.subTest(label=label):
                seeded = _cancelled_on(label)

                with self.assertLogs(_WORKFLOW_LOG):
                    dispatched = routed_owner(self, seeded, label)

                dispatched.assert_not_called()
                self.assertEqual(
                    tuple(seeded.github.label_history), _RETIRED,
                )

    def test_an_operator_label_with_no_edge_is_left(self) -> None:
        # `question` is applied by an operator who wants the issue discussed
        # rather than ended, declares no edge to `rejected`, and is swept
        # while closed -- so relabelling out from under them is not this
        # owner's to do. The refusal is the whole of the visit, and an
        # operator taking the label off is what ends it.
        seeded = _cancelled_on(WorkflowLabel.QUESTION)

        with self.assertLogs(_WORKFLOW_LOG):
            dispatched = routed_owner(self, seeded, WorkflowLabel.QUESTION)

        dispatched.assert_not_called()
        self.assertEqual(seeded.github.label_history, [])

    def test_a_parked_owner_is_marked_and_left(self) -> None:
        # `paused` parks the issue outside the state machine, and the ending
        # is external work. The MARK is not deferred with it -- the pass this
        # would drop is the only one that would ever record the close.
        seeded = _cancelled_on(WorkflowLabel.IMPLEMENTING, parked=True)

        with self.assertLogs(_WORKFLOW_LOG):
            dispatched = routed_owner(
                self, seeded, WorkflowLabel.IMPLEMENTING,
            )

        dispatched.assert_not_called()
        self.assertEqual(seeded.github.label_history, [])
        self.assertEqual(seeded.github.deleted_remote_branches, [])
        self.assertTrue(
            seeded.github.pinned_data(PARENT_NUMBER)[_KEY_CANCELLED],
        )


def _cancelled_on(label, *, parked: bool = False) -> SeededUmbrella:
    """A cancelled cycle a human has moved to some other label."""
    seeded = split_umbrella(
        None,
        owner=OwnerSeed(
            label=label,
            closed=False,
            cancelled=True,
            child=False,
            phase=LatePhase.ADJUDICATING,
        ),
    )
    if parked:
        seeded.parent.labels.append(FakeLabel(PAUSED_LABEL))
    return seeded


if __name__ == "__main__":
    unittest.main()
