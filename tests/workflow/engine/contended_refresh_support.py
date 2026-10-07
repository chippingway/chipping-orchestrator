# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An interrupted rebase whose push landed, on a checkout a whole tick's refresh walks.

The issue carries the record the attempt left and the pull request stands on
the replay. The refresh beneath the tick is the real one; what is stood in for
is the git it reads the checkout and the remote with -- as the landed push left
them -- and the size gate's reads.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from orchestrator.git.ref_transport import _RefRead
from tests.git.base_sync import refresh_test_support as support
from tests.git.base_sync.gate_reads_support import _gate_reads
from tests.git.base_sync.refresh_scenarios import _landed_recovery_scenario
from tests.git.base_sync.sync_test_support import _git_result, _patch_base_sync
from tests.support.fakes import FakeGitHubClient, FakePR, FakePRRef, make_issue

ANCHORED = support.ISSUE

# How a recovery that finds the replay already published finishes it.
RELABEL_ONLY = "crash_recovery_relabel_only"

KEY_PENDING_PUSH_SHA = support.KEY_PENDING_PUSH_SHA


class LandedCheckout:
    """The anchored issue's checkout on disk, under a worktrees root of its own."""

    def __init__(self, case) -> None:
        self._root = Path(case.enterContext(tempfile.TemporaryDirectory(prefix="orch-landed-checkout-")))
        (self._root / f"issue-{ANCHORED}").mkdir()
        _gate_reads(case)

    def walked(self):
        """The refresh's git for one tick: a base fetch that lands, and the checkout and branch the push left."""
        return _patch_base_sync(
            target_fetch=MagicMock(return_value=_git_result()),
            worktrees_root=MagicMock(return_value=self._root),
            remote_read=MagicMock(return_value=_RefRead(sha=support.REBASED_SHA)),
            **_landed_recovery_scenario(support.REBASED_SHA).patches,
        )


def seed_anchored(github: FakeGitHubClient, label: str) -> None:
    """Put the anchored issue on `github` under `label`, with its record and its pull request."""
    github.add_issue(make_issue(ANCHORED, label=label))
    github.seed_state(
        ANCHORED,
        pr_number=support.PR_NUMBER,
        branch=support.PR_BRANCH,
        review_round=3,
        **support._pending_attempt(support.REBASED_SHA),
    )
    github.add_pr(FakePR(
        number=support.PR_NUMBER,
        head_branch=support.PR_BRANCH,
        head=FakePRRef(sha=support.REBASED_SHA),
    ))


def finishes(github: FakeGitHubClient) -> list[str]:
    """How each `base_rebased` on `github` says the recovery finished."""
    return [
        event.get(support.METHOD_FIELD) for event in github.recorded_events
        if event.get(support.EVENT_FIELD) == support.EVENT_BASE_REBASED
    ]
