# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The two surfaces one IssueComment id space is read as, and their cursors.

GitHub numbers the issue thread and the pull request's conversation from one
id space, and that numbering is not a shared delivery record. Two roads hand
issue-thread replies to a developer and only one of them has ever read the
pull request: an implementing or validating resume quotes the thread alone and
settles `last_action_comment_id` for exactly what it quoted, while
`pr_last_comment_id` is the mark this stage and `fixing` consume PR feedback
against.

So the issue thread answers to both cursors -- a reply at or below either has
been in a developer prompt -- and the PR conversation answers to
`pr_last_comment_id` and to nothing else. One field asked of both surfaces is
wrong in both directions: the issue-thread cursor read over the pull request
hides every PR comment numbered below the last reply a developer answered,
and `pr_last_comment_id` read alone over the thread hands that same answered
reply back as fresh feedback the moment a manual relabel or a handoff walk
leaves it low.

`_issue_space_above` is the raw merged read the watermark walk takes instead,
tagged by surface rather than filtered, because that walk has its own rules
for what a comment above the mark may be -- and applying the thread's cursor
to the pull request there would be the same mistake in a second place.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.in_review import state as _state


def _consumed_issue_thread_id(state: PinnedState) -> int | None:
    """How far the issue thread ALONE has been delivered to a developer.

    `last_action_comment_id` is settled by the implementing and validating
    awaiting-human resumes, and those watch the issue thread and nothing else,
    so the field says a reply was quoted into a prompt and says nothing
    whatever about the pull request's conversation.
    """
    consumed = state.get("last_action_comment_id")
    return consumed if isinstance(consumed, int) else None


def _unread_issue_thread(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> list:
    """Issue-thread comments neither cursor over this surface has spent.

    Past `pr_last_comment_id` is only half the question: a reply an
    implementing or validating resume already answered is recorded on
    `last_action_comment_id` instead, and a `pr_last_comment_id` left BELOW it
    -- by a handoff walk that stopped at an unread PR comment, or by a manual
    relabel that left the key unset entirely -- would hand that answered reply
    to `fixing` a second time as fresh feedback.
    """
    consumed = _consumed_issue_thread_id(state)
    return [
        comment
        for comment in gh.comments_after(
            issue, state.get(_state._PR_LAST_COMMENT_ID),
        )
        if consumed is None or comment.id > consumed
    ]


def _unread_pr_conversation(gh: GitHubClient, pr, state: PinnedState) -> list:
    """PR-conversation comments past `pr_last_comment_id`, and past nothing
    else.

    The issue-thread cursor is deliberately not applied here. Nothing that
    advances it has read this surface, so a PR comment numbered below it is
    unseen rather than answered, and standing the field in as a watermark
    would silently drop exactly the feedback the pull request was opened to
    collect.
    """
    return list(
        gh.pr_conversation_comments_after(
            pr, state.get(_state._PR_LAST_COMMENT_ID),
        ),
    )


def _issue_space_above(
    gh: GitHubClient, issue: Issue, pr, floor: int | None,
) -> list[tuple]:
    """Both surfaces above `floor`, oldest first, each tagged with whether it
    is the issue thread.

    Unfiltered on purpose: the watermark walk that consumes this decides for
    itself what a comment above the mark may be, and the tag is what lets it
    apply the issue thread's delivery cursor to the issue thread alone.
    """
    return sorted(
        [(comment, True) for comment in gh.comments_after(issue, floor)]
        + [
            (comment, False)
            for comment in gh.pr_conversation_comments_after(pr, floor)
        ],
        key=lambda pair: pair[0].id,
    )
