# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import terminals as _terminals
from orchestrator.workflow.stages.decomposition import blocked as _blocked, umbrella as _umbrella
from tests.support.fakes import (
    FakeGitHubClient,
    FakeIssue,
    FakePR,
    FakePRRef,
    make_issue,
)
from tests.support.writer_claims import held_elsewhere
from tests.workflow.fixtures import (
    _TEST_SPEC,
    _agent,
    _PatchedWorkflowMixin,
)

LABEL_DONE = "done"
BLOCKED_PARENT_NUMBER = 70
BLOCKED_DONE_CHILD_NUMBER = 701
BLOCKED_MERGED_CHILD_NUMBER = 702
BLOCKED_MERGED_PR_NUMBER = 7020
UMBRELLA_PARENT_NUMBER = 80
UMBRELLA_DONE_CHILD_NUMBER = 801
UMBRELLA_MERGED_CHILD_NUMBER = 802
UMBRELLA_MERGED_PR_NUMBER = 8020
UNMERGED_PARENT_NUMBER = 71
UNMERGED_CHILD_NUMBER = 711
UNMERGED_PR_NUMBER = 7110


def _seed_child_with_merged_pr(
    gh: FakeGitHubClient,
    *,
    number: int,
    label: str,
    pr_number: int,
) -> FakeIssue:
    child = make_issue(number, label=label)
    child.closed = True
    gh.add_issue(child)
    pr = FakePR(
        number=pr_number,
        head_branch=f"orchestrator/chippingway__chipping-orchestrator/issue-{number}",
        head=FakePRRef(sha="cafe1234"),
        merged=True,
        state="closed",
    )
    gh.add_pr(pr)
    gh.seed_state(number, pr_number=pr_number)
    return child


def _blocked_on_a_merged_child() -> tuple[FakeGitHubClient, FakeIssue]:
    """A blocked parent whose one child was closed by an external merge."""
    gh = FakeGitHubClient()
    parent = make_issue(BLOCKED_PARENT_NUMBER, label="workflow:blocked")
    gh.add_issue(parent)
    _seed_child_with_merged_pr(
        gh,
        number=BLOCKED_MERGED_CHILD_NUMBER,
        label="workflow:validating",
        pr_number=BLOCKED_MERGED_PR_NUMBER,
    )
    gh.seed_state(BLOCKED_PARENT_NUMBER, children=[BLOCKED_MERGED_CHILD_NUMBER])
    return gh, parent


class _FinalizedOnceScanned:
    """The parent scans the child, then another poller finalizes it and lets go.

    A read of GitHub answers a snapshot, so the scan keeps the `validating`
    it read while the other poller's finalize lands on the issue itself --
    the window between the parent's scan and its claim on the child.
    """

    def __init__(self, gh: FakeGitHubClient, child_number: int) -> None:
        self._gh = gh
        self._read = gh.get_issue
        self._child_number = child_number
        self._scanned = False

    def __call__(self, number: int) -> FakeIssue:
        """Answer the read; the first of the child's is the scan's, and the finalize lands behind it."""
        issue = self._read(number)
        if int(number) != self._child_number or self._scanned:
            return issue
        self._scanned = True
        scanned = copy.copy(issue)
        with held_elsewhere(self._gh.repo_slug, self._child_number):
            _terminals._finalize_if_pr_merged(self._gh, _TEST_SPEC, issue, self._gh.read_pinned_state(issue))
        return scanned


class ChildMergedPrAutoFinalizeTest(unittest.TestCase, _PatchedWorkflowMixin):
    """A child whose linked PR was merged externally but whose workflow
    label was never advanced past an in-flight stage (e.g. `validating`)
    looks like a manually closed child to the parent aggregation. The
    finalize helper detects the merge during the parent's poll and flips
    the child to `done`, so the parent's aggregation can proceed.
    """

    def test_blocked_recovers_child_with_merged_pr(self) -> None:
        gh = FakeGitHubClient()
        parent = make_issue(BLOCKED_PARENT_NUMBER, label="workflow:blocked")
        gh.add_issue(parent)
        done_child = make_issue(BLOCKED_DONE_CHILD_NUMBER, label=LABEL_DONE)
        done_child.closed = True
        gh.add_issue(done_child)
        # children[1]: a `validating` child whose PR was merged externally
        # (the human clicked Merge before the reviewer agent finished).
        # Used to park the parent on "manually closed"; must now be
        # finalized in-line and counted toward the all-done aggregation.
        _seed_child_with_merged_pr(
            gh,
            number=BLOCKED_MERGED_CHILD_NUMBER,
            label="workflow:validating",
            pr_number=BLOCKED_MERGED_PR_NUMBER,
        )
        gh.seed_state(
            BLOCKED_PARENT_NUMBER,
            children=[BLOCKED_DONE_CHILD_NUMBER, BLOCKED_MERGED_CHILD_NUMBER],
        )

        self._run(
            lambda: _blocked._handle_blocked(gh, _TEST_SPEC, parent),
            run_agent=_agent(),
        )

        self.assertIn(
            (BLOCKED_MERGED_CHILD_NUMBER, LABEL_DONE),
            gh.label_history,
        )
        self.assertIn("merged_at", gh.pinned_data(BLOCKED_MERGED_CHILD_NUMBER))
        # Parent flipped to ready because every child is now `done`.
        self.assertIn((BLOCKED_PARENT_NUMBER, "workflow:ready"), gh.label_history)
        # No manual-close park comment posted.
        self.assertFalse(
            any(
                "closed without reaching" in body
                for issue_number, body in gh.posted_comments
                if issue_number == BLOCKED_PARENT_NUMBER
            )
        )

    def test_umbrella_recovers_child_with_merged_pr(self) -> None:
        gh = FakeGitHubClient()
        parent = make_issue(UMBRELLA_PARENT_NUMBER, label="workflow:umbrella")
        gh.add_issue(parent)
        done_child = make_issue(UMBRELLA_DONE_CHILD_NUMBER, label=LABEL_DONE)
        done_child.closed = True
        gh.add_issue(done_child)
        _seed_child_with_merged_pr(
            gh,
            number=UMBRELLA_MERGED_CHILD_NUMBER,
            label="workflow:implementing",
            pr_number=UMBRELLA_MERGED_PR_NUMBER,
        )
        gh.seed_state(
            UMBRELLA_PARENT_NUMBER,
            children=[UMBRELLA_DONE_CHILD_NUMBER, UMBRELLA_MERGED_CHILD_NUMBER],
            umbrella=True,
        )

        self._run(
            lambda: _umbrella._handle_umbrella(gh, _TEST_SPEC, parent),
            run_agent=_agent(),
        )

        self.assertIn(
            (UMBRELLA_MERGED_CHILD_NUMBER, LABEL_DONE),
            gh.label_history,
        )
        # Umbrella closes once both children are `done`.
        self.assertIn((UMBRELLA_PARENT_NUMBER, LABEL_DONE), gh.label_history)
        self.assertTrue(parent.closed)
        self.assertFalse(
            any(
                "closed without reaching" in body
                for issue_number, body in gh.posted_comments
                if issue_number == UMBRELLA_PARENT_NUMBER
            )
        )

    def test_a_held_merged_child_is_finalized_later(self) -> None:
        # Finalizing writes the child's label, thread, and record, so a child
        # another poller on this host is writing is left as the scan read it:
        # not finalized, and not taken for one a human closed by hand either.
        gh, parent = _blocked_on_a_merged_child()

        with held_elsewhere(gh.repo_slug, BLOCKED_MERGED_CHILD_NUMBER):
            self._run(lambda: _blocked._handle_blocked(gh, _TEST_SPEC, parent), run_agent=_agent())

        self.assertEqual(gh.label_history, [], "neither the child nor the parent moves")
        self.assertNotIn("merged_at", gh.pinned_data(BLOCKED_MERGED_CHILD_NUMBER))
        self.assertEqual(gh.posted_comments, [], "the parent is not parked over it")

        self._run(lambda: _blocked._handle_blocked(gh, _TEST_SPEC, parent), run_agent=_agent())

        self.assertIn((BLOCKED_MERGED_CHILD_NUMBER, LABEL_DONE), gh.label_history)
        self.assertIn((BLOCKED_PARENT_NUMBER, "workflow:ready"), gh.label_history)

    def test_a_finalize_since_the_scan_is_not_redone(self) -> None:
        # The claim the parent takes is granted, because the other poller let
        # go -- but the scan it decided on predates that poller's finalize, so
        # finalizing off the scan would merge the child a second time.
        gh, parent = _blocked_on_a_merged_child()

        with patch.object(gh, "get_issue", _FinalizedOnceScanned(gh, BLOCKED_MERGED_CHILD_NUMBER)):
            self._run(lambda: _blocked._handle_blocked(gh, _TEST_SPEC, parent), run_agent=_agent())

        merged = [event for event in gh.recorded_events if event["event"] == "pr_merged"]
        self.assertEqual(len(merged), 1, "the child is merged once, by the poller that finalized it")
        self.assertEqual(gh.label_history.count((BLOCKED_MERGED_CHILD_NUMBER, LABEL_DONE)), 1)
        self.assertIn((BLOCKED_PARENT_NUMBER, "workflow:ready"), gh.label_history, "the parent reads it done")
        self.assertFalse(gh.pinned_data(BLOCKED_PARENT_NUMBER).get("awaiting_human"), "nor parks over it")

    def test_unmerged_child_pr_keeps_parent_parked(self) -> None:
        # Regression guard: when the child PR is closed-without-merge,
        # the finalize helper must NOT flip the child to `done`. The
        # original manually-closed park still fires.
        gh = FakeGitHubClient()
        parent = make_issue(UNMERGED_PARENT_NUMBER, label="workflow:blocked")
        gh.add_issue(parent)
        closed_child = make_issue(UNMERGED_CHILD_NUMBER, label="workflow:validating")
        closed_child.closed = True
        gh.add_issue(closed_child)
        pr = FakePR(
            number=UNMERGED_PR_NUMBER,
            head_branch="orchestrator/chippingway__chipping-orchestrator/issue-711",
            head=FakePRRef(sha="cafe1234"),
            merged=False,
            state="closed",
        )
        gh.add_pr(pr)
        gh.seed_state(UNMERGED_CHILD_NUMBER, pr_number=UNMERGED_PR_NUMBER)
        gh.seed_state(UNMERGED_PARENT_NUMBER, children=[UNMERGED_CHILD_NUMBER])

        self._run(
            lambda: _blocked._handle_blocked(gh, _TEST_SPEC, parent),
            run_agent=_agent(),
        )

        self.assertNotIn(
            (UNMERGED_CHILD_NUMBER, LABEL_DONE),
            gh.label_history,
        )
        self.assertTrue(gh.pinned_data(UNMERGED_PARENT_NUMBER).get("awaiting_human"))
