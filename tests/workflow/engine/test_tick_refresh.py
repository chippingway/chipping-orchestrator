# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The base refresh a tick opens with, stood in for and driven for real."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.workflow.engine import issue_processing as _issue_processing, tick
from tests.git.base_sync.sync_test_support import _git_result
from tests.support.fakes import make_issue
from tests.support.writer_claims import held_elsewhere
from tests.workflow.engine import tick_parallel_test_support as support
from tests.workflow.engine.dispatch_scheduler_workers import patch_base_refresh
from tests.workflow.engine.refresh_checkouts_support import (
    AFTER_SHA,
    ONE_PUBLICATION,
    ROUND_BEFORE,
    Checkouts,
    Walked,
    observed,
    pr_of,
    seed_open_pr,
)
from tests.workflow.engine.writer_claim_test_support import (
    DISPATCH_MODES,
    StandInHandler,
    WriterClaimDispatchCase,
)
from tests.workflow.fixtures import LABEL_IMPLEMENTING, LABEL_IN_REVIEW, LABEL_VALIDATING

# A pull request the refresh publishes a rebase onto, a pre-PR neighbor whose
# checkout it rebases locally, and a pull request another poller is writing.
PUBLISHED = 7
PRE_PR = 8
HELD = 9

_HANDLED_LABELS = (LABEL_IN_REVIEW, LABEL_VALIDATING, LABEL_IMPLEMENTING)

_UNREACHABLE_BASE = 128


class TickInvokesBaseRefreshTest(unittest.TestCase):
    """`tick` must drive `_refresh_base_and_worktrees` before any
    issue is processed -- otherwise an in-flight worktree would still be
    anchored at the base SHA from when it was first added.
    """

    def test_refresh_called_once_before_issues(self) -> None:
        gh = support.FakeGitHubClient()
        gh.add_issue(support.make_issue(1, label=support.LABEL_IMPLEMENTING))
        refresh = MagicMock()
        process = MagicMock()
        with patch_base_refresh(refresh), \
             patch.object(_issue_processing, support.PROCESS_ISSUE, process):
            tick.tick(gh, support._TEST_SPEC)
        refresh.assert_called_once_with(gh, support._TEST_SPEC, scheduler=None)
        process.assert_called_once()

    def test_refresh_error_does_not_block_issues(self) -> None:
        gh = support.FakeGitHubClient()
        gh.add_issue(support.make_issue(1, label=support.LABEL_IMPLEMENTING))
        refresh = MagicMock(side_effect=RuntimeError("fetch boom"))
        process = MagicMock()
        with patch_base_refresh(refresh), \
             patch.object(_issue_processing, support.PROCESS_ISSUE, process):
            tick.tick(gh, support._TEST_SPEC)
        process.assert_called_once()


class RefreshThroughTickTest(WriterClaimDispatchCase):
    """The workflow's refresh under whole ticks, over three checkouts at once.

    Everything under the tick is real but the git the checkouts are read and
    rewritten with, the size gate's reads, and the stage handler, which stands
    in for one that runs and records.
    """

    def test_a_held_issue_waits_its_turn(self) -> None:
        for mode, limit, scheduled in DISPATCH_MODES:
            with self.subTest(mode=mode):
                checkouts = self._seeded()
                self._ticked_while_held(checkouts, limit=limit, scheduled=scheduled)
                self._ticked_once_released(checkouts, limit=limit, scheduled=scheduled)

    def test_a_failed_fetch_walks_no_checkout(self) -> None:
        checkouts = self._seeded()
        checkouts.fetch.return_value = _git_result(returncode=_UNREACHABLE_BASE, stderr="unreachable")

        ran = self._ran(checkouts, limit=1, scheduled=False)

        self.assertEqual(ran, {
            (PUBLISHED, LABEL_IN_REVIEW), (PRE_PR, LABEL_IMPLEMENTING), (HELD, LABEL_IN_REVIEW),
        }, "the dispatch runs every issue all the same")
        self.assertEqual(observed(self.github, checkouts), Walked(
            rounds={PUBLISHED: ROUND_BEFORE, PRE_PR: None, HELD: ROUND_BEFORE},
        ))

    def test_a_raising_sync_costs_only_its_issue(self) -> None:
        checkouts = self._seeded()
        checkouts.failing.add(PRE_PR)

        with self.assertLogs("orchestrator.base_sync", level="ERROR") as logged:
            ran = self._ran(checkouts, limit=1, scheduled=False)
            failures = "\n".join(logged.output)

        self.assertIn(f"issue=#{PRE_PR} base sync failed; continuing", failures)
        self.assertEqual(ran, {
            (PUBLISHED, LABEL_VALIDATING), (PRE_PR, LABEL_IMPLEMENTING), (HELD, LABEL_VALIDATING),
        })
        self.assertEqual(observed(self.github, checkouts), Walked(
            rebased=[PUBLISHED, PRE_PR, HELD],
            published={PUBLISHED: ONE_PUBLICATION, HELD: ONE_PUBLICATION},
            relabelled=[(PUBLISHED, LABEL_VALIDATING), (HELD, LABEL_VALIDATING)],
            noticed=[pr_of(PUBLISHED), pr_of(HELD)],
            announced={PUBLISHED: [AFTER_SHA], HELD: [AFTER_SHA]},
            rounds={PUBLISHED: 0, PRE_PR: None, HELD: 0},
        ))
        self.assertNotIn(PRE_PR, checkouts.carried)

    def _ticked_while_held(self, checkouts: Checkouts, *, limit: int, scheduled: bool) -> None:
        """A tick while another poller holds `HELD`, which reaches only its neighbors."""
        held_record = self.github.pinned_data(HELD)
        with held_elsewhere(self.github.repo_id, HELD):
            ran = self._ran(checkouts, limit=limit, scheduled=scheduled)

        self.assertEqual(ran, {(PUBLISHED, LABEL_VALIDATING), (PRE_PR, LABEL_IMPLEMENTING)})
        self.assertEqual(checkouts.fetch.call_count, 1, "one base fetch feeds the whole walk")
        self.assertEqual(observed(self.github, checkouts), Walked(
            rebased=[PUBLISHED, PRE_PR],
            published={PUBLISHED: ONE_PUBLICATION},
            relabelled=[(PUBLISHED, LABEL_VALIDATING)],
            noticed=[pr_of(PUBLISHED)],
            announced={PUBLISHED: [AFTER_SHA]},
            rounds={PUBLISHED: 0, PRE_PR: None, HELD: ROUND_BEFORE},
        ))
        self.assertEqual(self.github.pinned_data(HELD), held_record, "nothing is written on a held issue")

    def _ticked_once_released(self, checkouts: Checkouts, *, limit: int, scheduled: bool) -> None:
        """The tick after the holder lets go: `HELD` is published, and nothing is published twice."""
        ran = self._ran(checkouts, limit=limit, scheduled=scheduled)

        self.assertEqual(ran, {
            (PUBLISHED, LABEL_VALIDATING), (PRE_PR, LABEL_IMPLEMENTING), (HELD, LABEL_VALIDATING),
        })
        self.assertEqual(observed(self.github, checkouts), Walked(
            rebased=[PUBLISHED, PRE_PR, HELD],
            published={PUBLISHED: ONE_PUBLICATION, HELD: ONE_PUBLICATION},
            relabelled=[(PUBLISHED, LABEL_VALIDATING), (HELD, LABEL_VALIDATING)],
            noticed=[pr_of(PUBLISHED), pr_of(HELD)],
            announced={PUBLISHED: [AFTER_SHA], HELD: [AFTER_SHA]},
            rounds={PUBLISHED: 0, PRE_PR: None, HELD: 0},
        ))

    def _seeded(self) -> Checkouts:
        """A fresh repository carrying the three issues, each checkout behind base."""
        self.fresh_repository()
        seed_open_pr(self.github, PUBLISHED)
        self.github.add_issue(make_issue(PRE_PR, label=LABEL_IMPLEMENTING))
        seed_open_pr(self.github, HELD)
        return Checkouts(self, PUBLISHED, PRE_PR, HELD)

    def _ran(self, checkouts: Checkouts, *, limit: int, scheduled: bool) -> set[tuple[int, str]]:
        """Which issues one whole tick ran a handler for, and under which label."""
        stand_in = StandInHandler()
        self.ticked(
            stand_in, limit=limit, scheduled=scheduled,
            labels=_HANDLED_LABELS, refresh=checkouts.walked(),
        )
        return set(stand_in.ran_on)


if __name__ == "__main__":
    unittest.main()
