# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.agents import runner as _agent_runner
from orchestrator.git.worktrees import creation as _worktree_creation
from orchestrator.workflow.engine import (
    comments as _engine_comments,
    content_hash as _content_hash,
    issue_processing as _issue_processing,
    poll_models as _poll_models,
    prompt_notes as _prompt_notes,
    run_ledger_values as _run_ledger_values,
)
from orchestrator.workflow.stages.implementing import (
    resume as _implementing_resume,
    resume_batch as _resume_batch,
    session as _implementing_session,
    state as _implementing_state,
)
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
    _FAKE_WT,
    _TEST_SPEC,
    REVIEW_APPROVED_MESSAGE,
    _agent,
    _PatchedWorkflowMixin,
)

CONSUMED_REPLY_ISSUE = 900
CONSUMED_REPLY_PR = 1500
CONSUMED_REPLY_BRANCH = "orchestrator/chippingway__orchestrator/issue-900"
RESUME_WATERMARK_ISSUE = 901
ISSUE_THREAD_ISSUE = 800
ISSUE_THREAD_PR = 1600
ISSUE_THREAD_BRANCH = "orchestrator/chippingway__orchestrator/issue-800"
PICKUP_COMMENT_ID = 900
PARK_COMMENT_ID = 910
CONSUMED_REPLY_ID = 920
PR_OPEN_AFTER_RESUME_ID = 930
LATEST_REPLY_ID = 921
UNREAD_PR_COMMENT_ID = 915
REVIEW_DEBOUNCE_SECONDS = 600
LABEL_VALIDATING = "workflow:validating"
LABEL_IN_REVIEW = "in_review"
LABEL_FIXING = "workflow:fixing"
PICKUP_MESSAGE = ":robot: orchestrator picking this up."
BOT_LOGIN = "orchestrator"
HUMAN_LOGIN = "alice"
BACKEND_CLAUDE = "claude"
DEV_SESSION = "dev-sess"
REVIEWED_SHA = "cafe1234" * 5
CHECKS_SUCCESS = "success"
PR_LAST_COMMENT_ID = "pr_last_comment_id"
DEBOUNCE_SETTING = "IN_REVIEW_DEBOUNCE_SECONDS"
RUN_AGENT = "run_agent"
LONG_AGO = datetime.now(UTC) - timedelta(hours=1)
FROZEN_BATCH_ISSUE = 802
FROZEN_BATCH_PR = 1602
FROZEN_BATCH_BRANCH = "orchestrator/chippingway__orchestrator/issue-802"
HUMAN_REPLY = "answer: use sqlite"
LANDED_MID_RUN = "actually, hold on"
PARKED_QUESTION = "@hitl agent needs your input to proceed"
STILL_ASKING = "which of the two did you mean?"
AWAITING_HUMAN = "awaiting_human"
PARK_REASON = "park_reason"
LAST_ACTION_COMMENT_ID = "last_action_comment_id"
AGENT_TIMEOUT_REASON = "agent_timeout"
USER_CONTENT_HASH = "user_content_hash"
DRIFT_NOTICE = "issue body changed"
EDITED_BODY = "the requirements, rewritten while the issue was parked"

# The bare retry a session-failure park earns, and what only a fresh spawn's
# prompt carries: the preamble re-grounding it on the issue.
CONTINUE = "/orchestrator continue"
REGROUNDED = "resuming work on GitHub issue"

# The session read the dev resume takes between freezing the batch and
# building the prompt, captured before a case stands in for it.
RESOLVE_SESSION = "_resolve_dev_session_for_resume"
RESOLVES_SESSION = _implementing_session._resolve_dev_session_for_resume

# The two sessions an explicit retry turns into a fresh spawn on: none pinned
# at all, and one retired on sight by its silent-park streak. None drops the
# field rather than writing it.
RETRIED_SESSIONS = (
    ("a missing session", {_implementing_state._DEV_SESSION_ID: None}),
    ("a retired session", {
        _implementing_state._SILENT_PARK_COUNT: (
            _implementing_state._SILENT_PARKS_BEFORE_FRESH_SESSION
        ),
    }),
)

# Which agent each run was, as the spawn event every launch records names it.
EVENT_NAME = "event"
EVENT_AGENT_SPAWN = "agent_spawn"
AGENT_ROLE = "agent_role"
ROLE_DEVELOPER = "developer"

# The author every seeded orchestrator comment carries.
BOT_USER = FakeUser(BOT_LOGIN)

# A body somebody else pasted our own hidden marker into: the batch a park
# decides from refuses one, so no road here reads it as a human replying.
FORGED_REPLY = f"looks fine\n\n{_engine_comments._ORCH_COMMENT_MARKER}"

# A lifetime ledger spent to its last run, so the circuit refuses the resume
# before any process starts, and the operator command that buys it more.
SPENT_RUNS = 3
ADD_RUNS = "/orchestrator add-agent-runs 3"


class HandoffSkipsConsumedRepliesTest(unittest.TestCase, _PatchedWorkflowMixin):
    """A human reply consumed by `_resume_developer_on_human_reply` during
    implementing or validating must not re-surface as fresh PR feedback in
    in_review. The validating handoff watermark seed has to walk past such
    already-consumed comments; otherwise the next in_review tick re-routes
    the issue to `fixing` on the same human input the dev has already
    addressed.
    """

    def test_consumed_reply_not_replayed(self) -> None:
        gh = FakeGitHubClient()
        # Lifecycle: pickup (900) -> implementing dev asks question, parks
        # at 910 -> human replies "use sqlite" at 920 -> next tick resumes
        # the dev with that comment -> dev commits, _on_commits posts
        # PR-opened at 930 -> validating reviewer approves and posts
        # approval comment at 940. The reply at 920 was already fed to
        # the dev; in_review must NOT replay it.
        issue = make_issue(
            CONSUMED_REPLY_ISSUE,
            label=LABEL_VALIDATING,
            comments=[
                FakeComment(
                    id=PICKUP_COMMENT_ID,
                    body=PICKUP_MESSAGE,
                    user=BOT_USER,
                    created_at=LONG_AGO,
                ),
                FakeComment(
                    id=PARK_COMMENT_ID,
                    body="@hitl agent needs your input to proceed",
                    user=BOT_USER,
                    created_at=LONG_AGO,
                ),
                FakeComment(
                    id=CONSUMED_REPLY_ID,
                    body="use sqlite please",
                    user=FakeUser(HUMAN_LOGIN),
                    created_at=LONG_AGO,
                ),
                FakeComment(
                    id=PR_OPEN_AFTER_RESUME_ID,
                    body=":sparkles: PR opened: #1500",
                    user=BOT_USER,
                    created_at=LONG_AGO,
                ),
            ],
        )
        gh.add_issue(issue)
        pr = FakePR(
            number=CONSUMED_REPLY_PR,
            head_branch=CONSUMED_REPLY_BRANCH,
            head=FakePRRef(sha=REVIEWED_SHA),
            mergeable=True,
            check_state=CHECKS_SUCCESS,
        )
        gh.add_pr(pr)
        # `last_action_comment_id=920` reflects the post-resume bump --
        # the resume ate comments after the park (910) up through 920.
        gh.seed_state(
            CONSUMED_REPLY_ISSUE,
            pr_number=CONSUMED_REPLY_PR,
            branch=CONSUMED_REPLY_BRANCH,
            dev_agent=BACKEND_CLAUDE,
            dev_session_id=DEV_SESSION,
            review_round=0,
            orchestrator_comment_ids=[
                PICKUP_COMMENT_ID,
                PARK_COMMENT_ID,
                PR_OPEN_AFTER_RESUME_ID,
            ],
            pickup_comment_id=PICKUP_COMMENT_ID,
            last_action_comment_id=CONSUMED_REPLY_ID,
        )

        # Step 1: validating approves. The handoff seed must walk PAST
        # comment 920 (already consumed) instead of stopping at it.
        self._run_validating(
            gh,
            issue,
            run_agent=_agent(last_message=REVIEW_APPROVED_MESSAGE),
            head_shas=(REVIEWED_SHA,),
        )
        watermark = gh.pinned_data(CONSUMED_REPLY_ISSUE).get(PR_LAST_COMMENT_ID)
        self.assertIsNotNone(watermark)
        self.assertGreaterEqual(
            watermark,
            PR_OPEN_AFTER_RESUME_ID,
            f"watermark must advance past consumed reply (id 920); got {watermark}",
        )

        # Step 2: in_review tick. Comment 920 must NOT surface and the
        # handler reaches the manual-merge HITL ping path.
        pr.approved = True
        if not any(label.name == LABEL_IN_REVIEW for label in issue.labels):
            issue.labels = [FakeLabel(LABEL_IN_REVIEW)]
        with patch.object(
            config,
            DEBOUNCE_SETTING,
            REVIEW_DEBOUNCE_SECONDS,
        ):
            mocks = self._run_in_review(
                gh,
                issue,
                run_agent=_agent(),
            )

        # Manual-merge-only: no merge call. The HITL ping fires because
        # the seed kept the consumed reply out of `new_comments`.
        self._assert_ready_path(gh, mocks)

    def test_resume_bumps_last_action_to_consumed_max(self) -> None:
        # Direct unit-level check on `_resume_developer_on_human_reply`:
        # after the resume runs, `last_action_comment_id` must reflect
        # the highest consumed id, not the prior park id.

        gh = FakeGitHubClient()
        issue = make_issue(
            RESUME_WATERMARK_ISSUE,
            label="workflow:implementing",
            comments=[
                FakeComment(id=PARK_COMMENT_ID, body="park", user=BOT_USER),
                FakeComment(id=CONSUMED_REPLY_ID, body="use sqlite", user=FakeUser(HUMAN_LOGIN)),
                FakeComment(id=LATEST_REPLY_ID, body="and add a test", user=FakeUser(HUMAN_LOGIN)),
            ],
        )
        gh.add_issue(issue)
        gh.seed_state(
            RESUME_WATERMARK_ISSUE,
            dev_agent=BACKEND_CLAUDE,
            dev_session_id=DEV_SESSION,
            last_action_comment_id=PARK_COMMENT_ID,
        )
        state = gh.read_pinned_state(issue)

        with (
            patch.object(
                _worktree_creation,
                "_ensure_worktree",
                lambda spec, issue_number, **_: _FAKE_WT,
            ),
            patch.object(
                _agent_runner, RUN_AGENT, lambda *args, **kwargs: _agent(),
            ),
        ):
            resume_result = _implementing_resume._resume_developer_on_human_reply(
                gh, _TEST_SPEC, issue,
                _resume_batch._freeze(gh, issue, state),
            )

        self.assertIsNotNone(resume_result)
        self.assertEqual(
            state.get("last_action_comment_id"),
            LATEST_REPLY_ID,
            "resume must bump last_action_comment_id to max(consumed)",
        )

    def _assert_ready_path(self, github, mocks) -> None:
        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(github.merge_calls, [])
        self.assertNotIn(
            (CONSUMED_REPLY_ISSUE, "done"),
            github.label_history,
        )
        self.assertNotIn(
            (CONSUMED_REPLY_ISSUE, LABEL_FIXING),
            github.label_history,
        )
        ping_comments = [
            body
            for _, body in github.posted_comments
            if "ready for review/merge" in body
        ]
        self.assertEqual(len(ping_comments), 1)


class HandoffConsumedThroughIssueThreadOnlyTest(unittest.TestCase, _PatchedWorkflowMixin):
    """`last_action_comment_id` only records issue-thread comments fed via
    `_resume_developer_on_human_reply`; PR-conversation comments are never
    consumed via that path. The validating handoff seed must NOT apply
    `consumed_through` to the PR-conversation surface, or a human PR comment
    whose id sits below a later-consumed issue-thread reply gets silently
    advanced past and the HITL ping fires over unread feedback.
    """

    def test_pr_comment_below_consumed_max_is_kept(self) -> None:
        gh = FakeGitHubClient()
        # Lifecycle: pickup (900) -> park asking question (910) -> human
        # leaves a PR-conv comment at 915 (the one that MUST surface) ->
        # human also replies on the issue thread at 920 -> resume consumes
        # the issue reply and bumps `last_action_comment_id` to 920 ->
        # PR-opened comment at 930 -> validating reviewer approves and
        # posts approval at 940. The PR-conv comment at 915 was never fed
        # to the dev (validating only watches the issue thread); without
        # the fix the seed walks past it because 915 <= consumed_through
        # (920) and the next tick pings HITL over it.
        issue = make_issue(
            ISSUE_THREAD_ISSUE,
            label=LABEL_VALIDATING,
            comments=[
                FakeComment(
                    id=PICKUP_COMMENT_ID,
                    body=PICKUP_MESSAGE,
                    user=BOT_USER,
                    created_at=LONG_AGO,
                ),
                FakeComment(
                    id=PARK_COMMENT_ID,
                    body="@hitl agent needs your input to proceed",
                    user=BOT_USER,
                    created_at=LONG_AGO,
                ),
                FakeComment(
                    id=CONSUMED_REPLY_ID,
                    body="use sqlite please",
                    user=FakeUser(HUMAN_LOGIN),
                    created_at=LONG_AGO,
                ),
                FakeComment(
                    id=PR_OPEN_AFTER_RESUME_ID,
                    body=":sparkles: PR opened: #1600",
                    user=BOT_USER,
                    created_at=LONG_AGO,
                ),
            ],
        )
        gh.add_issue(issue)
        pr = FakePR(
            number=ISSUE_THREAD_PR,
            head_branch=ISSUE_THREAD_BRANCH,
            head=FakePRRef(sha=REVIEWED_SHA),
            mergeable=True,
            check_state=CHECKS_SUCCESS,
            issue_comments=[
                FakeComment(
                    id=UNREAD_PR_COMMENT_ID,
                    body="please add a docstring to the public class",
                    user=FakeUser(HUMAN_LOGIN),
                    created_at=LONG_AGO,
                ),
            ],
        )
        gh.add_pr(pr)
        gh.seed_state(
            ISSUE_THREAD_ISSUE,
            pr_number=ISSUE_THREAD_PR,
            branch=ISSUE_THREAD_BRANCH,
            dev_agent=BACKEND_CLAUDE,
            dev_session_id=DEV_SESSION,
            review_round=0,
            orchestrator_comment_ids=[
                PICKUP_COMMENT_ID,
                PARK_COMMENT_ID,
                PR_OPEN_AFTER_RESUME_ID,
            ],
            pickup_comment_id=PICKUP_COMMENT_ID,
            last_action_comment_id=CONSUMED_REPLY_ID,
        )

        # Step 1: validating approves and seeds in_review watermarks. The
        # seed must stop before 915 so the next in_review tick scans the
        # PR-conv surface and finds the human comment. Approval routes
        # through `documenting` first (the final-docs hop).
        self._run_validating(
            gh,
            issue,
            run_agent=_agent(last_message=REVIEW_APPROVED_MESSAGE),
            head_shas=(REVIEWED_SHA,),
        )
        self.assertIn((ISSUE_THREAD_ISSUE, "workflow:documenting"), gh.label_history)
        watermark = gh.pinned_data(ISSUE_THREAD_ISSUE).get(PR_LAST_COMMENT_ID)
        self.assertIsNotNone(watermark)
        self.assertLess(
            watermark,
            UNREAD_PR_COMMENT_ID,
            "watermark must stop before unread PR-conv comment id=915 "
            f"(consumed_through=920 must NOT apply across surfaces); got {watermark}",
        )

        # Step 2: simulate the documenting no-change exit (final docs
        # pass found nothing to commit) and run the in_review tick.
        # The PR-conv comment surfaces and the handler routes the issue
        # to `fixing` (the fixing handler owns the dev resume on the
        # next tick) instead of pinging HITL.
        if not any(label.name == LABEL_IN_REVIEW for label in issue.labels):
            issue.labels = [FakeLabel(LABEL_IN_REVIEW)]
        with patch.object(
            config,
            DEBOUNCE_SETTING,
            REVIEW_DEBOUNCE_SECONDS,
        ):
            mocks = self._run_in_review(
                gh,
                issue,
                run_agent=_agent(),
            )

        # Routed to fixing -- the unread PR-conv text is bookmarked for
        # the fixing handler. No HITL ping fires over unread feedback.
        # `pending_fix_issue_max_id` covers BOTH surfaces (they share the
        # IssueComment id space), and the batch is the PR-conv comment at
        # 915 alone: the issue-thread reply at 920 is at the delivery
        # cursor `consumed_through` records, so in_review drops it on the
        # surface that cursor answers for rather than bookmarking a reply
        # the developer already read.
        self._assert_unread_route(gh, mocks)

    def _assert_unread_route(self, github, mocks) -> None:
        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(github.merge_calls, [])
        self.assertIn(
            (ISSUE_THREAD_ISSUE, LABEL_FIXING),
            github.label_history,
        )
        state = github.pinned_data(ISSUE_THREAD_ISSUE)
        # The PR comment alone: the consumed issue-thread reply above it is
        # answered by the cursor that records it and never re-bookmarked.
        self.assertEqual(
            state.get("pending_fix_issue_max_id"),
            UNREAD_PR_COMMENT_ID,
        )
        self.assertLess(
            state.get(PR_LAST_COMMENT_ID),
            UNREAD_PR_COMMENT_ID,
        )


class _ReplyLandsDuringTheRun:
    """The dev's seeded answer, and a reply written while it was out.

    A class rather than a closure because the runner this repository patches
    is a value with a name, and the reply has to land between the prompt being
    built and the settlement being taken -- the minutes a real agent is gone
    for, which nothing reads the thread in.
    """

    def __init__(
        self, case, lands: str = "", *, timed_out: bool = False,
    ) -> None:
        self._case = case
        self._lands = lands
        self._timed_out = timed_out
        self.landed = 0

    def __call__(self, *called, **options):
        if self._lands:
            self.landed = self._case._they_say(self._lands)
        if self._timed_out:
            return _agent(session_id=DEV_SESSION, timed_out=True)
        return _agent(session_id=DEV_SESSION, last_message=STILL_ASKING)


class _FrozenBatchPark(_PatchedWorkflowMixin):
    """A validating issue parked on a question, its thread already read.

    Shared by the cases about what one tick's frozen batch delivers and the
    cases about what a spent run ledger's park and grant may consume of it.
    """

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(
            FROZEN_BATCH_ISSUE,
            label=LABEL_VALIDATING,
            comments=[
                FakeComment(
                    id=PARK_COMMENT_ID,
                    body=PARKED_QUESTION,
                    user=BOT_USER,
                    created_at=LONG_AGO,
                ),
            ],
        )
        self.github.add_issue(self.issue)
        self.github.add_pr(
            FakePR(
                number=FROZEN_BATCH_PR,
                head_branch=FROZEN_BATCH_BRANCH,
                head=FakePRRef(sha=REVIEWED_SHA),
            ),
        )
        self.github.seed_state(
            FROZEN_BATCH_ISSUE,
            pr_number=FROZEN_BATCH_PR,
            branch=FROZEN_BATCH_BRANCH,
            dev_agent=BACKEND_CLAUDE,
            dev_session_id=DEV_SESSION,
            review_round=0,
            orchestrator_comment_ids=[PARK_COMMENT_ID],
            **{
                AWAITING_HUMAN: True,
                PARK_REASON: None,
                LAST_ACTION_COMMENT_ID: PARK_COMMENT_ID,
                # The baseline a real park carries, so a reply moves the hash
                # and the drift check is asked about it as in production.
                USER_CONTENT_HASH: _content_hash._compute_user_content_hash(
                    self.issue, {PARK_COMMENT_ID},
                ),
            },
        )

    def _they_say(self, body: str) -> int:
        """Add one trusted human reply past the park's watermark."""
        identified = self.github.next_reply_id(self.issue)
        self.issue.comments.append(
            FakeComment(identified, body, user=FakeUser(HUMAN_LOGIN)),
        )
        return identified

    def _pinned(self) -> dict:
        return self.github.pinned_data(FROZEN_BATCH_ISSUE)


class AwaitingHumanFrozenBatchTest(_FrozenBatchPark, unittest.TestCase):
    """The batch a validating park decides from is the batch it delivers.

    One read rather than two, and one filter rather than two: the park-reason
    decisions and the dev resume behind them are answered from the same frozen
    replies, so a comment neither of them would accept cannot reach a prompt
    on the strength of the laxer of two readings -- and a comment written
    while the agent is out belongs to the next poll rather than to this one.
    """

    def test_a_forged_marker_buys_nothing(self) -> None:
        # The decisions above the resume and the resume itself read one
        # frozen batch, and that batch refuses a body carrying our marker that
        # no ledger entry vouches for. Read by a looser filter, it would be
        # quoted to the developer and the thread recorded as answered on the
        # strength of text anybody may paste.
        self._they_say(FORGED_REPLY)

        mocks = self._runs()

        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(self._pinned()[LAST_ACTION_COMMENT_ID], PARK_COMMENT_ID)
        self.assertTrue(self._pinned()[AWAITING_HUMAN])

    def test_a_reply_landing_mid_run_stays_unread(self) -> None:
        # The developer answers the reply it was handed and asks a follow-up,
        # so the tick parks again. The comment written while it was out is not
        # in that prompt and must not be crossed by the park's watermark
        # either -- the next poll is the first road that can read it.
        spoke = self._they_say(HUMAN_REPLY)

        landing = _ReplyLandsDuringTheRun(self, LANDED_MID_RUN)
        mocks = self._runs(run_agent=MagicMock(side_effect=landing))

        prompt = mocks[RUN_AGENT].call_args[0][1]
        self.assertIn(HUMAN_REPLY, prompt)
        self.assertNotIn(LANDED_MID_RUN, prompt)
        self.assertEqual(self._pinned()[LAST_ACTION_COMMENT_ID], spoke)
        self.assertLess(spoke, landing.landed)
        self.assertTrue(self._pinned()[AWAITING_HUMAN])

    def test_a_timed_out_run_keeps_what_landed(self) -> None:
        # The timeout park this route takes ends a run the same way, so it
        # owes the same bound: the transient recovery that retries it fires
        # only on a thread with nothing new on it, and a watermark carried
        # over the mid-run reply would answer that reply with a silent rerun.
        spoke = self._they_say(HUMAN_REPLY)

        landing = _ReplyLandsDuringTheRun(self, LANDED_MID_RUN, timed_out=True)
        self._runs(run_agent=MagicMock(side_effect=landing))

        self.assertEqual(self._pinned()[LAST_ACTION_COMMENT_ID], spoke)
        self.assertEqual(self._pinned()[PARK_REASON], AGENT_TIMEOUT_REASON)
        self.assertLess(spoke, landing.landed)

    def test_a_reply_reaches_the_dev_not_the_drift(self) -> None:
        # Over the baseline a real park carries a reply moves the hash, and it
        # is still the frozen batch that delivers it -- a pasted marker and an
        # answered run-grant command filtered out, as a prompt is -- and
        # settles the requirements it answers, so the poll after it is quiet.
        for described, thread, withheld in (
            ("beside a pasted marker", (HUMAN_REPLY, FORGED_REPLY), FORGED_REPLY),
            ("under an answered grant", (ADD_RUNS, HUMAN_REPLY), ADD_RUNS),
        ):
            with self.subTest(thread=described):
                self.setUp()
                for said in thread:
                    self._they_say(said)

                prompt = self._runs()[RUN_AGENT].call_args[0][1]

                self.assertIn(HUMAN_REPLY, prompt)
                self.assertNotIn(withheld, prompt)
                self.assertFalse(self._drift_said())
                self._runs()[RUN_AGENT].assert_not_called()

    def test_an_edit_to_the_body_is_still_drift(self) -> None:
        # What the park had not read moved, so the drift road answers the tick.
        self._they_say(HUMAN_REPLY)
        self.issue.body = EDITED_BODY

        prompt = self._runs()[RUN_AGENT].call_args[0][1]

        self.assertIn(EDITED_BODY, prompt)
        self.assertTrue(self._drift_said())

    def _drift_said(self) -> bool:
        return any(DRIFT_NOTICE in body for _, body in self.github.posted_comments)

    def _runs(self, **run_options):
        """One validating tick over this park, committing nothing."""
        run_options.setdefault(
            "run_agent",
            _agent(session_id=DEV_SESSION, last_message=STILL_ASKING),
        )
        return self._run_validating(
            self.github,
            self.issue,
            head_shas=(REVIEWED_SHA,),
            **run_options,
        )


class ContinueRetryRegroundingTest(_FrozenBatchPark, unittest.TestCase):
    """The conversation an explicit retry with no transcript is handed.

    A bare `/orchestrator continue` on a session-failure park consumes the
    command and hands the developer the orchestrator's retry prompt. Where
    the session is missing or retired that prompt is a fresh spawn's, and the
    conversation it quotes comes off the batch the command was classified
    from, less the command: read at spawn time, a comment written in between
    is delivered while the mark stops at the command, and the next poll hands
    it over again. The comment lands at the session read, the one seam
    between the freeze and the prompt that is called exactly once.
    """

    def test_a_retry_quotes_the_thread_it_classified(self) -> None:
        for described, session in RETRIED_SESSIONS:
            with self.subTest(session=described):
                self.setUp()

                prompt = self._retried_over(session)

                self.assertIn(REGROUNDED, prompt)
                self.assertIn(_prompt_notes._DEVELOPER_CONTINUE_RETRY_PROMPT, prompt)
                self.assertIn(PARKED_QUESTION, prompt)
                self.assertNotIn(CONTINUE, prompt)
                self.assertNotIn(LANDED_MID_RUN, prompt)

    def test_what_landed_is_read_by_the_next_poll(self) -> None:
        for described, session in RETRIED_SESSIONS:
            with self.subTest(session=described):
                self.setUp()
                self._retried_over(session)
                read_to = self._pinned()[LAST_ACTION_COMMENT_ID]

                followed = self._prompt_of_one_tick()

                self.assertEqual(read_to, self._commanded)
                self.assertIn(LANDED_MID_RUN, followed)
                self.assertGreaterEqual(
                    self._pinned()[LAST_ACTION_COMMENT_ID], self._landed,
                )

    def _retried_over(self, session: dict) -> str:
        """The retry's own prompt, a reply landing while it is built."""
        self._park_on_a_timeout(session)
        self._commanded = self._they_say(CONTINUE)
        self._lands = LANDED_MID_RUN
        return self._prompt_of_one_tick()

    def _park_on_a_timeout(self, session: dict) -> None:
        """This park, re-reasoned as the timeout a retry is owed on."""
        state = self.github.read_pinned_state(self.issue)
        state.set(PARK_REASON, AGENT_TIMEOUT_REASON)
        for field, written in session.items():
            if written is None:
                state.data.pop(field, None)
            else:
                state.set(field, written)
        self.github.write_pinned_state(self.issue, state)

    def _prompt_of_one_tick(self) -> str:
        """One validating tick with the session read stood in for."""
        with patch.object(
            _implementing_session, RESOLVE_SESSION, self._resolves_after_landing,
        ):
            mocks = self._run_validating(
                self.github,
                self.issue,
                run_agent=_agent(session_id=DEV_SESSION, last_message=STILL_ASKING),
                head_shas=(REVIEWED_SHA,),
            )
        return mocks[RUN_AGENT].call_args[0][1]

    def _resolves_after_landing(self, issue, state):
        """The session read, with the reply still owed written first."""
        if self._lands:
            self._landed = self._they_say(self._lands)
            self._lands = ""
        return RESOLVES_SESSION(issue, state)


class RunLimitCycleTest(_FrozenBatchPark, unittest.TestCase):
    """The dev resume a spent ledger refuses, and the reply it was handed.

    Driven through the dispatcher's hold and the real circuit rather than with
    a refused result seeded under the resume. The resume records nothing for
    a launch nothing invoked; what can record the reply as read is the three
    watermark writes the refusal sets off -- the park's notice, the next tick's
    repair of its lost write, and the grant that lifts it -- and only the real
    circuit and hold perform them. The grant is also where the run the human
    paid for happens, and what it puts back decides whose run that is.
    """

    def test_the_grant_resumes_the_refused_developer(self) -> None:
        # The circuit refuses the dev resume below it, so nothing was read,
        # and neither the notice nor its repair may record the reply as read.
        # The grant puts the question park back, so its own tick is the
        # resume that was refused: the developer, handed the reply and not
        # the grant command, recorded as having read it. Cleared instead, the
        # park is gone and this stage's ordinary road runs the REVIEWER over
        # words the human wrote to the developer.
        granted = self._refused_then_granted()
        after = self._polls()
        prompt = granted[RUN_AGENT].call_args[0][1]
        read_to = self._pinned()[LAST_ACTION_COMMENT_ID]

        self.assertIn(HUMAN_REPLY, prompt)
        self.assertNotIn(ADD_RUNS, prompt)
        self.assertEqual(
            [
                recorded[AGENT_ROLE] for recorded in self.github.recorded_events
                if recorded[EVENT_NAME] == EVENT_AGENT_SPAWN
            ],
            [ROLE_DEVELOPER],
        )
        self.assertEqual(
            self._pinned()[_run_ledger_values.AGENT_RUN_ALLOWANCE],
            SPENT_RUNS + SPENT_RUNS,
        )
        self.assertGreaterEqual(read_to, self._spoke)
        self.assertLess(read_to, self._commanded)
        after[RUN_AGENT].assert_not_called()

    def _refused_then_granted(self):
        """The refused resume, its park's repair, and the grant's own poll.

        No agent runs on the first two; the third runs the one the grant paid
        for, which is returned. The reply and the command are kept by id.
        """
        self._spend_every_run()
        self._spoke = self._they_say(HUMAN_REPLY)
        refused = self._polls()
        self._commanded = self._they_say(ADD_RUNS)
        replayed = self._polls()
        granted = self._polls()

        refused[RUN_AGENT].assert_not_called()
        replayed[RUN_AGENT].assert_not_called()
        granted[RUN_AGENT].assert_called_once()
        return granted

    def _spend_every_run(self) -> None:
        state = self.github.read_pinned_state(self.issue)
        state.set(_run_ledger_values.AGENT_RUN_ALLOWANCE, SPENT_RUNS)
        state.set(_run_ledger_values.AGENT_RUNS_USED, SPENT_RUNS)
        self.github.write_pinned_state(self.issue, state)

    def _polls(self):
        """One whole poll: the run-limit hold ahead of this stage's handler."""
        return self._run(
            lambda: _issue_processing._route_issue_to_handler(
                self.github, _TEST_SPEC, self.issue, LABEL_VALIDATING,
                reading=_poll_models._POLLED_OPEN,
            ),
            run_agent=MagicMock(
                return_value=_agent(session_id=DEV_SESSION, last_message=STILL_ASKING),
            ),
            head_shas=(REVIEWED_SHA,),
        )
