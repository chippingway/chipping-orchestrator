# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The close a reclamation has to catch between the obligations it settles.

A settled split owes a remote two things -- the branch its candidate sat on
and the immutable ref its children were cut from -- and it settles them one
request at a time, with a fresh consumer proof standing between the decision
and the ref delete it authorizes. Every one of those is a window the poll runs
beside.

The receipts each delivered ref owes are `test_late_receipt_close`'s, beside
this. What the mark changes here is not WHETHER the rest is settled: a
cancellation buys no shortcut through the reclamation rules, and the ref goes only because every
recorded consumer is proved ended, exactly as it would have. What it changes
is what the settling owes anybody -- a cancelled cycle tells its consumers
nothing -- and whether the reclamation can be attributed to it at all, which
is why the mark has to be DOWN before the ref is gone rather than after.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.git.snapshots import refs as _snapshot_refs
from orchestrator.workflow.late_split.models import (
    LateResourceState,
)
from orchestrator.workflow.stages.decomposition import (
    late_cleanup as _late_cleanup,
    parents as _parents,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.fixtures import _TEST_SPEC, _PatchedWorkflowMixin
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.stages.decomposition import late_cleanup_support as _support
from tests.workflow.stages.decomposition.late_cleanup_support import (
    OwnerSeed,
    RecordedDelete,
    SeededUmbrella,
    SnapshotOutcome,
)
from tests.workflow.stages.decomposition.late_observation_seams import (
    BRANCH_DELETE,
    latches_on_call,
    latches_on_child_scan,
)

# The pinned flag every case here reads: whether the record says the cycle is
# over by the time the remote is asked for anything.
_KEY_CANCELLED = "late_cancelled"

_WORKFLOW_LOG = "orchestrator.workflow"

_TEST_SLUG = _TEST_SPEC.slug

_RESOURCE_BRANCH = "branch"

_STATE_PENDING = "pending"


class LatchedInsideTheReclamationTest(
    ObservedCloseCase, _PatchedWorkflowMixin, unittest.TestCase,
):
    """A reclamation is one request per obligation, and the poll runs beside.

    An owner owing a branch AND a ref settles them in that order, and the ref
    half writes to somebody else's issue: every child cut from it is told,
    once each. A close observed inside the branch delete makes this a
    cancelled cycle before the ref half runs, and a cancelled cycle owes its
    children nothing -- not a comment, not a label, not a pinned write.

    What it does NOT buy is a shortcut through the rules: the ref still goes
    only because every recorded consumer is proved ended, exactly as it would
    have.
    """

    def setUp(self) -> None:
        self._fresh_process()
        self.seeded = _owing_both()
        self.recorded = dict(self.seeded.github.pinned_data(_support.CHILD_NUMBER))

    def test_the_cancellation_is_persisted_first(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG):
            self._walked()

        self.assertTrue(self._record()[_KEY_CANCELLED])

    def test_both_obligations_are_still_settled(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG):
            deleted = self._walked()

        self.assertEqual(
            self.seeded.github.deleted_remote_branches, [_support.SUPERSEDED_BRANCH],
        )
        self.assertEqual(deleted.refs, [_support.SNAPSHOT_REF])

    def test_the_child_is_told_nothing(self) -> None:
        # The one effect of a reclamation that reaches another issue, and the
        # one a cancelled cycle owes nobody.
        with self.assertLogs(_WORKFLOW_LOG):
            self._walked()

        self.assertEqual(self.seeded.github.posted_comments, [])
        self.assertEqual(
            self.seeded.github.pinned_data(_support.CHILD_NUMBER), self.recorded,
        )

    def _walked(self) -> RecordedDelete:
        """Poll this umbrella, closing it inside its branch delete."""
        remote = RecordedDelete(SnapshotOutcome.DELETED)
        with remote.answering(), latches_on_call(
            self.seeded.github, _TEST_SLUG, _support.PARENT_NUMBER, BRANCH_DELETE,
        ):
            _support.walk_owner(self, self.seeded)
        return remote

    def _record(self) -> dict:
        return self.seeded.github.pinned_data(_support.PARENT_NUMBER)


class LatchedInsideTheProofTest(
    ObservedCloseCase, _PatchedWorkflowMixin, unittest.TestCase,
):
    """The last reading a ref delete is taken past, and what it may not skip.

    A ref goes only once every recorded consumer is proved ended on a reading
    taken THIS visit, and that proof is a request per consumer with a remote
    probe behind it. A close observed anywhere in there is one the delete must
    not run ahead of: a ref that is gone while the record still reads live is
    a reclamation nothing afterwards can attribute to the cancellation that
    earned it.
    """

    def setUp(self) -> None:
        self._fresh_process()
        self.seeded = _owing_both()

    def test_the_mark_is_down_before_the_ref_goes(self) -> None:
        deleted = self._settled()

        self.assertEqual(deleted.refs, [_support.SNAPSHOT_REF])
        self.assertTrue(deleted.marked)

    def test_the_child_is_told_nothing(self) -> None:
        self._settled()

        self.assertEqual(self.seeded.github.posted_comments, [])

    def _settled(self) -> _MarkAtDelete:
        """Settle this owner's ledger, closing it inside the consumer proof."""
        deleted = _MarkAtDelete(self.seeded.github)
        state = self.seeded.github.read_pinned_state(self.seeded.parent)
        scan = _parents._read_child_labels(
            self.seeded.github, self.seeded.parent, [_support.CHILD_NUMBER],
        )
        with self.assertLogs(_WORKFLOW_LOG), deleted.answering(), (
            latches_on_child_scan(
                self.seeded.github, _TEST_SLUG, _support.PARENT_NUMBER,
            )
        ):
            _late_cleanup._settled_for_terminal(
                self.seeded.github, _TEST_SPEC, self.seeded.parent,
                state, scan,
            )
        return deleted


class _MarkAtDelete:
    """A remote that reads the owner's record the moment it is asked to delete.

    Which is the whole assertion: the mark and the delete are two writes on
    two different hosts, and only their ORDER says whether the reclamation
    was one the cancellation earned.
    """

    def __init__(self, github) -> None:
        self._github = github
        self.refs: list[str] = []
        self.marked = False

    def __call__(self, _spec, _cwd, *, ref: str, sha: str):
        """Answer the delete, having read what the record says right now."""
        self.refs.append(ref)
        self.marked = bool(
            self._github.pinned_data(_support.PARENT_NUMBER).get(_KEY_CANCELLED),
        )
        return SnapshotOutcome.DELETED

    def answering(self):
        """Put this in front of the one call that takes a ref away."""
        return patch.object(
            _snapshot_refs, "delete_snapshot_ref", side_effect=self,
        )


def _owing_both() -> SeededUmbrella:
    """An open umbrella owing a branch and the ref its child was cut from."""
    return _support.split_umbrella(
        LateResourceState.PENDING,
        snapshot=LateResourceState.RETAINED,
        owner=OwnerSeed(label=WorkflowLabel.UMBRELLA, closed=False),
    )


if __name__ == "__main__":
    unittest.main()
