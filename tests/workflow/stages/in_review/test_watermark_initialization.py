# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for the in_review initialization of an unset watermark: an issue a
human relabeled into the stage, or one an approval handed on without the
snapshot its seed is read off, and how far the first tick may say it has read
each of its surfaces."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from functools import partial
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import (
    comments as _comments,
    pickup as _pickup,
    prompt_context as _prompt_context,
    thread_delivery as _thread_delivery,
)
from orchestrator.workflow.stages.validating import handoff as _handoff
from tests.support.fakes import (
    FakeComment,
    FakeGitHubClient,
    FakePR,
    FakePRRef,
    FakePRReview,
    FakeUser,
    make_issue,
)
from tests.workflow import approval_records as _approval_records, verified_approvals as _verified
from tests.workflow.fixtures import (
    _agent,
    _issue_branch,
    _PatchedWorkflowMixin,
)

ENTRY_ISSUE = 150
ENTRY_PR = 300
EMPTY_PR_ISSUE = 400
EMPTY_PR = 900
PICKUP_COMMENT_ID = 910
PR_OPEN_COMMENT_ID = 911
APPROVAL_COMMENT_ID = 920
INLINE_REVIEW_ID = 30
REVIEW_SUMMARY_ID = 4000
FIRST_INLINE_REVIEW_ID = 42
FIRST_REVIEW_SUMMARY_ID = 5050
REVIEW_DEBOUNCE_SECONDS = 600
BOT_LOGIN = "orchestrator"
ORCH_MARKER = "<!--orchestrator-comment-->"
FIXING = "workflow:fixing"
# A comment on the pull request numbered BELOW the pickup: a PR a plan handoff
# reused or a human opened carries conversation the spawn never quoted, so
# being old is no evidence there that anybody read it.
PRE_PICKUP_PR_COMMENT_ID = 890
PRE_PICKUP_PR_BODY = "this reuses the schema we rejected last quarter"
# The same age on the issue thread, which only the delivered stretch can vouch
# for: the pickup's id alone says nothing about who read it.
PRE_PICKUP_THREAD_ID = 905
PRE_PICKUP_THREAD_BODY = "the migration must keep the old column for a release"
# Posted while validating ran: below the approval, above the PR-opened notice.
DURING_VALIDATING_ID = 915
DURING_VALIDATING_BODY = "hold the merge until the rollout window"
REVIEWED_SHA = "cafe1234" * 5
HUMAN_LOGIN = "alice"
BACKEND_CLAUDE = "claude"
DEV_SESSION = "dev-sess"
DEBOUNCE_SETTING = "IN_REVIEW_DEBOUNCE_SECONDS"
RUN_AGENT = "run_agent"
PR_LAST_COMMENT_ID = "pr_last_comment_id"
PR_LAST_REVIEW_COMMENT_ID = "pr_last_review_comment_id"
PR_LAST_REVIEW_SUMMARY_ID = "pr_last_review_summary_id"
WATERMARKS = (PR_LAST_COMMENT_ID, PR_LAST_REVIEW_COMMENT_ID, PR_LAST_REVIEW_SUMMARY_ID)
PENDING_FIX_ISSUE_IDS = "pending_fix_issue_ids"
UNANSWERED = "github did not answer"
# The oldest comment on a thread whose first prompt's excerpt cuts it
# part-way, under one long enough to take, with the pickup greeting quoted
# after it, nearly all of the excerpt's room.
CUT_ID = 10
CUT_BODY = "REQUIRED: keep the old column"
QUOTED_ID = 20
LONG_CONTEXT_CHARS = 3880
# A reply on the issue thread and then a bare control on the pull request,
# both landing between the two reads a walk takes, numbered above everything
# either read was taken over.
RACED_REPLY_ID = 1010
RACED_REPLY_BODY = "do not merge; this drops the audit rows"
RACED_CONTROL_ID = 1020
RACED_CONTROL_BODY = "/orchestrator add-agent-runs 1"
LONG_AGO = datetime.now(UTC) - timedelta(hours=1)


def _ours(comment_id: int, body: str) -> FakeComment:
    """A post the hidden marker alone proves is ours: the id ledger evicted it."""
    return FakeComment(
        id=comment_id,
        body=f"{body}\n\n{ORCH_MARKER}",
        user=FakeUser(BOT_LOGIN),
        created_at=LONG_AGO,
    )


def _theirs(comment_id: int, body: str) -> FakeComment:
    return FakeComment(
        id=comment_id, body=body, user=FakeUser(HUMAN_LOGIN), created_at=LONG_AGO,
    )


class _EntryFixtureMixin(_PatchedWorkflowMixin):
    def _entry_setup(
        self, *, pr_conversation=(), thread=(), delivered=(0, PICKUP_COMMENT_ID),
    ):
        """An issue reaching in_review with no watermark set.

        Its pickup greeting and PR-opened notice on the issue thread are ours
        by the hidden marker alone, the bounded id ledger having evicted its
        oldest entries; the approval on the PR conversation, our newest post,
        is still in it. The pickup stood the reply boundary on its own
        comment; `delivered` is the stretch of the issue thread a developer
        prompt was handed, apart from that boundary: the floor and the upper
        end its first spawn recorded, either None where the record never
        carried it. The two review surfaces carry human feedback nothing
        records having delivered.
        """
        gh = FakeGitHubClient()
        issue = make_issue(
            ENTRY_ISSUE,
            label="in_review",
            comments=[
                *thread,
                _ours(PICKUP_COMMENT_ID, ":robot: orchestrator picking this up."),
                _ours(PR_OPEN_COMMENT_ID, ":sparkles: PR opened: #300"),
            ],
        )
        gh.add_issue(issue)
        pr = FakePR(
            number=ENTRY_PR,
            head_branch=_issue_branch(ENTRY_ISSUE),
            head=FakePRRef(sha=REVIEWED_SHA),
            mergeable=True,
            check_state="success",
            issue_comments=[
                *pr_conversation,
                _ours(APPROVAL_COMMENT_ID, ":white_check_mark: codex review approved."),
            ],
            review_comments=[_theirs(INLINE_REVIEW_ID, "line 5: drop the trailing newline")],
            reviews=[
                FakePRReview(
                    id=REVIEW_SUMMARY_ID,
                    body="please rename foo to bar",
                    state="CHANGES_REQUESTED",
                    user=FakeUser(HUMAN_LOGIN),
                    submitted_at=LONG_AGO,
                    commit_id=REVIEWED_SHA,
                ),
            ],
        )
        gh.add_pr(pr)
        records = {
            "pickup_comment_id": PICKUP_COMMENT_ID,
            "last_action_comment_id": PICKUP_COMMENT_ID,
            "orchestrator_comment_ids": [APPROVAL_COMMENT_ID],
        }
        gh.seed_state(
            ENTRY_ISSUE,
            pr_number=ENTRY_PR,
            **_approval_records.approved_in_review(
                issue, ENTRY_PR, orchestrator_ids=records["orchestrator_comment_ids"],
            ),
            branch=_issue_branch(ENTRY_ISSUE),
            dev_agent=BACKEND_CLAUDE,
            dev_session_id=DEV_SESSION,
            **records,
            **self._recorded_delivery(delivered),
        )
        return gh, issue, pr

    def _recorded_delivery(self, delivered: tuple) -> dict:
        """The delivered stretch's two fields as a record carries them, a None one absent."""
        named = zip(("delivered_after_comment_id", "delivered_through_comment_id"), delivered, strict=True)
        return {field: bound for field, bound in named if bound is not None}

    def _debounced_tick(self, gh, issue, **run_options):
        with patch.object(config, DEBOUNCE_SETTING, REVIEW_DEBOUNCE_SECONDS):
            return self._run_in_review(gh, issue, run_agent=_agent(), **run_options)

    def _marks(self, gh, number: int = ENTRY_ISSUE) -> list:
        """The three watermarks as the issue's pinned comment carries them."""
        return [gh.pinned_data(number).get(field) for field in WATERMARKS]


class ManualEntryInitializationTest(unittest.TestCase, _EntryFixtureMixin):
    """Initialize each unset surface of a manually relabeled issue as far as
    recorded delivery goes, and no further."""

    def test_each_surface_initialized_by_its_evidence(self) -> None:
        # The issue side advances through the posts the hidden marker proves
        # are ours -- on both IssueComment surfaces -- so the pickup greeting,
        # the PR-opened notice, and the approval are never re-read as
        # somebody's review. The orchestrator posts on neither review surface
        # and nothing records a developer reading either, so both are
        # initialized at 0 and the review a developer was never shown routes
        # to `fixing` -- with no developer run and no hand-back here.
        gh, issue, _pr = self._entry_setup()

        mocks = self._debounced_tick(gh, issue)

        mocks[RUN_AGENT].assert_not_called()
        self.assertNotIn((ENTRY_ISSUE, "workflow:validating"), gh.label_history)
        self.assertIn((ENTRY_ISSUE, FIXING), gh.label_history)
        self.assertEqual(self._marks(gh), [APPROVAL_COMMENT_ID, 0, 0])
        state = gh.pinned_data(ENTRY_ISSUE)
        self.assertEqual(state.get("pending_fix_review_ids"), [INLINE_REVIEW_ID])
        self.assertEqual(state.get("pending_fix_review_summary_ids"), [REVIEW_SUMMARY_ID])
        self.assertIsNone(state.get(PENDING_FIX_ISSUE_IDS))

    def test_a_pre_pickup_pr_comment_is_not_crossed(self) -> None:
        # The initialization walks the same seed the approval handoff does,
        # and the delivered stretch is the issue thread's alone: a PR comment
        # older than the pickup was in no prompt, and the walk stops under it.
        gh, issue, _pr = self._entry_setup(
            pr_conversation=[_theirs(PRE_PICKUP_PR_COMMENT_ID, PRE_PICKUP_PR_BODY)],
        )

        self._debounced_tick(gh, issue)

        state = gh.pinned_data(ENTRY_ISSUE)
        self.assertLess(state.get(PR_LAST_COMMENT_ID), PRE_PICKUP_PR_COMMENT_ID)
        self.assertIn((ENTRY_ISSUE, FIXING), gh.label_history)
        self.assertEqual(state.get(PENDING_FIX_ISSUE_IDS), [PRE_PICKUP_PR_COMMENT_ID])

    def test_only_delivery_vouches_for_the_thread(self) -> None:
        # The same thread comment older than the pickup, under every record of
        # it. Quoted by the first prompt, it is inside the delivered stretch:
        # crossed, and nobody is asked about it again. Cut by that prompt's
        # excerpt bound, or on a record carrying no floor, no upper end, or
        # nothing -- the pickup's reply boundary standing over it all the same
        # -- it is outside it: the initialization crosses nothing and the
        # comment routes to `fixing`. No watermark crosses feedback no run
        # received, and neither a missing field nor the boundary marks anything
        # consumed.
        for delivered, crossed in (
            ((0, PRE_PICKUP_THREAD_ID), True),
            ((PRE_PICKUP_THREAD_ID, PICKUP_COMMENT_ID), False),
            ((0, None), False),
            ((None, PICKUP_COMMENT_ID), False),
            ((None, None), False),
        ):
            with self.subTest(delivered=delivered):
                gh, issue = self._entry_setup(
                    thread=[_theirs(PRE_PICKUP_THREAD_ID, PRE_PICKUP_THREAD_BODY)],
                    delivered=delivered,
                )[:2]

                self._debounced_tick(gh, issue)

                self.assertEqual(self._marks(gh)[0], APPROVAL_COMMENT_ID if crossed else 0)
                self.assertEqual(
                    gh.pinned_data(ENTRY_ISSUE).get(PENDING_FIX_ISSUE_IDS),
                    None if crossed else [PRE_PICKUP_THREAD_ID],
                )

    def test_a_reply_between_the_reads_stays_unread(self) -> None:
        # The issue thread is read first and the pull request second. A human
        # reply landing on the thread between the two is in neither read,
        # while the bare control typed into the pull request after it is in
        # the second -- and crossing the control would carry the mark over the
        # reply for good. Nothing above what the reads prove complete is
        # crossed, so the mark stops at our approval and the reply routes to
        # `fixing`.
        gh, issue, pr = self._entry_setup()
        raced = partial(self._read_behind_a_race, gh.pr_conversation_comments_after, issue, pr)

        with patch.object(gh, "pr_conversation_comments_after", side_effect=raced):
            self._debounced_tick(gh, issue)

        self.assertEqual(self._marks(gh), [APPROVAL_COMMENT_ID, 0, 0])
        self.assertIn((ENTRY_ISSUE, FIXING), gh.label_history)
        self.assertEqual(
            gh.pinned_data(ENTRY_ISSUE).get(PENDING_FIX_ISSUE_IDS), [RACED_REPLY_ID],
        )

    def test_first_tick_pings_for_mergeable_pr(self) -> None:
        # All gates passing and nothing unread anywhere: the initialization
        # must not park or otherwise block the handler from posting the HITL
        # ping.
        gh, issue, pr = self._entry_setup()
        # Drop the human review feedback (a PR nobody is owed an answer on)
        # and mark the PR as approved on the current head, over passing
        # evidence of it, so the gate passes.
        pr.reviews = []
        pr.review_comments = []
        pr.approved = True
        _verified.verifies_the_approval(gh, issue)

        self._debounced_tick(gh, issue, **_verified.proving(gh, issue))

        # No merge (humans drive the merge); HITL ping fires for the
        # mergeable PR.
        self.assertEqual(gh.merge_calls, [])
        self.assertNotIn((ENTRY_ISSUE, "done"), gh.label_history)
        ping_comments = [body for _, body in gh.posted_comments if "ready for review/merge" in body]
        self.assertEqual(len(ping_comments), 1)
        self.assertEqual(gh.pinned_data(ENTRY_ISSUE).get("ready_ping_sha"), REVIEWED_SHA)

    def _read_behind_a_race(self, read, issue, pr, current_pr, after_id):
        """`read` of the pull request, taken after a human replied on the issue
        thread and then typed a bare control into the pull request -- both
        behind the issue thread's own read, which is the one taken first."""
        if all(seen.id != RACED_REPLY_ID for seen in issue.comments):
            issue.comments.append(_theirs(RACED_REPLY_ID, RACED_REPLY_BODY))
            pr.issue_comments.append(_theirs(RACED_CONTROL_ID, RACED_CONTROL_BODY))
        return read(current_pr, after_id)


class FailedSnapshotInitializationTest(unittest.TestCase, _EntryFixtureMixin):
    """An approval whose snapshot will not read hands the issue on unseeded,
    and in_review initializes what it left unset."""

    def test_unread_snapshot_leaves_marks_unset(self) -> None:
        # Behind its notice the approval reads the pull request and both
        # threads. Where any of them will not answer, it writes nothing in
        # their place -- not even the 0 a scan from the beginning would be --
        # and in_review's first tick initializes each surface from what the
        # records prove, so the comment a human left while validating ran
        # still routes to `fixing`.
        for unread in ("get_pr", "pr_conversation_comments_after"):
            with self.subTest(unread=unread):
                self._assert_initialized_behind(unread)

    def test_initialized_zero_shows_later_reviews(self) -> None:
        # Nothing on any surface of the pull request yet. The first tick
        # persists 0 on every surface, so a review left after it is read past
        # an initialized mark rather than one the next tick decides afresh,
        # and routes to `fixing` -- an inline comment and a COMMENTED summary
        # alike.
        for surface, first_id, pending in (
            ("review_comments", FIRST_INLINE_REVIEW_ID, "pending_fix_review_ids"),
            ("reviews", FIRST_REVIEW_SUMMARY_ID, "pending_fix_review_summary_ids"),
        ):
            with self.subTest(surface=surface):
                self._assert_first_review_routes(surface, first_id, pending)

    def _assert_first_review_routes(self, surface: str, first_id: int, pending: str) -> None:
        gh, issue, pr = self._empty_pr_setup()

        self._run_in_review(gh, issue, run_agent=_agent())
        self.assertEqual(self._marks(gh, EMPTY_PR_ISSUE), [0, 0, 0])

        getattr(pr, surface).append(self._first_review(surface, first_id))
        mocks = self._debounced_tick(gh, issue)

        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(gh.merge_calls, [])
        self.assertIn((EMPTY_PR_ISSUE, FIXING), gh.label_history)
        self.assertEqual(gh.pinned_data(EMPTY_PR_ISSUE).get(pending), [first_id])

    def _assert_initialized_behind(self, unread: str) -> None:
        gh, issue = self._entry_setup(
            pr_conversation=[_theirs(DURING_VALIDATING_ID, DURING_VALIDATING_BODY)],
        )[:2]
        state = gh.read_pinned_state(issue)

        with patch.object(gh, unread, side_effect=RuntimeError(UNANSWERED)):
            _handoff._seed_in_review_handoff_watermarks(gh, issue, state, ENTRY_PR)

        seeded = [state.get(field) for field in WATERMARKS]
        self.assertEqual(seeded, [None, None, None])
        gh.write_pinned_state(issue, state)
        self._debounced_tick(gh, issue)
        self.assertEqual(self._marks(gh), [PR_OPEN_COMMENT_ID, 0, 0])
        routed = gh.pinned_data(ENTRY_ISSUE).get(PENDING_FIX_ISSUE_IDS)
        self.assertEqual(routed, [DURING_VALIDATING_ID])

    def _empty_pr_setup(self):
        gh = FakeGitHubClient()
        issue = make_issue(EMPTY_PR_ISSUE, label="in_review")
        gh.add_issue(issue)
        pr = FakePR(
            number=EMPTY_PR,
            head_branch=_issue_branch(EMPTY_PR_ISSUE),
            head=FakePRRef(sha=REVIEWED_SHA),
            mergeable=True,
            check_state="success",
        )
        gh.add_pr(pr)
        gh.seed_state(
            EMPTY_PR_ISSUE,
            pr_number=EMPTY_PR,
            **_approval_records.approved_in_review(issue, EMPTY_PR),
            branch=_issue_branch(EMPTY_PR_ISSUE),
            dev_agent=BACKEND_CLAUDE,
            dev_session_id=DEV_SESSION,
        )
        return gh, issue, pr

    def _first_review(self, surface: str, review_id: int):
        """The first review a human leaves on `surface` once the marks are initialized."""
        if surface == "review_comments":
            return _theirs(review_id, "line 7: rename foo to bar")
        return FakePRReview(
            id=review_id,
            body="please tighten the spec",
            state="COMMENTED",
            user=FakeUser(HUMAN_LOGIN),
            submitted_at=LONG_AGO,
            commit_id=REVIEWED_SHA,
        )


class UnreadThreadHoldsTest(unittest.TestCase, _EntryFixtureMixin):
    """An unset watermark nobody can initialize holds the tick."""

    def test_an_unreadable_thread_writes_nothing(self) -> None:
        # The walk needs both threads. Where the pull request's will not
        # answer, the tick ends there: no watermark written in its place, no
        # scan routing to `fixing`, and no ready ping over a surface nobody
        # read -- the next tick asks again.
        gh, issue, _pr = self._entry_setup()
        posted = len(gh.posted_comments)

        with patch.object(
            gh, "pr_conversation_comments_after", side_effect=RuntimeError(UNANSWERED),
        ), self.assertRaisesRegex(RuntimeError, UNANSWERED):
            self._debounced_tick(gh, issue)

        self.assertEqual(self._marks(gh), [None, None, None])
        self.assertNotIn((ENTRY_ISSUE, FIXING), gh.label_history)
        self.assertEqual(len(gh.posted_comments), posted)


class BoundedFirstPromptTest(unittest.TestCase, _EntryFixtureMixin):
    """Context the first prompt's excerpt bound cut stays unread feedback.

    The pickup stands the reply boundary past the whole thread -- nothing on it
    is a reply to anything -- and records no delivery. The implementer's first
    prompt is bounded and drops the oldest comments first; its spawn records
    the stretch above the newest one it cut. An issue then reaching in_review
    with no mark set has its initialization cross nothing that stretch leaves
    undelivered, and its scan routes the cut comment to `fixing` while the one
    the prompt quoted stays answered.
    """

    def test_a_cut_comment_routes_to_fixing(self) -> None:
        gh, issue = self._entry_setup(
            thread=[_theirs(CUT_ID, CUT_BODY), _theirs(QUOTED_ID, "x" * LONG_CONTEXT_CHARS)],
            delivered=(None, None),
        )[:2]
        state = gh.read_pinned_state(issue)
        notice = _comments._post_issue_comment(gh, issue, state, ":robot: orchestrator picking this up.")
        _pickup._record_pickup_comment(state, notice)
        _thread_delivery.records_delivery(state, _prompt_context._delivered_thread(gh, issue, state))
        gh.write_pinned_state(issue, state)

        self._debounced_tick(gh, issue)

        pinned = gh.pinned_data(ENTRY_ISSUE)
        self.assertEqual(pinned.get(_thread_delivery.DELIVERED_AFTER), CUT_ID)
        self.assertEqual(self._marks(gh)[0], 0)
        self.assertEqual(pinned.get(PENDING_FIX_ISSUE_IDS), [CUT_ID])
