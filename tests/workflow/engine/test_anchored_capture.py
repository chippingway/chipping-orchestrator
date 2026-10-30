# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured completion beside an interrupted auto-rebase anchor, through the refresh and the dispatch in turn.

The checkout is real, at the issue's layout path, one commit -- the one a
captured report is about -- ahead of the head the anchor names, with the base
advanced past both and the remote unreadable, which is the anchor recovery's
reset-and-park road: left to run, it puts the branch back on the anchor. So
the refresh holds the branch while the capture is unresolved, the dispatch
decides the capture ahead of the anchor's hold -- retiring it, since no road
hands a report on over a rewrite no recovery finished -- and only the refresh
after that answers the anchor. A capture nobody can read holds both sides
with nothing written. The stage handler is stood in for and never reached.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import (
    completion_records as _records,
    completion_routes as _routes,
    issue_processing as _issue_processing,
    stage_targets as _stage_targets,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import completion_recovery_support as _captures, refresh_anchor_support as _anchors

_ANCHOR = "pending_auto_base_rebase_push_sha"

_RETIRED = (_records.CaptureStage.RETIRED, _records.RetirementReason.INVALIDATED)

# The road the capture was taken on: a drift resume read on `workflow:validating`.
_DRIFT_ROAD = _captures.road(_routes.CompletionRoute.REQUIREMENTS_DRIFT, WorkflowLabel.VALIDATING)

_PASSES = ("first", "second")


class AnchoredCaptureTest(unittest.TestCase):
    """The anchor's recovery waits behind the capture, and the capture is decided ahead of the anchor's hold."""

    def setUp(self) -> None:
        self.world = _anchors.AnchoredCheckout(self)
        self.world.on_its_branch()
        self.anchor = self.world.head()
        _anchors._commits(self.world.checkout, "paid.txt", "captured developer work\n")
        self.source = self.world.head()
        _anchors._commits(self.world.target, _anchors.BASE_FILE, "base advanced\n")
        _anchors._git(self.world.target, "update-ref", "refs/remotes/origin/main", "HEAD")
        run = _records.CompletionRun(
            command=_captures.COMMAND, prompt_revision=_captures.PROMPT, worktree=str(self.world.checkout),
            branch=self.world.branch, before_sha=self.anchor, source_sha=self.source,
        )
        issue = self.world.gh.get_issue(_anchors.ISSUE)
        self.captured = _captures.landed_capture(self.world.gh, issue, run, _DRIFT_ROAD)
        self.handled: list[int] = []

    def test_it_is_retired_before_the_anchor_recovers(self) -> None:
        self.world.syncs()
        self.assertEqual(self.world.head(), self.source, "the refresh keeps the captured commit")

        self._dispatched()

        retired = _captures.read_capture(self.world.gh.pinned_data(_anchors.ISSUE))
        self.assertEqual((retired.stage, retired.reason), _RETIRED)
        self.assertEqual(retired.invocation, self.captured.invocation)
        self.assertEqual(self.handled, [], "the anchor's hold keeps the handler back")
        self.assertEqual(self.world.head(), self.source)
        self.world.syncs()
        self.assertEqual(self.world.head(), self.anchor, "the anchor's recovery answers it as it always would")

    def test_a_capture_nobody_can_read_holds_both(self) -> None:
        pinned = self.world.gh._pinned[_anchors.ISSUE]
        pinned.state_data[_captures.FIELD] = None
        held = self.world.gh.pinned_data(_anchors.ISSUE)

        for each in _PASSES:
            with self.subTest(each):
                self.world.syncs()
                self._dispatched()
                self.assertEqual(self.world.standing(), (self.source, held))
        self.assertEqual(self.handled, [])

    def _dispatched(self) -> None:
        """One dispatch of the issue, its stage handler stood in for."""
        issue = self.world.gh.get_issue(_anchors.ISSUE)
        with patch.object(_stage_targets, "_call_handler", self._handled):
            _issue_processing._process_issue(self.world.gh, self.world.spec, issue)

    def _handled(self, _gh, _spec, issue, _target) -> None:
        self.handled.append(issue.number)


if __name__ == "__main__":
    unittest.main()
