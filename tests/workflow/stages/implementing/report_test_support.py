# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Fixtures for the developer report an implementing publication delivers.

The world every case here runs in is the ordinary fresh publication: a clean
worktree carrying one commit, a push that lands, and a developer whose final
message ends on one of the two report outcomes. What each case varies is the
outcome, the pull request the code reaches, or the way GitHub answers the post.
"""

from __future__ import annotations

from orchestrator.github import developer_reports as _reports
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    content_hash as _content_hash,
    report_delivery_state as _delivery_state,
    report_records as _records,
)
from orchestrator.workflow.late_split import formats as _formats
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeUser, make_issue
from tests.workflow.fixtures import (
    LABEL_IMPLEMENTING,
    MEASURED_CANDIDATE_SHA,
    _agent,
    _issue_branch,
    _PatchedWorkflowMixin,
)

DEV_SESSION = "sess-report"

REPORT_ISSUE = 1

# The commit the ordinary world publishes, which is the one the size gate
# proves the checkout to and the one every record here is about.
PUBLISHED_SHA = MEASURED_CANDIDATE_SHA

BRANCH = _issue_branch(REPORT_ISSUE)

REPORT_TEXT = "Adds the thing the issue asked for. Verified with the suite."

LAST_MESSAGE_HEADING = "_Last agent message:_"

# The repository every fixture here is about, and one that is somebody else's.
OWN_SLUG = "chippingway/orchestrator"

FOREIGN_SLUG = "someone/else"

# The thread read a park stamps, which a reply has to land above.
WATERMARK = "last_action_comment_id"

# The comment a pickup posts and anchors both thread cursors on.
PICKUP_GREETING = "picking this up"
PICKUP_COMMENT_ID = "pickup_comment_id"
USER_CONTENT_HASH = "user_content_hash"

# A whole digest, since that is what a requirements revision is read at.
REQUIREMENTS_REVISION = "a" * max(_formats.DIGEST_LENGTHS)

DELIVERY_RECORD = _records.DELIVERED_REPORT
PENDING_RECORD = _records.PENDING_REPORT
CURRENT_RECORD = _records.CURRENT_REPORT
HANDOFF_RECORD = _records.REPORT_HANDOFF


def ready_message(report: str = REPORT_TEXT) -> str:
    """A finished run's message, ending on a report ready for publication."""
    return f"implemented\n\nREPORT: READY\n{report}\nREPORT: END"


def verified_message(
    pr_number: int,
    body: str,
    *,
    comment_id: int | None = None,
    slug: str = OWN_SLUG,
) -> str:
    """A finished run's message, asserting a report is already published.

    On a comment, named by its anchor, or on the description, by the bare URL.
    """
    anchor = "" if comment_id is None else f"#issuecomment-{comment_id}"
    return (
        "implemented\n\nREPORT: VERIFIED "
        f"https://github.com/{slug}/pull/{pr_number}"
        f"{anchor} sha256:{_reports.content_digest(body)}"
    )


def receipt_scope(revision: int = 1, issue_number: int = REPORT_ISSUE) -> str:
    """The header prefix every comment published for one transaction carries."""
    return _reports.DeveloperReport(
        pr_number=1,
        source_sha=PUBLISHED_SHA,
        requirements_revision="r",
        report_revision=revision,
        receipt=f"issue-{issue_number}-report-{revision}",
        text=REPORT_TEXT,
    ).receipt_scope


def published_reports(github, pr_number: int, revision: int = 1) -> list:
    """Every comment on one pull request published for one transaction."""
    return [
        posted for posted in github.get_pr(pr_number).issue_comments
        if receipt_scope(revision) in posted.body
    ]


def replies(github, issue, body: str = "please deliver the report inline"):
    """Put one trusted human reply above whatever watermark a park left."""
    reply = FakeComment(
        id=github.pinned_data(issue.number)[WATERMARK] + 1,
        body=body,
        user=FakeUser("alice"),
    )
    issue.comments.append(reply)
    return reply


def owing_state() -> PinnedState:
    """A pinned comment carrying one delivered report nothing has bound yet."""
    state = PinnedState()
    _delivery_state.record_delivered_report(state, _records.DeliveredReport(
        receipt=f"issue-{REPORT_ISSUE}-report-1",
        report_revision=1,
        mode=_records.ReportMode.PUBLISH,
        route=WorkflowLabel.IMPLEMENTING,
        requirements_revision=REQUIREMENTS_REVISION,
        report=REPORT_TEXT,
    ))
    return state


class _ReportDeliveryMixin(_PatchedWorkflowMixin):
    """One implementing tick over a worktree that carries a fresh commit."""

    def seeded(self, issue_number: int = REPORT_ISSUE):
        """An open issue labelled `implementing`, as the pickup left it.

        Its greeting anchors the watermark -- the floor the park ending a run
        walks from, which reads no further than our own identified comments --
        and nothing else is recorded yet.
        """
        github = FakeGitHubClient()
        issue = make_issue(issue_number, label=LABEL_IMPLEMENTING)
        github.add_issue(issue)
        greeting = github.comment(issue, _comments._with_orch_marker(PICKUP_GREETING))
        github.seed_state(issue_number, **{
            WATERMARK: greeting.id,
            PICKUP_COMMENT_ID: greeting.id,
            _comments._ORCH_COMMENT_IDS: [greeting.id],
            USER_CONTENT_HASH: _content_hash._compute_user_content_hash(issue, {greeting.id}),
        })
        return github, issue

    def deliver(self, github, issue, message: str, **run_options):
        """Run one tick whose developer comes back with `message`."""
        return self._ticks(
            github, issue, message,
            **{"has_new_commits": [False, True], **run_options},
        )

    def redeliver(self, github, issue, message: str, **run_options):
        """Run a resumed tick whose developer reports and commits nothing."""
        return self._ticks(
            github, issue, message,
            **{"head_shas": (PUBLISHED_SHA, PUBLISHED_SHA), **run_options},
        )

    def republish(self, github, issue, **run_options):
        """Run the tick that recovers committed work; no developer runs on it."""
        return self._ticks(github, issue, "unused", **run_options)

    def _ticks(self, github, issue, message: str, **run_options):
        """One implementing tick over a clean worktree whose push lands."""
        return self._run_implementing(
            github,
            issue,
            run_agent=_agent(session_id=DEV_SESSION, last_message=message),
            **{
                "has_new_commits": True,
                "dirty_files": (),
                "push_branch": True,
                **run_options,
            },
        )
