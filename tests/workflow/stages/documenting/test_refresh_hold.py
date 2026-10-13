# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The base refresh ahead of a documenting tick leaves a launch nothing answered for to the handler's park.

A quota stop a live pause or a refused retirement held writes nothing, so the
record its launch landed is still on the comment when the next tick's refresh
runs -- before any handler, against a base that advanced meanwhile. Rebased
there, the commit the pass left would be rewritten and pushed, or with none
the base pushed and the issue handed back to review, with no pass having
finished. The refresh stands down instead, and the handler behind it parks.
"""
from __future__ import annotations

import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.scheduler import writer_claims as _writer_claims
from orchestrator.workflow.engine import base_refresh
from tests.git.base_sync.sync_test_support import _patch_base_sync
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.stages.documenting.documenting_scenario_test_support import (
    QUOTA_ISSUE_NUMBER,
    SHA_BEFORE,
    SHA_DOCS,
    SHA_STOPPED,
    _AgyContinueDocumentingFixture,
)

# The holds a quota stop's tick can return under, each leaving no park behind,
# beside what the stopped pass left: the heads its tick reads, and how far the
# branch then stands ahead of its pull request -- a commit, and nothing at all.
CASES = tuple(
    (hold, *left)
    for hold in ("_paused_meanwhile", "_retirement_refused")
    for left in (((SHA_BEFORE, SHA_STOPPED, SHA_DOCS), 1), ((SHA_BEFORE,), 0))
)
# What the refresh would rewrite the branch with, were it let through: a base
# one commit ahead of the checkout.
BASE_AHEAD = MagicMock(returncode=0, stdout="1", stderr="")
REFRESH_SEAMS = ("git", "rebase", "push")
PUSH_BRANCH = "_push_branch"
# The park fields, the launch record, and the rebase anchor, as the handler's
# park leaves them: no anchor, since no rebase ran.
PARKED = MappingProxyType({
    "awaiting_human": True,
    "park_reason": "agent_silent",
    "docs_launched_sha": None,
    "pending_auto_base_rebase_push_sha": None,
})


class LaunchRecordRefreshHoldTest(unittest.TestCase, _AgyContinueDocumentingFixture):
    """A refresh over a standing launch record touches nothing, and the handler behind it parks."""

    def test_refresh_leaves_the_park_to_the_handler(self) -> None:
        # Whichever hold kept the stop's tick from parking, and whether or not
        # the pass committed: the refresh runs no git and pushes nothing
        # though base moved, and the handler then parks for a continue,
        # launching and publishing nothing, without the anchor or the size
        # park a rebase would have left.
        for hold, head_shas, ahead in CASES:
            with self.subTest(hold=hold, ahead=ahead), self._fresh_host():
                self._assert_held_then_parked(getattr(self, hold), head_shas, ahead)

    def _assert_held_then_parked(self, held, head_shas, ahead) -> None:
        """Stop a pass under `held`, refresh over what it left, then run the tick behind the refresh."""
        gh, issue, run_agent = self._stopped(held, head_shas=head_shas)
        self._assert_refresh_held(gh)

        left_on = head_shas[-1:]
        tick = self._tick(gh, issue, run_agent, head_shas=left_on, ahead=ahead)
        self.assertEqual((run_agent.call_count, tick[PUSH_BRANCH].call_count), (1, 0))
        self.assertEqual(gh.label_history, [])
        self.assertEqual(self._parked_fields(gh), dict(PARKED))

    def _assert_refresh_held(self, gh) -> None:
        """One pre-tick refresh of the issue's checkout, base one commit ahead, which touched no git seam."""
        seams = {
            "git": MagicMock(return_value=BASE_AHEAD),
            "rebase": MagicMock(return_value=(True, [])),
            "push": MagicMock(return_value=True),
        }
        checkout = Path(f"/tmp/refresh-hold-issue-{QUOTA_ISSUE_NUMBER}")
        clean_on_its_head = {"dirty": MagicMock(return_value=[]), "head_sha": MagicMock(return_value=SHA_BEFORE)}
        with _patch_base_sync(**clean_on_its_head, **seams):
            base_refresh._sync_worktree_with_base(gh, _TEST_SPEC, checkout, QUOTA_ISSUE_NUMBER)
        for seam in REFRESH_SEAMS:
            seams[seam].assert_not_called()

    def _parked_fields(self, gh) -> dict:
        """The park fields, the launch record, and the rebase anchor as the pinned comment carries them."""
        state = gh.pinned_data(QUOTA_ISSUE_NUMBER)
        return {key: state.get(key) for key in PARKED}

    @contextmanager
    def _fresh_host(self):
        """A host namespace of the case's own, so a retirement one case leaves owed there is not the next one's."""
        with (
            tempfile.TemporaryDirectory(prefix="refresh-hold-claims-") as host,
            patch.object(_writer_claims, "_namespace", lambda: Path(host)),
        ):
            yield


if __name__ == "__main__":
    unittest.main()
