# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for implementing backend behavior."""

from __future__ import annotations

import unittest

from orchestrator.workflow.stages.validating import handler as _validating
from tests.workflow import published_reports as _published_reports
from tests.workflow.stages.implementing import retry_test_support as support

ACTION_COMMENT_ID = support.ACTION_COMMENT_ID
BACKEND_CLAUDE = support.BACKEND_CLAUDE
BACKEND_CODEX = support.BACKEND_CODEX
DEV_FIX_BACKEND_ISSUE = support.DEV_FIX_BACKEND_ISSUE
DEV_SESSION = support.DEV_SESSION
DONE_MESSAGE = support.DONE_MESSAGE
FRESH_BACKEND_ISSUE = support.FRESH_BACKEND_ISSUE
FRESH_SESSION = support.FRESH_SESSION
FakeComment = support.FakeComment
FakeGitHubClient = support.FakeGitHubClient
FakeUser = support.FakeUser
HUMAN_REPLY_ID = support.HUMAN_REPLY_ID
KEY_DEV_AGENT = support.KEY_DEV_AGENT
KEY_DEV_SESSION_ID = support.KEY_DEV_SESSION_ID
LABEL_IMPLEMENTING = support.LABEL_IMPLEMENTING
LABEL_VALIDATING = support.LABEL_VALIDATING
OK_MESSAGE = support.OK_MESSAGE
RESUME_SESSION_ID = support.RESUME_SESSION_ID
REVIEW_APPROVED_MESSAGE = support.REVIEW_APPROVED_MESSAGE
REVIEW_BACKEND_ISSUE = support.REVIEW_BACKEND_ISSUE
RUN_AGENT = support.RUN_AGENT
UNREAD_SESSION = support.UNREAD_SESSION
UNREAD_SESSION_ISSUE = support.UNREAD_SESSION_ISSUE
_PatchedWorkflowMixin = support._PatchedWorkflowMixin
_TEST_SPEC = support._TEST_SPEC
_agent = support._agent
_issue_branch = support._issue_branch
_open_pr_for = support._open_pr_for
config = support.config
make_issue = support.make_issue
patch = support.patch

# A conversation id under a key the session read does not resolve.
KEY_UNREAD_SESSION = "codex_session_id"

# What a reply's fresh conversation pins, beside the key it leaves alone.
UNREAD_SESSION_RECORDS = (KEY_DEV_AGENT, KEY_DEV_SESSION_ID, KEY_UNREAD_SESSION)

# The command a fresh conversation is opened and pinned under, and the one the
# configuration flips to before the next reply, as spec, backend, and args.
PINNED_COMMAND = ("claude --model claude-opus-4-7", BACKEND_CLAUDE, ("--model", "claude-opus-4-7"))
FLIPPED_COMMAND = ("codex -m another-model", BACKEND_CODEX, ("-m", "another-model"))

# The settings a configured command is spelled across, in the order above.
COMMAND_SETTINGS = ("DEV_AGENT_SPEC", "DEV_AGENT", "DEV_AGENT_ARGS")

# A reply posted after the park the first reply's run takes.
LATER_REPLY_ID = 9000

# A commit-less run's answer that parks the issue for a human again.
QUESTION_MESSAGE = "Should the cache live in sqlite or in redis?"


class ConfigurableBackendTest(unittest.TestCase, _PatchedWorkflowMixin):
    """The dev/review backends are picked from config, with the dev backend
    locked to the `dev_agent` command that opened `dev_session_id` so a
    config flip mid-flight does not break a resumable session.
    """

    def test_fresh_spawn_uses_dev_agent_config(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(FRESH_BACKEND_ISSUE, label=LABEL_IMPLEMENTING)
        gh.add_issue(issue)

        with patch.object(config, "DEV_AGENT", BACKEND_CLAUDE):
            mocks = self._run_implementing(
                gh,
                issue,
                run_agent=_agent(session_id="sess-fresh", last_message=DONE_MESSAGE),
                has_new_commits=[False, True],
                dirty_files=(),
                push_branch=True,
            )

        self.assertEqual(mocks[RUN_AGENT].call_args.args[0], BACKEND_CLAUDE)
        pinned_data = gh.pinned_data(FRESH_BACKEND_ISSUE)
        self.assertEqual(pinned_data[KEY_DEV_AGENT], BACKEND_CLAUDE)
        self.assertEqual(pinned_data[KEY_DEV_SESSION_ID], "sess-fresh")

    def test_reviewer_spawn_uses_review_agent_config(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(REVIEW_BACKEND_ISSUE, label=LABEL_VALIDATING)
        gh.add_issue(issue)
        gh.seed_state(
            REVIEW_BACKEND_ISSUE,
            pr_number=REVIEW_BACKEND_ISSUE,
            branch=_issue_branch(REVIEW_BACKEND_ISSUE),
            dev_agent=BACKEND_CLAUDE,
            dev_session_id=DEV_SESSION,
            review_round=0,
        )
        _open_pr_for(gh, issue_number=REVIEW_BACKEND_ISSUE, pr_number=REVIEW_BACKEND_ISSUE)

        _published_reports.publishes_the_report(gh, issue)
        with patch.object(config, "REVIEW_AGENT", BACKEND_CODEX):
            mocks = self._run(
                lambda: _validating._handle_validating(gh, _TEST_SPEC, issue),
                run_agent=_agent(
                    session_id="rev-sess",
                    last_message=REVIEW_APPROVED_MESSAGE,
                ),
            )

        self.assertEqual(mocks[RUN_AGENT].call_args.args[0], BACKEND_CODEX)
        pinned_data = gh.pinned_data(REVIEW_BACKEND_ISSUE)
        self.assertEqual(pinned_data["review_agent"], BACKEND_CODEX)
        self.assertEqual(pinned_data["last_review_session_id"], "rev-sess")

    def test_dev_fix_uses_recorded_backend_not_config(self) -> None:
        # Issue locked to codex via pinned state; even if config flips to
        # claude, the validating dev-fix call must stay on codex.
        gh = FakeGitHubClient()
        issue = make_issue(DEV_FIX_BACKEND_ISSUE, label=LABEL_VALIDATING)
        gh.add_issue(issue)
        gh.seed_state(
            DEV_FIX_BACKEND_ISSUE,
            pr_number=DEV_FIX_BACKEND_ISSUE,
            branch=_issue_branch(DEV_FIX_BACKEND_ISSUE),
            dev_agent=BACKEND_CODEX,
            dev_session_id=DEV_SESSION,
            review_round=0,
        )
        _open_pr_for(gh, issue_number=DEV_FIX_BACKEND_ISSUE, pr_number=DEV_FIX_BACKEND_ISSUE)
        with (
            patch.object(config, "DEV_AGENT", BACKEND_CLAUDE),
            patch.object(config, "REVIEW_AGENT", BACKEND_CLAUDE),
        ):
            _published_reports.publishes_the_report(gh, issue)
            mocks = self._run(
                lambda: _validating._handle_validating(gh, _TEST_SPEC, issue),
                run_agent=[
                    _agent(
                        session_id="rev-sess",
                        last_message=("1. Tighten\n\nVERDICT: CHANGES_REQUESTED"),
                    ),
                    _agent(session_id=DEV_SESSION, last_message="fixed"),
                ],
                dirty_files=(),
                push_branch=True,
                head_shas=["aaa", "aaa", "bbb"],
            )

        # Reviewer takes config; dev-fix takes pinned state.
        self.assertEqual(mocks[RUN_AGENT].call_count, 2)
        agent_calls = mocks[RUN_AGENT].call_args_list
        self.assertEqual(agent_calls[0].args[0], BACKEND_CLAUDE)
        self.assertEqual(agent_calls[1].args[0], BACKEND_CODEX)
        self.assertEqual(
            agent_calls[1].kwargs["options"].resume_session_id,
            DEV_SESSION,
        )

    def test_unread_session_key_is_no_pinned_session(self) -> None:
        # A conversation id under a key the session read does not resolve
        # locks nothing: the reply is answered by a fresh conversation under
        # the configured command, pinned in full before it runs, and that key
        # is left exactly as it was. The next reply resumes the fresh
        # conversation under the pinned command, whatever the configuration
        # has flipped to meanwhile.
        gh, issue = self._parked(**{KEY_UNREAD_SESSION: UNREAD_SESSION})

        opened = self._reply_tick(gh, issue, HUMAN_REPLY_ID, PINNED_COMMAND)

        self.assertEqual(opened, (BACKEND_CLAUDE, None, PINNED_COMMAND[2]))
        self.assertEqual(
            {key: gh.pinned_data(UNREAD_SESSION_ISSUE).get(key) for key in UNREAD_SESSION_RECORDS},
            {KEY_DEV_AGENT: PINNED_COMMAND[0], KEY_DEV_SESSION_ID: FRESH_SESSION, KEY_UNREAD_SESSION: UNREAD_SESSION},
            "the full command is pinned beside the fresh conversation; nothing migrates or clears the unread key",
        )

        resumed = self._reply_tick(gh, issue, LATER_REPLY_ID, FLIPPED_COMMAND)

        self.assertEqual(
            resumed,
            (BACKEND_CLAUDE, FRESH_SESSION, PINNED_COMMAND[2]),
            "the next reply resumes the fresh conversation under the command it was pinned under",
        )

    def test_pin_under_no_command_is_dropped(self) -> None:
        # The session read resolves no conversation without a pinned command,
        # so the reply runs fresh, and the pin standing alone is dropped as
        # the configured command is pinned: a run that returns no id of its
        # own leaves the next reply fresh too, never resuming that pin under
        # a command it never ran on.
        gh, issue = self._parked(dev_session_id=DEV_SESSION)

        launches = [
            self._reply_tick(gh, issue, reply_id, PINNED_COMMAND, returned=None)
            for reply_id in (HUMAN_REPLY_ID, LATER_REPLY_ID)
        ]

        fresh = (BACKEND_CLAUDE, None, PINNED_COMMAND[2])
        self.assertEqual(launches, [fresh, fresh])
        self.assertEqual(
            {key: gh.pinned_data(UNREAD_SESSION_ISSUE).get(key) for key in (KEY_DEV_AGENT, KEY_DEV_SESSION_ID)},
            {KEY_DEV_AGENT: PINNED_COMMAND[0], KEY_DEV_SESSION_ID: None},
        )

    def _parked(self, **records) -> tuple:
        """An implementing issue parked on a human, its comment carrying `records` and no command."""
        gh = FakeGitHubClient()
        issue = make_issue(UNREAD_SESSION_ISSUE, label=LABEL_IMPLEMENTING)
        gh.add_issue(issue)
        gh.seed_state(
            UNREAD_SESSION_ISSUE,
            awaiting_human=True,
            last_action_comment_id=ACTION_COMMENT_ID,
            branch=_issue_branch(UNREAD_SESSION_ISSUE),
            **records,
        )
        return gh, issue

    def _reply_tick(self, gh, issue, reply_id: int, command: tuple, *, returned: str | None = FRESH_SESSION) -> tuple:
        """One tick answering a reply under the configured `command`; the backend, resumed id, and args it launched.

        The run hands `returned` back, asks a question, and commits nothing,
        so the issue parks again for the next reply.
        """
        reply = FakeComment(id=reply_id, body="use sqlite", user=FakeUser("alice"))
        issue.comments.append(reply)
        with patch.multiple(config, **dict(zip(COMMAND_SETTINGS, command, strict=True))):
            mocks = self._run_implementing(
                gh,
                issue,
                run_agent=_agent(session_id=returned, last_message=QUESTION_MESSAGE),
                has_new_commits=[False],
                dirty_files=(),
            )
        launch = mocks[RUN_AGENT].call_args
        options = launch.kwargs["options"]
        return launch.args[0], options.resume_session_id, options.extra_args
