# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The close an umbrella's own walk has to catch for itself.

An umbrella poll reads every recorded child, and that is a request per child.
Everything past the scan ACTS on what it read: it reclaims a remote a settled
split still owes, or it hands the issue `done` and closes it, or it releases a
child to an agent. A close observed inside the scan reaches no other pass --
the scheduler admits no second worker for an issue one is already running --
so the walk is what has to stop.

`done` is the worst of the three, and it is why the barrier is here rather than
one layer down: that write takes the issue off both labels the closed-owner
sweep queries, so the cancellation would never be recorded by anything, ever.
"""
from __future__ import annotations

import unittest

from orchestrator.scheduler import writer_claims
from orchestrator.workflow.engine import observations as _observations
from orchestrator.workflow.state import WorkflowLabel
from tests.support.writer_claims import signed_by_another_poller
from tests.workflow.fixtures import _TEST_SPEC, _PatchedWorkflowMixin
from tests.workflow.observation_support import ObservedCloseCase, read_now
from tests.workflow.stages.decomposition.late_cancel_support import (
    settled_umbrella as _settled_umbrella,
)
from tests.workflow.stages.decomposition.late_cleanup_support import (
    CHILD_KIND as _CHILD_KIND,
    CHILD_NUMBER,
    PARENT_NUMBER,
    SUPERSEDED_BRANCH,
    resource_states,
    walk_owner,
)
from tests.workflow.stages.decomposition.late_observation_seams import (
    BRANCH_DELETE,
    ISSUE_COMMENT,
    latches_on_call,
    latches_on_child_scan,
)
from tests.workflow.stages.decomposition.late_test_support import CYCLE_ID, KEYS

_WORKFLOW_LOG = "orchestrator.workflow"

_STATE_PENDING = "pending"

_RECONCILED = "reconciled"

_TRANSITION_GUARD = "WORKFLOW_TRANSITION_GUARD"

_ENFORCE = "enforce"

_TEST_SLUG = _TEST_SPEC.slug

# The cycle before this umbrella's own: the one another poller on this host
# settled and restarted from.
_RESTARTED_FROM = CYCLE_ID - 1


class LatchedCloseStopsTheUmbrellaTest(
    ObservedCloseCase, _PatchedWorkflowMixin, unittest.TestCase,
):
    """An umbrella whose every child is done, closed inside its own scan."""

    def setUp(self) -> None:
        self._fresh_process()
        self.seeded = _settled_umbrella()

    def test_the_cancellation_is_recorded(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG):
            self._walked()

        self.assertTrue(self._record()[KEYS.cancelled])

    def test_the_terminal_is_not_written(self) -> None:
        # `done` would take this issue off both labels the closed-owner sweep
        # queries, so a cancellation it bypassed would never be recorded at
        # all -- not by the sweep, and not by the dispatcher's own guard.
        with self.assertLogs(_WORKFLOW_LOG):
            self._walked()

        self.assertEqual(self.seeded.github.label_history, [])
        self.assertFalse(self.seeded.parent.closed)

    def test_the_remote_is_left_to_the_ending(self) -> None:
        # The ending settles the branch by exactly these rules; what it may
        # not do is settle it on a reading this walk cannot trust.
        with self.assertLogs(_WORKFLOW_LOG):
            self._walked()

        self.assertEqual(self.seeded.github.deleted_remote_branches, [])
        self.assertEqual(
            resource_states(self.seeded.github)[SUPERSEDED_BRANCH],
            _STATE_PENDING,
        )

    def test_a_walk_nobody_latched_completes_as_ever(self) -> None:
        # The baseline: with no observation held, the umbrella resolves.
        self._walked(closing=False)

        self.assertEqual(
            self.seeded.github.label_history,
            [(PARENT_NUMBER, WorkflowLabel.DONE)],
        )

    def _walked(self, *, closing: bool = True) -> None:
        """Poll this umbrella, optionally closing it inside its own scan."""
        if not closing:
            walk_owner(self, self.seeded)
            return
        with latches_on_child_scan(
            self.seeded.github, _TEST_SLUG, PARENT_NUMBER,
        ):
            walk_owner(self, self.seeded)

    def _record(self) -> dict:
        return self.seeded.github.pinned_data(PARENT_NUMBER)


class AnotherCyclesCloseTest(
    ObservedCloseCase, _PatchedWorkflowMixin, unittest.TestCase,
):
    """An umbrella holding a close scoped to the cycle a restart replaced.

    Another poller on this host settled the cycle that close ended and an
    operator restarted it, and let go after the close was read. The close is
    no reading of the cycle this walk holds, so neither the walk's barriers
    nor the window its terminal retires the cycle through may end that cycle
    with it.
    """

    def setUp(self) -> None:
        self._fresh_process()

    def test_the_walk_completes_as_ever(self) -> None:
        seeded = _settled_umbrella()
        _observations.observe_close(_TEST_SLUG, PARENT_NUMBER, read_now())
        _observations.scope_close(_TEST_SLUG, PARENT_NUMBER, _RESTARTED_FROM)
        signed_by_another_poller(seeded.github.repo_id, PARENT_NUMBER)

        with writer_claims.issue_writer(seeded.github.repo_id, PARENT_NUMBER) as held:
            self.assertTrue(held)
            walk_owner(self, seeded)

        self.assertFalse(seeded.github.pinned_data(PARENT_NUMBER).get(KEYS.cancelled))
        self.assertEqual(seeded.github.label_history, [(PARENT_NUMBER, WorkflowLabel.DONE)])


class LatchedDuringTerminalCleanupTest(
    ObservedCloseCase, _PatchedWorkflowMixin, unittest.TestCase,
):
    """A close latched inside the settlement the terminal waits on.

    The fence ahead of the scan is not the last word, because the settlement
    behind it is itself remote work -- a branch delete, a ref delete, a
    receipt on each child cut from a reclaimed ref. `done` past one of those
    is the write that cannot be recovered from: it takes the issue off both
    labels the closed-owner sweep queries and closes it, so a cancellation
    that got past it would be stranded with nothing left to visit the issue.
    """

    def setUp(self) -> None:
        self._fresh_process()
        self.seeded = _settled_umbrella()

    def test_the_terminal_is_not_written(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG):
            self._walked()

        self.assertEqual(self.seeded.github.label_history, [])
        self.assertFalse(self.seeded.parent.closed)

    def test_the_cancellation_is_recorded_instead(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG):
            self._walked()

        record = self.seeded.github.pinned_data(PARENT_NUMBER)
        self.assertTrue(record[KEYS.cancelled])

    def test_the_settlement_it_already_made_stands(self) -> None:
        # The delete landed before the reading arrived, and the ledger says
        # so: the ending re-asks what is still owed rather than re-doing what
        # is not.
        with self.assertLogs(_WORKFLOW_LOG):
            self._walked()

        self.assertEqual(
            self.seeded.github.deleted_remote_branches, [SUPERSEDED_BRANCH],
        )

    def _walked(self) -> None:
        """Poll this umbrella, closing it inside its own branch delete."""
        with latches_on_call(
            self.seeded.github, _TEST_SLUG, PARENT_NUMBER, BRANCH_DELETE,
        ):
            walk_owner(self, self.seeded)


class _TerminalCase(ObservedCloseCase, _PatchedWorkflowMixin):
    """One settled umbrella, closed inside one request of its terminal."""

    def setUp(self) -> None:
        self._fresh_process()
        self.seeded = _settled_umbrella()

    def _walked(self, seam: str) -> None:
        """Poll this umbrella, closing it inside one terminal request."""
        with latches_on_call(
            self.seeded.github, _TEST_SLUG, PARENT_NUMBER, seam,
        ):
            walk_owner(self, self.seeded)

    def _record(self) -> dict:
        return self.seeded.github.pinned_data(PARENT_NUMBER)


class LatchedInsideTheTerminalTest(_TerminalCase, unittest.TestCase):
    """The terminal is three requests, and `done` is the one with no way back.

    It takes the issue off both labels the closed-owner sweep queries and
    closes it, so a live generation left standing under one is an observation
    nothing ever comes back to. A close observed before that write stops it
    and the owner stays on `umbrella` with the mark down; one observed after
    it cannot take the label back, and marks the cancellation anyway so no
    LIVE cycle is left under a terminal.
    """

    def test_a_close_at_the_notice_writes_no_terminal(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG):
            self._walked(ISSUE_COMMENT)

        self.assertEqual(self.seeded.github.label_history, [])
        self.assertFalse(self.seeded.parent.closed)
        self.assertTrue(self._record()[KEYS.cancelled])

    def test_the_ending_discharges_the_child_receipts(self) -> None:
        # The ending writes a terminal, so it owes the whole ledger and not
        # just the mark: a child entry is `pending` from the moment the child
        # was created, and `rejected` is what authorizes a restart -- which
        # projects a fresh cycle only over a ledger with nothing unreconciled
        # left on it.
        with self.assertLogs(_WORKFLOW_LOG):
            self._walked(ISSUE_COMMENT)
        self.seeded.parent.closed = True

        self.seeded.swept(self)

        github = self.seeded.github
        self.assertEqual(
            resource_states(github, _CHILD_KIND),
            {str(CHILD_NUMBER): _RECONCILED},
        )
        self.assertEqual(
            set(resource_states(github).values())
            | set(resource_states(github, _CHILD_KIND).values()),
            {_RECONCILED},
        )


if __name__ == "__main__":
    unittest.main()
