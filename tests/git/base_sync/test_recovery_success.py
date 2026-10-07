# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The three ways an interrupted auto-rebase reaches `validating` again.

Each owes the head it lands the report debt a clean finish records, and none
may reach the route with it unrecorded -- nor lose it to a base that moved
again under the recovery.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from tests.git.base_sync.refresh_scenarios import (
    PUSH_PATCH,
    REBASE_PATCH,
    _clean_rebase_scenario,
    _landed_recovery_scenario,
    _scenario,
)
from tests.git.base_sync.refresh_test_support import (
    AFTER_SHA,
    NEW_REBASED_SHA,
    REBASED_SHA,
    _diverged,
    _git_result,
    _pending_attempt,
    _RemoteHeadGit,
    _SyncWorktreeWithBaseFixture,
)
from tests.git.base_sync.report_debt_test_support import (
    EARLIER_SHA,
    FOREIGN_SHA,
    KEY_REWRITE_DEBT,
    DurableAtTheRelabel,
    owed,
    refreshes,
    settles_a_report_of,
    stands_on,
)
from tests.support.fakes import FakeGitHubClient, FakePRRef

ISSUE = 7

# Worktree HEAD SHAs threaded through the rebase / push / recovery flows.
# The post-rebase and recovered heads come off the shared fixture, where they
# are the commit the size gate proves the checkout to.
BEFORE_SHA = "be40e5ba" * 5

LABEL_VALIDATING = "workflow:validating"

EVENT_BASE_REBASED = "base_rebased"

KEY_PENDING_PUSH_SHA = "pending_auto_base_rebase_push_sha"
KEY_REVIEW_ROUND = "review_round"
KEY_PARK_REASON = "park_reason"

PARK_PUSH_FAILED = "auto_base_rebase_push_failed"

TWO_BEHIND_STDOUT = "2\n"
UP_TO_DATE_STDOUT = "0\n"
FORCE_WITH_LEASE_KWARG = "force_with_lease"
EVENT_FIELD = "event"
SHA_FIELD = "sha"
METHOD_FIELD = "method"

# The mark a finish leaves between its announcement and its clear.
KEY_ANNOUNCED_SHA = "pending_auto_base_rebase_announced_sha"

DIED = "the process died before the tick returned"


class CrashRecoverySuccessUnitTest(_SyncWorktreeWithBaseFixture, unittest.TestCase):
    def test_pr_crash_recovery_pushes_unpushed_rebase(self) -> None:
        self._seed_pr_issue(
            pending_auto_base_rebase_push_sha=BEFORE_SHA,
        )
        self._add_pr()
        scenario = _scenario(
            dirty=MagicMock(return_value=[]),
            rebase=MagicMock(),
            head_sha=MagicMock(return_value=REBASED_SHA),
            ahead_behind=MagicMock(return_value=_diverged(1, 0)),
            fetch=MagicMock(return_value=_git_result()),
            push=MagicMock(return_value=True),
            git=MagicMock(
                return_value=_git_result(stdout=UP_TO_DATE_STDOUT),
            ),
            hardened=MagicMock(side_effect=_RemoteHeadGit(BEFORE_SHA)),
        )

        scenario.run(self)

        scenario[PUSH_PATCH].assert_called_once()
        self.assertEqual(
            scenario[PUSH_PATCH].call_args.kwargs.get(FORCE_WITH_LEASE_KWARG),
            BEFORE_SHA,
        )
        scenario[REBASE_PATCH].assert_not_called()
        self._assert_finished_owing(REBASED_SHA)
        self._assert_recovery_event(
            "crash_recovery_pushed",
            expected_sha=REBASED_SHA,
        )

    def test_crash_recovery_finishes_landed_push(self) -> None:
        self._seed_pr_issue(**_pending_attempt(REBASED_SHA), review_round=3)
        # The dead tick's push landed and its answer never came back: the pull
        # request already stands on the rebased head the recovery observes.
        self._add_pr(head=FakePRRef(sha=REBASED_SHA))
        scenario = _scenario(
            dirty=MagicMock(return_value=[]),
            rebase=MagicMock(),
            head_sha=MagicMock(return_value=REBASED_SHA),
            ahead_behind=MagicMock(return_value=_diverged(0, 0)),
            fetch=MagicMock(return_value=_git_result()),
            push=MagicMock(),
            git=MagicMock(
                return_value=_git_result(stdout=UP_TO_DATE_STDOUT),
            ),
            hardened=MagicMock(side_effect=_RemoteHeadGit(REBASED_SHA)),
        )

        scenario.run(self)

        scenario[PUSH_PATCH].assert_not_called()
        scenario[REBASE_PATCH].assert_not_called()
        self._assert_finished_owing(REBASED_SHA)
        self._assert_recovery_event("crash_recovery_relabel_only")

    def test_crash_recovery_clears_same_head_flag(self) -> None:
        self._seed_pr_issue(
            pending_auto_base_rebase_push_sha=BEFORE_SHA,
        )
        self._add_pr()
        scenario = _scenario(
            dirty=MagicMock(return_value=[]),
            rebase=MagicMock(return_value=(True, [])),
            head_sha=MagicMock(
                side_effect=[BEFORE_SHA, BEFORE_SHA, AFTER_SHA],
            ),
            fetch=MagicMock(return_value=_git_result()),
            push=MagicMock(return_value=True),
            git=MagicMock(
                return_value=_git_result(stdout=TWO_BEHIND_STDOUT),
            ),
        )

        scenario.run(self)

        scenario[REBASE_PATCH].assert_called_once()
        scenario[PUSH_PATCH].assert_called_once()
        self._assert_recovery_event("auto_clean_rebase")

    def _assert_finished_owing(self, landed: str) -> None:
        """The round is the reviewer's again, and the head landed is owed its report."""
        durable = self.gh.pinned_data(ISSUE)
        self.assertEqual(
            (durable.get(KEY_REVIEW_ROUND), durable.get(KEY_REWRITE_DEBT)),
            (0, owed(BEFORE_SHA, landed)),
        )

    def _assert_recovery_event(
        self,
        method: str,
        *,
        expected_sha: str | None = None,
    ) -> None:
        self.assertIn((ISSUE, LABEL_VALIDATING), self.gh.label_history)
        state = self.gh.pinned_data(ISSUE)
        self.assertIsNone(state.get(KEY_PENDING_PUSH_SHA))
        events = []
        for event in self.gh.recorded_events:
            if event.get(EVENT_FIELD) == EVENT_BASE_REBASED:
                events.append(event)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].get(METHOD_FIELD), method)
        if expected_sha is not None:
            self.assertEqual(events[0].get(SHA_FIELD), expected_sha)


class _InterruptedFinishFixture(_SyncWorktreeWithBaseFixture):
    """A clean rebase over a settled report of its anchor, lost past its push, and the tick after it."""

    def _reported_before_the_rebase(self, **state) -> None:
        """Seed the issue afresh, its pull request on the anchor and its report of it settled."""
        self.gh = FakeGitHubClient()
        self._seed_pr_issue(**state)
        settles_a_report_of(self.gh, BEFORE_SHA)

    def _resumes(self, landed: str) -> None:
        """Run the next tick over a pull request standing on `landed`, and hold it to the finish.

        The relabel is where the reviewer is routed, so what is durable when it
        comes is what a process lost in it leaves: the debt, and the anchor
        that brings that tick back.
        """
        stands_on(self.gh, landed)
        relabel = DurableAtTheRelabel(self.gh)

        with patch.object(self.gh, "set_workflow_label", relabel):
            _landed_recovery_scenario(landed).run(self)

        self.assertEqual(
            [(seen.get(KEY_REWRITE_DEBT), seen.get(KEY_PENDING_PUSH_SHA)) for seen in relabel.seen],
            [(owed(BEFORE_SHA, landed), BEFORE_SHA)],
        )
        durable = self.gh.pinned_data(ISSUE)
        self.assertIsNone(durable.get(KEY_PENDING_PUSH_SHA))
        self.assertEqual(durable[KEY_REWRITE_DEBT], owed(BEFORE_SHA, landed))
        self.assertTrue(refreshes(durable, landed))
        self.assertEqual(self.gh.workflow_label(self.gh._issues[ISSUE]), LABEL_VALIDATING)

    def _crashes_before_the_mark(self):
        # The mark lands through the guarded edit of the pinned comment, the
        # first the finish makes past its notice and its event.
        return patch.object(self.gh, "edit_pinned_state", MagicMock(side_effect=RuntimeError(DIED)))

    def _crashes_at_the_relabel(self):
        return patch.object(self.gh, "set_workflow_label", MagicMock(side_effect=RuntimeError(DIED)))


class InterruptedFinishReportDebtUnitTest(_InterruptedFinishFixture, unittest.TestCase):
    """A clean finish lost past its push comes back owing the head it landed.

    The settled report is about the head the push replaced. Whichever window
    the process was lost in, the next tick makes the debt for the landed head
    durable before it relabels, and the validating refresh asks about it.
    """

    def test_each_lost_finish_resumes_into_its_debt(self) -> None:
        for window, crash, durable_debt in (
            # The notice and the event went out and nothing recorded them: the
            # debt was staged for the write the process never made.
            ("before the mark", self._crashes_before_the_mark, None),
            # The mark's write carried the debt, so the relabel that was lost
            # leaves it durable beside the anchor that brings the tick back.
            ("at the relabel", self._crashes_at_the_relabel, owed(BEFORE_SHA, AFTER_SHA)),
        ):
            with self.subTest(window):
                self._reported_before_the_rebase()
                with crash(), self.assertRaises(RuntimeError):
                    _clean_rebase_scenario().run(self)
                self.assertEqual(
                    self.gh.pinned_data(ISSUE).get(KEY_REWRITE_DEBT), durable_debt,
                )

                self._resumes(AFTER_SHA)

    def test_a_bare_earlier_mark_is_owed_its_debt(self) -> None:
        # Announced by a finish that recorded no debt beside its mark: the
        # route that finish still owes writes it while the anchor stands and
        # before its relabel, so a relabel lost there comes back owing it.
        self._reported_before_the_rebase(
            **_pending_attempt(AFTER_SHA), **{KEY_ANNOUNCED_SHA: AFTER_SHA},
        )

        self._resumes(AFTER_SHA)

    def test_a_further_advance_owes_the_latest_head(self) -> None:
        # The recovery finishes the head the dead tick landed and finds the
        # base has moved again, so the same tick rebases that head and
        # publishes the next: the debt keeps the head the settled report is
        # about and names the last head pushed, which the refresh asks about.
        self._reported_before_the_rebase(**_pending_attempt(NEW_REBASED_SHA))
        stands_on(self.gh, NEW_REBASED_SHA)
        scenario = _landed_recovery_scenario(NEW_REBASED_SHA, TWO_BEHIND_STDOUT)

        scenario.run(self)

        self.assertEqual(
            scenario[PUSH_PATCH].call_args.kwargs.get(FORCE_WITH_LEASE_KWARG),
            NEW_REBASED_SHA,
        )
        durable = self.gh.pinned_data(ISSUE)
        self.assertEqual(durable[KEY_REWRITE_DEBT], owed(BEFORE_SHA, AFTER_SHA))
        self.assertTrue(refreshes(durable, AFTER_SHA))
        self.assertIn((ISSUE, LABEL_VALIDATING), self.gh.label_history)


class ForeignUpdateReportDebtUnitTest(_InterruptedFinishFixture, unittest.TestCase):
    """A lost finish whose pull request somebody moved while the process was down claims nothing."""

    def test_a_push_over_the_landing_claims_nothing(self) -> None:
        # The push landed and the process was lost before its mark; somebody
        # then pushed the pull request onto a head of their own. The recovery
        # puts the checkout back on the anchor and parks rather than finish a
        # route the pull request no longer carries: neither the head it landed
        # nor theirs is claimed, and the debt already standing is kept.
        standing = owed(EARLIER_SHA, BEFORE_SHA)
        self._reported_before_the_rebase(**{KEY_REWRITE_DEBT: standing})
        with self._crashes_before_the_mark(), self.assertRaises(RuntimeError):
            _clean_rebase_scenario().run(self)
        stands_on(self.gh, FOREIGN_SHA)

        _landed_recovery_scenario(AFTER_SHA, remote=FOREIGN_SHA).run(self)

        durable = self.gh.pinned_data(ISSUE)
        self.assertEqual(
            (durable.get(KEY_REWRITE_DEBT), durable.get(KEY_PARK_REASON)),
            (standing, PARK_PUSH_FAILED),
        )
        self.assertNotIn((ISSUE, LABEL_VALIDATING), self.gh.label_history)

if __name__ == "__main__":
    unittest.main()
