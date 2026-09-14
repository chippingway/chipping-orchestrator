# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from tests.workflow.fixtures import (
    _FAKE_WT,
    _TEST_SPEC,
    AGENT_RUN_CHARGE_WRITES,
    MEASURED_CANDIDATE_SHA,
    _agent,
)
from tests.workflow.stages.conflicts.conflicts_test_support import (
    RESOLVED_HEAD_SHA,
    _ResolvingConflictMixin,
)

CONFLICT_ISSUE = 200
CONFLICT_FILE = "a.py"
BEFORE_HEAD = "be40e5ba" * 5
LATE_APPROVED_SHA = "late_approved_sha"
KEY_PUBLISHED_SHA = "late_published_sha"
MAX_ADDED_LINES = "MAX_ADDED_LINES"
CEILING = 5
PAST_THE_CEILING = 6
RUN_AGENT = "run_agent"
PUSH_BRANCH = "_push_branch"
LABEL_VALIDATING = "workflow:validating"


def _assert_resolution_prompt(test_case, prompt: str) -> None:
    test_case.assertIn(CONFLICT_FILE, prompt)
    test_case.assertIn("b.py", prompt)
    test_case.assertIn("rebase", prompt.lower())
    test_case.assertIn("git rebase --skip", prompt)
    test_case.assertIn("git commit --allow-empty", prompt)
    test_case.assertIn("git rebase --abort", prompt)


def _assert_resolved_state(test_case, github) -> None:
    pinned_state = github.pinned_data(CONFLICT_ISSUE)
    test_case.assertEqual(pinned_state.get("review_round"), 0)
    test_case.assertEqual(pinned_state.get("conflict_round"), 1)
    test_case.assertIn("last_conflict_resolved_at", pinned_state)
    # The size gate approves the resolution before it goes out and records it
    # as one still owed a push; the push that lands pays that debt. Left
    # standing it would freeze this branch out of the pre-tick base refresh
    # with nothing coming back to drop it.
    test_case.assertIsNone(pinned_state.get(LATE_APPROVED_SHA))


def _assert_interrupted_state(test_case, github) -> None:
    pinned_state = github.pinned_data(CONFLICT_ISSUE)
    test_case.assertFalse(pinned_state.get("awaiting_human"))
    test_case.assertEqual(pinned_state.get("conflict_round"), 0)
    test_case.assertNotIn((CONFLICT_ISSUE, LABEL_VALIDATING), github.label_history)
    test_case.assertFalse(
        any(
            "timed out" in body
            or "rebase is still in progress" in body
            or "agent needs your input" in body
            or "git push failed" in body
            for _, body in github.posted_comments
        )
    )


class ResolvingConflictAgentExecutionTest(unittest.TestCase, _ResolvingConflictMixin):
    """Drive `_handle_resolving_conflict` through the agent-execution
    branches: the dev spawned to resolve a rebase conflict pushes, times
    out, fails to push, or is interrupted mid-flight.
    """

    def test_resolved_pushes_and_routes_to_validating(self) -> None:
        # Agent-resolved conflict push pushes the resolved branch and
        # hands straight back to `validating`. Docs do not run here --
        # the single docs pass runs after reviewer approval before
        # `in_review` via the final-docs handoff.
        gh, issue = self._seed()[:2]
        mocks = self._run_with_merge(
            gh,
            issue,
            merge_succeeded=False,
            conflicted_files=[CONFLICT_FILE, "b.py"],
            head_shas=[BEFORE_HEAD, RESOLVED_HEAD_SHA],
            push_branch=True,
        )[0]
        # Agent IS spawned with the conflict-resolution prompt.
        self.assertEqual(mocks[RUN_AGENT].call_count, 1)
        prompt = mocks[RUN_AGENT].call_args.args[1]
        _assert_resolution_prompt(self, prompt)
        # Named against the commit the size gate measured rather than
        # against whatever the checkout became, and leased against the
        # pre-rebase head this stage read for itself -- the tighter claim
        # about a ref it is rewriting.
        mocks[PUSH_BRANCH].assert_called_once_with(
            _TEST_SPEC,
            _FAKE_WT,
            self.issue_branch,
            revision=MEASURED_CANDIDATE_SHA,
            force_with_lease=BEFORE_HEAD,
        )
        self.assertIn((CONFLICT_ISSUE, LABEL_VALIDATING), gh.label_history)
        self.assertNotIn((CONFLICT_ISSUE, "workflow:documenting"), gh.label_history)
        _assert_resolved_state(self, gh)

    def test_it_freezes_the_head_it_read(self) -> None:
        # This stage read the remote for itself and pinned its push to what it
        # read. Freezing anything else would leave the immediate push refusing
        # a head that moved while a settled adjudication -- which re-pins from
        # the record -- pinned to the head that moved and overwrote it.
        gh, issue = self._seed()[:2]

        with patch.object(config, MAX_ADDED_LINES, CEILING):
            self._run_with_merge(
                gh,
                issue,
                merge_succeeded=False,
                conflicted_files=[CONFLICT_FILE, "b.py"],
                head_shas=[BEFORE_HEAD, RESOLVED_HEAD_SHA],
                push_branch=True,
                added_lines=PAST_THE_CEILING,
            )

        self.assertEqual(
            gh.pinned_data(CONFLICT_ISSUE)[KEY_PUBLISHED_SHA], BEFORE_HEAD,
        )

    def test_agent_timeout_parks_awaiting_human(self) -> None:
        gh, issue, _ = self._seed()
        mocks, _, _ = self._run_with_merge(
            gh,
            issue,
            merge_succeeded=False,
            conflicted_files=[CONFLICT_FILE],
            head_shas=[BEFORE_HEAD, "after"],
            run_agent_result=_agent(
                session_id="dev-sess",
                last_message="",
                timed_out=True,
            ),
        )
        mocks[PUSH_BRANCH].assert_not_called()
        pinned_state = gh.pinned_data(CONFLICT_ISSUE)
        self.assertTrue(pinned_state.get("awaiting_human"))
        # Label stays on resolving_conflict -- the dispatcher will keep
        # routing here until the operator clears the park.
        self.assertNotIn((CONFLICT_ISSUE, LABEL_VALIDATING), gh.label_history)
        last_comment = gh.posted_comments[-1][1]
        self.assertIn("timed out", last_comment)

    def test_push_failure_parks_awaiting_human(self) -> None:
        gh, issue, _ = self._seed()
        mocks, _, _ = self._run_with_merge(
            gh,
            issue,
            merge_succeeded=False,
            conflicted_files=[CONFLICT_FILE],
            head_shas=[BEFORE_HEAD, RESOLVED_HEAD_SHA],
            push_branch=False,
        )
        # Agent ran successfully and committed, but the push failed.
        self.assertEqual(mocks[RUN_AGENT].call_count, 1)
        mocks[PUSH_BRANCH].assert_called_once()
        pinned_state = gh.pinned_data(CONFLICT_ISSUE)
        self.assertTrue(pinned_state.get("awaiting_human"))
        # No label flip -- still resolving_conflict.
        self.assertNotIn((CONFLICT_ISSUE, LABEL_VALIDATING), gh.label_history)

    def test_interrupted_resolution_keeps_state(self) -> None:
        # A dev run spawned to resolve the rebase conflict, but the shutdown
        # sweep killed it mid-flight. The partial result must be ignored:
        # `_post_conflict_resolution_result` returns WITHOUT writing pinned
        # state, so durable state stays retryable -- no park, no flip, no
        # round increment, no push off the partial tree.
        gh, issue, _ = self._seed()
        self._seed_with_baseline_hash(gh, issue)
        before_writes = gh.write_state_calls

        mocks, _, _ = self._run_with_merge(
            gh,
            issue,
            merge_succeeded=False,
            conflicted_files=[CONFLICT_FILE],
            head_shas=[BEFORE_HEAD, "after"],
            run_agent_result=_agent(
                session_id="dev-sess",
                last_message="",
                interrupted=True,
            ),
        )

        # The conflict-resolution dev run spawned, then was seen interrupted.
        mocks[RUN_AGENT].assert_called_once()
        self.assertEqual(
            gh.write_state_calls, before_writes + AGENT_RUN_CHARGE_WRITES,
        )
        mocks[PUSH_BRANCH].assert_not_called()
        _assert_interrupted_state(self, gh)


if __name__ == "__main__":
    unittest.main()
