# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The round a first `discussion` tick opens, and the turn it hands back.

One tick on a freshly labeled issue runs the configured decomposer once in the
issue's own worktree, posts what it wrote to the thread, and parks awaiting a
human -- and stops there: no developer, no reviewer, no PR, and no teardown of
the tree the next round reads. The tick after that one is the humans' turn, so
a parked issue earns nothing at all until they answer.
"""

from __future__ import annotations

import unittest

from orchestrator import config
from orchestrator.workflow.engine import prompts as _prompts
from tests.workflow.fixtures import (
    _TEST_SPEC,
    EVENT_AGENT_EXIT,
    EVENT_AGENT_SPAWN,
    KEY_AWAITING_HUMAN,
    KEY_PARK_REASON,
    _agent,
)
from tests.workflow.stages.discussion import discussion_test_support as _support
from tests.workflow.stages.discussion.discussion_test_support import _DiscussionWorkflowMixin

_FIRST_ROUND_ISSUE_NUMBER = 910
_WORKTREE_ISSUE_NUMBER = 911
_ROLE_ISSUE_NUMBER = 912
_PROMPT_ISSUE_NUMBER = 913
_FOREIGN_PARK_ISSUE_NUMBER = 914
# One issue per park reason, since each seeds its own client.
_PARKED_ISSUE_NUMBER = 915
_PARKED_WATERMARK = 44000
_STAGE_DISCUSSION = "discussion"
_ROLE_DECOMPOSER = "decomposer"
_DISCUSSION_PARKS = (
    _support.PARK_DISCUSSION_RESPONSE,
    _support.PARK_DISCUSSION_COMMITS,
    _support.PARK_DISCUSSION_PLAN_INVALID,
    _support.PARK_DISCUSSION_PUSH_FAILED,
    _support.PARK_DISCUSSION_DIRTY,
    _support.PARK_DISCUSSION_SILENT,
    _support.PARK_DISCUSSION_STRANDED,
    _support.PARK_DISCUSSION_TIMEOUT,
)


class DiscussionFirstRoundTest(unittest.TestCase, _DiscussionWorkflowMixin):
    """What one opening round publishes, records, and leaves on disk."""

    def test_response_posts_and_parks(self) -> None:
        gh, issue = _support._seed_discussion(_FIRST_ROUND_ISSUE_NUMBER)

        mocks = self._run_discussion(
            gh,
            issue,
            run_agent=_agent(
                session_id=_support.DISCUSSION_SESSION,
                last_message=_support.DISCUSSION_RESPONSE,
            ),
        )

        self.assert_nothing_published(gh, mocks)
        # The response reaches the thread as its own quoted comment, pinging
        # the humans whose turn it now is.
        self.assertEqual(len(gh.posted_comments), 1)
        _, body = gh.posted_comments[0]
        self.assertIn(config.HITL_MENTIONS, body)
        self.assertIn(f"> {_support.DISCUSSION_RESPONSE}", body)

        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(
            (
                pinned_data[_support.KEY_DISCUSSION_AGENT],
                pinned_data[_support.KEY_DISCUSSION_SESSION_ID],
                pinned_data[KEY_PARK_REASON],
            ),
            (
                config.DECOMPOSE_AGENT_SPEC,
                _support.DISCUSSION_SESSION,
                _support.PARK_DISCUSSION_RESPONSE,
            ),
        )
        self.assertTrue(pinned_data[KEY_AWAITING_HUMAN])
        self.assertIn(_support.KEY_LAST_DISCUSSION_AT, pinned_data)

    def test_round_runs_in_the_issue_worktree(self) -> None:
        # The design under discussion is the design this branch will carry, so
        # the round reads the issue's own checkout rather than the decomposer's
        # scratch one -- and that tree survives the park for the next round and
        # the operator to read.
        gh, issue = _support._seed_discussion(_WORKTREE_ISSUE_NUMBER)

        mocks = self._run_discussion(
            gh,
            issue,
            run_agent=_agent(last_message=_support.DISCUSSION_RESPONSE),
        )

        mocks[_support.ENSURE_WORKTREE].assert_called_once_with(
            _TEST_SPEC,
            issue.number,
            branch=_support._issue_branch(issue.number),
        )
        mocks[_support.ENSURE_DECOMPOSE_WORKTREE].assert_not_called()
        self.assert_worktree_preserved(mocks)

    def test_decomposer_answers_as_discussion(self) -> None:
        # The stage borrows the decomposer's configured agent -- a discussion
        # is the decomposer reasoning before anything is decomposed -- but the
        # run is attributed to `discussion`, so its analytics rows and audit
        # events do not read as a decomposition that never happened.
        gh, issue = _support._seed_discussion(_ROLE_ISSUE_NUMBER)

        mocks = self._run_discussion(
            gh,
            issue,
            run_agent=_agent(last_message=_support.DISCUSSION_RESPONSE),
        )

        mocks[_support.RUN_AGENT].assert_called_once()
        call = mocks[_support.RUN_AGENT].call_args
        self.assertEqual(call.args[0], config.DECOMPOSE_AGENT)
        self.assertEqual(
            call.kwargs.get("extra_args"), config.DECOMPOSE_AGENT_ARGS,
        )
        # One run means one role: nothing implements or reviews a design the
        # humans have not confirmed yet.
        agent_events = [
            (event["event"], event["agent_role"], event["stage"])
            for event in gh.recorded_events
            if event["event"] in {EVENT_AGENT_SPAWN, EVENT_AGENT_EXIT}
        ]
        self.assertEqual(
            agent_events,
            [
                (EVENT_AGENT_SPAWN, _ROLE_DECOMPOSER, _STAGE_DISCUSSION),
                (EVENT_AGENT_EXIT, _ROLE_DECOMPOSER, _STAGE_DISCUSSION),
            ],
        )

    def test_round_uses_the_discussion_prompt(self) -> None:
        gh, issue = _support._seed_discussion(_PROMPT_ISSUE_NUMBER)

        mocks = self._run_discussion(
            gh,
            issue,
            run_agent=_agent(last_message=_support.DISCUSSION_RESPONSE),
        )

        self.assertEqual(
            mocks[_support.RUN_AGENT].call_args.args[1],
            _prompts._build_discussion_prompt(
                _TEST_SPEC,
                issue,
                "",
                config.default_repo_specs(),
                self.plan_path(issue.number),
            ),
        )

    def test_a_parked_issue_earns_no_second_round(self) -> None:
        # The round already on the thread is the one the humans are answering,
        # so a tick that spawned a second one would replace the question they
        # are mid-answer with a differently-worded one. Every park this stage
        # writes says that, not just the one carrying an analysis.
        for park_reason in _DISCUSSION_PARKS:
            with self.subTest(park_reason=park_reason):
                self._assert_no_round(
                    _PARKED_ISSUE_NUMBER + _DISCUSSION_PARKS.index(park_reason),
                    park_reason,
                )

    def test_an_unrelated_park_still_opens_the_round(self) -> None:
        # Pinned state outlives a relabel, so an issue an operator moves here
        # while another stage has it parked arrives awaiting a reply nobody
        # will send it here. Gating on bare `awaiting_human` would leave it
        # inert for good, so only this stage's own park suppresses a round.
        gh, issue = _support._seed_discussion(_FOREIGN_PARK_ISSUE_NUMBER)
        gh.seed_state(
            issue.number,
            awaiting_human=True,
            park_reason=_support.PARK_FOREIGN_QUESTION,
            dev_agent=config.DEV_AGENT_SPEC,
            last_action_comment_id=_PARKED_WATERMARK,
        )

        mocks = self._run_discussion(
            gh,
            issue,
            run_agent=_agent(
                session_id=_support.DISCUSSION_SESSION,
                last_message=_support.DISCUSSION_RESPONSE,
            ),
        )

        mocks[_support.RUN_AGENT].assert_called_once()
        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(
            pinned_data[KEY_PARK_REASON], _support.PARK_DISCUSSION_RESPONSE,
        )
        self.assertTrue(pinned_data[KEY_AWAITING_HUMAN])

    def _assert_no_round(self, issue_number: int, park_reason: str) -> None:
        gh, issue = _support._seed_discussion(issue_number)
        gh.seed_state(
            issue.number,
            awaiting_human=True,
            park_reason=park_reason,
            discussion_agent=config.DECOMPOSE_AGENT_SPEC,
            discussion_session_id=_support.DISCUSSION_SESSION,
            last_action_comment_id=_PARKED_WATERMARK,
        )
        before_writes = gh.write_state_calls

        mocks = self._run_discussion(
            gh,
            issue,
            run_agent=_agent(last_message="a second opening round"),
        )

        mocks[_support.RUN_AGENT].assert_not_called()
        mocks[_support.ENSURE_WORKTREE].assert_not_called()
        self.assertEqual(gh.posted_comments, [])
        self.assertEqual(gh.write_state_calls, before_writes)
        self.assertEqual(gh.recorded_events, [])


if __name__ == "__main__":
    unittest.main()
