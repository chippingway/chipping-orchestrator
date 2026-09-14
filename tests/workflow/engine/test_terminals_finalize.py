# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Direct coverage of the two entry points that fetch a PR of their own.

`_finalize_if_pr_merged` is the single-ending one the umbrella / blocked
aggregation asks: the no-`pr_number` / open-PR / closed-without-merge negative
cases, the merged-PR finalize on an open vs. already-closed issue, and the
terminal usage-verdict receipt it posts (tracked before the pinned-state
write). `_pr_terminal_stops_the_tick` is what the stages carrying no PR-state
arc of their own ask instead, and it decides BOTH endings off ONE reading --
which is the thing worth pinning, since two fetches would be two moments."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import terminals
from tests.support.fakes import (
    FakeGitHubClient,
    FakePR,
    FakePRRef,
    make_issue,
)
from tests.workflow.fixtures import (
    _TEST_SPEC,
    EVENT_PR_MERGED,
    _agent,
    _issue_branch,
    _PatchedWorkflowMixin,
    _state_with_pr_number,
)

_VALIDATING_LABEL = "workflow:validating"
_IMPLEMENTING_LABEL = "workflow:implementing"
_IMPLEMENTING_STAGE = "implementing"
_STATE_CLOSED = "closed"
_PR_HEAD_SHA = "cafe1234"
_CLEANUP_MOCK_KEY = "_cleanup_terminal_branch"
_NO_PR_ISSUE_NUMBER = 200
_OPEN_PR_ISSUE_NUMBER = 201
_OPEN_PR_NUMBER = 20100
_CLOSED_PR_ISSUE_NUMBER = 202
_CLOSED_PR_NUMBER = 20200
_OPEN_ISSUE_MERGED_NUMBER = 203
_OPEN_ISSUE_MERGED_PR_NUMBER = 20300
_CLOSED_ISSUE_MERGED_NUMBER = 204
_CLOSED_ISSUE_MERGED_PR_NUMBER = 20400
_USAGE_ISSUE_NUMBER = 205
_USAGE_PR_NUMBER = 20500
_USAGE_TOTAL_TOKENS = 45200
_USAGE_TOTAL_COST = 0.87
_NO_USAGE_ISSUE_NUMBER = 206
_NO_USAGE_PR_NUMBER = 20600
_ONE_READING_ISSUE_NUMBER = 207
_ONE_READING_PR_NUMBER = 20700


def _client_with_issue(number: int, label: str):
    """A fresh fake client carrying one labelled issue."""
    github = FakeGitHubClient()
    seeded = make_issue(number, label=label)
    github.add_issue(seeded)
    return github, seeded


def _receipt_bodies(gh: FakeGitHubClient, issue_number: int) -> list[str]:
    return [
        body
        for posted_number, body in gh.posted_comments
        if posted_number == issue_number and body.startswith(":receipt:")
    ]


def _receipt_comment(issue):
    return next(
        comment
        for comment in issue.comments
        if comment.body.startswith(":receipt:")
    )


class FinalizeIfPrMergedTest(unittest.TestCase, _PatchedWorkflowMixin):
    """Direct coverage of the single-ending `_finalize_if_pr_merged` helper.

    The umbrella / blocked aggregation is what calls it: a child whose PR was
    merged externally while its own workflow label stayed on an in-flight
    stage would otherwise hold the all-`done` aggregation forever, and that
    aggregation may not be held on a child whose remote merely blinked.

    The three stages that carry no PR-state arc of their own -- implementing,
    documenting, validating -- ask `_pr_terminal_stops_the_tick` instead,
    which decides BOTH pull-request endings off one reading; the class beside
    this one covers that. The merged arc is the same either way, so it carries
    its own tests here in addition to the per-handler smoke tests.
    """

    def test_no_pr_number_returns_false(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(_NO_PR_ISSUE_NUMBER, label=_VALIDATING_LABEL)
        gh.add_issue(issue)
        mocks = self._run(
            lambda: self.assertFalse(
                terminals._finalize_if_pr_merged(
                    gh, _TEST_SPEC, issue, PinnedState()
                )
            ),
            run_agent=_agent(),
        )
        self.assertEqual(gh.label_history, [])
        self.assertFalse(issue.closed)
        mocks[_CLEANUP_MOCK_KEY].assert_not_called()

    def test_open_pr_returns_false(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(_OPEN_PR_ISSUE_NUMBER, label=_VALIDATING_LABEL)
        gh.add_issue(issue)
        pr = FakePR(
            number=_OPEN_PR_NUMBER,
            head_branch=_issue_branch(_OPEN_PR_ISSUE_NUMBER),
            head=FakePRRef(sha=_PR_HEAD_SHA),
            merged=False, state="open",
        )
        gh.add_pr(pr)
        state = _state_with_pr_number(
            gh,
            _OPEN_PR_ISSUE_NUMBER,
            _OPEN_PR_NUMBER,
        )

        mocks = self._run(
            lambda: self.assertFalse(
                terminals._finalize_if_pr_merged(
                    gh, _TEST_SPEC, issue, state
                )
            ),
            run_agent=_agent(),
        )
        self.assertEqual(gh.label_history, [])
        self.assertFalse(issue.closed)
        mocks[_CLEANUP_MOCK_KEY].assert_not_called()

    def test_closed_unmerged_pr_returns_false(self) -> None:
        # Closed without merge is `rejected` territory; the helper covers
        # only the merged case so the in_review / fixing / resolving_conflict
        # handlers stay in charge of the rejected arc with their own
        # `closed_without_merge_at` stamp + `pr_closed_without_merge` event.
        gh = FakeGitHubClient()
        issue = make_issue(_CLOSED_PR_ISSUE_NUMBER, label=_VALIDATING_LABEL)
        gh.add_issue(issue)
        pr = FakePR(
            number=_CLOSED_PR_NUMBER,
            head_branch=_issue_branch(_CLOSED_PR_ISSUE_NUMBER),
            head=FakePRRef(sha=_PR_HEAD_SHA),
            merged=False, state=_STATE_CLOSED,
        )
        gh.add_pr(pr)
        state = _state_with_pr_number(
            gh,
            _CLOSED_PR_ISSUE_NUMBER,
            _CLOSED_PR_NUMBER,
        )

        mocks = self._run(
            lambda: self.assertFalse(
                terminals._finalize_if_pr_merged(
                    gh, _TEST_SPEC, issue, state
                )
            ),
            run_agent=_agent(),
        )
        self.assertEqual(gh.label_history, [])
        self.assertFalse(issue.closed)
        mocks[_CLEANUP_MOCK_KEY].assert_not_called()


class FinalizeMergedPrTest(unittest.TestCase, _PatchedWorkflowMixin):
    """Merged PRs finalize labels, cleanup branches, and post usage."""

    def test_merged_pr_finalizes_open_issue(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(
            _OPEN_ISSUE_MERGED_NUMBER,
            label=_IMPLEMENTING_LABEL,
        )
        gh.add_issue(issue)
        gh.add_pr(
            FakePR(
                number=_OPEN_ISSUE_MERGED_PR_NUMBER,
                head_branch=_issue_branch(_OPEN_ISSUE_MERGED_NUMBER),
                head=FakePRRef(sha=_PR_HEAD_SHA),
                merged=True,
                state=_STATE_CLOSED,
            ),
        )
        state = _state_with_pr_number(
            gh,
            _OPEN_ISSUE_MERGED_NUMBER,
            _OPEN_ISSUE_MERGED_PR_NUMBER,
            branch=_issue_branch(_OPEN_ISSUE_MERGED_NUMBER),
        )

        mocks = self._run(
            lambda: self.assertTrue(
                terminals._finalize_if_pr_merged(
                    gh, _TEST_SPEC, issue, state
                )
            ),
            run_agent=_agent(),
        )
        self.assertIn((_OPEN_ISSUE_MERGED_NUMBER, "done"), gh.label_history)
        self.assertIn("merged_at", state.data)
        self.assertTrue(issue.closed)
        mocks[_CLEANUP_MOCK_KEY].assert_called_once_with(
            gh,
            _TEST_SPEC,
            _OPEN_ISSUE_MERGED_NUMBER,
            branch=_issue_branch(_OPEN_ISSUE_MERGED_NUMBER),
        )
        # An `external`-merge audit event is emitted, naming the entry
        # stage the issue was swept from.
        merged_event = next(
            event for event in gh.recorded_events
            if event["event"] == EVENT_PR_MERGED
        )
        self.assertEqual(merged_event.get("merge_method"), "external")
        self.assertEqual(merged_event.get("stage"), _IMPLEMENTING_STAGE)

    def test_merged_pr_finalizes_closed_issue(self) -> None:
        # An externally-merged PR with `Resolves #N` auto-closes the issue
        # before the orchestrator can react. The helper must still
        # finalize the label (and not attempt to re-close).
        gh = FakeGitHubClient()
        issue = make_issue(
            _CLOSED_ISSUE_MERGED_NUMBER,
            label=_VALIDATING_LABEL,
        )
        issue.closed = True
        gh.add_issue(issue)
        pr = FakePR(
            number=_CLOSED_ISSUE_MERGED_PR_NUMBER,
            head_branch=_issue_branch(_CLOSED_ISSUE_MERGED_NUMBER),
            head=FakePRRef(sha=_PR_HEAD_SHA),
            merged=True, state=_STATE_CLOSED,
        )
        gh.add_pr(pr)
        state = _state_with_pr_number(
            gh,
            _CLOSED_ISSUE_MERGED_NUMBER,
            _CLOSED_ISSUE_MERGED_PR_NUMBER,
        )

        self._run(
            lambda: self.assertTrue(
                terminals._finalize_if_pr_merged(
                    gh, _TEST_SPEC, issue, state
                )
            ),
            run_agent=_agent(),
        )
        self.assertIn((_CLOSED_ISSUE_MERGED_NUMBER, "done"), gh.label_history)
        self.assertTrue(issue.closed)

    def test_posts_tracked_usage_verdict(self) -> None:
        # The terminal finalize surfaces the cumulative usage verdict as a
        # tracked comment posted BEFORE `write_pinned_state`, so its id is
        # persisted in `orchestrator_comment_ids` alongside the merge stamp.
        gh = FakeGitHubClient()
        issue = make_issue(_USAGE_ISSUE_NUMBER, label=_IMPLEMENTING_LABEL)
        gh.add_issue(issue)
        gh.add_pr(
            FakePR(
                number=_USAGE_PR_NUMBER,
                head_branch=_issue_branch(_USAGE_ISSUE_NUMBER),
                head=FakePRRef(sha=_PR_HEAD_SHA),
                merged=True,
                state=_STATE_CLOSED,
            ),
        )
        state = _state_with_pr_number(
            gh,
            _USAGE_ISSUE_NUMBER,
            _USAGE_PR_NUMBER,
            issue_agent_runs=3,
            issue_total_tokens=_USAGE_TOTAL_TOKENS,
            issue_total_cost_usd=_USAGE_TOTAL_COST,
            issue_cost_sources=["estimated"],
        )

        self._run(
            lambda: terminals._finalize_if_pr_merged(
                gh, _TEST_SPEC, issue, state
            ),
            run_agent=_agent(),
        )

        receipts = _receipt_bodies(gh, _USAGE_ISSUE_NUMBER)
        self.assertEqual(len(receipts), 1)
        self.assertIn(
            "this issue: 3 agent runs · 45,200 tokens · $0.87 (est.)",
            receipts[0],
        )
        # Posted before the write, so its id rode the same persisted state.
        receipt_comment = _receipt_comment(issue)
        self.assertIn(
            receipt_comment.id,
            gh.pinned_data(_USAGE_ISSUE_NUMBER).get(
                "orchestrator_comment_ids",
                [],
            ),
        )

    def test_no_counters_posts_no_verdict(self) -> None:
        # No agent ever ran against this issue (external-merge of a
        # never-worked issue): the finalize skips the zero receipt.
        gh = FakeGitHubClient()
        issue = make_issue(_NO_USAGE_ISSUE_NUMBER, label=_IMPLEMENTING_LABEL)
        gh.add_issue(issue)
        gh.add_pr(
            FakePR(
                number=_NO_USAGE_PR_NUMBER,
                head_branch=_issue_branch(_NO_USAGE_ISSUE_NUMBER),
                head=FakePRRef(sha=_PR_HEAD_SHA),
                merged=True,
                state=_STATE_CLOSED,
            ),
        )
        state = _state_with_pr_number(
            gh,
            _NO_USAGE_ISSUE_NUMBER,
            _NO_USAGE_PR_NUMBER,
        )

        self._run(
            lambda: terminals._finalize_if_pr_merged(
                gh, _TEST_SPEC, issue, state
            ),
            run_agent=_agent(),
        )

        self.assertEqual(_receipt_bodies(gh, _NO_USAGE_ISSUE_NUMBER), [])


class PrTerminalOneReadingTest(unittest.TestCase, _PatchedWorkflowMixin):
    """Both endings of one pull request, decided off one fetch.

    The stages that carry no PR-state arc of their own ask for both, and two
    fetches would be two moments: a merge landing between them answers `open`
    to the first and `merged` to the second, which a closed-without-merge arc
    is right to ignore -- and the stage behind it runs anyway, spawning a
    reviewer or measuring a candidate onto work that has already landed.
    """

    def test_it_spends_one_reading_for_both(self) -> None:
        # The direct pin, because the race is invisible in the outcome of any
        # single run: what closed the window is that there is no second read
        # for a merge to land inside.
        gh, issue, state = self._linked(merged=False, pr_state="open")
        counted = _CountsTheReads(gh)

        with counted.held():
            self._run(
                lambda: self.assertFalse(
                    terminals._pr_terminal_stops_the_tick(
                        gh, _TEST_SPEC, issue, state,
                    ),
                ),
                run_agent=_agent(),
            )

        self.assertEqual(counted.reads, 1)

    def test_each_ending_is_decided(self) -> None:
        # And both are actually answered off that one reading, so the single
        # fetch is not bought by dropping one of the two terminals.
        for described, merged, label in (
            ("merged", True, "done"),
            ("closed without merging", False, "rejected"),
        ):
            with self.subTest(pull_request=described):
                history = self._finalized(merged)

                self.assertIn((_ONE_READING_ISSUE_NUMBER, label), history)

    def _finalized(self, merged: bool) -> list:
        """Run the terminal over an ended pull request, and report the labels."""
        gh, issue, state = self._linked(merged=merged, pr_state=_STATE_CLOSED)
        self._run(
            lambda: self.assertTrue(
                terminals._pr_terminal_stops_the_tick(
                    gh, _TEST_SPEC, issue, state,
                ),
            ),
            run_agent=_agent(),
        )
        return gh.label_history

    def _linked(self, *, merged: bool, pr_state: str):
        """An issue whose recorded pull request is in that state."""
        gh, issue = _client_with_issue(
            _ONE_READING_ISSUE_NUMBER, _VALIDATING_LABEL,
        )
        gh.add_pr(FakePR(
            number=_ONE_READING_PR_NUMBER,
            head_branch=_issue_branch(_ONE_READING_ISSUE_NUMBER),
            head=FakePRRef(sha=_PR_HEAD_SHA),
            merged=merged,
            state=pr_state,
        ))
        return gh, issue, _state_with_pr_number(
            gh, _ONE_READING_ISSUE_NUMBER, _ONE_READING_PR_NUMBER,
        )


class _CountsTheReads:
    """How many times one terminal call fetched the pull request it decides on.

    A class rather than a `Mock` wrapper because the fake's own lookup has to
    keep working: what is being counted is the number of MOMENTS the answer
    was read at, and a double that stopped returning the pull request would
    measure nothing.
    """

    def __init__(self, github) -> None:
        self.reads = 0
        self._github = github
        self._wrapped = github.get_pr

    def __call__(self, *called, **options):
        self.reads += 1
        return self._wrapped(*called, **options)

    def held(self):
        """Patch the lookup this counts, for the duration of one call."""
        return patch.object(self._github, "get_pr", self)


if __name__ == "__main__":
    unittest.main()
