# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The release walk, claiming every child it would start and reading each again.

A walk inside `child_claims.claiming()` takes each child's writer claim before
it vouches for any, reads each again behind its claim, and releases all of
them or none: a child another poller on this host holds, one it moved since
the parent's scan, or one the read behind the claims cannot reach holds the
whole walk, parks nothing, and leaves the next walk to try again.

No production walk is made inside `claiming()` yet -- the last case holds an
ordinary tick to the release it always made.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import tick as _tick
from orchestrator.workflow.stages.decomposition import parents as _parents
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.support.writer_claim_processes import HELD, SharedNamespaceCase
from tests.support.writer_claims import claimable, held_elsewhere
from tests.workflow.fixtures import (
    _TEST_SPEC,
    KEY_AWAITING_HUMAN,
    LABEL_DONE,
    LABEL_READY,
    _agent,
    _PatchedWorkflowMixin,
)
from tests.workflow.stages.decomposition import child_claim_test_support as _support

_FIRST, _SECOND = _support.CHILDREN

# The name a poller started after the repository's rename fetched it under.
_RENAMED = "chippingway/renamed-orchestrator"

# A poller in another process holding one issue until told to let go. It keys
# the claim by the repository's numeric id alone and knows no name for it.
_HOLDER = """
import sys

from orchestrator.scheduler import writer_claims

with writer_claims.issue_writer(int(sys.argv[1]), int(sys.argv[2])) as held:
    print("held" if held else "refused", flush=True)
    sys.stdin.readline()
"""


class ClaimedReleaseTest(unittest.TestCase):
    """One `blocked` parent whose two children are both ready to start."""

    def setUp(self) -> None:
        github, parent = _support.blocked_family()
        self.github = github
        self.parent = parent

    def test_one_held_child_releases_none(self) -> None:
        with held_elsewhere(self.github.repo_id, _SECOND), self.assertLogs(_support.WORKFLOW_LOG):
            held = _support.walked(self.github, self.parent)

        self.assertEqual(self.github.label_history, [], "neither child is released")
        self.assertEqual(held, [(_FIRST, []), (_SECOND, [])])
        self.assertIsNone(self.github.pinned_data(_support.PARENT).get(KEY_AWAITING_HUMAN), "nothing parks")
        self.assertTrue(claimable(self.github.repo_id, _FIRST), "the claim taken first is given back")

        _support.walked(self.github, self.parent)

        self.assertEqual(self.github.label_history, list(_support.RELEASED))

    def test_a_child_moved_since_its_scan_waits(self) -> None:
        # Another poller finishes a child between the scan and the claims and
        # lets it go: read again under the claim it is no longer `blocked`, so
        # it is not put back to `ready`, and its sibling waits for a walk that
        # scans again.
        scan = _parents._read_child_labels(self.github, self.parent, list(_support.CHILDREN))
        with held_elsewhere(self.github.repo_id, _FIRST):
            self.github.add_issue(make_issue(_FIRST, label=LABEL_DONE, closed=True))

        _support.walked(self.github, self.parent, scan)

        self.assertEqual(self.github.label_history, [], "nothing is released off the stale scan")
        self.assertIsNone(self.github.pinned_data(_support.PARENT).get(KEY_AWAITING_HUMAN))

        _support.walked(self.github, self.parent)

        self.assertEqual(self.github.label_history, [(_SECOND, LABEL_READY)])

    def test_a_failed_reread_releases_none(self) -> None:
        scan = _parents._read_child_labels(self.github, self.parent, list(_support.CHILDREN))
        outage = ConnectionError("github unreachable")

        with patch.object(self.github, "get_issue", side_effect=outage), self.assertLogs(_support.WORKFLOW_LOG):
            held = _support.walked(self.github, self.parent, scan)

        self.assertEqual(self.github.label_history, [])
        self.assertEqual(held, [(_FIRST, []), (_SECOND, [])])

    def test_a_raising_walk_gives_claims_back(self) -> None:
        refused = _support.RefusedWrite(self.github, self.github.set_workflow_label)

        with patch.object(self.github, "set_workflow_label", refused), self.assertRaises(RuntimeError):
            _support.walked(self.github, self.parent)

        self.assertEqual(refused.claimable_during, [False], "the child is relabelled under its claim")
        self.assertTrue(claimable(self.github.repo_id, _FIRST))
        self.assertTrue(claimable(self.github.repo_id, _SECOND))

        _support.walked(self.github, self.parent)

        self.assertEqual(self.github.label_history, list(_support.RELEASED))


class AnotherProcessReleaseTest(SharedNamespaceCase):
    """A child a poller in another process holds, keyed on the id every poller here meets on."""

    def test_another_process_s_child_holds_the_walk(self) -> None:
        github, parent = _support.blocked_family(FakeGitHubClient(repo_slug=_RENAMED))
        holder = self.run_elsewhere(_HOLDER, github.repo_id, _FIRST)
        self.assertEqual(holder.said(), HELD)

        with self.assertLogs(_support.WORKFLOW_LOG):
            _support.walked(github, parent)

        self.assertEqual(github.label_history, [], "whatever name this poller knows the repository by")
        self.assertEqual(holder.let_go(), 0)

        _support.walked(github, parent)

        self.assertEqual(github.label_history, list(_support.RELEASED))


class OrdinaryTickTest(unittest.TestCase, _PatchedWorkflowMixin):
    """What a tick does today, outside `claiming()`."""

    def test_a_tick_releases_past_a_held_child(self) -> None:
        # No production path enters `claiming()`, so the walk a tick runs takes
        # no child's claim and reads no child again: another poller holding
        # both children changes nothing about their release.
        github, _ = _support.blocked_family()

        with held_elsewhere(github.repo_id, *_support.CHILDREN):
            self._run(lambda: _tick.tick(github, _TEST_SPEC), run_agent=_agent())

        for released in _support.RELEASED:
            self.assertIn(released, github.label_history)


if __name__ == "__main__":
    unittest.main()
