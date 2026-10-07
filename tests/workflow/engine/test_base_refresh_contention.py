# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A worktree whose issue another writer holds, on every route its sync can take.

The sync takes the issue's writer claim before it reads the issue, on the key
every dispatch path takes it on, so another poller's dispatch or refresh holding
it costs this tick every read, git command, and write the route would have made
-- and nothing else -- and the sync after it is let go runs the route whole.
Held by this sync, the claim stays held until the route ends. Real competing
processes over a real repository are pinned in
`tests/git/base_sync/test_recovery_refresh_real_git.py`.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.workflow.engine import base_refresh, issue_processing as _issue_processing
from tests.git.base_sync import refresh_test_support as support
from tests.git.base_sync.clean_assertions import (
    _assert_clean_events,
    _assert_clean_publication,
    _assert_clean_state_comments,
)
from tests.git.base_sync.refresh_scenarios import (
    PUSH_PATCH,
    REBASE_PATCH,
    _clean_rebase_scenario,
    _landed_recovery_scenario,
    _scenario,
)
from tests.git.base_sync.report_debt_test_support import stands_on
from tests.git.base_sync.sync_test_support import _git_result
from tests.support.writer_claims import claimable, held_elsewhere, unusable_namespace

ISSUE = support.ISSUE

# The hardened-git double a reset runs through, and the reset it makes.
HARDENED_PATCH = "hardened"
_RESET_TO_THE_ANCHOR = (support.RESET_COMMAND, support.HARD_RESET_FLAG, support.BEFORE_SHA)

RELABEL_ONLY = "crash_recovery_relabel_only"

# Another issue of the same repository, and the same issue number in another
# repository: neither shares this issue's claim.
OTHER_ISSUE = 8
OTHER_REPO_ID = 2


class _ContendedSyncCase(support._SyncWorktreeWithBaseFixture, unittest.TestCase):
    """One sync while another poller holds the issue, and the sync after it lets go."""

    def _held_then_released(self, scenario) -> None:
        """Sync while another poller holds the issue, then once it lets go."""
        record = self.gh.pinned_data(ISSUE)
        reads = MagicMock(wraps=self.gh.get_issue)
        with held_elsewhere(self.gh.repo_id, ISSUE), patch.object(self.gh, "get_issue", reads):
            scenario.run(self)

        reads.assert_not_called()
        self._assert_untouched(scenario, record)
        scenario.run(self)

    def _assert_untouched(self, scenario, record: dict) -> None:
        """No git command run, and nothing written on GitHub."""
        for name, double in scenario.patches.items():
            self.assertFalse(double.called, f"{name} ran")
        self.assertEqual(self.gh.pinned_data(ISSUE), record)
        self.assertEqual(self.gh.write_state_calls, 0)
        written = (self.gh.label_history, self.gh.posted_comments, self.gh.posted_pr_comments)
        self.assertEqual(written, ([], [], []))
        self.assertEqual(self.gh.recorded_events, [])


class HeldRouteTest(_ContendedSyncCase):
    """Each route waits out the holder, and runs whole once it is let go."""

    def test_a_held_pre_pr_rebase_waits(self) -> None:
        scenario = _scenario(
            dirty=MagicMock(return_value=[]),
            git=MagicMock(return_value=_git_result(stdout=support.TWO_BEHIND_STDOUT)),
            rebase=MagicMock(return_value=(True, [])),
        )

        self._held_then_released(scenario)

        scenario[REBASE_PATCH].assert_called_once()

    def test_a_held_pr_rebase_waits(self) -> None:
        self._seed_pr_issue(review_round=3)
        scenario = _clean_rebase_scenario(support.THREE_BEHIND_STDOUT)

        self._held_then_released(scenario)

        _assert_clean_publication(self, self, scenario)
        _assert_clean_events(self, self)

    def test_a_held_unreadable_checkout_waits(self) -> None:
        self._seed_pr_issue(pending_auto_base_rebase_push_sha=support.BEFORE_SHA)
        scenario = _scenario(
            dirty=MagicMock(return_value=[]),
            git=MagicMock(return_value=_git_result(returncode=support.GIT_FAILURE_EXIT_CODE)),
            hardened=MagicMock(return_value=_git_result()),
        )

        self._held_then_released(scenario)

        resets = [
            recorded.args[:3] for recorded in scenario[HARDENED_PATCH].call_args_list
            if recorded.args[:3] == _RESET_TO_THE_ANCHOR
        ]
        self.assertEqual(resets, [_RESET_TO_THE_ANCHOR])
        pinned = self.gh.pinned_data(ISSUE)
        self.assertIsNone(pinned.get(support.KEY_PENDING_PUSH_SHA))
        self.assertEqual(pinned.get(support.KEY_PARK_REASON), support.PARK_PUSH_FAILED)

    def test_a_held_recovery_finishes_once(self) -> None:
        # The landing an interrupted attempt left is finished by the refresh
        # that holds the issue, and by no refresh after it.
        self._seed_pr_issue(**support._pending_attempt(support.REBASED_SHA), review_round=3)
        stands_on(self.gh, support.REBASED_SHA)
        scenario = _landed_recovery_scenario(support.REBASED_SHA)

        self._held_then_released(scenario)
        scenario.run(self)

        scenario[PUSH_PATCH].assert_not_called()
        self.assertEqual(self.gh.label_history, [(ISSUE, support.LABEL_VALIDATING)])
        self.assertEqual(len(self.gh.posted_pr_comments), 1)
        finishes = [
            event.get(support.METHOD_FIELD) for event in self.gh.recorded_events
            if event.get(support.EVENT_FIELD) == support.EVENT_BASE_REBASED
        ]
        self.assertEqual(finishes, [RELABEL_ONLY])
        self.assertIsNone(self.gh.pinned_data(ISSUE).get(support.KEY_PENDING_PUSH_SHA))


class ClaimScopeTest(_ContendedSyncCase):
    """What the claim covers: this issue's key, a namespace that works, and the whole route."""

    def test_another_key_held_leaves_this_one_free(self) -> None:
        # A claim on another issue of this repository, or on this number in
        # another repository, does not hold this one.
        self._seed_pr_issue(review_round=3)
        scenario = _clean_rebase_scenario(support.THREE_BEHIND_STDOUT)

        with held_elsewhere(self.gh.repo_id, OTHER_ISSUE), held_elsewhere(OTHER_REPO_ID, ISSUE):
            scenario.run(self)

        _assert_clean_publication(self, self, scenario)

    def test_an_unusable_namespace_withholds_the_sync(self) -> None:
        # A claim nobody can take says nothing about another holder, and the
        # issue is withheld rather than rewritten uncoordinated.
        self._seed_pr_issue(review_round=3)
        record = self.gh.pinned_data(ISSUE)
        scenario = _clean_rebase_scenario(support.THREE_BEHIND_STDOUT)

        with unusable_namespace(), self.assertLogs("orchestrator.scheduler", level="WARNING"):
            scenario.run(self)

        self._assert_untouched(scenario, record)

    def test_the_route_keeps_the_claim_to_its_end(self) -> None:
        # Mid-push, another poller's refresh and its dispatch seam each meet
        # the hold and do nothing: one push, one notice, one relabel.
        self._seed_pr_issue(review_round=3)
        scenario = _clean_rebase_scenario(support.THREE_BEHIND_STDOUT)
        rivals = _RivalPollers(self)
        scenario[PUSH_PATCH].side_effect = rivals

        scenario.run(self)

        self.assertEqual(rivals.met, [(False, 0)], "neither rival got in, and the refresh read nothing")
        _assert_clean_publication(self, self, scenario)
        _assert_clean_state_comments(self, self)
        self.assertTrue(claimable(self.gh.repo_id, ISSUE), "and the claim goes with the route")


class _RivalPollers:
    """A push that has another poller's refresh and dispatch ask for the issue while it runs.

    What each met is kept: whether the dispatch seam was granted the claim,
    and how many issue reads the refresh made. The push then lands.
    """

    def __init__(self, fixture: support._SyncWorktreeWithBaseFixture) -> None:
        self._fixture = fixture
        self.met: list[tuple[bool, int]] = []

    def __call__(self, *_args, **_kwargs) -> bool:
        fixture = self._fixture
        reads = MagicMock(wraps=fixture.gh.get_issue)
        with patch.object(fixture.gh, "get_issue", reads):
            base_refresh._sync_worktree_with_base(fixture.gh, fixture.spec, fixture.wt, ISSUE)
        with _issue_processing._writer_claim(fixture.gh, fixture.spec, ISSUE) as dispatched:
            self.met.append((dispatched, reads.call_count))
        return True


if __name__ == "__main__":
    unittest.main()
