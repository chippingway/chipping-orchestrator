# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The approved issue a squash-on-approval tick runs over, and its doubles.

One seeded issue, one pull request, and one run of the validating handler with
the squash seam standing in for the real rewrite. Every case about what the
approval arc does with a squash outcome -- the handoff it earns, the park a
failure takes, the hold the size gate answers with, the route a recorded
collapse takes ahead of every agent -- starts from exactly this world, so it is
seeded here rather than in whichever module happened to need it first.

The collapse world beside it is the same seeding one step on: what a comment
carrying an unfinished squash, a park nobody has answered, an edited body, or a
human reply looks like, and the squash outcomes those cases are run against.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.publication import models as _publication
from orchestrator.git.publication.models import _SquashOutcome
from orchestrator.workflow.late_split import (
    collapses as _collapses,
    handoffs as _late_handoffs,
)
from orchestrator.workflow.stages.validating import state as _validating_state
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
    REVIEW_APPROVED_MESSAGE,
    _agent,
    _PatchedWorkflowMixin,
)

APPROVAL_ISSUE = 5

# The flags a size-gate park leaves in memory for its caller to persist, and
# the reason it words them under.
AWAITING_HUMAN = "awaiting_human"
PARK_REASON = "park_reason"
PARK_MEASUREMENT_FAILED = "late_measurement_failed"
PARK_SQUASH_FAILED = _validating_state._REASON_SQUASH_FAILED
APPROVAL_PR = 31
APPROVAL_BRANCH = "orchestrator/chippingway__orchestrator/issue-5"
REVIEWED_SHA = "reviewedAA"
# The commit a squash leaves behind, at the shape this domain holds every
# recorded end to: a whole object id, since the handoff record is one and a
# value that could not name a commit is one no later tick may act on.
SQUASHED_SHA = "5c3a91b7" * 5
PICKUP_COMMENT_ID = 900
PR_OPEN_COMMENT_ID = 901
REVIEW_DEBOUNCE_SECONDS = 600
SQUASH_ON_APPROVAL = "SQUASH_ON_APPROVAL"
LABEL_DOCUMENTING = "workflow:documenting"

# The two mocked seams a case asks whether anything ran through, spelled once:
# the agent spawn every road here has to leave alone, and the squash itself.
RUN_AGENT = "run_agent"
SQUASH_SEAM = "_squash_and_force_push"

# The client calls a case stands in for: the durable write, the relabel behind
# it, and the pull-request comment the notice goes out through.
PINNED_WRITE = "write_pinned_state"
SET_LABEL = "set_workflow_label"
PR_COMMENT = "pr_comment"

# What the collapse the mocked squash leaves behind says about itself, and the
# two keys a case reads it back under.
COLLAPSED_HEAD = "aa11bb22" * 5
COLLAPSED_BASE = "cc33dd44" * 5
COLLAPSED_COMMITS = 3
COLLAPSE_KEY = _collapses.LATE_COLLAPSE_HEAD
HANDOFF_KEY = _late_handoffs.LATE_COLLAPSE_HANDOFF

# The baseline a body edit leaves behind, and the field it is compared
# against: an issue whose content no longer hashes to it is one the drift
# route would resume the dev over.
USER_CONTENT_HASH = "user_content_hash"
STALE_CONTENT_HASH = "stale-hash"

# A human answering the park a refused recovery took.
HUMAN_REPLY_ID = 950
HUMAN_LOGIN = "maintainer"


class _MeasurementPark:
    """A squash the size gate held on a reading nobody could take.

    The park's own shape: the notice is worded and the flags are set in
    memory, and the caller is told the gate owns the issue. Nothing here
    relabels, because a park is not the adjudication.
    """

    def __call__(self, gate, _branch) -> _SquashOutcome:
        gate.state.set(AWAITING_HUMAN, True)
        gate.state.set(PARK_REASON, PARK_MEASUREMENT_FAILED)
        return _SquashOutcome(held=True)


class _LandsWithACollapseRecorded:
    """A squash that published and left its collapse recorded.

    What the real rewrite leaves on the pinned comment by the time it hands
    back: the push is on the remote, the receipt is written, and the terms of
    the collapse are still there because the notice they are worded from has
    not gone out yet.
    """

    def __call__(self, gate, _branch) -> _SquashOutcome:
        _collapses.record_pending_collapse(
            gate.state,
            head=COLLAPSED_HEAD,
            base_sha=COLLAPSED_BASE,
            count=COLLAPSED_COMMITS,
        )
        return _SquashOutcome(
            success=True, sha=SQUASHED_SHA, count=COLLAPSED_COMMITS,
        )


class _RefusesTheCollapse:
    """A squash owner that reports a record it could not account for.

    What a claim this build cannot read whole, or one the objects do not bear
    out, comes back as: the branch is left standing on a collapse and a human
    is owed the park.
    """

    def __call__(self, _gate, _branch) -> _SquashOutcome:
        return _SquashOutcome(
            error="this issue records a squash it could not finish",
            standing=_publication.BRANCH_COLLAPSED,
        )


class _RefusesTheRelabel:
    """A GitHub that takes every write and will not move the label.

    The one boundary a durable write cannot cover, because it is on the far
    side of one: everything the handoff owes is on the comment already, and
    the issue is still `validating`.
    """

    def __call__(self, issue, new_label, **_options):
        raise RuntimeError("label update rejected")


class _SquashApprovalFixtureMixin(_PatchedWorkflowMixin):
    def _setup(self):
        gh = FakeGitHubClient()
        long_ago = datetime.now(UTC) - timedelta(hours=1)
        issue = make_issue(
            APPROVAL_ISSUE,
            label="workflow:validating",
            title="add a feature",
            comments=[
                FakeComment(
                    id=PICKUP_COMMENT_ID,
                    body=":robot: orchestrator picking this up.",
                    user=FakeUser("orchestrator"),
                    created_at=long_ago,
                ),
                FakeComment(
                    id=PR_OPEN_COMMENT_ID,
                    body=":sparkles: PR opened: #31",
                    user=FakeUser("orchestrator"),
                    created_at=long_ago,
                ),
            ],
        )
        gh.add_issue(issue)
        # PR head SHA mirrors the post-squash remote head -- the force-push
        # inside the squash helper updates the remote, so by the time the
        # next gh.get_pr() is taken (inside _handle_validating's seeding
        # block, AND on the next in_review tick) the remote head matches
        # the new local SHA.
        pr = FakePR(
            number=APPROVAL_PR,
            head_branch=APPROVAL_BRANCH,
            head=FakePRRef(sha=SQUASHED_SHA),
            mergeable=True,
            check_state="success",
        )
        gh.add_pr(pr)
        gh.seed_state(
            APPROVAL_ISSUE,
            pr_number=APPROVAL_PR,
            branch=APPROVAL_BRANCH,
            dev_agent="claude",
            dev_session_id="dev-sess",
            review_round=0,
            orchestrator_comment_ids=[PICKUP_COMMENT_ID, PR_OPEN_COMMENT_ID],
            pickup_comment_id=PICKUP_COMMENT_ID,
        )
        return gh, issue, pr

    def _run_squash_approval(
        self,
        github,
        issue,
        squash_result,
    ):
        with patch.object(config, SQUASH_ON_APPROVAL, True):
            return self._run_validating(
                github,
                issue,
                run_agent=_agent(last_message=REVIEW_APPROVED_MESSAGE),
                head_shas=(REVIEWED_SHA,),
                squash_result=squash_result,
            )

    def _assert_squash_handoff(self, github, pr, mocks) -> None:
        self.assertEqual(
            mocks["_squash_and_force_push"].call_count,
            1,
        )
        self.assertEqual(mocks["run_agent"].call_count, 1)
        self.assertIn(
            (APPROVAL_ISSUE, LABEL_DOCUMENTING),
            github.label_history,
        )
        state = github.pinned_data(APPROVAL_ISSUE)
        squash_notice_posted = any(
            ":package: squashed 3 commits to 1" in body
            for _, body in github.posted_pr_comments
        )
        self.assertTrue(
            squash_notice_posted,
            f"squash notice not posted; got: {github.posted_pr_comments}",
        )
        approval_and_squash_ids = [
            comment.id
            for comment in pr.issue_comments
        ]
        self.assertTrue(approval_and_squash_ids)
        self.assertGreaterEqual(
            state.get("pr_last_comment_id"),
            max(approval_and_squash_ids),
            "watermark must include approval and squash comments",
        )

    def _run_review_after_squash(self, github, issue, pr):
        long_ago = datetime.now(UTC) - timedelta(hours=1)
        for comment in list(issue.comments) + list(pr.issue_comments):
            if comment.created_at is None:
                comment.created_at = long_ago
        pr.approved = True
        if not any(label.name == "in_review" for label in issue.labels):
            issue.labels = [FakeLabel("in_review")]
        with patch.object(
            config,
            "IN_REVIEW_DEBOUNCE_SECONDS",
            REVIEW_DEBOUNCE_SECONDS,
        ):
            return self._run_in_review(
                github,
                issue,
                run_agent=_agent(),
            )

    def _assert_ready_ping(self, github, mocks) -> None:
        mocks["run_agent"].assert_not_called()
        self.assertEqual(github.merge_calls, [])
        self.assertNotIn(
            (APPROVAL_ISSUE, "done"),
            github.label_history,
        )
        ping_comments = [
            body
            for _, body in github.posted_comments
            if "ready for review/merge" in body
        ]
        self.assertEqual(len(ping_comments), 1)
        self.assertEqual(
            github.pinned_data(APPROVAL_ISSUE).get("ready_ping_sha"),
            SQUASHED_SHA,
        )

    def _assert_squash_parked(self, github, mocks) -> None:
        self.assertEqual(
            mocks["_squash_and_force_push"].call_count,
            1,
        )
        state = github.pinned_data(APPROVAL_ISSUE)
        self.assertTrue(state.get("awaiting_human"))
        park_posted = any(
            "squash-on-approval failed" in body
            for _, body in github.posted_comments
        )
        self.assertTrue(
            park_posted,
            f"HITL park message not posted; got: {github.posted_comments}",
        )
        self.assertNotIn(
            (APPROVAL_ISSUE, "in_review"),
            github.label_history,
            "park must not relabel to in_review",
        )
        self.assertNotIn(
            (APPROVAL_ISSUE, LABEL_DOCUMENTING),
            github.label_history,
            "park must not start the final-docs hop",
        )


class _CollapseWorldMixin:
    """What a tick can find on the comment before the approval road runs."""

    def _approved_issue(self):
        """The seeded client and issue, without the pull request beside them."""
        return self._setup()[:2]

    def _lands_a_collapse(self, github, issue):
        """One approval tick whose squash publishes and records its collapse."""
        return self._run_squash_approval(
            github, issue, _LandsWithACollapseRecorded(),
        )

    def _records_a_collapse(self, github) -> None:
        """Put the terms of an unfinished squash on the pinned comment."""
        issue = github.get_issue(APPROVAL_ISSUE)
        state = github.read_pinned_state(issue)
        _collapses.record_pending_collapse(
            state,
            head=COLLAPSED_HEAD,
            base_sha=COLLAPSED_BASE,
            count=COLLAPSED_COMMITS,
        )
        github.write_pinned_state(issue, state)

    def _edits_the_body(self, github) -> None:
        """Leave a user-content baseline this issue no longer hashes to."""
        self._pins(github, USER_CONTENT_HASH, STALE_CONTENT_HASH)

    def _parks(self, github, reason: str = PARK_MEASUREMENT_FAILED) -> None:
        """Park the issue, under the owner whose notice worded it."""
        self._pins(github, AWAITING_HUMAN, True)
        self._pins(github, PARK_REASON, reason)

    def _pins(self, github, key: str, pinned) -> None:
        issue = github.get_issue(APPROVAL_ISSUE)
        state = github.read_pinned_state(issue)
        state.set(key, pinned)
        github.write_pinned_state(issue, state)

    def _human_replies(self, issue) -> None:
        """A human answering the park, on the issue thread."""
        issue.comments.append(FakeComment(
            id=HUMAN_REPLY_ID,
            body="reconciled the branch by hand",
            user=FakeUser(HUMAN_LOGIN),
        ))
