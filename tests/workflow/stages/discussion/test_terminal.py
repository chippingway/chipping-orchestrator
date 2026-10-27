# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What ends a discussion, and what it keeps until one of them does.

Every module beside this one covers a conversation still running. This one
covers the tick that finds it over: the plan PR the humans merged or turned
down, the plan PR they have not decided about yet, and the issue somebody
closed with no plan on a pull request at all.

The two halves of that are asserted together throughout, because each is only
right given the other. A terminal has to record itself -- the stamp, the label,
the receipt, the event, the close -- and only then reap the checkout and the
branches; a hold has to record nothing at all and reap nothing, since what the
worktree carries is what the open pull request is open against.
"""

from __future__ import annotations

import logging
import unittest
from dataclasses import dataclass
from unittest.mock import MagicMock

from orchestrator.workflow.stages.discussion import plan_terminal as _plan_terminal
from tests.workflow.fixtures import (
    EVENT_PR_CLOSED_WITHOUT_MERGE,
    EVENT_PR_MERGED,
    LABEL_DISCUSSION,
    LABEL_DONE,
    LABEL_REJECTED,
    STATE_CLOSED,
)
from tests.workflow.stages.discussion.discussion_terminal_test_support import (
    KEY_CLOSED_WITHOUT_MERGE_AT,
    KEY_MERGED_AT,
    RECEIPT_COUNTERS,
    _DiscussionTerminalMixin,
    _PlanScenario,
    _seed_closed_discussion,
    _seed_interrupted_publication,
    _seed_published_plan,
)
from tests.workflow.stages.discussion.discussion_test_support import (
    CLEANUP_TERMINAL_BRANCH,
    KEY_BRANCH,
    KEY_PR_NUMBER,
    PARK_DISCUSSION_RESPONSE,
    PUSH_BRANCH,
    RUN_AGENT,
    _issue_branch,
)

_MERGED_ISSUE_NUMBER = 960
_MERGED_PR_NUMBER = 96000
_REJECTED_ISSUE_NUMBER = 961
_REJECTED_PR_NUMBER = 96100
_OPEN_ISSUE_NUMBER = 962
_OPEN_PR_NUMBER = 96200
_HELD_ISSUE_NUMBER = 963
_HELD_PR_NUMBER = 96300
_RESTART_ISSUE_NUMBER = 964
_RESTART_PR_NUMBER = 96400
_PRE_PR_ISSUE_NUMBER = 965
_INHERITED_ISSUE_NUMBER = 966
_INHERITED_PR_NUMBER = 96600
_ORDERED_ISSUE_NUMBER = 967
_ORDERED_PR_NUMBER = 96700
_FAILED_ISSUE_NUMBER = 968
_FAILED_PR_NUMBER = 96800
_RECEIPT_DONE_ISSUE_NUMBER = 969
_RECEIPT_DONE_PR_NUMBER = 96900
_RECEIPT_REJECTED_ISSUE_NUMBER = 970
_RECEIPT_REJECTED_PR_NUMBER = 97000
_UNREADABLE_ISSUE_NUMBER = 971
_UNREADABLE_PR_NUMBER = 97100
_CRASH_MERGED_ISSUE_NUMBER = 972
_CRASH_MERGED_PR_NUMBER = 97200
_CRASH_CLOSED_ISSUE_NUMBER = 973
_CRASH_CLOSED_PR_NUMBER = 97300
_CRASH_OPEN_ISSUE_NUMBER = 974
_CRASH_OPEN_PR_NUMBER = 97400
_CRASH_NO_PR_ISSUE_NUMBER = 975
_CRASH_NO_PR_NUMBER = 97500

_MERGED = _PlanScenario(
    _MERGED_ISSUE_NUMBER, _MERGED_PR_NUMBER, merged=True, pr_state=STATE_CLOSED,
)
_REJECTED = _PlanScenario(
    _REJECTED_ISSUE_NUMBER, _REJECTED_PR_NUMBER, pr_state=STATE_CLOSED,
)
_OPEN = _PlanScenario(_OPEN_ISSUE_NUMBER, _OPEN_PR_NUMBER)
_UNREADABLE = _PlanScenario(
    _UNREADABLE_ISSUE_NUMBER, _UNREADABLE_PR_NUMBER,
)
_HELD = _PlanScenario(
    _HELD_ISSUE_NUMBER, _HELD_PR_NUMBER, issue_closed=True,
)
_RESTART = _PlanScenario(
    _RESTART_ISSUE_NUMBER, _RESTART_PR_NUMBER, issue_closed=True,
)
_ORDERED = _PlanScenario(
    _ORDERED_ISSUE_NUMBER,
    _ORDERED_PR_NUMBER,
    merged=True,
    pr_state=STATE_CLOSED,
)
_FAILED_TEARDOWN = _PlanScenario(
    _FAILED_ISSUE_NUMBER, _FAILED_PR_NUMBER, pr_state=STATE_CLOSED,
)

# The crash window, on an issue a human closed inside it: the publication
# opened its pull request and died before writing the number down, so the
# marker is the only thing that still points at what the humans decided.
_CRASH_MERGED = _PlanScenario(
    _CRASH_MERGED_ISSUE_NUMBER,
    _CRASH_MERGED_PR_NUMBER,
    merged=True,
    pr_state=STATE_CLOSED,
    issue_closed=True,
)
_CRASH_CLOSED = _PlanScenario(
    _CRASH_CLOSED_ISSUE_NUMBER,
    _CRASH_CLOSED_PR_NUMBER,
    pr_state=STATE_CLOSED,
    issue_closed=True,
)
_CRASH_OPEN = _PlanScenario(
    _CRASH_OPEN_ISSUE_NUMBER, _CRASH_OPEN_PR_NUMBER, issue_closed=True,
)
_CRASH_NO_PR = _PlanScenario(
    _CRASH_NO_PR_ISSUE_NUMBER, _CRASH_NO_PR_NUMBER, issue_closed=True,
)


@dataclass(frozen=True)
class _CrashWindowCase:
    """One verdict the humans left inside the crash window, and its ending."""

    label: str
    stamp: str
    event_name: str
    scenario: _PlanScenario


_CRASH_DECIDED_CASES = (
    _CrashWindowCase(
        LABEL_DONE, KEY_MERGED_AT, EVENT_PR_MERGED, _CRASH_MERGED,
    ),
    _CrashWindowCase(
        LABEL_REJECTED,
        KEY_CLOSED_WITHOUT_MERGE_AT,
        EVENT_PR_CLOSED_WITHOUT_MERGE,
        _CRASH_CLOSED,
    ),
)

# One receipt case per ending, since the receipt is what the whole
# conversation cost and neither ending may drop it.
_RECEIPT_CASES = (
    (
        LABEL_DONE,
        _PlanScenario(
            _RECEIPT_DONE_ISSUE_NUMBER,
            _RECEIPT_DONE_PR_NUMBER,
            merged=True,
            pr_state=STATE_CLOSED,
        ),
    ),
    (
        LABEL_REJECTED,
        _PlanScenario(
            _RECEIPT_REJECTED_ISSUE_NUMBER,
            _RECEIPT_REJECTED_PR_NUMBER,
            pr_state=STATE_CLOSED,
        ),
    ),
)

_PRE_PR_CASES = (
    (_PRE_PR_ISSUE_NUMBER, {"park_reason": PARK_DISCUSSION_RESPONSE}),
    (
        _INHERITED_ISSUE_NUMBER,
        {
            KEY_PR_NUMBER: _INHERITED_PR_NUMBER,
            KEY_BRANCH: _issue_branch(_INHERITED_ISSUE_NUMBER),
        },
    ),
)

_TEARDOWN_FAILED = "worktree removal failed"

# The flat pre-namespace ref, which no live work stands on. Spelled out
# rather than imported, so a recovery that starts answering with it fails
# here instead of agreeing with itself.
_LEGACY_BRANCH = "orchestrator/issue-{issue}"


class _TeardownWatcher:
    """A teardown that records what the tick had done before it ran.

    Every field is read at call time rather than after the tick, because
    what it is here to prove is the ORDER: a value read afterwards would be
    the same whichever side of the teardown wrote it.
    """

    def __init__(self, run) -> None:
        self._run = run
        self.writes = 0
        self.labels: tuple = ()
        self.receipts: tuple = ()
        self.issue_closed = False

    def __call__(self, *_args, **_kwargs) -> None:
        self.writes = self._run.gh.write_state_calls
        self.labels = tuple(self._run.gh.label_history)
        self.receipts = tuple(self._run.receipts())
        self.issue_closed = self._run.issue.closed


class DiscussionPlanPrTerminalTest(unittest.TestCase, _DiscussionTerminalMixin):
    """The plan PR is polled before any agent path, and it decides the tick.

    A design the humans took is `done` and one they turned down is `rejected`;
    either way the conversation is over, the run is attributed to `discussion`,
    and the branch the plan was published on is no longer anybody's to keep.
    """

    def test_merged_plan_pr_finishes_done(self) -> None:
        run = _seed_published_plan(_MERGED)

        mocks = self._run_terminal(run)

        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(run.gh.opened_prs, [])
        self.assert_finalized(run, label=LABEL_DONE, stamp=KEY_MERGED_AT)
        self.assert_terminal_event(
            run, EVENT_PR_MERGED, pr_number=_MERGED.pr_number,
        )
        self.assert_reaped(run, mocks[CLEANUP_TERMINAL_BRANCH])

    def test_closed_plan_pr_finishes_rejected(self) -> None:
        run = _seed_published_plan(_REJECTED)

        mocks = self._run_terminal(run)

        mocks[RUN_AGENT].assert_not_called()
        self.assert_finalized(
            run, label=LABEL_REJECTED, stamp=KEY_CLOSED_WITHOUT_MERGE_AT,
        )
        self.assert_terminal_event(
            run, EVENT_PR_CLOSED_WITHOUT_MERGE, pr_number=_REJECTED.pr_number,
        )
        self.assert_reaped(run, mocks[CLEANUP_TERMINAL_BRANCH])

    def test_terminals_post_the_tracked_receipt(self) -> None:
        for label, scenario in _RECEIPT_CASES:
            with self.subTest(label=label):
                run = _seed_published_plan(scenario, **RECEIPT_COUNTERS)

                self._run_terminal(run)

                self.assertEqual(
                    run.gh.label_history, [(run.issue.number, label)],
                )
                self.assert_receipt(run)

    def test_open_plan_pr_retains_the_checkout(self) -> None:
        # The design is still with the humans, so the tick decides nothing --
        # and above all reaps nothing: the worktree and the branches are what
        # the pull request they are reading is open against.
        run = _seed_published_plan(_OPEN)
        lookup = run.watch_pr_lookups()

        mocks = self._run_terminal(run)

        # The poll is the behavior here. Every effect asserted below is one a
        # tick that ended without asking GitHub anything would produce too, so
        # the lookup is what separates a hold from a blind early return.
        lookup.assert_called_once_with(_OPEN.pr_number)
        self.assert_held(run, mocks)
        self.assert_nothing_published(run.gh, mocks)
        self.assertFalse(run.issue.closed)

    def test_unreadable_plan_pr_holds_the_tick(self) -> None:
        # Nothing below the fetch is a claim anybody can make about a pull
        # request GitHub declined to serve, so the tick stops right there --
        # no round, no finalize, and no teardown of a branch that may still be
        # carrying a design under review. The next poll asks again.
        run = _seed_published_plan(_UNREADABLE)
        lookup = run.refuse_pr_lookups()

        with self.assertLogs(_plan_terminal.log, level=logging.ERROR):
            mocks = self._run_terminal(run)

        lookup.assert_called_once_with(_UNREADABLE.pr_number)
        self.assert_held(run, mocks)
        self.assert_nothing_published(run.gh, mocks)


class DiscussionClosedIssueTerminalTest(
    unittest.TestCase, _DiscussionTerminalMixin,
):
    """A human closing the issue, with and without a plan on a pull request.

    With one, the close says nothing about the design: the pull request is
    still the thing that decides, so the issue keeps the `discussion` label
    that leaves it inside the closed-issue sweep, and its checkout, until the
    pull request resolves. Without one there is nothing left to wait for, and
    the flip to `rejected` is what takes the issue back out of that sweep.
    """

    def test_closed_issue_waits_for_an_open_pr(self) -> None:
        run = _seed_published_plan(_HELD)
        lookup = run.watch_pr_lookups()

        mocks = self._run_terminal(run)

        lookup.assert_called_once_with(_HELD.pr_number)
        self.assert_held(run, mocks)
        # The label is what the sweep finds a closed issue by, so a terminal
        # flip here would strand the branch: nothing would revisit the issue
        # once the pull request finally resolved.
        self.assertEqual(run.gh.workflow_label(run.issue), LABEL_DISCUSSION)

    def test_closed_issue_finishes_on_the_merge(self) -> None:
        # Nothing survives between ticks but pinned state, so the hold and the
        # terminal are separate handler calls over the same issue -- which is
        # also what an orchestrator restart between them looks like.
        run = _seed_published_plan(_RESTART)

        self.assert_held(run, self._run_terminal(run))

        plan_pr = run.gh.get_pr(_RESTART.pr_number)
        plan_pr.merged = True
        plan_pr.state = STATE_CLOSED
        mocks = self._run_terminal(run)

        self.assert_finalized(run, label=LABEL_DONE, stamp=KEY_MERGED_AT)
        self.assert_terminal_event(
            run, EVENT_PR_MERGED, pr_number=_RESTART.pr_number,
        )
        self.assert_reaped(run, mocks[CLEANUP_TERMINAL_BRANCH])

    def test_pre_pr_close_rejects_without_teardown(self) -> None:
        # Two shapes of the same pre-PR close: a conversation mid-round, and
        # one relabeled here carrying somebody else's `pr_number`. Neither has
        # a plan on a pull request, so neither polls one -- and neither deletes
        # a branch, which in the second case is a live PR's.
        for issue_number, seeded in _PRE_PR_CASES:
            with self.subTest(issue=issue_number):
                run = _seed_closed_discussion(issue_number, **seeded)

                mocks = self._run_terminal(run)

                mocks[RUN_AGENT].assert_not_called()
                self.assert_finalized(
                    run,
                    label=LABEL_REJECTED,
                    stamp=KEY_CLOSED_WITHOUT_MERGE_AT,
                )
                self.assertEqual(run.gh.opened_prs, [])
                self.assertEqual(run.events(EVENT_PR_CLOSED_WITHOUT_MERGE), [])
                self.assert_worktree_preserved(mocks)


class DiscussionCrashWindowTerminalTest(
    unittest.TestCase, _DiscussionTerminalMixin,
):
    """A close that lands between the plan PR being opened and recorded.

    The publication writes its marker, pushes, opens the pull request, and
    only then writes the number down. A tick that dies in the middle leaves a
    real pull request with nothing pinned pointing at it -- and the humans can
    decide the issue, or that pull request, inside the same window. Read as a
    discussion that never published, the close would be finalized on its own
    and the label that keeps the issue in the closed-issue sweep would go with
    it, leaving the branch and the worktree for nothing to reap.
    """

    def test_a_decided_pr_finishes_the_closed_issue(self) -> None:
        for case in _CRASH_DECIDED_CASES:
            with self.subTest(label=case.label):
                self._assert_crash_window_finalized(case)

    def test_an_open_pr_holds_the_closed_issue(self) -> None:
        # The plan is on a pull request nobody has decided, so the close says
        # nothing about it. Finalizing here would take the issue out of the
        # sweep that is the only thing still watching that pull request.
        run = _seed_interrupted_publication(_CRASH_OPEN)

        mocks = self._run_terminal(run)

        self.assert_held(run, mocks)
        self.assert_nothing_published(run.gh, mocks)
        self.assertEqual(run.gh.workflow_label(run.issue), LABEL_DISCUSSION)

    def test_no_pr_leaves_the_pre_pr_close_alone(self) -> None:
        # The same marker with nothing out there carrying its commit -- a push
        # that never landed. There is no pull request to wait for, so the close
        # is the whole signal and the ordinary pre-PR ending applies.
        run = _seed_interrupted_publication(_CRASH_NO_PR, with_pr=False)

        mocks = self._run_terminal(run)

        mocks[RUN_AGENT].assert_not_called()
        self.assert_finalized(
            run, label=LABEL_REJECTED, stamp=KEY_CLOSED_WITHOUT_MERGE_AT,
        )
        self.assertEqual(run.events(EVENT_PR_CLOSED_WITHOUT_MERGE), [])
        self.assert_worktree_preserved(mocks)

    def _assert_crash_window_finalized(self, case) -> None:
        run = _seed_interrupted_publication(case.scenario)

        mocks = self._run_terminal(run)

        mocks[RUN_AGENT].assert_not_called()
        mocks[PUSH_BRANCH].assert_not_called()
        self.assertEqual(run.gh.opened_prs, [])
        self.assert_finalized(run, label=case.label, stamp=case.stamp)
        # Both records are made before the tail reads them: the event names
        # the number, and the teardown resolves its ref from the branch. The
        # branch is the one the stage really pushed to -- a recovered number
        # with no branch beside it is a record the resolver refuses, and a
        # flat `orchestrator/issue-N` beside it would reap a ref the stage
        # never pushed, leaving the real local and remote branches standing.
        self.assertEqual(
            (run.pinned[KEY_PR_NUMBER], run.pinned[KEY_BRANCH]),
            (case.scenario.pr_number, run.branch),
        )
        self.assertNotEqual(
            run.pinned[KEY_BRANCH],
            _LEGACY_BRANCH.format(issue=run.issue.number),
        )
        self.assert_terminal_event(
            run, case.event_name, pr_number=case.scenario.pr_number,
        )
        self.assert_reaped(run, mocks[CLEANUP_TERMINAL_BRANCH])


class DiscussionTeardownOrderTest(unittest.TestCase, _DiscussionTerminalMixin):
    """Teardown is last, and nothing before it depends on teardown working.

    The order is the contract: an operator who finds a leftover worktree still
    has an issue that says what happened to it, while a terminal recorded after
    a teardown that failed would be one nothing could re-derive.
    """

    def test_teardown_runs_after_the_record(self) -> None:
        run = _seed_published_plan(_ORDERED, **RECEIPT_COUNTERS)
        watcher = _TeardownWatcher(run)

        self._run_terminal(run, watcher)

        self.assertEqual(watcher.writes, 1)
        self.assertEqual(watcher.labels, ((run.issue.number, LABEL_DONE),))
        self.assertEqual(len(watcher.receipts), 1)
        self.assertTrue(watcher.issue_closed)

    def test_failed_teardown_keeps_the_record(self) -> None:
        run = _seed_published_plan(_FAILED_TEARDOWN, **RECEIPT_COUNTERS)

        with self.assertRaises(OSError):
            self._run_terminal(run, MagicMock(
                side_effect=OSError(_TEARDOWN_FAILED),
            ))

        self.assert_finalized(
            run, label=LABEL_REJECTED, stamp=KEY_CLOSED_WITHOUT_MERGE_AT,
        )
        self.assert_receipt(run)
        self.assert_terminal_event(
            run,
            EVENT_PR_CLOSED_WITHOUT_MERGE,
            pr_number=_FAILED_TEARDOWN.pr_number,
        )


if __name__ == "__main__":
    unittest.main()
