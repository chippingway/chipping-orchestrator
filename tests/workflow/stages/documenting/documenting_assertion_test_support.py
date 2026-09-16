# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from tests.support.fakes import FakeGitHubClient

RUN_AGENT = "run_agent"
PUSH_BRANCH = "_push_branch"
AMEND_COMMIT_MESSAGE = "_amend_commit_message"
COMMIT_MESSAGE = "_commit_message"
DOCS_CHECKED_SHA = "docs_checked_sha"
REVISION = "revision"


def _assert_referenced_publication(
    case, mocks, state, amendment: tuple[str, str], published_sha: str,
) -> None:
    """The one push a docs pass made, the amendment ahead of it, and its stamp.

    `amendment` is the commit the pass read and the message it was to carry.
    The message read and the amendment are both asked for that commit by id,
    since one bound to whatever HEAD became is the race the amendment refuses;
    the push and `docs_checked_sha` are asked for the replacement it handed
    back -- so a pass that pushed or stamped the commit the agent made reads as
    the failure it is.
    """
    amended_from, message = amendment
    mocks[PUSH_BRANCH].assert_called_once()
    mocks[AMEND_COMMIT_MESSAGE].assert_called_once()
    case.assertEqual(mocks[COMMIT_MESSAGE].call_args.args[1], amended_from)
    case.assertEqual(
        mocks[AMEND_COMMIT_MESSAGE].call_args.args[1:], (amended_from, message),
    )
    case.assertEqual(mocks[PUSH_BRANCH].call_args.kwargs[REVISION], published_sha)
    case.assertEqual(state.get(DOCS_CHECKED_SHA), published_sha)


def _agent_prompt(mocks) -> str:
    agent_call = mocks[RUN_AGENT].call_args
    return agent_call.kwargs.get("prompt") or agent_call.args[1]


def _issue_comment_text(
    github: FakeGitHubClient,
    issue_number: int | None = None,
) -> str:
    return "\n".join(
        body
        for posted_issue_number, body in github.posted_comments
        if issue_number is None or posted_issue_number == issue_number
    )


def _pr_comment_text(github: FakeGitHubClient) -> str:
    return "\n".join(
        body
        for _pull_request_number, body in github.posted_pr_comments
    )


def _lifecycle_events(
    github: FakeGitHubClient,
    stage: str,
) -> list[dict]:
    return [
        event
        for event in github.recorded_events
        if event["event"] in ("agent_spawn", "agent_exit")
        and event.get("stage") == stage
    ]
