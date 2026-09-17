# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The close that lands while a cleared split is publishing itself.

Publication is not one moment. The parent says what it became, the held plan
pull request is closed over a supersession notice, and the retirement hands the
parent to `umbrella` -- three GitHub round-trips, each of which a human can
close the issue inside, and the last of which is followed immediately by the
one effect of the whole transaction that puts an agent on somebody's
repository. So the owner is read between them rather than once for all of them,
and this module is one gap at a time.

What each ending inherits differs, and that is the other half of the subject:
a cycle stopped at the supersession still owns a held pull request nobody has
told, and one stopped just past it owns a superseded branch the retirement
never got to write down.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.late_split.phases import LatePhase
from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.stages.decomposition.late_close_race_support import (
    closes_on_announcement,
    closes_on_retirement,
    closes_on_supersession,
)
from tests.workflow.stages.decomposition.late_observation_seams import (
    CHILD_RELABEL,
    latches_on_call,
)
from tests.workflow.stages.decomposition.late_test_support import (
    KEYS,
    PLAN_PR_NUMBER,
)
from tests.workflow.stages.decomposition.late_transaction_support import (
    CHILDREN,
    KEY_LINKS_ANNOUNCED,
    KEY_PR_NUMBER,
    HeldPlanPrSplitCase,
    label_of,
)

_RESOURCE_PLAN_PR = "plan_pr"
_RESOURCE_BRANCH = "branch"
_PR_OPEN = "open"
_PR_CLOSED = "closed"
_STATE_RECONCILED = "reconciled"
_STATE_PENDING = "pending"

_WORKFLOW_LOG = "orchestrator.workflow"

REPO_SLUG = _TEST_SPEC.slug

# What the parent still carries while its transaction is unfinished.
_DECOMPOSING = "workflow:decomposing"

# What it wears once the retirement write has landed.
_UMBRELLA = "workflow:umbrella"

# What a child carries until something releases it.
_BLOCKED = "workflow:blocked"


class ClosedDuringAnnouncementTest(HeldPlanPrSplitCase, unittest.TestCase):
    """A close inside the comment that says what the parent became.

    Publication is three moments rather than one, and this is the gap after
    the first: the forward links are on the thread, and the plan pull request
    is still open under its hold. Reading the owner once for the whole of
    publication would let this close through to the supersession, the
    umbrella label, and the children behind them.
    """

    def setUp(self) -> None:
        super().setUp()
        self.closing = closes_on_announcement(self)

    def test_the_cycle_ends_at_the_supersession(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG), self.closing:
            outcome = self._transact()

        pinned = self._pinned()
        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertTrue(pinned[KEYS.cancelled])
        self.assertEqual(
            pinned[KEYS.cancelled_phase], LatePhase.SUPERSEDING.value,
        )
        self._assert_the_announcement_it_made_is_kept()
        self._assert_the_plan_pr_is_left_for_the_ending()
        self._assert_nothing_below_it_runs()

    def _assert_the_announcement_it_made_is_kept(self) -> None:
        # The receipt the ending reads: a cancellation past this stamp is one
        # whose supersession was reached, which is what later lets it take on
        # the branch that pull request carries.
        self.assertTrue(self._pinned()[KEY_LINKS_ANNOUNCED])

    def _assert_the_plan_pr_is_left_for_the_ending(self) -> None:
        # A cancelled cycle's plan PR is closed over a cancellation notice
        # rather than a supersession one, and that is the ending's to post.
        self.assertEqual(self.github.pulls[PLAN_PR_NUMBER].state, _PR_OPEN)
        self.assertEqual(self.github.posted_pr_comments, [])

    def _assert_nothing_below_it_runs(self) -> None:
        self.assertEqual(label_of(self.github, self.issue.number), _DECOMPOSING)
        self.assertEqual(
            [
                label_of(self.github, child.number)
                for child in self.github.created_child_issues
            ],
            [_BLOCKED for _ in CHILDREN],
        )
        self.assertEqual(self.github.deleted_remote_branches, [])


class ClosedDuringSupersessionTest(HeldPlanPrSplitCase, unittest.TestCase):
    """A close inside the call that closes the plan pull request.

    The last gap, and the one that decides whether an agent is put on
    somebody's repository: past it the parent is handed to `umbrella` and the
    children this walk releases are started. The supersession itself landed,
    so what the ending inherits is a settled pull request and a branch the
    retirement never got to write down.
    """

    def setUp(self) -> None:
        super().setUp()
        self.closing = closes_on_supersession(self)

    def test_the_supersession_that_landed_is_recorded(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG), self.closing:
            outcome = self._transact()

        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertEqual(self.github.pulls[PLAN_PR_NUMBER].state, _PR_CLOSED)
        self.assertEqual(
            self._resources()[(_RESOURCE_PLAN_PR, str(PLAN_PR_NUMBER))],
            _STATE_RECONCILED,
        )
        self._assert_the_parent_is_not_retired()
        self._assert_no_child_is_started()
        self._assert_the_branch_is_left_to_the_ending()

    def _assert_the_parent_is_not_retired(self) -> None:
        self.assertEqual(label_of(self.github, self.issue.number), _DECOMPOSING)
        self.assertEqual(self._pinned()[KEY_PR_NUMBER], PLAN_PR_NUMBER)

    def _assert_no_child_is_started(self) -> None:
        # The effect the whole re-read exists for: a settled split releases
        # the child with no dependency of its own, and a cancelled cycle
        # releases neither.
        self.assertEqual(
            [
                label_of(self.github, child.number)
                for child in self.github.created_child_issues
            ],
            [_BLOCKED for _ in CHILDREN],
        )

    def _assert_the_branch_is_left_to_the_ending(self) -> None:
        # Nothing here deletes it and nothing here records it: the record
        # says the supersession landed, and taking the branch on from that is
        # the cancellation's own step.
        self.assertEqual(self.github.deleted_remote_branches, [])
        self.assertNotIn(
            _RESOURCE_BRANCH,
            [kind for kind, _ in self._resources()],
        )


class ClosedDuringRetirementTest(HeldPlanPrSplitCase, unittest.TestCase):
    """A close inside the write that hands the parent to `umbrella`.

    The gap past every other one, and the only one where the cycle is already
    published: the plan pull request is closed over its supersession, the
    label is written, and the very next step starts an agent on a child. A
    close landing inside that write is the last one the transaction can still
    catch for itself.
    """

    def setUp(self) -> None:
        super().setUp()
        self.closing = closes_on_retirement(self)

    def test_the_cycle_ends_rather_than_settling(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG), self.closing:
            outcome = self._transact()

        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertTrue(self._pinned()[KEYS.cancelled])
        self.assertEqual(self.github.deleted_remote_branches, [])
        self._assert_no_child_is_started()
        self._assert_the_retirement_it_wrote_stands()

    def _assert_no_child_is_started(self) -> None:
        # The requirement the whole barrier is here for: a settled split
        # releases the child with no dependency of its own, and a cycle a
        # close ended releases neither.
        self.assertEqual(
            [
                label_of(self.github, child.number)
                for child in self.github.created_child_issues
            ],
            [_BLOCKED for _ in CHILDREN],
        )

    def _assert_the_retirement_it_wrote_stands(self) -> None:
        # The write landed, so what the record says is what the ending reads:
        # an umbrella owing a branch, which is one of the two labels the
        # cancelled cycle's own terminal is declared from.
        self.assertEqual(label_of(self.github, self.issue.number), _UMBRELLA)
        self.assertEqual(
            [
                state for (kind, _), state in self._resources().items()
                if kind == _RESOURCE_BRANCH
            ],
            [_STATE_PENDING],
        )


class LatchedDuringActivationTest(
    ObservedCloseCase, HeldPlanPrSplitCase, unittest.TestCase,
):
    """A close latched inside the relabel that releases the first child.

    The walk holds every child after it -- that is its own answer, and the
    whole of what a shared dep-graph walk may decide. What the TRANSACTION
    does with that answer is the subject here: reporting settled would send
    it on to reclaim the superseded branch, which is external work on an
    issue this reading says nobody wants, and would leave no mark saying why.
    """

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()

    def test_the_cycle_ends_rather_than_settling(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG), self._closing():
            outcome = self._transact()

        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertTrue(self._pinned()[KEYS.cancelled])
        self._assert_the_branch_is_left_to_the_ending()
        self._assert_the_children_it_never_reached_wait()

    def _assert_the_branch_is_left_to_the_ending(self) -> None:
        self.assertEqual(self.github.deleted_remote_branches, [])
        self.assertEqual(
            [
                state for (kind, _), state in self._resources().items()
                if kind == _RESOURCE_BRANCH
            ],
            [_STATE_PENDING],
        )

    def _assert_the_children_it_never_reached_wait(self) -> None:
        # The walk's own answer, asserted here so the two halves are one
        # description: the transaction ends the cycle BECAUSE the walk
        # stopped releasing.
        self.assertEqual(
            [
                label_of(self.github, child.number)
                for child in self.github.created_child_issues
            ],
            [_BLOCKED for _ in CHILDREN],
        )

    def _closing(self):
        """Latch the close inside the relabel that releases a child.

        Past the retirement's own read, because the label write that hands
        the parent to `umbrella` goes through the same seam: only the relabel
        of a CHILD arms this one.
        """
        return latches_on_call(
            self.github, REPO_SLUG, self.issue.number, CHILD_RELABEL,
        )


if __name__ == "__main__":
    unittest.main()
