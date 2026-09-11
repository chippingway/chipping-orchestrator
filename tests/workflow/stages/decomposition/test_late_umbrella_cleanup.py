# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The branch a split leaves behind, retried where it can still be settled.

The umbrella's all-children-resolved branch is the last tick that could reclaim
it and the only one that comes back if it cannot, so these cases drive the real
stage handler: an issue that has become an umbrella never reaches the
transaction again.

"The branch" is every surface it exists on -- the remote ref, the checkout, and
the local ref -- because a remote delete beside a checkout that would not come
down leaves a worktree on a superseded branch that the per-tick base refresh
goes on merging into.
"""
from __future__ import annotations

import unittest

from orchestrator.git.snapshots.refs import SnapshotOutcome
from orchestrator.workflow.late_split.models import LateResourceState
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import _PatchedWorkflowMixin
from tests.workflow.stages.decomposition import late_cleanup_support as _support
from tests.workflow.stages.decomposition.late_cleanup_support import OwnerSeed, RecordedDelete, SeededUmbrella
from tests.workflow.stages.decomposition.late_crash_support import refusing

# Four targets a ledger entry could name and this issue is not published under:
# an unprotected default branch, another issue's branch in the same namespace,
# one outside the namespace altogether, and -- the one a prefix-and-tail
# reading lets through -- another repository's branch for an issue whose number
# happens to match. Two specs sharing a `target_root` is what slug-namespacing
# exists for, so that last one is the ordinary shape, not a contrived one.
_WARNING = "WARNING"

_ERROR = "ERROR"

_MAIN = "main"

_ANOTHER_ISSUE = "orchestrator/chippingway__orchestrator/issue-99"

_NOT_OURS = "feature/issue-41"

_ANOTHER_REPOSITORY = "orchestrator/other-repository/issue-41"

_PARKED = "awaiting_human"


class _UmbrellaCleanupCase(_PatchedWorkflowMixin):
    """One umbrella tick over an issue that still owes a branch."""

    def _walk(self, owed: LateResourceState, **teardown) -> SeededUmbrella:
        """Seed an umbrella owing its branch that way, and run one tick."""
        seeded = _support.split_umbrella(owed)
        _support.walk_owner(self, seeded, **teardown)
        return seeded


class UmbrellaCleanupTest(_UmbrellaCleanupCase, unittest.TestCase):
    """An umbrella settles what it owes before it closes, or stays open."""

    def test_it_reclaims_the_owed_branch_and_closes(self) -> None:
        seeded = self._walk(LateResourceState.PENDING)

        self.assertEqual(
            seeded.github.deleted_remote_branches, [_support.SUPERSEDED_BRANCH],
        )
        self.assertTrue(seeded.parent.closed)
        self.assertIn(_support.RESOLVED_STAMP, seeded.github.pinned_data(_support.PARENT_NUMBER))

    def test_it_records_what_the_reclamation_did(self) -> None:
        seeded = self._walk(LateResourceState.PENDING)

        self.assertEqual(
            _support.resource_states(seeded.github), {_support.SUPERSEDED_BRANCH: _support.STATE_RECONCILED},
        )
        reported = [
            record for record in seeded.github.recorded_events
            if record.get("event") == _support.EVENT_LATE_CLEANUP
        ]
        self.assertEqual(len(reported), 1)
        self.assertEqual(reported[0]["outcome"], _support.STATE_RECONCILED)

    def test_a_failed_obligation_is_retried(self) -> None:
        # "Recorded and retried" is the whole contract: the entry names the
        # branch so the retry asks about the same one.
        seeded = self._walk(LateResourceState.FAILED)

        self.assertEqual(
            seeded.github.deleted_remote_branches, [_support.SUPERSEDED_BRANCH],
        )
        self.assertTrue(seeded.parent.closed)

    def test_a_retained_branch_is_still_owed(self) -> None:
        # `retained` is a state the ledger accepts from any writer and this
        # binary never writes for a branch -- there is no condition under
        # which one is kept. Read as neither owed nor settled, it is retried
        # by nothing and reported by nothing, and the umbrella closes over a
        # branch still on the remote.
        seeded = self._walk(LateResourceState.RETAINED)

        self.assertEqual(
            seeded.github.deleted_remote_branches, [_support.SUPERSEDED_BRANCH],
        )
        self.assertTrue(seeded.parent.closed)
        self.assertEqual(
            _support.resource_states(seeded.github), {_support.SUPERSEDED_BRANCH: _support.STATE_RECONCILED},
        )

    def test_a_settled_one_costs_no_second_call(self) -> None:
        seeded = self._walk(LateResourceState.RECONCILED)

        self.assertEqual(seeded.github.deleted_remote_branches, [])
        self.assertTrue(seeded.parent.closed)

    def test_an_umbrella_owing_nothing_is_left(self) -> None:
        # Every umbrella that reached its terminal another way answers the
        # same question without a write.
        github = FakeGitHubClient()
        parent = make_issue(_support.PARENT_NUMBER, label=_support.UMBRELLA)
        github.add_issue(parent)
        github.add_issue(make_issue(_support.CHILD_NUMBER, label=_support.LABEL_DONE))
        github.seed_state(
            _support.PARENT_NUMBER, children=[_support.CHILD_NUMBER], umbrella=True,
        )
        seeded = SeededUmbrella(github=github, parent=parent)

        _support.walk_owner(self, seeded)

        self.assertEqual(seeded.github.deleted_remote_branches, [])
        self.assertTrue(seeded.parent.closed)


class UmbrellaParkedCleanupTest(_UmbrellaCleanupCase, unittest.TestCase):
    """A parent stopped for a human still settles what it owes the remote.

    Both dispositions that park an umbrella CLOSE the child they name -- a
    rejection and a close by hand -- which is exactly the reading the
    reclamation rule takes of a consumer. Nothing else ever revisits an OPEN
    umbrella, so a park that returned before settling would hold a reclaimable
    ref and a superseded branch for as long as the human took to answer.
    """

    def test_a_parked_umbrella_still_frees_the_remote(self) -> None:
        for child_label in (_support.LABEL_REJECTED, _support.LABEL_READY):
            with self.subTest(child_label=child_label):
                seeded, deleted = self._parked(child_label)
                github = seeded.github

                self.assertEqual(deleted.refs, [_support.SNAPSHOT_REF])
                self.assertEqual(
                    github.deleted_remote_branches, [_support.SUPERSEDED_BRANCH],
                )
                self.assertEqual(
                    set(_support.resource_states(github).values()), {_support.STATE_RECONCILED},
                )

    def test_the_park_is_left_exactly_as_it_was(self) -> None:
        # The settlement decides no terminal and takes nothing back: the
        # parent is still stopped for the human, still open, and still on the
        # label that brings the next tick back to it.
        for child_label in (_support.LABEL_REJECTED, _support.LABEL_READY):
            with self.subTest(child_label=child_label):
                seeded, _deleted = self._parked(child_label)
                parked = seeded.github.pinned_data(_support.PARENT_NUMBER)

                self.assertTrue(parked[_PARKED])
                self.assertFalse(seeded.parent.closed)
                self.assertNotIn(_support.RESOLVED_STAMP, parked)
                self.assertEqual(seeded.github.label_history, [])

    def _parked(self, child_label: str):
        """One umbrella tick over a child ended the way a park reads it."""
        seeded = _support.split_umbrella(
            LateResourceState.PENDING,
            snapshot=LateResourceState.RETAINED,
            child_label=child_label,
            owner=OwnerSeed(child_closed=True),
        )
        deleted = RecordedDelete(SnapshotOutcome.DELETED)
        with deleted.answering():
            _support.walk_owner(self, seeded)
        return seeded, deleted


class UmbrellaCleanupRefusalTest(_UmbrellaCleanupCase, unittest.TestCase):
    """What a reclamation that did not finish costs the terminal."""

    def test_a_refusal_holds_the_umbrella_open(self) -> None:
        # Closing here would leave an obligation nobody ever settles: nothing
        # revisits a closed umbrella, and no other tick reads this ledger.
        seeded = _support.split_umbrella(LateResourceState.PENDING)
        seeded.github._pull_state._delete_remote_branch_returns_ok = False

        with self.assertLogs(_support.WORKFLOW_LOG, level=_WARNING):
            teardown = _support.walk_owner(self, seeded)

        self.assertFalse(seeded.parent.closed)
        self.assertNotIn(_support.RESOLVED_STAMP, seeded.github.pinned_data(_support.PARENT_NUMBER))
        self.assertEqual(
            _support.resource_states(seeded.github), {_support.SUPERSEDED_BRANCH: _support.STATE_FAILED},
        )
        self.assertTrue(teardown.attempted)

    def test_a_refusal_tears_the_local_surfaces_down(self) -> None:
        # The local half needs nothing from the remote, and a remote that
        # refuses is a permission or ruleset problem only a human can clear.
        # Skipping the teardown until then leaves a checkout on a superseded
        # branch that the per-tick base refresh goes on merging into for as
        # long as the refusal lasts -- and the ledger cannot show it, because
        # the entry reads `failed` either way.
        seeded = _support.split_umbrella(LateResourceState.PENDING)

        with refusing(seeded.github, "delete_remote_branch"), self.assertLogs(_support.WORKFLOW_LOG, level=_ERROR):
            teardown = _support.walk_owner(self, seeded)

        self.assertEqual(teardown.issues, [_support.PARENT_NUMBER])
        self.assertEqual(
            teardown.branch_deleted.call_args.args[1:],
            (_support.PARENT_NUMBER, _support.SUPERSEDED_BRANCH),
        )
        self.assertFalse(seeded.parent.closed)

    def test_a_retained_branch_that_stays_holds_it(self) -> None:
        # The other half: owed means owed, so a delete that does not land on
        # one of these holds the terminal exactly as it does on a `pending`.
        seeded = _support.split_umbrella(LateResourceState.RETAINED)
        seeded.github._pull_state._delete_remote_branch_returns_ok = False

        with self.assertLogs(_support.WORKFLOW_LOG, level=_WARNING):
            teardown = _support.walk_owner(self, seeded)

        self.assertFalse(seeded.parent.closed)
        self.assertEqual(
            _support.resource_states(seeded.github), {_support.SUPERSEDED_BRANCH: _support.STATE_FAILED},
        )
        self.assertTrue(teardown.attempted)

    def test_a_checkout_that_stays_holds_the_terminal(self) -> None:
        # A remote delete that succeeded beside a checkout that would not come
        # down is not a settled obligation.
        with self.assertLogs(_support.WORKFLOW_LOG, level=_WARNING):
            seeded = self._walk(
                LateResourceState.PENDING, local_gone=False,
            )

        self.assertFalse(seeded.parent.closed)
        self.assertEqual(
            _support.resource_states(seeded.github), {_support.SUPERSEDED_BRANCH: _support.STATE_FAILED},
        )

    def test_a_local_teardown_that_lands_later_closes(self) -> None:
        # "Recorded and retried" over the WHOLE ordinary cleanup, not just its
        # remote half: the entry stays owed until every surface is gone.
        seeded = _support.split_umbrella(LateResourceState.PENDING)
        with self.assertLogs(_support.WORKFLOW_LOG, level=_WARNING):
            _support.walk_owner(self, seeded, local_gone=False)

        _support.walk_owner(self, seeded)

        self.assertTrue(seeded.parent.closed)
        self.assertEqual(
            _support.resource_states(seeded.github), {_support.SUPERSEDED_BRANCH: _support.STATE_RECONCILED},
        )

    def test_a_foreign_branch_is_never_deleted(self) -> None:
        # The target comes off a ledger a human can edit and is spent on a
        # destructive call, so a hand-edited entry naming an unprotected
        # branch must delete nothing -- and must not let the umbrella close
        # over an obligation nobody settled.
        for foreign in (_MAIN, _ANOTHER_ISSUE, _NOT_OURS, _ANOTHER_REPOSITORY):
            with self.subTest(branch=foreign):
                seeded = _support.split_umbrella(
                    LateResourceState.PENDING, branch=foreign,
                )

                with self.assertLogs(_support.WORKFLOW_LOG, level=_ERROR):
                    _support.walk_owner(self, seeded)

                self.assertEqual(seeded.github.deleted_remote_branches, [])
                self.assertFalse(seeded.parent.closed)
                self.assertEqual(
                    _support.resource_states(seeded.github), {foreign: _support.STATE_FAILED},
                )


if __name__ == "__main__":
    unittest.main()
