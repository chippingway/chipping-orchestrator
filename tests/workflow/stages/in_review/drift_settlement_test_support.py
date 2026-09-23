# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The in_review issue a requirements edit finds, and the words around it.

Every case here is about the ONE window a pull-request comment can reach this
stage's drift prompt through. The fresh-feedback scan runs first and routes
anything unread to `workflow:fixing`, so a comment that reaches the resume is
one written after that scan answered "nothing here" -- which is precisely what
`_drift_unread_pr_conv` re-reads the surface for.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from orchestrator.github.labels import PAUSED_LABEL
from orchestrator.workflow.engine import drift as _engine_drift
from tests.support.fakes import (
    FakeComment,
    FakeGitHubClient,
    FakeLabel,
    FakePR,
    FakePRRef,
    FakeUser,
    make_issue,
)
from tests.workflow.fixtures import (
    DEFAULT_PR_HEAD_SHA,
    LABEL_IN_REVIEW,
    MEASURED_CANDIDATE_SHA,
    _agent,
    _issue_branch,
    _PatchedWorkflowMixin,
)

SETTLEMENT_ISSUE = 1846
SETTLEMENT_PR = 18461
BRANCH = _issue_branch(SETTLEMENT_ISSUE)

HUMAN = "alice"
OUTSIDER = "mallory"
DEV_AGENT = "claude"
DEV_SESSION = "dev-sess"

RUN_AGENT = "run_agent"
LAST_ACTION_COMMENT_ID = "last_action_comment_id"
PR_LAST_COMMENT_ID = "pr_last_comment_id"
PR_LAST_REVIEW_COMMENT_ID = "pr_last_review_comment_id"
PR_LAST_REVIEW_SUMMARY_ID = "pr_last_review_summary_id"
USER_CONTENT_HASH = "user_content_hash"
PR_CONVERSATION_READER = "pr_conversation_comments_after"
THREAD_READER = "comments_after"
ISSUE_READER = "get_issue"

# Where both IssueComment cursors stand when the edit arrives: above the reply
# already on the thread, so nothing there is fresh feedback and the drift road
# owns the tick.
READ_THROUGH = 100
EARLIER_REPLY_ID = 50

UPDATED_BODY = "new acceptance criteria"
STALE_HASH = "stale-hash"
EARLIER_REPLY = "the criterion we agreed on last week"
LATE_PR_COMMENT = "and keep the CLI flag spelled the way it is"
OUTSIDER_URL = "https://example.invalid/malicious-patch.zip"
ACK_REPLY = "ACK: the existing commits already cover it"
QUESTION_REPLY = "which of the two did you mean?"

BEFORE_SHA = DEFAULT_PR_HEAD_SHA
RESUMED_SHA = MEASURED_CANDIDATE_SHA


def _said(comment_id: int, body: str, author: str = HUMAN) -> FakeComment:
    """One comment on either IssueComment surface, stamped an hour back.

    Old enough that no quiet window is still waiting on it, so a case about
    what a prompt carried is never also a case about the debounce.
    """
    return FakeComment(
        id=comment_id,
        body=body,
        user=FakeUser(author),
        created_at=datetime.now(UTC) - timedelta(hours=1),
    )


def _quoted(comment, label: str = "") -> str:
    """One comment as a drift prompt renders it."""
    author = comment.user.login
    body = comment.body
    return f"@{author}{label}: {body}"


def _expected_prompt(issue, spoken: list, appended: list) -> str:
    """The whole prompt a drift resume quoting exactly these comments gives.

    Built through the stage's own builder over the rendered lines, so a case
    compares what an agent was really handed rather than looking for a
    fragment inside it: a second copy of a reply, a comment the excerpt should
    have cut, and an outsider's URL all read as a substring hit and none
    survives this comparison.
    """
    conversation = "\n\n".join(_quoted(comment) for comment in spoken)
    if appended:
        block = "\n\n".join(
            _quoted(comment, label=" (PR comment)") for comment in appended
        )
        prefix = f"{conversation}\n\n" if conversation else ""
        conversation = (
            f"{prefix}Unread PR conversation comments:\n\n{block}"
        )
    return _engine_drift._build_user_content_change_prompt(issue, conversation)


class _LandsBetweenTheReads:
    """The pair a human writes between this road's TWO reads.

    The pull request's conversation is read first -- before the notice this
    road posts on it -- and the issue thread afterwards, so somebody posting
    in between lands on one surface the prompt can still quote and one it
    cannot. `unseen` is the half nobody read: on the pull request, numbered
    BELOW the reply the thread read does carry, which is the shape that lets a
    cursor spanning both surfaces step over it.

    It hooks the whole-thread read (`after_id is None`) because that is the
    read the resume freezes its record from, and it is the only one this tick
    takes over the entire thread.
    """

    def __init__(self, github, pull_request, *, unseen, quoted) -> None:
        self._answer = github.comments_after
        self._pull_request = pull_request
        self._unseen = unseen
        self._quoted = quoted
        self.landed = False

    def __call__(self, issue, after_id, **options):
        if after_id is None and not self.landed:
            self.landed = True
            self._pull_request.issue_comments.append(self._unseen)
            issue.comments.append(self._quoted)
        return self._answer(issue, after_id, **options)


class _LandsBeforeTheResume:
    """A pull-request comment written between the feedback scan and the resume.

    A class rather than a closure because it stands in for a named seam -- the
    client's own reader -- and the comment has to land in the one window that
    leaves it for the drift prompt to carry: after the scan that would have
    routed it to `workflow:fixing` has already answered, and before the read
    the resume freezes its record from. With no comment to land it is the
    client's own reader and nothing more, so every case runs through the same
    seam whether or not it is about that window.
    """

    def __init__(self, github, pull_request, comment=None) -> None:
        self._answer = github.pr_conversation_comments_after
        self._pull_request = pull_request
        self._comment = comment
        self.landed = False

    def __call__(self, pr, after_id):
        answered = self._answer(pr, after_id)
        if self._comment is not None and not self.landed:
            self.landed = True
            self._pull_request.issue_comments.append(self._comment)
        return answered


def _issue_view(github, paused: bool):
    """What a live-pause guard sees when it re-fetches after a run.

    An unpaused case answers with the client's own read, so the guard sees
    exactly what it sees in production; a paused one answers with the label an
    operator applied while the agent was out.
    """
    if not paused:
        return github.get_issue
    view = make_issue(SETTLEMENT_ISSUE, label=LABEL_IN_REVIEW)
    view.labels.append(FakeLabel(PAUSED_LABEL))
    return lambda number: view


class _EditedUnderReview(_PatchedWorkflowMixin):
    """An open pull request whose requirements a human moved under it."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(
            SETTLEMENT_ISSUE,
            label=LABEL_IN_REVIEW,
            body=UPDATED_BODY,
            comments=[_said(EARLIER_REPLY_ID, EARLIER_REPLY)],
        )
        self.github.add_issue(self.issue)
        self.pull_request = FakePR(
            number=SETTLEMENT_PR,
            head_branch=BRANCH,
            head=FakePRRef(sha=BEFORE_SHA),
            mergeable=True,
            check_state="success",
        )
        self.github.add_pr(self.pull_request)
        self.github.seed_state(
            self.issue,
            pr_number=SETTLEMENT_PR,
            branch=BRANCH,
            dev_agent=DEV_AGENT,
            dev_session_id=DEV_SESSION,
            review_round=1,
            **{
                USER_CONTENT_HASH: STALE_HASH,
                LAST_ACTION_COMMENT_ID: READ_THROUGH,
                PR_LAST_COMMENT_ID: READ_THROUGH,
                PR_LAST_REVIEW_COMMENT_ID: 0,
                PR_LAST_REVIEW_SUMMARY_ID: 0,
            },
        )

    def pinned(self) -> dict:
        return self.github.pinned_data(SETTLEMENT_ISSUE)

    def earlier_reply(self):
        """The reply the thread already carried, both cursors above it."""
        return self.issue.comments[0]

    def drifts(self, run, *, committed=False, paused=False, lands=None):
        """Run one whole in_review tick over this edit.

        `lands` is the pull-request comment a human writes in the window
        between the feedback scan and the resume's own read; without one the
        surface is empty and the prompt carries the issue thread alone.
        """
        reader = _LandsBeforeTheResume(self.github, self.pull_request, lands)
        with (
            self._patched(PR_CONVERSATION_READER, reader),
            self._patched(ISSUE_READER, _issue_view(self.github, paused)),
        ):
            return self._run_in_review(
                self.github,
                self.issue,
                run_agent=run,
                has_new_commits=committed,
                dirty_files=(),
                push_branch=True,
                head_shas=(
                    [BEFORE_SHA, RESUMED_SHA] if committed
                    else [BEFORE_SHA, BEFORE_SHA]
                ),
            )

    def drifts_while_both_land(self, run, *, unseen, quoted):
        """Run one tick with a comment landing on each side of the two reads.

        `unseen` goes onto the pull request after that surface has been read
        and `quoted` onto the issue thread before the thread read, which is
        the interleaving a cursor spanning both surfaces can step over.
        """
        reader = _LandsBetweenTheReads(
            self.github, self.pull_request, unseen=unseen, quoted=quoted,
        )
        with self._patched(THREAD_READER, reader):
            return self._run_in_review(
                self.github,
                self.issue,
                run_agent=run,
                has_new_commits=False,
                dirty_files=(),
                push_branch=True,
                head_shas=[BEFORE_SHA, BEFORE_SHA],
            )

    def enters_review_again(self):
        """The next `in_review` tick, after a human puts the label back."""
        self.github.apply_foreign_label(self.issue, LABEL_IN_REVIEW)
        return self._run_in_review(
            self.github, self.issue, run_agent=_agent(session_id=DEV_SESSION),
        )

    def _patched(self, reader: str, answer):
        """One of this client's readers, answered by the double a case needs.

        Every case goes through the same seams whether or not it is about a
        comment landing in one of this road's windows, so an unpaused,
        nothing-lands tick reads exactly what production reads.
        """
        return patch.object(
            self.github, reader, MagicMock(side_effect=answer),
        )
