# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a split entered past publication leaves between an effect and its record.

The same seams the plan-PR road is killed at, asked of the road that closes
the implementation pull request the work is already on -- because that road
reaches them carrying something the other never does. The pull request exists
before the transaction starts, its branch is the one the reclamation takes
down, and the supersession that closes it is proved rather than searched for.
So a crash in front of the children, between the notice and the close, or
between the close and the branch behind it leaves a different world here, and
each case runs the transaction again from what the pinned comment holds --
exactly what the next eligible tick does, since the verdict is already
recorded and the retry costs a read rather than an agent.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.stages.decomposition import (
    late_retirement as _late_retirement,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.stages.decomposition.late_crash_support import (
    killed_after,
    killed_before,
)
from tests.workflow.stages.decomposition.late_published_split_support import (
    PublishedSplitCase,
)
from tests.workflow.stages.decomposition.late_test_support import (
    LATE_ISSUE_NUMBER,
)
from tests.workflow.stages.decomposition.late_transaction_support import (
    CHILDREN,
    KEY_SPLIT_CHILDREN,
    SNAPSHOT_REF,
    SUPERSESSION_MARKER,
    SnapshotSeed,
    first_child,
    label_of,
)

PR_OPEN = "open"

PR_CLOSED = "closed"

RESOURCE_BRANCH = "branch"

RESOURCE_SNAPSHOT = "snapshot_ref"

STATE_PENDING = "pending"

STATE_RECONCILED = "reconciled"

STATE_FAILED = "failed"

STATE_RETAINED = "retained"

# The seam the child loop is cut at, so one slice of the manifest exists on
# GitHub and the rest of the transaction never ran.
CREATE_CHILD = "create_child_issue"


class PublishedChildBoundaryTest(PublishedSplitCase, unittest.TestCase):
    """A publication is closed only once every child is there to take it on."""

    def test_a_partial_split_supersedes_nothing(self) -> None:
        # The order is what makes the crash survivable: an implementation
        # pull request closed over a notice naming children that do not all
        # exist is a change nobody can reopen and work nobody was handed.
        self._killed_mid_create()

        self.assertEqual(self.published_pr.state, PR_OPEN)
        self.assertEqual(self.github.posted_pr_comments, [])
        self.assertEqual(
            label_of(self.github, LATE_ISSUE_NUMBER),
            WorkflowLabel.DECOMPOSING,
        )

    def test_a_resumed_split_adopts_and_supersedes(self) -> None:
        # The crash lands in the window nothing outside GitHub knows the
        # number in -- the register is still empty -- so what adopts the
        # stranded slice is the marker on its body rather than a record. It is
        # reused rather than opened a second time, and the publication is
        # closed behind the whole manifest.
        self._killed_mid_create()
        stranded = [child.number for child in self.github.created_child_issues]
        self.assertIsNone(self._pinned().get(KEY_SPLIT_CHILDREN))

        resumed = self._resume()

        self.assertEqual(resumed.disposition, _LateDisposition.SETTLED)
        self.assertEqual(
            [child.number for child in self.github.created_child_issues][:1],
            stranded,
        )
        self.assertEqual(
            len(self.github.created_child_issues), len(CHILDREN),
        )
        self.assertEqual(self.published_pr.state, PR_CLOSED)

    def _killed_mid_create(self) -> None:
        """One slice created on GitHub, and a process that never returned."""
        with self.assertRaises(KeyboardInterrupt):
            self._transact(
                generation=self.generation,
                killed=killed_after(self.github, CREATE_CHILD),
            )


class PublishedSupersessionBoundaryTest(PublishedSplitCase, unittest.TestCase):
    """The publication's own thread is what stops a repeated notice."""

    def test_a_death_post_notice_says_it_once(self) -> None:
        # The notice and the close are one call and the write recording them
        # is another, so a resume that trusted the ledger alone would say it
        # twice on a pull request that already carries it.
        with self.assertRaises(KeyboardInterrupt):
            self._transact(
                generation=self.generation,
                killed=killed_after(self.github, "supersede_pr"),
            )

        self._resume()

        self.assertEqual(self._notices(), 1)
        self.assertEqual(self.published_pr.state, PR_CLOSED)

    def test_a_death_between_notice_and_close_closes(self) -> None:
        # The notice landed and the close did not, which is the state a
        # receipt cannot describe: the reading finds the pull request open,
        # proves the head again, and finishes the half that was left.
        with self.assertRaises(KeyboardInterrupt):
            self._transact(
                generation=self.generation,
                killed=killed_after(self.github, "pr_comment"),
            )
        self.assertEqual(self.published_pr.state, PR_OPEN)

        self._resume()

        self.assertEqual(self._notices(), 1)
        self.assertEqual(self.published_pr.state, PR_CLOSED)

    def test_a_reopened_publication_is_closed_again(self) -> None:
        # The ledger records what an earlier pass did, and a human can reopen
        # a pull request between that write and the resume. Skipping on the
        # strength of the entry would let the children loose beside a change
        # still carrying the superseded work.
        self._killed_before_the_retirement()
        self.published_pr.state = PR_OPEN

        resumed = self._resume()

        self.assertEqual(resumed.disposition, _LateDisposition.SETTLED)
        self.assertEqual(self.published_pr.state, PR_CLOSED)
        self.assertEqual(self._notices(), 1)

    def test_a_refused_reopen_holds_activation(self) -> None:
        # And where it cannot be closed again nothing is handed on: the parent
        # stays on the adjudication and every child stays blocked.
        self._killed_before_the_retirement()
        self.published_pr.state = PR_OPEN
        self.github.unsupersedable_prs.add(self.published_pr.number)

        resumed = self._resume()

        self.assertEqual(resumed.disposition, _LateDisposition.PARKED)
        self.assertEqual(self.published_pr.state, PR_OPEN)
        self.assertEqual(
            label_of(self.github, LATE_ISSUE_NUMBER),
            WorkflowLabel.DECOMPOSING,
        )
        self.assertEqual(
            first_child(self.github).labels[0].name, WorkflowLabel.BLOCKED,
        )

    def _killed_before_the_retirement(self) -> None:
        """The window the close opens: settled, and nothing handed on yet."""
        with self.assertRaises(KeyboardInterrupt):
            self._transact(
                generation=self.generation,
                killed=killed_before(_late_retirement, "_handed_to_children"),
            )
        self.assertEqual(self.published_pr.state, PR_CLOSED)

    def _notices(self) -> int:
        """How many supersession notices this generation's marker is on."""
        return len([
            body for _, body in self.github.posted_pr_comments
            if SUPERSESSION_MARKER in body
        ])


class PublishedCleanupBoundaryTest(PublishedSplitCase, unittest.TestCase):
    """The branch the closed publication was standing on, and its retries."""

    def test_a_death_pre_cleanup_leaves_it_owed(self) -> None:
        # The obligation is written in the retirement, ahead of the first
        # attempt on it, so a reclamation has the branch to retry rather than
        # a pull request that is closed and a ref nothing on the issue names.
        with self.assertRaises(KeyboardInterrupt):
            self._transact(
                generation=self.generation,
                killed=killed_before(self.github, "delete_remote_branch"),
            )

        self.assertEqual(self._branch_ledger(), {self.branch: STATE_PENDING})

    def test_a_death_post_delete_reconciles(self) -> None:
        # The delete landed and the write recording it did not. An absent
        # branch is success to the transport, so the resume asks once about
        # the same name and settles the entry it already had.
        with self.assertRaises(KeyboardInterrupt):
            self._transact(
                generation=self.generation,
                killed=killed_after(self.github, "delete_remote_branch"),
            )

        self._resume()

        self.assertEqual(
            self._branch_ledger(), {self.branch: STATE_RECONCILED},
        )

    def test_a_refused_teardown_holds_no_child(self) -> None:
        # Cleanup is tidiness with a deadline, not a precondition. A checkout
        # that would not come down leaves the entry owed for the umbrella's
        # own terminal to retry, and the children run regardless -- work
        # stalled on housekeeping is what the order after activation avoids.
        outcome = self._transact(
            generation=self.generation,
            snapshot=SnapshotSeed(local_gone=False),
        )

        self.assertEqual(outcome.disposition, _LateDisposition.SETTLED)
        self.assertEqual(self._branch_ledger(), {self.branch: STATE_FAILED})
        self.assertNotEqual(
            first_child(self.github).labels[0].name, WorkflowLabel.BLOCKED,
        )
        self.assertEqual(
            label_of(self.github, LATE_ISSUE_NUMBER), WorkflowLabel.UMBRELLA,
        )
        # And the ref the children were cut from is retained through all of
        # it: what the failed branch holds is the umbrella's terminal, never
        # the snapshot its consumers still need.
        self.assertEqual(
            self._resources()[(RESOURCE_SNAPSHOT, SNAPSHOT_REF)],
            STATE_RETAINED,
        )

    def _branch_ledger(self) -> dict:
        """Every branch obligation this split recorded, by target."""
        return {
            target: recorded
            for (kind, target), recorded in self._resources().items()
            if kind == RESOURCE_BRANCH
        }


if __name__ == "__main__":
    unittest.main()
