# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Fixtures for the tick that finds a discussion over rather than running one.

The seeds here are the two shapes that tick can arrive in: an issue whose plan
its publication already put on a pull request, and one a human closed with no
plan on a pull request at all. Both records the publication writes are seeded
together, because the stage reads them as a pair -- a `pr_number` alone is one
an issue relabeled here from a PR stage arrived carrying.

`_TerminalRun` carries the client and the issue so the readings a terminal is
judged by -- what was written, what was posted, what was emitted -- are asked
of one object rather than reassembled in every test.

`_TerminalTick` exists for the teardown alone. The hermetic patch set installs
its own neutral `_cleanup_terminal_branch`, so a test whose subject IS the
teardown has to land its mock INSIDE the tick, where it is the one the terminal
resolves rather than the one that was replaced.
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any
from unittest.mock import MagicMock

from orchestrator.workflow.stages.discussion import handler as _discussion
from tests.support.fakes import FakePR, FakePRRef
from tests.workflow.fixtures import (
    _TEST_SPEC,
    STAGE_DISCUSSION,
    STATE_OPEN,
    _agent,
    _issue_branch,
)
from tests.workflow.git_owners import seam_patch
from tests.workflow.stages.discussion import discussion_test_support as _support
from tests.workflow.stages.discussion.discussion_test_support import _DiscussionWorkflowMixin

PLAN_SHA = "plan-commit-sha"

# What the agent would say if a round opened at all, which none of these ticks
# may reach.
UNEXPECTED_AGENT_MESSAGE = "no round may open on a finished discussion"

KEY_MERGED_AT = "merged_at"

KEY_CLOSED_WITHOUT_MERGE_AT = "closed_without_merge_at"

KEY_TRACKED_COMMENT_IDS = "orchestrator_comment_ids"

_STAGE_KEY = "stage"

_PR_NUMBER_KEY = "pr_number"

_SHA_KEY = "sha"

_EVENT_KEY = "event"

_RECEIPT_PREFIX = ":receipt:"

# What GitHub declining to say what the plan PR has become looks like from
# here: any exception at all, since the stage may not decide on a read it
# never took.
_LOOKUP_REFUSED = "GitHub declined the plan PR lookup"

# The counters a discussion that ran a few rounds reaches its terminal holding,
# and the line the receipt renders them as.
RECEIPT_COUNTERS = MappingProxyType({
    "issue_agent_runs": 3,
    "issue_total_tokens": 4200,
    "issue_total_cost_usd": 0.42,
    "issue_cost_sources": ["reported"],
})

RECEIPT_LINE = "this issue: 3 agent runs · 4,200 tokens · $0.42"


@dataclass(frozen=True)
class _PlanScenario:
    """A published plan and the pull request the humans have it on."""

    issue_number: int
    pr_number: int
    merged: bool = False
    pr_state: str = STATE_OPEN
    issue_closed: bool = False


@dataclass(frozen=True)
class _TerminalRun:
    """One seeded issue, and the readings its terminal is judged by."""

    gh: Any
    issue: Any

    @property
    def branch(self) -> str:
        return _issue_branch(self.issue.number)

    @property
    def pinned(self) -> dict:
        return self.gh.pinned_data(self.issue.number)

    def receipts(self) -> list[str]:
        return [
            body
            for issue_number, body in self.gh.posted_comments
            if issue_number == self.issue.number
            and body.startswith(_RECEIPT_PREFIX)
        ]

    def tracked_receipt_id(self) -> int | None:
        """The id of the receipt comment, as the thread carries it."""
        for comment in self.issue.comments:
            if comment.body.startswith(_RECEIPT_PREFIX):
                return comment.id
        return None

    def events(self, event_name: str) -> list[dict]:
        return [
            event
            for event in self.gh.recorded_events
            if event[_EVENT_KEY] == event_name
        ]

    def watch_pr_lookups(self) -> Any:
        """Make the plan-PR fetch observable, keeping its real answer.

        A tick that polled an OPEN pull request and a tick that returned
        without asking are indistinguishable by their effects -- neither
        writes, labels, comments, spawns, or reaps anything. Whether GitHub
        was asked at all is the only thing that tells them apart, so the arc
        that holds has to assert on the lookup itself.
        """
        lookup = MagicMock(wraps=self.gh.get_pr)
        self.gh.get_pr = lookup
        return lookup

    def refuse_pr_lookups(self) -> Any:
        """Have GitHub decline to say what the plan PR has become."""
        lookup = MagicMock(side_effect=RuntimeError(_LOOKUP_REFUSED))
        self.gh.get_pr = lookup
        return lookup


class _TerminalTick:
    """One `_handle_discussion` call, optionally under the caller's teardown."""

    def __init__(self, run: _TerminalRun, teardown=None) -> None:
        self._run = run
        self._teardown = teardown

    def __call__(self) -> None:
        with contextlib.ExitStack() as stack:
            if self._teardown is not None:
                stack.enter_context(
                    seam_patch(_support.CLEANUP_TERMINAL_BRANCH, self._teardown),
                )
            _discussion._handle_discussion(
                self._run.gh, _TEST_SPEC, self._run.issue,
            )


def _seed_published_plan(
    scenario: _PlanScenario, **extra_state,
) -> _TerminalRun:
    """A discussion holding the plan PR its publication left behind."""
    gh, issue = _support._seed_discussion(scenario.issue_number)
    issue.closed = scenario.issue_closed
    branch = _issue_branch(scenario.issue_number)
    gh.add_pr(FakePR(
        number=scenario.pr_number,
        head_branch=branch,
        head=FakePRRef(sha=PLAN_SHA),
        merged=scenario.merged,
        state=scenario.pr_state,
    ))
    gh.seed_state(
        scenario.issue_number,
        **{
            _support.KEY_PLAN_PATH: f"plans/issue-{scenario.issue_number}.md",
            _support.KEY_PLAN_SHA: PLAN_SHA,
            _support.KEY_PR_NUMBER: scenario.pr_number,
            _support.KEY_BRANCH: branch,
            **extra_state,
        },
    )
    return _TerminalRun(gh, issue)


def _seed_closed_discussion(issue_number: int, **state) -> _TerminalRun:
    """A discussion a human closed before any plan reached a pull request."""
    gh, issue = _support._seed_discussion(issue_number)
    issue.closed = True
    gh.seed_state(issue_number, awaiting_human=True, **state)
    return _TerminalRun(gh, issue)


def _seed_interrupted_publication(
    scenario: _PlanScenario, *, with_pr: bool = True,
) -> _TerminalRun:
    """The crash window: a pull request opened, its number never written.

    The marker is the ONLY thing seeded, because it is the only thing a real
    one of these carries. The publication's first durable write records the
    tip it is about to push and nothing else; `branch`, `pr_number`, and the
    plan path all land together in the write the crash skipped. Seeding
    `branch` here would hand the tick the very answer it has to work out for
    itself -- and would hide the resolver reading a recovered `pr_number` with
    no branch beside it as a legacy in-flight PR on `orchestrator/issue-N`.

    `with_pr=False` is the same window with nothing out there to find -- a
    push that never landed, or a tick that died before it -- which is what
    tells a genuine pre-PR close from this one.
    """
    gh, issue = _support._seed_discussion(scenario.issue_number)
    issue.closed = scenario.issue_closed
    if with_pr:
        gh.add_pr(FakePR(
            number=scenario.pr_number,
            head_branch=_issue_branch(scenario.issue_number),
            head=FakePRRef(sha=PLAN_SHA),
            merged=scenario.merged,
            state=scenario.pr_state,
        ))
    gh.seed_state(
        scenario.issue_number, **{_support.KEY_PUBLISHING_SHA: PLAN_SHA},
    )
    return _TerminalRun(gh, issue)


class _DiscussionTerminalMixin(_DiscussionWorkflowMixin):
    """One terminal tick, and the two readings every arc is judged by."""

    def assert_finalized(
        self, run: _TerminalRun, *, label: str, stamp: str,
    ) -> None:
        """The shared tail: stamped, relabeled, and the issue closed."""
        self.assertEqual(run.gh.label_history, [(run.issue.number, label)])
        self.assertIn(stamp, run.pinned)
        self.assertTrue(run.issue.closed)

    def assert_held(self, run: _TerminalRun, mocks) -> None:
        """A tick that decided nothing: no write, no comment, no teardown."""
        self.assertEqual(run.gh.label_history, [])
        self.assertEqual(run.gh.write_state_calls, 0)
        self.assertEqual(run.gh.posted_comments, [])
        self.assertEqual(run.gh.recorded_events, [])
        mocks[_support.RUN_AGENT].assert_not_called()
        self.assert_worktree_preserved(mocks)

    def assert_reaped(self, run: _TerminalRun, teardown) -> None:
        """The worktree and both branches went, and by the recorded ref."""
        teardown.assert_called_once_with(
            run.gh, _TEST_SPEC, run.issue.number, branch=run.branch,
        )

    def assert_receipt(self, run: _TerminalRun) -> None:
        """One receipt, carrying the counters, tracked by the state it rode."""
        receipts = run.receipts()
        self.assertEqual(len(receipts), 1)
        self.assertIn(RECEIPT_LINE, receipts[0])
        self.assertIn(
            run.tracked_receipt_id(), run.pinned[KEY_TRACKED_COMMENT_IDS],
        )

    def assert_terminal_event(
        self, run: _TerminalRun, event_name: str, *, pr_number: int,
    ) -> None:
        """The one event this arc emits, and what it attributes the run to."""
        emitted = self.only_event(run, event_name)
        self.assertEqual(emitted[_STAGE_KEY], STAGE_DISCUSSION)
        self.assertEqual(emitted[_PR_NUMBER_KEY], pr_number)
        self.assertEqual(emitted[_SHA_KEY], PLAN_SHA)

    def only_event(self, run: _TerminalRun, event_name: str) -> dict:
        emitted = run.events(event_name)
        self.assertEqual(len(emitted), 1)
        return emitted[0]

    def _run_terminal(self, run: _TerminalRun, teardown=None):
        return self._run(
            _TerminalTick(run, teardown),
            run_agent=_agent(last_message=UNEXPECTED_AGENT_MESSAGE),
        )
