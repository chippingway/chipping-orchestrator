# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What keeps a later discussion round on the agent that opened the first.

A round can end with no disposition -- a mid-run pause withholds every one by
contract, a crash takes them with it -- and the next tick opens it again; a
human answering the frontier opens one deliberately. The configured
`DECOMPOSE_AGENT` can change between any two of those ticks, so the spec
pinned at the first spawn is read back rather than re-resolved: a round that
followed the new config would move the conversation onto a backend and argument
set that never ran on this issue, and then overwrite the pin with them. A
resume has one more thing to lose by it -- the session id is only meaningful
to the CLI that issued it, so the flipped backend would be handed a
conversation it has never heard of.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.workflow.fixtures import _agent
from tests.workflow.stages.discussion import discussion_test_support as _support
from tests.workflow.stages.discussion.discussion_resume_test_support import (
    DISCUSSION_REPLY,
    _reply,
    _seed_parked_discussion,
)
from tests.workflow.stages.discussion.discussion_test_support import _DiscussionWorkflowMixin

_REPLAY_ISSUE_NUMBER = 1000
_FIRST_SPAWN_ISSUE_NUMBER = 1001
_RESUME_ISSUE_NUMBER = 1002


class DiscussionSessionLockTest(unittest.TestCase, _DiscussionWorkflowMixin):

    def test_a_first_spawn_takes_the_configured_spec(self) -> None:
        gh, issue = _support._seed_discussion(_FIRST_SPAWN_ISSUE_NUMBER)

        with _support._configured_spec(_support.SPEC_WITH_ARGS, _support.SPEC_BACKEND, _support.SPEC_ARGS):
            mocks = self._run_discussion(
                gh,
                issue,
                run_agent=_agent(
                    session_id=_support.DISCUSSION_SESSION,
                    last_message=_support.DISCUSSION_RESPONSE,
                ),
            )

        self._assert_ran_under(mocks, _support.SPEC_BACKEND, _support.SPEC_ARGS)
        self.assertEqual(
            gh.pinned_data(issue.number)[_support.KEY_DISCUSSION_AGENT], _support.SPEC_WITH_ARGS,
        )

    def test_a_replay_keeps_the_locked_spec(self) -> None:
        # Round one is withheld by a mid-run pause, so the issue keeps its
        # anchor and its pin. The operator then flips `DECOMPOSE_AGENT` before
        # the replay: the round that reopens is still the one this issue's
        # discussion belongs to, so it runs under the pinned spec.
        gh, issue = _support._seed_discussion(_REPLAY_ISSUE_NUMBER)

        with (
            _support._configured_spec(_support.SPEC_WITH_ARGS, _support.SPEC_BACKEND, _support.SPEC_ARGS),
            patch.object(
                gh,
                "get_issue",
                return_value=_support._paused_view(_REPLAY_ISSUE_NUMBER, "paused"),
            ),
        ):
            self._run_discussion(
                gh,
                issue,
                run_agent=_agent(last_message=_support.DISCUSSION_RESPONSE),
            )

        with _support._configured_spec(_support.FLIPPED_SPEC, _support.FLIPPED_BACKEND, _support.FLIPPED_ARGS):
            replay_mocks = self._run_discussion(
                gh,
                issue,
                run_agent=_agent(
                    session_id=_support.DISCUSSION_SESSION,
                    last_message=_support.DISCUSSION_RESPONSE,
                ),
            )

        self._assert_ran_under(replay_mocks, _support.SPEC_BACKEND, _support.SPEC_ARGS)
        # And the flip did not overwrite the pin on the way through.
        self.assertEqual(
            gh.pinned_data(issue.number)[_support.KEY_DISCUSSION_AGENT], _support.SPEC_WITH_ARGS,
        )

    def test_a_resume_keeps_the_lock_and_session(self) -> None:
        # The operator flips `DECOMPOSE_AGENT` while the issue sits parked on
        # the frontier it posted. The human then answers: that answer belongs
        # to the conversation the pinned backend is holding, so both the
        # command line and the session it resumes come from the pin.
        gh, issue = _seed_parked_discussion(
            _RESUME_ISSUE_NUMBER,
            replies=(_reply(DISCUSSION_REPLY),),
            agent_spec=_support.SPEC_WITH_ARGS,
        )

        with _support._configured_spec(_support.FLIPPED_SPEC, _support.FLIPPED_BACKEND, _support.FLIPPED_ARGS):
            resume_mocks = self._run_discussion(
                gh,
                issue,
                run_agent=_agent(
                    session_id=_support.DISCUSSION_SESSION,
                    last_message=_support.DISCUSSION_RESPONSE,
                ),
            )

        self._assert_ran_under(resume_mocks, _support.SPEC_BACKEND, _support.SPEC_ARGS)
        self.assertEqual(
            resume_mocks[_support.RUN_AGENT].call_args.kwargs.get(_support.RESUME_SESSION_ID),
            _support.DISCUSSION_SESSION,
        )
        self.assertEqual(
            gh.pinned_data(issue.number)[_support.KEY_DISCUSSION_AGENT], _support.SPEC_WITH_ARGS,
        )

    def _assert_ran_under(self, mocks, backend: str, extra_args: tuple) -> None:
        mocks[_support.RUN_AGENT].assert_called_once()
        spawn_call = mocks[_support.RUN_AGENT].call_args
        self.assertEqual(spawn_call.args[0], backend)
        self.assertEqual(spawn_call.kwargs.get("extra_args"), extra_args)


if __name__ == "__main__":
    unittest.main()
