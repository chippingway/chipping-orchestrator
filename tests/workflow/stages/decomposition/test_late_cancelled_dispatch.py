# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a reopened owner may reach while its cancelled cycle is unfinished.

Cancellation is irreversible within its cycle, so a human who reopens the
issue does not get that cycle back. Both labels an adjudication can be wearing
name a handler that ACTS on the issue rather than settling it: one spawns the
decomposer, the other walks the dependency graph and activates children. So
what is pinned here is the one place a label becomes a handler call, driven
through the real dispatcher, on both of those labels -- and the ending the
reopen has to pass through before anything works the issue again, which is the
same `rejected` an operator removes to authorize a restart.
"""
from __future__ import annotations

import unittest
from unittest.mock import Mock

from orchestrator.workflow.late_split.models import (
    LatePhase,
    LateResourceState,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.fixtures import _PatchedWorkflowMixin
from tests.workflow.stages.decomposition import late_cleanup_support as _support
from tests.workflow.stages.decomposition.late_cleanup_support import (
    OwnerSeed,
    RecordedDelete,
    SeededUmbrella,
    SnapshotOutcome,
)
from tests.workflow.stages.decomposition.late_route_support import (
    routed_owner,
)

# The two states an adjudication runs under, and therefore the only two an
# owner can be reopened onto still carrying one.
_ADJUDICATION_LABELS = (WorkflowLabel.DECOMPOSING, WorkflowLabel.UMBRELLA)

_WORKFLOW_LOG = "orchestrator.workflow"

# The ref an owner one level down was itself cut from. What it points at
# never matters here -- only that asking about it can fail.
_ANCESTOR_REF = "refs/orchestrator/late-split/issue-4/cycle-1/gen-0"

_RETIRED = ((_support.PARENT_NUMBER, WorkflowLabel.REJECTED),)

_KEY_CANCELLED = "late_cancelled"


def _reopened_owner(
    label: WorkflowLabel,
    owed: LateResourceState = LateResourceState.PENDING,
    ancestor: str = "",
) -> SeededUmbrella:
    """A cancelled owner a human reopened, still owing one branch.

    Marked the way either observer leaves it -- the flag, the stamp, and the
    boundary the cancellation interrupted -- on an issue that is open again,
    which is the state no pass but the dispatcher's own guard ever sees.

    `ancestor` makes it a NESTED owner as well, which is what puts the reuse
    guard between the dispatcher's one pinned read and this issue's own.
    """
    return _support.split_umbrella(
        owed,
        owner=OwnerSeed(
            label=label,
            closed=False,
            cancelled=True,
            ancestor_ref=ancestor,
            child=False,
        ),
    )


def _closed_handoff() -> SeededUmbrella:
    """A `single` closed inside the handoff, its cycle still reading live."""
    return _support.split_umbrella(
        None,
        owner=OwnerSeed(
            label=WorkflowLabel.IMPLEMENTING,
            closed=True,
            cancelled=False,
            child=False,
            phase=LatePhase.ADJUDICATING,
        ),
    )


def _cancelled_handoff() -> SeededUmbrella:
    """A `single` whose close landed inside the handoff to `implementing`.

    Nothing was ever superseded and no child exists, which is what makes the
    label the whole of what the terminal has to go on: the ledger holds no
    obligation for the guard to be stopped by.
    """
    return _support.split_umbrella(
        None,
        owner=OwnerSeed(
            label=WorkflowLabel.IMPLEMENTING,
            closed=False,
            cancelled=True,
            child=False,
            phase=LatePhase.ADJUDICATING,
        ),
    )


class CancelledOwnerDispatchTest(_PatchedWorkflowMixin, unittest.TestCase):
    """A cancelled cycle is cleanup and nothing else until it settles."""

    def test_neither_label_reaches_its_handler(self) -> None:
        for label in _ADJUDICATION_LABELS:
            with self.subTest(label=label):
                seeded = _reopened_owner(label)

                dispatched = routed_owner(self, seeded, label)

                dispatched.assert_not_called()

    def test_the_cleanup_it_is_held_for_runs(self) -> None:
        # Refusing with nothing behind it would freeze the issue until a human
        # closed it again: the closed-owner sweep visits closed issues only,
        # so this guard is the one pass that comes back to a reopened owner.
        seeded = _reopened_owner(WorkflowLabel.DECOMPOSING)

        routed_owner(self, seeded, WorkflowLabel.DECOMPOSING)

        self.assertEqual(
            seeded.github.deleted_remote_branches, [_support.SUPERSEDED_BRANCH],
        )
        self.assertEqual(
            _support.resource_states(seeded.github)[_support.SUPERSEDED_BRANCH],
            _support.STATE_RECONCILED,
        )

    def test_a_settled_cycle_stops_at_the_terminal(self) -> None:
        # Which is what makes the refusal end -- but through the ending, not
        # around it. `rejected` is what the CYCLE earns, so the reopen reaches
        # it exactly as a close would, and the handler is still never called:
        # resuming a cycle a close already ended is what irreversible means.
        for label in _ADJUDICATION_LABELS:
            with self.subTest(label=label):
                seeded = _reopened_owner(label)
                routed_owner(self, seeded, label)

                dispatched = routed_owner(self, seeded, label)

                dispatched.assert_not_called()
                self.assertEqual(tuple(seeded.github.label_history), _RETIRED)

    def test_an_unlabeled_owner_reaches_no_handler(self) -> None:
        # An operator authorizes a fresh attempt by taking `rejected` off, and
        # a human who strips a workflow label mid-cleanup leaves exactly the
        # same nothing behind -- so neither is dispatched, and what separates
        # them is whether the terminal was ever applied. Nothing here says it
        # was, so the ending writes the one it still owes once its obligations
        # settle, and holds where they have not. The restart an applied
        # terminal authorizes is its own owner's, and is pinned there.
        for reclaims, written in ((True, _RETIRED), (False, ())):
            with self.subTest(reclaims=reclaims):
                seeded = _reopened_owner(WorkflowLabel.DECOMPOSING)
                seeded.parent.labels = []
                seeded.github._pull_state._delete_remote_branch_returns_ok = (
                    reclaims
                )

                dispatched = routed_owner(self, seeded, None)

                dispatched.assert_not_called()
                self.assertEqual(
                    tuple(seeded.github.label_history), written,
                )

    def test_a_cleanup_that_cannot_finish_repeats(self) -> None:
        seeded = _reopened_owner(WorkflowLabel.DECOMPOSING)
        seeded.github._pull_state._delete_remote_branch_returns_ok = False

        with self.assertLogs(_WORKFLOW_LOG):
            routed_owner(self, seeded, WorkflowLabel.DECOMPOSING)
            dispatched = routed_owner(self, seeded, WorkflowLabel.DECOMPOSING)

        dispatched.assert_not_called()
        self.assertEqual(
            seeded.github.deleted_remote_branches,
            [_support.SUPERSEDED_BRANCH, _support.SUPERSEDED_BRANCH],
        )

    def test_an_ancestor_outage_does_not_starve_it(self) -> None:
        # A nested owner: its own cancelled cycle owes a branch, and the ref
        # it was itself cut from cannot be asked about. The reuse guard
        # answers an outage by HOLDING the dispatch -- writing nothing, tick
        # after tick -- so asking it first would leave this owner's own
        # obligations unreconciled for as long as the outage lasted.
        seeded = _reopened_owner(
            WorkflowLabel.DECOMPOSING, ancestor=_ANCESTOR_REF,
        )
        outage = RecordedDelete(
            SnapshotOutcome.DELETED, presence=SnapshotOutcome.UNREADABLE,
        )

        dispatched = routed_owner(
            self, seeded, WorkflowLabel.DECOMPOSING, outage,
        )

        dispatched.assert_not_called()
        self.assertEqual(
            seeded.github.deleted_remote_branches, [_support.SUPERSEDED_BRANCH],
        )
        self.assertEqual(tuple(seeded.github.label_history), _RETIRED)


class ClosedUnderAnOrdinaryLabelTest(
    _PatchedWorkflowMixin, unittest.TestCase,
):
    """A closed owner whose label names a terminal, not the cleanup sweep.

    The cleanup route takes a closed owner on either label an adjudication
    runs under. What reaches the dispatcher's guard closed is the one window
    no label covers: a `single` verdict hands its issue to `implementing` a
    moment before it retires the cycle, so a close landing there wears a
    label whose handler drains a merged pull request or a human close and
    writes the late record off nowhere.

    Nothing else would ever end that cycle -- the relabel guard beside it
    merely puts `decomposing` back, which a reopen before the next tick takes
    away again -- so an observed close ends it here.
    """

    def setUp(self) -> None:
        self.seeded = _closed_handoff()

    def test_the_live_cycle_is_cancelled(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG):
            self._routed()

        self.assertTrue(
            self.seeded.github.pinned_data(_support.PARENT_NUMBER)[_KEY_CANCELLED],
        )

    def test_the_handler_is_never_reached(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG):
            dispatched = self._routed()

        dispatched.assert_not_called()
        self.assertEqual(tuple(self.seeded.github.label_history), _RETIRED)

    def test_a_reopen_finds_the_mark_already_down(self) -> None:
        # The whole of why it is marked HERE: a reopen before the next tick
        # takes the closed reading away, and only the record survives it.
        with self.assertLogs(_WORKFLOW_LOG):
            self._routed()
        self.seeded.parent.closed = False

        dispatched = self._routed()

        dispatched.assert_not_called()

    def test_a_closed_issue_with_no_cycle_runs(self) -> None:
        # The baseline: every other closed issue still reaches the terminal
        # arc its own label names.
        self.seeded = _support.split_umbrella(
            None,
            owner=OwnerSeed(
                label=WorkflowLabel.IMPLEMENTING,
                closed=True,
                recorded=False,
                child=False,
            ),
        )

        dispatched = self._routed()

        dispatched.assert_called_once()

    def _routed(self) -> Mock:
        """Route this closed owner the way a tick does."""
        return routed_owner(self, self.seeded, WorkflowLabel.IMPLEMENTING)


class CancelledHandoffDispatchTest(_PatchedWorkflowMixin, unittest.TestCase):
    """The third label a cancelled cycle can be standing under.

    A `single` verdict hands the issue to `implementing` a moment before a
    close is observed, and that cycle owes no remote anything -- so a terminal
    withheld there would let the guard find nothing outstanding and wave the
    issue straight through to the handler that publishes it.
    """

    def test_the_handoff_label_ends_here_too(self) -> None:
        seeded = _cancelled_handoff()

        dispatched = routed_owner(self, seeded, WorkflowLabel.IMPLEMENTING)

        dispatched.assert_not_called()
        self.assertEqual(tuple(seeded.github.label_history), _RETIRED)

    def test_the_handoff_refusal_ends(self) -> None:
        # And it ends where the other two do: the terminal is what takes the
        # issue out of every route, rather than a hold that repeats forever.
        seeded = _cancelled_handoff()
        routed_owner(self, seeded, WorkflowLabel.IMPLEMENTING)
        seeded.github.label_history.clear()

        dispatched = routed_owner(self, seeded, WorkflowLabel.IMPLEMENTING)

        dispatched.assert_not_called()
        self.assertEqual(seeded.github.label_history, [])


if __name__ == "__main__":
    unittest.main()
