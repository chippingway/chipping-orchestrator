# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The base refresh a tick opens with, stood in for and driven for real."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.workflow.engine import (
    base_refresh as _base_refresh,
    issue_processing as _issue_processing,
    tick,
    usage as _usage,
)
from tests.git.base_sync.sync_test_support import _git_result
from tests.support.fakes import make_issue
from tests.support.writer_claims import held_elsewhere
from tests.workflow.engine import refused_checkouts_support as refused, tick_parallel_test_support as support
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

_WORKFLOW_LOG = "orchestrator.workflow"

# The version each refused record is pinned under: none, as a release before
# version 1 pinned one, or one this build does not know.
_ANOTHER_VERSION = 2
_PINNED_UNDER = (
    (refused.PUBLISHED, _ANOTHER_VERSION),
    (refused.PRE_PR, None),
    (refused.INTERRUPTED, _ANOTHER_VERSION),
)

# What is said of each refused record: the refresh leaves it standing, and the
# dispatch refuses it.
_BOTH_SAID = frozenset((refused.LEFT_STANDING, refused.NOT_DISPATCHED))

# What admission reads each of those comments as.
_REFUSED_AS = "unsupported"


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


class RefusedRecordTickTest(WriterClaimDispatchCase):
    """A whole tick over real checkouts whose issues' pinned records admission refuses.

    Everything under the tick is real -- the refresh and the dispatch, the
    admission each holds its reading to, every handler behind them, and the
    production pinned-state reader and writers over the comments pinned on
    each thread -- but the agent runner, the base the size gate measures
    against, and the transport, which a bare repository on disk answers.
    """

    def setUp(self) -> None:
        self.fresh_repository()
        self.world = refused.RefusedCheckouts(self, self.github)
        for number, version in _PINNED_UNDER:
            self.world.pin(number, version)
        self.agent = self.enterContext(patch.object(_usage, "_run_agent_tracked"))
        self.assertEqual(
            {issue_number: standing[1] for issue_number, standing in self.world.on_github().items()},
            dict.fromkeys(refused.REFUSED, _REFUSED_AS),
            "the production reader refuses every comment pinned",
        )

    def test_only_the_shared_base_fetch_moves(self) -> None:
        # The fetch moves this clone's base ref onto the advance, and nothing
        # an issue owns moves with it: no rebase, reset, push, or recovery, no
        # agent or run charged, and nothing written, posted, or relabelled --
        # every thread, its pinned comment's bytes included, reads as it did.
        # Each refusal is said by the refresh and by the dispatch.
        on_disk = self.world.disk.standing()
        on_github = self.world.on_github()
        refresh = self.world.refreshed()
        self.assertEqual(self.world.disk.base(), self.world.base_before, "nothing has fetched the advance yet")

        with self.assertLogs(_WORKFLOW_LOG, level="WARNING") as logged:
            self.ticked(StandInHandler(), limit=1, scheduled=False, labels=(), refresh=refresh)
            said = self.world.said(logged.output)

        self.assertEqual(self.world.disk.base(), self.world.base_after, "the base fetch ran")
        self.assertEqual(self.world.disk.standing(), on_disk)
        self.assertEqual(self.world.on_github(), on_github)
        self.assertEqual(self.world.disk.push.leases, [])
        self.agent.assert_not_called()
        self.assertEqual(said, dict.fromkeys(refused.REFUSED, _BOTH_SAID))

    def test_a_current_record_is_recovered(self) -> None:
        # The interrupted rebase's own record, current, is what the refresh
        # recovers from: the replay is published under the anchor's lease and
        # the anchor taken down, while the refused issues stay as they stand.
        self.world.pin(refused.INTERRUPTED, refused.SUPPORTED_VERSION)
        heads = self.world.disk.standing()["heads"]
        interrupted = self.world.records[refused.INTERRUPTED]

        with self.assertLogs(_WORKFLOW_LOG, level="WARNING"):
            _base_refresh._refresh_base_and_worktrees(self.github, self._spec())

        published = self.world.disk.remote_head(interrupted[refused.KEY_BRANCH])
        recovered = self.github.read_pinned_state(self.github.get_issue(refused.INTERRUPTED))
        self.assertEqual(self.world.disk.push.leases, [interrupted[refused.KEY_ANCHOR]])
        self.assertEqual(published, interrupted[refused.KEY_REPLAY])
        self.assertIsNone(recovered.get(refused.KEY_ANCHOR))
        self.assertEqual(self.world.disk.standing()["heads"], heads)

    def _spec(self, parallel_limit: int = 1):
        """The repository on disk, which this case ticks one issue at a time."""
        self.assertEqual(parallel_limit, self.world.disk.spec.parallel_limit)
        return self.world.disk.spec


if __name__ == "__main__":
    unittest.main()
