# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Focused agent and state assertions for conflict-resume tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from tests.workflow import fixtures

# The gated-push cases reach the effect through this module rather than
# past it. Nothing below reads it, so the same-name alias is what declares
# the import a re-export instead of a dead one.
from tests.workflow.mid_run_effects import (
    _MovesThePullRequest as _MovesThePullRequest,
)

CONFLICT_ISSUE = 200
HUMAN_REPLY_ID = 2000
AWAITING_HUMAN = "awaiting_human"
CONFLICT_ROUND = "conflict_round"
LAST_ACTION_COMMENT_ID = "last_action_comment_id"
RUN_AGENT = "run_agent"
PUSH_BRANCH = "_push_branch"
LABEL_VALIDATING = "workflow:validating"
DEV_SESSION = "dev-sess"


def stale_session_agent():
    stale_stderr = "Error: No conversation found with session ID: poisoned-sess"
    return MagicMock(
        side_effect=[
            fixtures._agent(session_id="", last_message="", stderr=stale_stderr),
            fixtures._agent(session_id="fresh-sess", last_message="resolved"),
        ],
    )


def assert_stale_agent_calls(test_case, run_agent, patched) -> None:
    test_case.assertEqual(
        [agent_call.kwargs["options"].resume_session_id for agent_call in run_agent.call_args_list],
        ["poisoned-sess", None],
        "stale-session resume must be transparently retried as fresh",
    )
    patched[PUSH_BRANCH].assert_called_once()


def assert_stale_state(test_case, github) -> None:
    test_case.assertIn((CONFLICT_ISSUE, LABEL_VALIDATING), github.label_history)
    test_case.assertNotIn((CONFLICT_ISSUE, "workflow:documenting"), github.label_history)
    state = github.pinned_data(CONFLICT_ISSUE)
    test_case.assertFalse(
        state.get(AWAITING_HUMAN),
        "awaiting_human must be cleared on a recovered resume",
    )
    test_case.assertNotEqual(state.get("park_reason"), "agent_silent")
    test_case.assertEqual(state.get(CONFLICT_ROUND), 2)
    test_case.assertEqual(state.get("dev_session_id"), "fresh-sess")


def assert_continue_agent(test_case, github, patched) -> None:
    launch = patched[RUN_AGENT].call_args
    prompt = launch.args[1]
    test_case.assertIn("session/usage limit", prompt)
    test_case.assertNotIn("/orchestrator continue", prompt)
    test_case.assertEqual(launch.kwargs["options"].resume_session_id, DEV_SESSION)
    patched[PUSH_BRANCH].assert_called_once()
    test_case.assertFalse(
        any("issue body changed" in body for _, body in github.posted_comments)
    )


def assert_continue_state(test_case, github) -> None:
    test_case.assertIn((CONFLICT_ISSUE, LABEL_VALIDATING), github.label_history)
    state = github.pinned_data(CONFLICT_ISSUE)
    test_case.assertFalse(state.get(AWAITING_HUMAN))
    test_case.assertEqual(state.get(CONFLICT_ROUND), 2)
    test_case.assertEqual(state.get(LAST_ACTION_COMMENT_ID), HUMAN_REPLY_ID)
