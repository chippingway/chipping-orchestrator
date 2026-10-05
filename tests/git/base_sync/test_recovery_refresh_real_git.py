# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The refresh's own roads into an interrupted rebase, over a real repository.

What the recovery does once it is reached is pinned beside this. What these
pin is how a tick gets there, or holds until it does: a checkout whose branch
names a commit this store cannot read, a base fetch that failed before any
walk, an issue relabelled off the refreshed stages mid-attempt, and an issue
another poller on the host is writing -- through its own dispatch or its own
refresh, each a real second process -- which no road reaches until it is let
go, and which the road that reaches it keeps every other poller off of.
"""
from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from orchestrator.git import branch_transport
from orchestrator.git.base_sync import recovery_holds, refresh
from tests.git.base_sync import recovery_git_support as fixtures
from tests.git.base_sync.vouched_replay_git_support import (
    VouchedReplayGitFixtureMixin,
)
from tests.support import writer_claim_processes as _processes
from tests.support.writer_claims import claimable

# A stage the refresh does not drive, which an operator can relabel onto.
RESOLVING = "workflow:resolving_conflict"

# A commit id no object in this repository answers to.
MISSING_COMMIT = "dead" * 10

# The pre-tick base fetch failing, which returns the refresh before it walks a
# single worktree.
GIT_FAILURE_EXIT_CODE = 128

_FAILED_BASE_FETCH = subprocess.CompletedProcess(
    args=["git"], returncode=GIT_FAILURE_EXIT_CODE, stdout="",
    stderr="could not resolve host",
)

# The name another poller polls the repository under. The claim is keyed on
# the repository's id, so the name is only what its skip line would say.
OTHER_POLLER_SLUG = "acme/widget"


class RefreshRecoveryRealGitTest(VouchedReplayGitFixtureMixin, unittest.TestCase):
    """A tick that reaches the recovery, or holds until one does."""

    def test_an_unreadable_checkout_is_parked(self) -> None:
        # The branch names a commit this store does not hold, so the refresh
        # cannot count the lag against base -- and stopping there would leave
        # the anchor for a recovery no tick reaches, under a dispatcher that
        # holds the handler back while it stands. The checkout the attempt
        # left cannot be compared against anything, so it is put back on the
        # anchor and a human is asked.
        self._points_the_branch_at_nothing()

        self._syncs()

        self.assertEqual(self.push.leases, [])
        self._assert_parked_on_the_anchor()
        self.assertFalse(self._holds_dispatch())

    def test_a_failed_refresh_holds_an_unreadable_one(self) -> None:
        # The same checkout on a tick whose base fetch failed: the refresh
        # returned before walking any worktree, so nothing answered the
        # anchor, and the handler this tick still dispatches may not be handed
        # it. Only the park a refresh that does reach it writes lets it go.
        self._points_the_branch_at_nothing()

        with patch.object(
            branch_transport, "_authed_target_fetch",
            return_value=_FAILED_BASE_FETCH,
        ):
            refresh._refresh_base_and_worktrees(self.gh, self.spec)

        self.assertFalse(
            self.gh.pinned_data(fixtures.ISSUE).get(fixtures.KEY_AWAITING_HUMAN),
        )
        self.assertTrue(self._holds_dispatch())

        self._syncs()

        self._assert_parked_on_the_anchor()
        self.assertFalse(self._holds_dispatch())

    def test_a_relabelled_attempt_waits_for_a_reply(self) -> None:
        # Moved off the refreshed stages mid-attempt, the replay is kept and
        # parked. Putting the label back is not the retry: the park is the
        # refresh's own and a reply is what releases it, which is what the
        # notice asks for -- and only then does the recovery finish the push.
        self._syncs(RESOLVING)
        self.assertTrue(any(
            "reply on this issue" in body
            for _, body in self.gh.posted_comments
        ))

        self._syncs(fixtures.LABEL)
        self.assertEqual(self.push.leases, [])
        self.assertEqual(
            self.gh.pinned_data(fixtures.ISSUE)[fixtures.KEY_PENDING_PUSH_SHA],
            self.anchor,
        )

        self.gh.comment(self.issue, "label is back; retry the rebase")
        self._syncs()

        self.assertEqual(self.push.leases, [self.anchor])
        self.assertIn(
            (fixtures.ISSUE, fixtures.VALIDATING), self.gh.label_history,
        )

    def _points_the_branch_at_nothing(self) -> None:
        """Leave the checkout's branch naming a commit this store lacks."""
        branch_ref = self.work / ".git" / "refs" / "heads" / fixtures.BRANCH
        branch_ref.write_text(f"{MISSING_COMMIT}\n")

    def _syncs(self, label: str | None = None) -> None:
        """One refresh pass over this checkout, onto `label` where one is named."""
        if label is not None:
            self.gh.set_workflow_label(self.issue, label)
        refresh._sync_worktree_with_base(
            self.gh, self.spec, self.work, fixtures.ISSUE,
        )

    def _holds_dispatch(self) -> bool:
        """Whether the dispatcher would hold this issue's handler right now."""
        return recovery_holds._recovery_holds_dispatch(
            self.issue, fixtures.LABEL,
            self.gh.read_pinned_state(self.issue), self.work,
        )

    def _assert_parked_on_the_anchor(self) -> None:
        """The reset landed, the anchor went with it, and a human is asked."""
        self.assertEqual(fixtures.head_sha(self.work), self.anchor)
        published = self.gh.pinned_data(fixtures.ISSUE)
        self.assertTrue(published.get(fixtures.KEY_AWAITING_HUMAN))
        self.assertEqual(
            published.get(fixtures.KEY_PARK_REASON), fixtures.PARK_PUSH_FAILED,
        )
        self.assertIsNone(published.get(fixtures.KEY_PENDING_PUSH_SHA))



class ContendedRecoveryRealGitTest(VouchedReplayGitFixtureMixin, unittest.TestCase):
    """An interrupted rebase on an issue another poller is writing, finished once and by one writer."""

    def setUp(self) -> None:
        self.root = _processes.shared_namespace(self)
        super().setUp()

    def test_another_dispatch_holds_the_recovery_back(self) -> None:
        self._waits_for(_processes.DISPATCHING_POLLER, _processes.HELD)

    def test_another_refresh_holds_the_recovery_back(self) -> None:
        # Stopped mid-route, on the issue read its own refresh begins with.
        self._waits_for(_processes.REFRESHING_POLLER, _processes.READ)

    def test_a_recovery_keeps_the_issue_to_its_end(self) -> None:
        # Mid-push, another poller's refresh reads nothing and its dispatch
        # seam is refused; the recovery publishes and routes the replay once,
        # and gives the claim back with the route.
        contended = _ContendedPush(self)

        with patch.object(branch_transport, fixtures.PUSH_BRANCH, contended):
            self._syncs()

        self.assertEqual(contended.met, [_processes.UNTOUCHED, _processes.REFUSED])
        self._assert_finished_once()
        self.assertTrue(claimable(self.gh.repo_id, fixtures.ISSUE))

    def _waits_for(self, program: str, holding: str) -> None:
        """Sync while another poller's `program` holds the issue, then twice once it lets go.

        The held sync touches nothing. The first one after finishes the
        attempt, which the second does not finish again.
        """
        record = self.gh.pinned_data(fixtures.ISSUE)
        other = _elsewhere(self, program)
        self.assertEqual(other.said(), holding)

        self._syncs()

        _assert_untouched(self, record)
        self.assertEqual(other.let_go(), 0)
        self._syncs()
        self._syncs()
        self._assert_finished_once()

    def _syncs(self) -> None:
        """One refresh pass over this checkout."""
        refresh._sync_worktree_with_base(
            self.gh, self.spec, self.work, fixtures.ISSUE,
        )

    def _assert_finished_once(self) -> None:
        """The replay pushed, announced, and routed once, its anchor gone."""
        self.assertEqual(self.push.leases, [self.anchor])
        published = fixtures.head_sha(self.remote, fixtures.BRANCH_REF)
        self.assertEqual(published, self.recovered)
        self.assertEqual(self.gh.label_history, [(fixtures.ISSUE, fixtures.VALIDATING)])
        self.assertEqual(len(self.gh.posted_pr_comments), 1)
        self.assertEqual(len(self.rebase_events()), 1)
        self.assertIsNone(self.gh.pinned_data(fixtures.ISSUE).get(fixtures.KEY_PENDING_PUSH_SHA))


class _ContendedPush:
    """The recovery's push, with another poller's refresh and dispatch asking for the issue first.

    What each said is kept, and the push then goes out as the fixture's own.
    """

    def __init__(self, case: ContendedRecoveryRealGitTest) -> None:
        self._case = case
        self.met: list[str] = []

    def __call__(self, *args, **kwargs) -> bool:
        refreshing = _elsewhere(self._case, _processes.REFRESHING_POLLER)
        dispatching = _elsewhere(self._case, _processes.DISPATCHING_POLLER)
        self.met.extend((refreshing.said(), dispatching.said()))
        self._case.assertEqual(refreshing.exited(), 0)
        self._case.assertEqual(dispatching.let_go(), 0)
        return self._case.push(*args, **kwargs)


def _elsewhere(case: ContendedRecoveryRealGitTest, program: str) -> _processes.OtherProcess:
    """Run another poller's `program` over the case's issue, in a process of its own."""
    other = _processes.OtherProcess(
        case.root, program, case.gh.repo_id, OTHER_POLLER_SLUG, fixtures.ISSUE,
    )
    case.addCleanup(other.close)
    return other


def _assert_untouched(case: ContendedRecoveryRealGitTest, record: dict) -> None:
    """No push, neither head moved -- the replay unpublished on the checkout -- and nothing written on GitHub."""
    case.assertEqual(case.push.leases, [])
    case.assertEqual(fixtures.head_sha(case.work), case.recovered)
    published = fixtures.head_sha(case.remote, fixtures.BRANCH_REF)
    case.assertEqual(published, case.anchor)
    case.assertEqual(case.gh.pinned_data(fixtures.ISSUE), record)
    written = (case.gh.label_history, case.gh.posted_comments, case.gh.posted_pr_comments)
    case.assertEqual(written, ([], [], []))
    case.assertEqual(case.gh.recorded_events, [])


if __name__ == "__main__":
    unittest.main()
