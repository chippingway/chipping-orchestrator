# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The two surfaces one IssueComment id space is read as, and their cursors.

GitHub numbers the issue thread and the pull request's conversation from one
id space, and that numbering is not a shared delivery record. Two roads hand
issue-thread comments to a developer and only one of them has ever read the
pull request: the implementer's first prompt and every implementing or
validating resume quote the thread alone, recorded as the delivered stretch
of it (`engine/thread_delivery`) -- above the newest comment the first
prompt's bounded excerpt left out, through the newest a prompt quoted, apart
from the reply boundary a park waits above -- while `pr_last_comment_id` is
the mark this stage and `fixing` consume PR feedback against.

So the issue thread answers to both -- a comment the delivered stretch covers,
or at or below `pr_last_comment_id`, has been in a developer prompt -- and the
PR conversation answers to `pr_last_comment_id` and to nothing else. A comment
below the reply boundary that no prompt quoted -- context the first prompt's
bound cut, or a reply a park's notice was stamped over -- is outside the
stretch and still unread. One field asked of both
surfaces is wrong in both directions: the issue-thread record read over the
pull request hides every PR comment numbered below the last reply a developer
answered, and `pr_last_comment_id` read alone over the thread hands that same
answered reply back as fresh feedback the moment a manual relabel or a handoff
walk leaves it low.

`_issue_space_above` is the raw merged read the watermark walk takes instead,
tagged by surface rather than filtered, because that walk has its own rules
for what a comment above the mark may be -- and applying the thread's cursor
to the pull request there would be the same mistake in a second place.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import thread_delivery as _thread_delivery
from orchestrator.workflow.stages.in_review import state as _state


def _unread_issue_thread(
    gh: GitHubClient, issue: Issue, state: PinnedState, comments=None,
) -> list:
    """Issue-thread comments neither cursor over this surface has spent.

    Past `pr_last_comment_id` is only half the question: a reply an
    implementing or validating resume already answered is recorded on the
    delivered stretch of the thread instead (`thread_delivery.DeliveredThread`),
    and a `pr_last_comment_id` left BELOW it -- by a handoff walk that stopped
    at an unread PR comment, or by a manual relabel that left the key unset
    entirely -- would hand that answered reply to `fixing` a second time as
    fresh feedback. The stretch is asked rather than the reply boundary it
    ends on, because the boundary also stands over context no prompt quoted:
    the thread a pickup or handoff stood it past, as far as the first prompt's
    bound cut it, and a record carrying no floor, which counts nothing.

    `comments` is a read the caller already holds, cut in place of the
    thread's own. A caller that derives more than the batch from this surface
    -- the conversation a fresh spawn is re-grounded on, the requirements its
    report is stamped with -- owes every one of those answers to the SAME
    read, since a second one taken later in the tick carries a comment the
    first does not.
    """
    delivered = _thread_delivery.DeliveredThread.read(state)
    return [
        comment
        for comment in gh.comments_after(
            issue, state.get(_state._PR_LAST_COMMENT_ID), comments=comments,
        )
        if not delivered.covers(comment.id)
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
    apply the issue thread's delivered stretch to the issue thread alone. The
    issue thread is read FIRST, and the walk bounds itself by that order
    (`models._AnsweredIssueSpace.read_through`): a thread comment landing
    after its read is in neither list.
    """
    return sorted(
        [(comment, True) for comment in gh.comments_after(issue, floor)]
        + [
            (comment, False)
            for comment in gh.pr_conversation_comments_after(pr, floor)
        ],
        key=lambda pair: pair[0].id,
    )
