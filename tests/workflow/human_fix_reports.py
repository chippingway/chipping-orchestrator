# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The fix round a human opens on an APPROVED pull request, driven as it runs.

The third way into the one fix loop `fix_reports` holds the world for. The
reviewer's two roads reach `fixing` from `validating`; this one reaches it from
`in_review`, where a human comments on a pull request the reviewer has already
approved: that stage bookmarks the batch, refreshes the requirements baseline so
its own comment does not read as drift, and flips the label, and the `fixing`
tick behind it is the round that answers.

Both ticks are driven for real rather than seeded, because what the route WRITES
is half of what the road is -- the bookmarks a settlement clears, and
`pending_fix_at`, the discriminator the round accounting reads. Seeded instead, a
case would be asserting against a shape of its own rather than against the one
`in_review` leaves.

The `in_review` tick resumes NOBODY, and that is held in the driver rather than
at each case: the route spawns no agent of its own on any road that reaches it,
so a developer paid for there is one nobody asked for.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from orchestrator.workflow.engine import review_subjects as _review_subjects
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow import fix_reports as _fix_world
from tests.workflow.fixtures import _agent

# What a human writes on a pull request the reviewer has already approved, which
# is what the route bookmarks and hands this stage. One asks for code and one
# asks for words, because a round's handover forks on which it is.
HUMAN_CODE_FEEDBACK = "the error path still swallows the exception"

HUMAN_REPORT_FEEDBACK = "your report never says how the suite was run"

# What a human adds on the pull request while the developer is out, which this
# round's prompt never carried and no reader of it may move past.
LATER_PR_COMMENT = "and the retry loop needs a bound while you are in there"

# What a developer says on a poll that asked it nothing. Staged rather than
# refused outright, so a road that does resume a developer where it may not is
# caught by the case's own spawn count instead of by a runner raising out of the
# handler.
_UNSPOKEN = "nothing this poll asked for"

# The seam a tick's spawn count is read off.
_RUN_AGENT = "run_agent"


class _MidRunPrComment:
    """A run during which a human comments on the PULL REQUEST, then replies.

    The pull request rather than the issue thread, and the difference is the
    whole point of the helper: an issue reply is requirements the round never
    saw, which the settlement refuses to publish a report over, while a PR
    comment is ordinary feedback this round simply did not answer. So what this
    stages is a report that DOES publish, beside a comment every reader has to
    stop below.

    The id is minted through the client, above everything the ticks ahead of it
    have already posted.
    """

    def __init__(self, case, reply: str) -> None:
        self._case = case
        self._reply = reply
        self.comment: FakeComment | None = None

    def __call__(self, *_args, **_kwargs):
        self.comment = FakeComment(
            id=self._case.github.next_reply_id(self._case.issue),
            body=LATER_PR_COMMENT,
            user=FakeUser("alice"),
        )
        self._case.pull_request.issue_comments.append(self.comment)
        return _agent(
            session_id=_fix_world.DEV_SESSION, last_message=self._reply,
        )


def comments_mid_run(case, reply: str) -> _MidRunPrComment:
    """A human commenting on the pull request while the developer is out."""
    return _MidRunPrComment(case, reply)


def shared_account_reply(case, body: str) -> FakeComment:
    """One human reply written from the account the orchestrator posts as.

    The ordinary single-operator deployment: one personal access token, and
    every comment either of them writes wearing the same login. So the AUTHOR
    tells the two apart nowhere, and what keeps the orchestrator's own comments
    out of the feedback it reads back is the hidden marker it writes into
    them -- which a person typing into the same account carries none of.
    """
    posted = FakeComment(
        id=case.github.next_reply_id(case.issue),
        body=body,
        user=case.issue.commenter,
    )
    case.issue.comments.append(posted)
    return posted


def approves_the_report(case) -> None:
    """Record the approval the fresh review a report's hand-back earns gives.

    What `in_review` holds an approval to is the report the pull request
    carries: a case that puts a handed-back issue straight back on that label
    records the approval of the report it carries, as the review in between
    would have.
    """
    current = case.records()["current"]
    state = case.github.read_pinned_state(case.issue)
    _review_subjects.record_approved(state, _review_subjects.ReviewSubject(
        pr_number=current.subject.pr_number,
        commit=current.subject.source_sha,
        requirements_revision=current.subject.requirements_revision,
        report=_review_subjects.ReviewReport(
            text="",
            report_revision=current.report_revision,
            content_revision=current.content_revision,
            source_sha=current.subject.source_sha,
            requirements_revision=current.subject.requirements_revision,
            location=current.location,
        ),
    ))
    case.github.write_pinned_state(case.issue, state)


class _HumanFixReportMixin(_fix_world._FixReportMixin):
    """The fix loop as a human's comment on an approved pull request drives it.

    The reviewer's world, unchanged: the same open pull request, the same
    checkout, the same push that moves what it lands on. Only the way in is
    this module's.
    """

    def rescanned(self):
        """One `in_review` tick over whatever the pull request now carries.

        The refusal is held here rather than at each case, because it is the
        route's contract rather than any one case's claim: this stage bookmarks
        fresh feedback and flips the label, and the dev resume belongs to the
        fixing handler -- so a developer paid for on this tick is one nobody
        asked for, on every road that reaches it.
        """
        routing = self._ticked(
            self._run_in_review,
            MagicMock(side_effect=_fix_world._Runs(_UNSPOKEN)),
        )
        routing[_RUN_AGENT].assert_not_called()
        return routing

    def routed(self, feedback: str = HUMAN_CODE_FEEDBACK):
        """One fresh human comment, and the `in_review` tick that routes it."""
        _fix_world.replied(self, feedback)
        return self.rescanned()

    def resumed(self, reply, **run_options):
        """One fixing tick, resuming the developer over the feedback in hand."""
        return self._ticked(
            self._run_fixing,
            MagicMock(side_effect=_fix_world._Runs(reply)),
            **run_options,
        )

    def human_fix(self, reply, feedback: str = HUMAN_CODE_FEEDBACK, **run_options):
        """The human-feedback route, both of the ticks it takes."""
        self.routed(feedback)
        return self.resumed(reply, **run_options)

    def polled(self, reply: str = _UNSPOKEN, **run_options):
        """One later fixing tick, over whatever the issue is still carrying."""
        return self.resumed(reply, committed=False, **run_options)
