# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Pollable-issue listing: closed-issue sweep coverage and sweep cadence."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from tests.support.fakes import FakeGitHubClient, make_issue

_IMPLEMENTING_LABEL = "workflow:implementing"
_CLOSED_IMPLEMENTING_ISSUE = 301
_CLOSED_DOCUMENTING_ISSUE = 302
_CLOSED_VALIDATING_ISSUE = 303
_CLOSED_LEGACY_IMPLEMENTING_ISSUE = 311
_CLOSED_LEGACY_FIXING_ISSUE = 312
_CLOSED_LEGACY_CONFLICT_ISSUE = 313
_CLEANUP_ISSUE = 321
_SWEEP_CADENCE_ATTR = "CLOSED_ISSUE_SWEEP_EVERY_N_TICKS"

# One closed issue per swept spelling: three namespaced, three pre-namespace.
_CLOSED_SWEEP_CASES = (
    (_CLOSED_IMPLEMENTING_ISSUE, _IMPLEMENTING_LABEL),
    (_CLOSED_DOCUMENTING_ISSUE, "workflow:documenting"),
    (_CLOSED_VALIDATING_ISSUE, "workflow:validating"),
    (_CLOSED_LEGACY_IMPLEMENTING_ISSUE, "implementing"),
    (_CLOSED_LEGACY_FIXING_ISSUE, "fixing"),
    (_CLOSED_LEGACY_CONFLICT_ISSUE, "resolving_conflict"),
)


def _swept_numbers(issue_number: int, label: str) -> list[int]:
    """Poll a repository holding one closed issue under the given label."""
    gh = FakeGitHubClient()
    closed = make_issue(issue_number, label=label)
    closed.closed = True
    gh.add_issue(closed)
    return [issue.number for issue in gh.list_pollable_issues()]


class ListPollableIssuesTest(unittest.TestCase):
    """Closed-but-`in_review` issues must still be picked up so external
    manual merges (which auto-close the linked issue via "Resolves #N") get
    finalized to `done` instead of being silently dropped."""

    def test_open_only_when_no_in_review_closed(self) -> None:
        gh = FakeGitHubClient()
        gh.add_issue(make_issue(1, label=_IMPLEMENTING_LABEL))
        gh.add_issue(make_issue(2, label="workflow:validating"))
        out = list(gh.list_pollable_issues())
        self.assertEqual({issue.number for issue in out}, {1, 2})

    def test_closed_review_included_for_merge_finish(self) -> None:
        open_issue = make_issue(1, label=_IMPLEMENTING_LABEL)
        closed_in_review = make_issue(7, label="in_review")
        closed_in_review.closed = True
        # Closed but no in_review label: must be skipped (already finalized).
        closed_done = make_issue(8, label="done")
        closed_done.closed = True
        gh = FakeGitHubClient((open_issue, closed_in_review, closed_done))

        self.assertEqual(_polled_numbers(gh), {1, 7})

    def test_closed_question_included_for_cleanup(self) -> None:
        # A human closing a `question`-labeled Q&A issue is the terminal
        # signal `_handle_question` consumes to finalize the issue to
        # `done` and clean up the per-issue worktree/branch. Without the
        # closed-issue sweep including `question`, the dispatcher would
        # never re-visit the closed issue and the worktree would linger.
        gh = FakeGitHubClient()
        open_issue = make_issue(1, label=_IMPLEMENTING_LABEL)
        closed_question = make_issue(9, label="question")
        closed_question.closed = True
        for seeded_issue in (open_issue, closed_question):
            gh.add_issue(seeded_issue)
        out = {
            pollable_issue.number
            for pollable_issue in gh.list_pollable_issues()
        }
        self.assertEqual(out, {1, 9})

    def test_closed_discussion_included_for_its_pr(self) -> None:
        # A human can close a `discussion` issue while the plan PR it produced
        # is still open, and that close says nothing about the design -- so
        # `_handle_discussion` holds its terminal, keeps the label, and waits
        # for the pull request. The sweep is the only thing that revisits a
        # closed issue, so without `discussion` in it the worktree and the
        # branches the plan lives on would outlive every pass that knows to
        # reap them.
        gh = FakeGitHubClient()
        closed_discussion = make_issue(10, label="discussion")
        closed_discussion.closed = True
        gh.add_issue(closed_discussion)
        out = {
            pollable_issue.number
            for pollable_issue in gh.list_pollable_issues()
        }
        self.assertEqual(out, {10})


class ListPollableIssuesClosedSweepTest(unittest.TestCase):
    """A closed issue parked mid-flight must still be yielded: the terminals
    each handler asks at entry cannot fire unless the sweep hands the
    dispatcher the issue.

    Either label spelling counts. A closed issue is the one case no other pass
    revisits, so on a repository whose labels the bootstrap could not rename,
    the pre-namespace spelling is the only thing left to find it by.
    """

    def test_yielded_under_either_spelling(self) -> None:
        for issue_number, label in _CLOSED_SWEEP_CASES:
            with self.subTest(label=label):
                self.assertIn(issue_number, _swept_numbers(issue_number, label))


class CleanupSweepTest(unittest.TestCase):
    """The closed decomposition states are swept, and only for cleanup.

    An issue closed on `decomposing` or `umbrella` may still hold the remote
    to a superseded branch and to the immutable ref its children were cut
    from, and nothing else ever revisits a closed issue.

    `ready` and `blocked` are queried for the same reason one step further
    on: a decomposition outcome writes one of them, and a run spawned before
    its owner was observed closed lands after that observation -- so an
    ending latched, receipted, and never marked can be left on an issue that
    is closed under either. The latch that would route it is memory, so
    without the query a process that exits first loses the ending for good.
    """

    def test_a_closed_snapshot_owner_is_yielded(self) -> None:
        for label in ("workflow:decomposing", "workflow:umbrella"):
            with self.subTest(label=label):
                self.assertIn(
                    _CLEANUP_ISSUE, _swept_numbers(_CLEANUP_ISSUE, label),
                )

    def test_an_interrupted_ending_is_yielded(self) -> None:
        for label in ("workflow:ready", "workflow:blocked"):
            with self.subTest(label=label):
                self.assertIn(
                    _CLEANUP_ISSUE, _swept_numbers(_CLEANUP_ISSUE, label),
                )

    def test_an_open_pre_pr_state_is_polled_as_ever(self) -> None:
        # The query is about CLOSED issues only: an open `ready` issue is a
        # developer's to pick up, and nothing here changes how it is polled.
        gh = FakeGitHubClient()
        gh.add_issue(make_issue(_CLEANUP_ISSUE, label="workflow:ready"))

        with patch.object(config, _SWEEP_CADENCE_ATTR, 1):
            polled = [issue.number for issue in gh.list_pollable_issues()]

        self.assertEqual(polled, [_CLEANUP_ISSUE])

    def test_a_cleanup_owner_rides_the_same_cadence(self) -> None:
        # The whole point of folding it into the sweep that already runs: a
        # cleanup owner costs no request on a tick the closed-issue sweep is
        # skipping anyway.
        gh = FakeGitHubClient()
        gh.add_issue(make_issue(1, label=_IMPLEMENTING_LABEL))
        closed = make_issue(_CLEANUP_ISSUE, label="workflow:umbrella")
        closed.closed = True
        gh.add_issue(closed)

        with patch.object(config, _SWEEP_CADENCE_ATTR, 3):
            swept = sorted(issue.number for issue in gh.list_pollable_issues())
            held = sorted(issue.number for issue in gh.list_pollable_issues())

        self.assertEqual(swept, [1, _CLEANUP_ISSUE])
        self.assertEqual(held, [1])


class ClosedSweepCadenceTest(unittest.TestCase):
    """`CLOSED_ISSUE_SWEEP_EVERY_N_TICKS` batches the per-label closed-issue
    recovery sweep so its fixed request cost is not paid every tick. The
    open-issue poll must stay every tick; only the closed sweep is throttled.
    """

    def test_unthrottled_sweep_runs_every_tick(self) -> None:
        gh = FakeGitHubClient()
        gh.add_issue(make_issue(1, label=_IMPLEMENTING_LABEL))
        closed = make_issue(7, label="in_review")
        closed.closed = True
        gh.add_issue(closed)
        # Pin the knob: it resolves from the environment, so reading it
        # unpatched would assert about the operator's shell, not the cadence.
        with patch.object(config, _SWEEP_CADENCE_ATTR, 1):
            for _ in range(3):
                out = {issue.number for issue in gh.list_pollable_issues()}
                self.assertEqual(out, {1, 7})

    def test_sweep_runs_first_then_every_nth_call(self) -> None:
        gh = FakeGitHubClient()
        gh.add_issue(make_issue(1, label=_IMPLEMENTING_LABEL))
        closed = make_issue(7, label="in_review")
        closed.closed = True
        gh.add_issue(closed)
        with patch.object(config, _SWEEP_CADENCE_ATTR, 3):
            # Call 1 (first): sweep runs -> closed issue present.
            self.assertEqual({issue.number for issue in gh.list_pollable_issues()}, {1, 7})
            # Calls 2 and 3: sweep skipped -> open issue only.
            self.assertEqual({issue.number for issue in gh.list_pollable_issues()}, {1})
            self.assertEqual({issue.number for issue in gh.list_pollable_issues()}, {1})
            # Call 4 (== first + N): sweep runs again.
            self.assertEqual({issue.number for issue in gh.list_pollable_issues()}, {1, 7})

    def test_throttle_never_drops_open_issues(self) -> None:
        gh = FakeGitHubClient()
        gh.add_issue(make_issue(1, label=_IMPLEMENTING_LABEL))
        gh.add_issue(make_issue(2, label="workflow:validating"))
        with patch.object(config, _SWEEP_CADENCE_ATTR, 5):
            for _ in range(5):
                out = {issue.number for issue in gh.list_pollable_issues()}
                self.assertEqual(out, {1, 2})


def _polled_numbers(gh: FakeGitHubClient) -> set[int]:
    """Which issues one poll of this client yields."""
    return {
        pollable_issue.number
        for pollable_issue in gh.list_pollable_issues()
    }


if __name__ == "__main__":
    unittest.main()
