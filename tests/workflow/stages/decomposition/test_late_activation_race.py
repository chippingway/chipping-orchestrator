# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a child's own state does while the walk that releases it runs.

Two races, and the activation walk is the one thing they both end at. The park
between the children and the activation can stand for as long as a human takes
to settle a pull request, so by the time the transaction resumes a child's
state is no longer its to assume -- and the transition guard only warns by
default, so nothing else would stop a write that put a terminal child back to
`ready`.

The other is the parent's own state. A relabel is a request and the poll runs
beside it, so a close observed after the FIRST child was released reaches no
other pass -- and this walk is the one step of a late split that puts an agent
on somebody's repository.
"""
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.decomposition import (
    activation as _activation,
)
from orchestrator.workflow.stages.decomposition.models import _ChildScan
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.stages.decomposition.late_observation_seams import (
    CHILD_RELABEL,
    latches_on_call,
)
from tests.workflow.stages.decomposition.late_test_support import (
    PLAN_PR_NUMBER,
)
from tests.workflow.stages.decomposition.late_transaction_support import (
    HeldPlanPrSplitCase,
    first_child,
    label_of,
)

_OWNER_NUMBER = 90

_SIBLINGS = (901, 902)

_WORKFLOW_LOG = "orchestrator.workflow"


class SupersessionRaceTest(HeldPlanPrSplitCase, unittest.TestCase):
    """What a child's own state does while the supersession is parked.

    The park can stand for as long as a human takes to settle a pull request,
    so by the time activation runs a child's state is no longer this
    transaction's to assume -- and the transition guard only warns by default,
    so nothing else would stop a write that put a terminal child back.
    """

    def setUp(self) -> None:
        super().setUp()
        self.github.unsupersedable_prs.add(PLAN_PR_NUMBER)
        self._transact(generation=self.generation)
        self.github.unsupersedable_prs.clear()

    def test_a_child_that_ended_meanwhile_is_left(self) -> None:
        ended = first_child(self.github)
        self.github.set_workflow_label(
            ended, WorkflowLabel.REJECTED, guarded=False,
        )

        self._resume()

        self.assertEqual(
            label_of(self.github, ended.number), WorkflowLabel.REJECTED,
        )

    def test_a_child_a_human_closed_is_left(self) -> None:
        # A close leaves the label exactly where it was, so this child still
        # reads `blocked`. Started anyway, it would be relabeled `ready` over
        # the close and the umbrella would wait on an issue nobody is running.
        closed = first_child(self.github)
        closed.closed = True

        self._resume()

        self.assertEqual(
            label_of(self.github, closed.number), WorkflowLabel.BLOCKED,
        )
        self.assertTrue(closed.closed)

    def test_a_child_still_blocked_is_released(self) -> None:
        # The other half of the same read: the walk moves the ones that are
        # still where the split left them.
        self._resume()

        self.assertEqual(
            label_of(self.github, first_child(self.github).number),
            WorkflowLabel.READY,
        )

    def test_a_child_the_manifest_holds_stays_blocked(self) -> None:
        self._resume()

        held = self.github.created_child_issues[1]
        self.assertEqual(
            label_of(self.github, held.number), WorkflowLabel.BLOCKED,
        )


class LatchedCloseStopsTheWalkTest(
    ObservedCloseCase, unittest.TestCase,
):
    """A close latched during one relabel releases no child after it.

    Two dep-free siblings, so a walk nothing stopped would flip both. The
    parent reads OPEN throughout -- a human reopened it -- and the latch is
    the only thing that knows otherwise.
    """

    def setUp(self) -> None:
        self._fresh_process()
        self.github = FakeGitHubClient()
        self.owner = make_issue(_OWNER_NUMBER, label=WorkflowLabel.UMBRELLA)
        self.github.add_issue(self.owner)
        for number in _SIBLINGS:
            self.github.add_issue(
                make_issue(number, label=WorkflowLabel.BLOCKED),
            )
            # Linked the way a split seeds every child it creates.
            self.github.seed_state(number, parent_number=_OWNER_NUMBER)

    def test_only_the_first_sibling_is_released(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG), self._closing():
            self._walked()

        self.assertEqual(
            [label_of(self.github, number) for number in _SIBLINGS],
            [WorkflowLabel.READY, WorkflowLabel.BLOCKED],
        )

    def test_the_one_it_held_is_reported_held(self) -> None:
        # So the caller's own logging says a child is waiting rather than
        # reporting a walk that released everything it looked at.
        with self.assertLogs(_WORKFLOW_LOG), self._closing():
            held = self._walked()

        self.assertEqual([number for number, _ in held], [_SIBLINGS[1]])

    def test_a_walk_nobody_latched_releases_both(self) -> None:
        held = self._walked()

        self.assertEqual(
            [label_of(self.github, number) for number in _SIBLINGS],
            [WorkflowLabel.READY, WorkflowLabel.READY],
        )
        self.assertEqual(held, [])

    def _walked(self) -> list:
        """Run the shared dep-graph walk over two dep-free siblings."""
        return _activation._activate_ready_children(
            self.github,
            _TEST_SPEC,
            self.owner,
            PinnedState(data={"children": list(_SIBLINGS)}),
            _ChildScan(
                list(_SIBLINGS),
                {
                    number: self.github.get_issue(number)
                    for number in _SIBLINGS
                },
                {number: WorkflowLabel.BLOCKED for number in _SIBLINGS},
            ),
        )

    def _closing(self):
        """Latch the close inside the write that releases the first child."""
        return latches_on_call(
            self.github, _TEST_SPEC.slug, _OWNER_NUMBER, CHILD_RELABEL,
        )


if __name__ == "__main__":
    unittest.main()
