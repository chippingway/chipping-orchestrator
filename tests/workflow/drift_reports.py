# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The open pull request a requirements-drift resume reports onto.

Both review stages resume the developer when the issue is edited under an open
pull request, and both publish what that session reports. The world every case
runs in is the one production leaves: a pull request on the issue's branch
whose last publication the code-publication receipt names, a checkout standing
on its head, and a push that moves the pull request to the commit it sends --
so the reconciliation that settles the report reads the same evidence it would
read on a real host. What a case varies is the run's reply, the push, the way
GitHub answers the post, and what a human does while the agent is out.
"""
from __future__ import annotations

import copy
from functools import partial
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    content_hash as _content_hash,
    report_delivery_state as _delivery_state,
    report_record_state as _record_state,
    report_settlement_state as _settlement,
    report_transaction as _report_transaction,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import (
    DEFAULT_PR_HEAD_SHA,
    FakeComment,
    FakeGitHubClient,
    FakeUser,
    make_issue,
)
from tests.workflow.fixtures import (
    _TEST_SPEC,
    MEASURED_CANDIDATE_SHA,
    _agent,
    _issue_branch,
    _open_pr_for,
    _PatchedWorkflowMixin,
)

DEV_SESSION = "dev-sess"

# The head the pull request stands on when the edit lands, which the receipt
# names and the checkout is on; and the commit a resume that answers the edit
# with code leaves, which is the one the size gate proves the checkout to.
PUBLISHED_HEAD = DEFAULT_PR_HEAD_SHA

FIXED_HEAD = MEASURED_CANDIDATE_SHA

EDITED_BODY = "updated acceptance criteria"

# What a human changes, or says, while the resumed session is out.
LATER_BODY = "the criteria moved again while the agent worked"

LATER_COMMENT = "one more thing the edit should cover"

LATER_COMMENT_ID = 50_000

REPORT_TEXT = "Answers the edited criteria; the suite passes."

LATER_REPORT_TEXT = "Covers the second edit as well, on the same commit."

# The run options a case seeds the checkout's own head readings with, and the
# divergence proof its remote branch answers -- the commits the branch carries
# that the pull request has not, and the head they were counted against, which
# is what a publication from that checkout is leased to.
HEAD_SHAS = "head_shas"

AHEAD_BEHIND = "branch_ahead_behind"

FETCHED_TIP = "fetched_branch_tip"

# A resume that committed nothing over a checkout carrying the commit an
# earlier run left unpublished: the head is that commit, one ahead of the pull
# request, which is the tip a publication from here replaces.
STRANDED = MappingProxyType({
    HEAD_SHAS: (FIXED_HEAD, FIXED_HEAD),
    AHEAD_BEHIND: (1, 0),
    FETCHED_TIP: PUBLISHED_HEAD,
})

# The commit a run leaves on the branch and publishes nothing of, whatever
# became of that run -- a report it never wrote, or a shutdown that killed it
# before anything was recorded. The pull request is left standing under it.
STRANDED_HEAD = "a" * len(FIXED_HEAD)

STRANDS = MappingProxyType({HEAD_SHAS: (PUBLISHED_HEAD, STRANDED_HEAD)})

# The retry behind such a run, which commits AGAIN: it begins on the stranded
# head and leaves its own on top, so the pull request stands two commits below
# the checkout and the head this publication replaces is neither of them.
RETRY_OVER_STRANDED = MappingProxyType({
    HEAD_SHAS: (STRANDED_HEAD, FIXED_HEAD),
    AHEAD_BEHIND: (2, 0),
    FETCHED_TIP: PUBLISHED_HEAD,
})

# A checkout path that exists, so the reconciliation's own reading of the
# worktree is taken rather than deferred as a checkout on another host.
_EXISTING_WORKTREE = Path("/tmp")


def reported(text: str = REPORT_TEXT) -> str:
    """A finished resume's message, ending on a report ready for publication."""
    return f"done\n\nREPORT: READY\n{text}\nREPORT: END"


def handed_revision(issue) -> str:
    """The revision a resume launched on this issue as it stands is handed."""
    return _content_hash._compute_user_content_hash(issue, set())


def edits(case, body: str) -> str:
    """Rewrite the issue body as GitHub answers the next read with it.

    A NEW issue object registered in the client's place, since that is what a
    human editing the issue leaves: the tick that fetched the old one still
    holds it, and everything read afterwards reads this.
    """
    edited = copy.copy(case.issue)
    edited.body = body
    case.github.add_issue(edited)
    case.issue = edited
    return body


def human_reply(case, body: str = "please write the report") -> None:
    """Put one trusted human reply above everything the thread already holds."""
    thread = [comment.id for comment in case.issue.comments]
    watermark = case.pinned().get("last_action_comment_id") or 0
    case.issue.comments.append(FakeComment(
        id=max((*thread, watermark, LATER_COMMENT_ID)) + 1,
        body=body,
        user=FakeUser("alice"),
    ))


class _MidRunChange:
    """A run during which a human changes the issue, before the agent replies.

    An `edit` is what GitHub answers a later read with: a NEW issue object
    carrying the new body, registered in the client's place, while the tick
    that launched the run still holds the one it fetched first. A `comment`
    lands on the thread itself, which every read walks afresh.
    """

    def __init__(self, case, change: str, reply: str) -> None:
        self._case = case
        self._change = change
        self._reply = reply

    def __call__(self, *_args, **_kwargs):
        if self._change == "edit":
            self._edits()
        else:
            self._case.issue.comments.append(FakeComment(
                id=LATER_COMMENT_ID, body=LATER_COMMENT, user=FakeUser("alice"),
            ))
        return _agent(session_id=DEV_SESSION, last_message=self._reply)

    def _edits(self) -> None:
        edits(self._case, LATER_BODY)


class _LandingPush:
    """A push that lands and leaves the pull request on the commit it sent."""

    def __init__(self, pull_request) -> None:
        self._pull_request = pull_request

    def __call__(self, spec, worktree, branch, *, force_with_lease=None, revision=None):
        if revision:
            self._pull_request.head.sha = revision
        return True


class _DriftReportMixin(_PatchedWorkflowMixin):
    """Review-stage ticks over an issue edited under its open pull request.

    `seeded` builds the world on the case -- `github`, `issue`, and the
    `pull_request` -- and every other method reads it from there, so a case
    that loops over subtests re-seeds it rather than threading it through.
    """

    def seeded(self, issue_number: int, pr_number: int, label: str, **extra) -> None:
        """The issue, its open pull request, and a baseline the edit moved off."""
        self.github = FakeGitHubClient()
        self.issue = make_issue(issue_number, label=label, body=EDITED_BODY)
        self.github.add_issue(self.issue)
        self.pull_request = _open_pr_for(
            self.github, issue_number=issue_number, pr_number=pr_number,
        )
        self.github.seed_state(issue_number, **{
            "user_content_hash": "stale-hash",
            "dev_agent": "claude",
            "dev_session_id": DEV_SESSION,
            "pr_number": pr_number,
            "branch": _issue_branch(issue_number),
            "review_round": 0,
            "pr_last_comment_id": 0,
            "pr_last_review_comment_id": 0,
            "pr_last_review_summary_id": 0,
            # The receipt the publication that opened this pull request left.
            "implementing_published_sha": PUBLISHED_HEAD,
            "implementing_published_pr": pr_number,
            "implementing_published_lease": None,
            **extra,
        })

    def drift(self, run_agent, **run_options):
        """Run one tick of the issue's stage over a checkout on this host.

        `run_agent` is a reply, or the run itself. A resume that `committed`
        leaves the checkout on `FIXED_HEAD`; one that did not leaves it where
        the pull request stands. The push moves the pull request onto the
        commit it sends, as GitHub would answer it.
        """
        if isinstance(run_agent, str):
            run_agent = _agent(session_id=DEV_SESSION, last_message=run_agent)
        standing = self.pull_request.head.sha
        after = FIXED_HEAD if run_options.pop("committed", True) else standing
        options = {
            "has_new_commits": True,
            "dirty_files": (),
            "push_branch": _LandingPush(self.pull_request),
            HEAD_SHAS: (standing, after),
            FETCHED_TIP: after,
            **run_options,
        }
        stage = (
            self._run_in_review
            if any(seen.name == WorkflowLabel.IN_REVIEW for seen in self.issue.labels)
            else self._run_validating
        )
        with patch.object(
            _worktree_paths, "_worktree_path", return_value=_EXISTING_WORKTREE,
        ):
            return stage(self.github, self.issue, run_agent=run_agent, **options)

    def reconcile(self):
        """The dispatch reconciliation ahead of the next handler, on this host."""
        head = self.pull_request.head.sha
        with patch.object(
            _worktree_paths, "_worktree_path", return_value=_EXISTING_WORKTREE,
        ):
            return self._run(
                partial(
                    _report_transaction._reconciles_pending_report,
                    self.github, _TEST_SPEC, self.issue, None,
                    self.github.read_pinned_state(self.issue),
                ),
                run_agent=_agent(),
                head_shas=(head,),
                fetched_branch_tip=head,
            )

    def mid_run(self, change: str, reply: str) -> _MidRunChange:
        """A run during which a human `edit`s or `comment`s, then replies."""
        return _MidRunChange(self, change, reply)

    def published_reports(self, text: str = REPORT_TEXT) -> list:
        """Every comment on the pull request that carries one report's text."""
        return [
            posted for posted in self.pull_request.issue_comments
            if text in (posted.body or "")
        ]

    def records(self) -> dict:
        """The delivered, pending, and current reports the pinned comment holds."""
        state = PinnedState(state_data=self.pinned())
        return {
            "delivered": _delivery_state.read_delivered_report(state),
            "pending": _record_state.read_pending_report(state),
            "current": _settlement.read_current_report(state),
        }

    def pinned(self) -> dict:
        """What the issue's pinned comment holds now."""
        return self.github.pinned_data(self.issue.number)
