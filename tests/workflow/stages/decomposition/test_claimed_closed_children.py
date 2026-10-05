# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A parent's writes to its closed children, each under the child's own writer claim.

The finalize of a child an external merge closed writes its label, thread,
and record; the notice that a consumer's snapshot is gone writes its thread.
Another poller on this host may be dispatching either child, so each write
takes that child's claim first. A finalize is decided on the child read again
behind the claim, so a child that poller finalized since the parent's scan is
never finalized twice; a notice is a comment built to land beside this
process's own handler, so only another process's hold keeps it owed.
"""
from __future__ import annotations

import unittest

from orchestrator.scheduler import writer_claims as _writer_claims
from orchestrator.workflow.engine import terminals as _terminals
from orchestrator.workflow.late_split import obligations as _obligations, phases as _late_phases
from orchestrator.workflow.stages.decomposition import (
    late_cleanup_state as _late_cleanup_state,
    late_consumer_release as _late_consumer_release,
    parents as _parents,
)
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.support.writer_claims import held_elsewhere
from tests.workflow.fixtures import _TEST_SPEC, LABEL_DONE, _agent, _PatchedWorkflowMixin
from tests.workflow.stages.decomposition import child_claim_test_support as _support
from tests.workflow.stages.decomposition.late_cleanup_support import PARENT_NUMBER, SNAPSHOT_REF, UMBRELLA
from tests.workflow.stages.decomposition.late_test_support import late_generation

# Two consumers cut from one ref, so a pass nothing holds back tells both.
_CONSUMERS = (911, 912)

# What finalizing the merged child leaves in the label history.
_FINALIZED = ((_support.MERGED_CHILD, LABEL_DONE),)


class ClaimedMergeFinalizeTest(unittest.TestCase, _PatchedWorkflowMixin):
    """A `blocked` parent whose one child an external merge closed."""

    def setUp(self) -> None:
        github, parent = _support.blocked_on_a_merged_child()
        self.github = github
        self.parent = parent

    def test_a_held_merged_child_waits(self) -> None:
        # Neither finalized nor counted as closed by hand: the parent waits on
        # it rather than parking over it, and the next walk finalizes it.
        with held_elsewhere(self.github.repo_id, _support.MERGED_CHILD), self.assertLogs(_support.WORKFLOW_LOG):
            parked, _ = self._parked_on_children()

        self.assertFalse(parked)
        self.assertEqual(self.github.label_history, [], "the child is not finalized")
        self.assertNotIn("merged_at", self.github.pinned_data(_support.MERGED_CHILD))
        self.assertEqual(self.github.posted_comments, [], "nor the parent parked over it")

        parked, scan = self._parked_on_children()

        self.assertFalse(parked)
        self.assertEqual(self.github.label_history, list(_FINALIZED))
        self.assertEqual(scan.labels[_support.MERGED_CHILD], LABEL_DONE)

    def test_a_finalize_since_the_scan_stays(self) -> None:
        # The claim is granted, because the other poller let go -- but it
        # finalized the child after the parent's scan, so a finalize decided
        # on that scan would merge the child a second time.
        scan = _parents._read_child_labels(self.github, self.parent, [_support.MERGED_CHILD])
        with held_elsewhere(self.github.repo_id, _support.MERGED_CHILD):
            self._run(self._finalized_elsewhere, run_agent=_agent())

        parked, _ = self._parked_on_children(scan)

        merged = [event for event in self.github.recorded_events if event["event"] == "pr_merged"]
        self.assertEqual(len(merged), 1, "the child is merged once, by the poller that finalized it")
        self.assertEqual(self.github.label_history, list(_FINALIZED))
        self.assertEqual(scan.labels[_support.MERGED_CHILD], LABEL_DONE, "the parent reads it done")
        self.assertFalse(parked, "and does not park over it")

    def _finalized_elsewhere(self) -> None:
        """The other poller's own finalize of the merged child."""
        child = self.github.get_issue(_support.MERGED_CHILD)
        _terminals._finalize_if_pr_merged(self.github, _TEST_SPEC, child, self.github.read_pinned_state(child))

    def _parked_on_children(self, scan=None) -> tuple:
        """Whether the parent parks on its children, and the scan it asked of."""
        scan = scan or _parents._read_child_labels(self.github, self.parent, [_support.MERGED_CHILD])
        answered = []
        state = self.github.read_pinned_state(self.parent)
        self._run(
            lambda: answered.append(
                _parents._parked_on_children(self.github, _TEST_SPEC, self.parent, state, scan),
            ),
            run_agent=_agent(),
        )
        return answered[0], scan


class ClaimedConsumerNoticeTest(unittest.TestCase):
    """A reclaimed snapshot's notice, posted on each consumer under its own claim."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.owner = make_issue(PARENT_NUMBER, label=UMBRELLA)
        self.github.add_issue(self.owner)
        for number in _CONSUMERS:
            self.github.add_issue(make_issue(number, closed=True))

    def test_a_held_consumer_keeps_it_owed(self) -> None:
        with held_elsewhere(self.github.repo_id, _CONSUMERS[1]), self.assertLogs(_support.WORKFLOW_LOG):
            told = self._released()

        self.assertFalse(told, "the obligation stays outstanding")
        self.assertEqual(self._told(), [_CONSUMERS[0]])

        self.assertTrue(self._released())
        self.assertEqual(self._told(), list(_CONSUMERS), "each consumer is told once")

    def test_a_notice_lands_beside_our_writer(self) -> None:
        # The notice is a comment built to land beside the consumer's own
        # handler, so this process holding the consumer is no reason to wait.
        with _writer_claims.issue_writer(self.github.repo_id, _CONSUMERS[0]):
            told = self._released()

        self.assertTrue(told)
        self.assertEqual(self._told(), list(_CONSUMERS))

    def _released(self) -> bool:
        """Deliver the ref's notices, and say whether every consumer was told."""
        scan = _parents._read_child_labels(self.github, self.owner, list(_CONSUMERS))
        walk = _late_cleanup_state._Pass(
            gh=self.github,
            spec=_TEST_SPEC,
            issue=self.owner,
            state=self.github.read_pinned_state(self.owner),
            scan=scan,
        )
        generation = late_generation(
            threshold=None,
            additions=None,
            phase=_late_phases.LatePhase.CLEANING_UP,
            obligations=_obligations.LateObligations().with_consumers(_CONSUMERS),
        )
        _, told = _late_consumer_release._release_consumers(walk, generation, SNAPSHOT_REF, scan)
        return told

    def _told(self) -> list[int]:
        """The consumers a notice was posted on, in order."""
        return [number for number, _ in self.github.posted_comments]


if __name__ == "__main__":
    unittest.main()
