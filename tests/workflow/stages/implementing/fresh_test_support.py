# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Focused assertions for implementing fresh-run and resume tests."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.agents.backends import claude
from orchestrator.agents.models import AgentResult
from tests.workflow.fixtures import AGENT_RUN_CHARGE_WRITES
from tests.workflow.stages import implementing_fixing_test_cases


def claude_run_exiting(returncode: int) -> AgentResult:
    """Return the result `run_claude` builds for an empty run exiting `returncode`.

    The child is a double, but the classification and result assembly are the
    real ones, so a stage test sees exactly the fields such an exit yields.
    """
    process = MagicMock()
    process.communicate.return_value = ("", "")
    process.returncode = returncode
    with patch("orchestrator.agents.processes.subprocess.Popen", return_value=process):
        return claude.run_claude("implement", Path(tempfile.gettempdir()))


def assert_pr_routing(test_case, scenario) -> None:
    github = scenario.github
    test_case.assertEqual(len(github.opened_prs), 1)
    opened_pr = github.opened_prs[0]
    test_case.assertTrue(
        implementing_fixing_test_cases.posted_comment_contains(
            github,
            f":sparkles: PR opened: #{opened_pr.number}",
        ),
    )
    test_case.assertIn((1, "workflow:validating"), github.label_history)
    test_case.assertNotIn((1, "in_review"), github.label_history)
    test_case.assertNotIn((1, "workflow:documenting"), github.label_history)


def assert_pr_state(test_case, scenario) -> None:
    opened_pr = scenario.github.opened_prs[0]
    state = scenario.github.pinned_data(1)
    test_case.assertEqual(state["pr_number"], opened_pr.number)
    test_case.assertEqual(
        state["branch"],
        "orchestrator/chippingway__orchestrator/issue-1",
    )
    test_case.assertEqual(state["dev_agent"], config.DEV_AGENT)
    test_case.assertEqual(state["dev_session_id"], "sess-1")
    test_case.assertNotIn("codex_session_id", state)
    test_case.assertEqual(state["review_round"], 0)


def assert_human_reply_resume(
    test_case,
    github,
    mocks,
    run_agent_key,
    legacy_session,
) -> None:
    mocks[run_agent_key].assert_called_once()
    agent_call = mocks[run_agent_key].call_args
    test_case.assertEqual(agent_call.args[0], "codex")
    test_case.assertEqual(
        agent_call.kwargs.get("resume_session_id"),
        legacy_session,
    )
    followup = agent_call.args[1]
    test_case.assertIn("please use sqlite", followup)
    test_case.assertIn("NEVER start a background job", followup)
    test_case.assertEqual(len(github.opened_prs), 1)
    test_case.assertFalse(
        github.pinned_data(2).get("awaiting_human"),
    )


def assert_interrupted_spawn_state(
    test_case,
    github,
    before_writes,
    issue_number,
) -> None:
    test_case.assertEqual(
        github.write_state_calls, before_writes + AGENT_RUN_CHARGE_WRITES,
    )
    test_case.assertEqual(github.opened_prs, [])
    test_case.assertEqual(github.label_history, [])
    test_case.assertEqual(github.posted_comments, [])
    state = github.pinned_data(issue_number)
    # The interrupted spawn's session id is NOT persisted -- the next
    # process re-spawns fresh rather than resuming a half-built session.
    test_case.assertNotIn("dev_session_id", state)
    test_case.assertFalse(state.get("awaiting_human"))
    test_case.assertIsNone(state.get("park_reason"))
    test_case.assertFalse(state.get("silent_park_count"))


def assert_interrupted_resume_state(
    test_case,
    github,
    before_writes,
    issue_number,
    action_comment_id,
) -> None:
    test_case.assertEqual(
        github.write_state_calls, before_writes + AGENT_RUN_CHARGE_WRITES,
    )
    state = github.pinned_data(issue_number)
    test_case.assertTrue(state.get("awaiting_human"))
    test_case.assertEqual(
        state.get("last_action_comment_id"),
        action_comment_id,
    )
    test_case.assertEqual(github.opened_prs, [])
    test_case.assertEqual(github.label_history, [])
    test_case.assertFalse(
        implementing_fixing_test_cases.posted_comment_contains(
            github,
            "agent needs your input",
        )
        or implementing_fixing_test_cases.posted_comment_contains(
            github,
            "timed out",
        ),
    )
