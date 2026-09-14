# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A tick whose base refresh could not reach an interrupted rebase.

The refresh answers a pinned auto-rebase anchor ahead of every handler, but a
base fetch that failed or a pull request that would not read returns before
its recovery runs. What is left for the dispatcher is an issue standing on a
replay no push published, with a handler about to spawn an agent over it --
and the boundary pinned here is that the tick stops there -- under a park its
own stage left as well, which the refresh answers the anchor beneath rather
than the handler releasing it -- a checkout that is not on disk is restored
rather than handed to one, and a stage the refresh does not drive is answered
on the refresh's own ineligible road.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator.git import branch_transport
from orchestrator.git.base_sync import pr as _pr, refresh as _refresh
from orchestrator.git.verification import probes as _probes
from orchestrator.git.worktrees import (
    creation as _worktree_creation,
    paths as _worktree_paths,
)
from orchestrator.workflow.engine import dispatch_guards
from tests.support.fakes import FakeGitHubClient, FakePR, FakePRRef, make_issue
from tests.workflow.fixtures import _FAKE_WT, _TEST_SPEC

ISSUE = 7

PR_NUMBER = 42

ANCHOR = "be40e5ba" * 5

ANCHOR_KEY = "pending_auto_base_rebase_push_sha"

VALIDATING = "workflow:validating"

# Stages the refresh does not drive, which an operator can relabel onto: one it
# walks, and the two read-only ones it skips without answering anything.
RESOLVING = "workflow:resolving_conflict"
QUESTION = "question"
DISCUSSION = "discussion"

# A commit the interrupted rebase left the checkout on, off the anchor.
REPLAY = "5e71ab1e" * 5

PARK_FAILED = "auto_base_rebase_failed"

# The refresh's own read of the pull request, failing the way a transient
# GitHub error does.
_UNREADABLE_PR = RuntimeError("502 from GitHub")

# The pre-tick base fetch failing, which returns the refresh before it walks a
# single worktree.
GIT_FAILURE_EXIT_CODE = 128

_FAILED_BASE_FETCH = MagicMock(
    returncode=GIT_FAILURE_EXIT_CODE, stderr="could not resolve host",
)

# The pull request branch fetch a recovery takes before it reads the head.
_FETCHED_BRANCH = MagicMock(returncode=0, stderr="")

# A park its own stage left, which only that stage's handler takes down.
STAGE_PARK = "review_cap"

# That park, and the two that freeze a branch on a commit its stage still owes.
_STAGE_PARKS = (STAGE_PARK, "agent_timeout", "late_measurement_failed")


def _walks(gh: FakeGitHubClient, checkout: Path) -> None:
    """One refresh pass over this checkout, its pull request open and current.

    Through the walk's own selection rather than the PR sync behind it, since
    whether a park freezes the walk out is part of what is being asked.
    """
    gh.add_pr(FakePR(
        number=PR_NUMBER,
        head_branch="orchestrator/acme__widget/issue-7",
        head=FakePRRef(sha=ANCHOR),
    ))
    with patch.object(
        branch_transport, "_authed_fetch", return_value=_FETCHED_BRANCH,
    ), patch.object(_refresh, "_worktree_behind_base", return_value=0):
        _refresh._sync_worktree_with_base(gh, _TEST_SPEC, checkout, ISSUE)


class _InterruptedRebaseCase(unittest.TestCase):
    """A `validating` issue whose rebase died before its grant or its push.

    The attempt pinned its anchor and the terms it was made under, and got no
    further than that: no permission, no debt, no generation -- nothing the
    dispatcher's reconciliation would ever stop a tick for on its own. Its
    checkout is on disk and standing on a commit this store holds.
    """

    def setUp(self) -> None:
        self._opens(VALIDATING)
        self.checkout = Path(self.enterContext(
            tempfile.TemporaryDirectory(prefix="orch-dispatch-recovery-"),
        ))
        self.head = MagicMock(return_value=ANCHOR)
        for name, probe in (
            ("_head_sha", self.head),
            ("_commit_present", MagicMock(return_value=True)),
        ):
            patcher = patch.object(_probes, name, probe)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _opens(self, label) -> None:
        """Start over on an issue under `label`, with nothing pinned yet."""
        self.gh = FakeGitHubClient()
        self.issue = make_issue(ISSUE, label=str(label))
        self.gh.add_issue(self.issue)

    def _seed(self, **pinned) -> None:
        self.gh.seed_state(
            ISSUE,
            pr_number=PR_NUMBER,
            branch="orchestrator/acme__widget/issue-7",
            pending_auto_base_rebase_push_sha=ANCHOR,
            pending_auto_base_rebase_rewrite_pr=PR_NUMBER,
            pending_auto_base_rebase_rewrite_stage=str(VALIDATING),
            **pinned,
        )

    def _refreshes_with_an_unreadable_pr(self) -> None:
        """The refresh pass that returns before its recovery can run."""
        with patch.object(self.gh, "get_pr", side_effect=_UNREADABLE_PR):
            _pr._sync_pr_worktree_to_base(
                self.gh, _TEST_SPEC, self.issue,
                self.gh.read_pinned_state(self.issue), _FAKE_WT, PR_NUMBER, 0,
            )

    def _refreshes_with_a_failed_fetch(self) -> None:
        """The refresh pass that returns before it walks any worktree."""
        with patch.object(
            branch_transport, "_authed_target_fetch",
            return_value=_FAILED_BASE_FETCH,
        ):
            _refresh._refresh_base_and_worktrees(self.gh, _TEST_SPEC)

    def _strands_twice(self, label) -> MagicMock:
        """Stop two ticks over a missing checkout, handing back its restore."""
        restore = MagicMock()
        gone = self.checkout / "gone"
        with patch.object(_worktree_creation, "_ensure_pr_worktree", restore):
            self.assertTrue(self._stops(gone, label))
            self.assertTrue(self._stops(gone, label))
        return restore

    def _stops(
        self, checkout: Path | None = None, label=VALIDATING,
    ) -> bool:
        """Whether the dispatcher stops this tick short of its handler."""
        with patch.object(
            _worktree_paths, "_worktree_path",
            MagicMock(return_value=checkout or self.checkout),
        ):
            return dispatch_guards._record_stops_the_tick(
                self.gh, _TEST_SPEC, self.issue, label,
                self.gh.read_pinned_state(self.issue),
            )


class DeferredRecoveryTest(_InterruptedRebaseCase):
    """The tick the refresh could not finish is not handed to a reviewer."""

    def test_an_unanswered_anchor_stops_the_tick(self) -> None:
        self._seed()
        self._refreshes_with_an_unreadable_pr()

        # The refresh left the anchor exactly where the crash did...
        pinned = self.gh.pinned_data(ISSUE)
        self.assertEqual(pinned.get(ANCHOR_KEY), ANCHOR)
        # ...and the dispatcher defers to it rather than spawning the
        # reviewer over a replay no push has published.
        self.assertTrue(self._stops())

    def test_without_one_the_handler_runs(self) -> None:
        # What says the stop above is the anchor's and nothing else's.
        self.gh.seed_state(ISSUE, pr_number=PR_NUMBER)

        self.assertFalse(self._stops())

    def test_a_stage_park_waits_for_the_refresh(self) -> None:
        # Each handler would take its park down and run on into its agent --
        # a widened cap, a timed-out run retried, a reading taken again -- so
        # the tick holds. Nor does the park freeze the refresh's walk out, the
        # two that freeze a branch on a stage's own commit included: it answers
        # the anchor alone -- here an attempt that never started -- and leaves
        # the park where the stage put it.
        for park_reason in _STAGE_PARKS:
            with self.subTest(park_reason=park_reason):
                self._opens(VALIDATING)
                self._seed(awaiting_human=True, park_reason=park_reason)
                self.assertTrue(self._stops())

                _walks(self.gh, self.checkout)

                pinned = self.gh.pinned_data(ISSUE)
                self.assertIsNone(pinned.get(ANCHOR_KEY))
                self.assertEqual(pinned.get("park_reason"), park_reason)

    def test_an_absent_checkout_is_held_and_restored(self) -> None:
        # The refresh walks only the checkouts on disk, and the handler would
        # rebuild this one onto the unpublished replay -- so the tick holds and
        # the dispatcher restores it for the next refresh to walk.
        self._seed()
        restore = MagicMock()

        with patch.object(_worktree_creation, "_ensure_pr_worktree", restore):
            self.assertTrue(self._stops(self.checkout / "gone"))

        restore.assert_called_once()
        self.assertEqual(restore.call_args.args[1], ISSUE)

    def test_a_relabelled_missing_checkout_strands(self) -> None:
        # Relabelled off the refreshed stages with no checkout on disk -- onto
        # a read-only stage the refresh skips outright, too -- the ineligible
        # road is as unreachable as the recovery, so the dispatcher takes that
        # road's answer itself, once, and the handler for the new stage never
        # rebuilds the checkout onto the replay.
        for label in (RESOLVING, QUESTION, DISCUSSION):
            with self.subTest(label=label):
                self._opens(label)
                self._seed()

                self._strands_twice(label).assert_not_called()

                pinned = self.gh.pinned_data(ISSUE)
                self.assertEqual(pinned.get(ANCHOR_KEY), ANCHOR)
                self.assertTrue(pinned.get("awaiting_human"))
                self.assertEqual(pinned.get("park_reason"), PARK_FAILED)
                self.assertEqual(len(self.gh.posted_comments), 1)

    def test_a_failed_fetch_holds_a_relabelled_replay(self) -> None:
        # The base fetch failed, so the refresh walked nothing and the anchor a
        # relabel moved off the refreshed stages is where the crash left it.
        # The dispatcher takes the refresh's ineligible road itself: a checkout
        # still on the anchor strands nothing and is cleared, and one standing
        # on a replay parks with every record kept.
        for head, anchor, parked in ((ANCHOR, None, False), (REPLAY, ANCHOR, True)):
            with self.subTest(parked=parked):
                self._opens(RESOLVING)
                self._seed()
                self.head.return_value = head
                self._refreshes_with_a_failed_fetch()
                self.assertEqual(self.gh.pinned_data(ISSUE)[ANCHOR_KEY], ANCHOR)

                self.assertTrue(self._stops(label=RESOLVING))

                pinned = self.gh.pinned_data(ISSUE)
                self.assertEqual(pinned.get(ANCHOR_KEY), anchor)
                self.assertIs(bool(pinned.get("awaiting_human")), parked)

    def test_a_restore_that_fails_still_holds(self) -> None:
        # The next tick tries again; this one still runs no handler.
        self._seed()
        refused = MagicMock(side_effect=RuntimeError("worktree add failed"))

        with patch.object(
            _worktree_creation, "_ensure_pr_worktree", refused,
        ), self.assertLogs("orchestrator.base_sync", level="ERROR"):
            self.assertTrue(self._stops(self.checkout / "gone"))


if __name__ == "__main__":
    unittest.main()
