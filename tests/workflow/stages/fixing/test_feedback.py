# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for fixing feedback behavior."""

from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import report_consumed_values as _consumed_values
from orchestrator.workflow.stages.fixing import feedback as _feedback, models as _models
from tests.workflow.stages.fixing import fixing_test_support as support
from tests.workflow.stages.fixing.prompt_expectations import (
    only_prompt,
    pr_feedback_prompt,
)

IssueScenario = support.IssueScenario

ALICE = support.ALICE
AWAITING_HUMAN = support.AWAITING_HUMAN
BATCH_PR_CONVERSATION_ID = support.BATCH_PR_CONVERSATION_ID
BOB = support.BOB
CAROL = support.CAROL
CHANGES_REQUESTED = support.CHANGES_REQUESTED
DEBOUNCE_CONFIG = support.DEBOUNCE_CONFIG
DEBOUNCE_SECONDS = support.DEBOUNCE_SECONDS
DEV_SESSION = support.DEV_SESSION
DOCUMENTING = support.DOCUMENTING
FIX_FEEDBACK = support.FIX_FEEDBACK
FOLLOWUP_ID = support.FOLLOWUP_ID
FRESH_COMMENT_DELAY_MINUTES = support.FRESH_COMMENT_DELAY_MINUTES
FakeComment = support.FakeComment
FakePRReview = support.FakePRReview
FakeUser = support.FakeUser
HISTORICAL_COMMENT_ID = support.HISTORICAL_COMMENT_ID
INITIAL_PR_COMMENT_WATERMARK = support.INITIAL_PR_COMMENT_WATERMARK
INLINE_FEEDBACK_ID = support.INLINE_FEEDBACK_ID
IN_REVIEW = support.IN_REVIEW
ISSUE = support.ISSUE
LAST_ACTION_COMMENT_ID = support.LAST_ACTION_COMMENT_ID
PENDING_FIX_AT = support.PENDING_FIX_AT
PENDING_FIX_ISSUE_MAX_ID = support.PENDING_FIX_ISSUE_MAX_ID
PENDING_FIX_REVIEWER_COMMENT_ID = support.PENDING_FIX_REVIEWER_COMMENT_ID
PENDING_FIX_REVIEW_MAX_ID = support.PENDING_FIX_REVIEW_MAX_ID
PENDING_FIX_REVIEW_SUMMARY_MAX_ID = support.PENDING_FIX_REVIEW_SUMMARY_MAX_ID
PR_LAST_COMMENT_ID = support.PR_LAST_COMMENT_ID
PR_LAST_REVIEW_COMMENT_ID = support.PR_LAST_REVIEW_COMMENT_ID
PR_LAST_REVIEW_SUMMARY_ID = support.PR_LAST_REVIEW_SUMMARY_ID
PUSHED_MESSAGE = support.PUSHED_MESSAGE
PUSH_BRANCH = support.PUSH_BRANCH
REVIEWER_FEEDBACK_ID = support.REVIEWER_FEEDBACK_ID
REVIEW_ROUND = support.REVIEW_ROUND
REVIEW_SUMMARY_FEEDBACK_ID = support.REVIEW_SUMMARY_FEEDBACK_ID
RUN_AGENT = support.RUN_AGENT
SHA_AFTER = support.SHA_AFTER
SHA_BEFORE = support.SHA_BEFORE
SHA_SAME = support.SHA_SAME
TRIGGER_ID = support.TRIGGER_ID
VALIDATING = support.VALIDATING
_FixingFixtureMixin = support._FixingFixtureMixin
_agent = support._agent
config = support.config
datetime = support.datetime
patch = support.patch
timedelta = support.timedelta
timezone = support.timezone

# The human whose replies these cases are about, built once: every comment
# below is one person writing on the thread or the pull request.
REPLIER = FakeUser(ALICE)

ADD_RUNS = "/orchestrator add-agent-runs 3"
TIGHTEN = "tighten the retry message"
# Long enough ago that no quiet window is still waiting on either comment.
LONG_SETTLED = datetime.fromtimestamp(0, tz=timezone.utc)


class FixingFeedbackRoutingTest(unittest.TestCase, _FixingFixtureMixin):
    def test_newer_comment_extends_debounce_window(self) -> None:
        # First tick: an older triggering comment is past the window but a
        # newer comment just landed -- the freshest
        # timestamp resets the gate. Handler must NOT resume; no agent
        # call, no label change.
        long_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        just_now = datetime.now(timezone.utc)
        triggering = FakeComment(
            id=TRIGGER_ID,
            body="please fix the bug",
            user=REPLIER,
            created_at=long_ago,
        )
        followup = FakeComment(
            id=FOLLOWUP_ID,
            body="actually rename it too",
            user=REPLIER,
            created_at=just_now,
        )
        self._pr = self._open_pr()
        scenario = IssueScenario(
            *self._seed(
                pr=self._pr,
                issue_comments=[triggering, followup],
            )
        )

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            self._mocks = self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(),
            )

        self._mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(scenario.github.label_history, [])

    # --- comments arriving while already labeled fixing -------------------

    def test_fresh_comment_during_fixing_is_picked_up(self) -> None:
        # Tick 1 (in_review handoff already done; we simulate that state):
        # the triggering comment id=TRIGGER_ID sits past the watermark with the
        # bookmark recorded. Before tick 2 fires, a SECOND human comment
        # followup lands. The rescan picks BOTH up and the followup quotes
        # both surfaces. Both comments are past the debounce window.
        long_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        also_old = datetime.now(timezone.utc) - timedelta(minutes=FRESH_COMMENT_DELAY_MINUTES)
        triggering = FakeComment(
            id=TRIGGER_ID,
            body="please fix the docstring",
            user=REPLIER,
            created_at=long_ago,
        )
        late_arrival = FakeComment(
            id=FOLLOWUP_ID,
            body="and rename helper to util",
            user=FakeUser(BOB),
            created_at=also_old,
        )
        self._pr = self._open_pr()
        scenario = IssueScenario(
            *self._seed(
                pr=self._pr,
                issue_comments=[triggering, late_arrival],
            )
        )

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            self._mocks = self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(
                    session_id=DEV_SESSION,
                    last_message=PUSHED_MESSAGE,
                ),
                head_shas=(SHA_BEFORE, SHA_AFTER),
            )

        self._mocks[RUN_AGENT].assert_called_once()
        self._agent_call = self._mocks[RUN_AGENT].call_args
        self._prompt = self._agent_call.args[1]
        # Both comments are quoted in the followup so the dev sees the
        # full conversation that landed while the label was `fixing`.
        self.assertIn("please fix the docstring", self._prompt)
        self.assertIn("and rename helper to util", self._prompt)
        # Watermark advanced past BOTH consumed comments.
        self.assertGreaterEqual(
            scenario.github.pinned_data(ISSUE).get(PR_LAST_COMMENT_ID),
            FOLLOWUP_ID,
        )

    def test_a_grant_command_is_no_feedback(self) -> None:
        # A bare `/orchestrator add-agent-runs` a grant left unread is a
        # control, not review: the rescan quotes the human's feedback and not
        # the command, however the command came to be past the watermark.
        scenario = IssueScenario(*self._seed(
            pr=self._open_pr(),
            issue_comments=[
                FakeComment(
                    id=TRIGGER_ID, body=TIGHTEN, user=REPLIER, created_at=LONG_SETTLED,
                ),
                FakeComment(
                    id=FOLLOWUP_ID, body=ADD_RUNS, user=FakeUser(BOB), created_at=LONG_SETTLED,
                ),
            ],
        ))

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            mocks = self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(session_id=DEV_SESSION, last_message=PUSHED_MESSAGE),
                head_shas=(SHA_BEFORE, SHA_AFTER),
            )

        mocks[RUN_AGENT].assert_called_once()
        prompt = mocks[RUN_AGENT].call_args.args[1]
        self.assertIn(TIGHTEN, prompt)
        self.assertNotIn(ADD_RUNS, prompt)

    # --- dev resume + push --> flip to validating ------------------------

    def test_pushed_fix_resets_and_enters_validating(self) -> None:
        # A pushed fix flips DIRECTLY back to `validating` so the
        # reviewer agent re-evaluates the freshened diff next tick.
        # Docs do not run on the pushed-fix exit -- the single docs
        # pass runs after reviewer approval before `in_review` via the
        # final-docs handoff, so running the docs stage against an
        # unapproved diff here would just push a no-op and waste a tick.
        long_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        comment = FakeComment(
            id=TRIGGER_ID,
            body=FIX_FEEDBACK,
            user=REPLIER,
            created_at=long_ago,
        )
        pr = self._open_pr()
        scenario = IssueScenario(*self._seed(pr=pr, issue_comments=[comment]))

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            mocks = self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(
                    session_id=DEV_SESSION,
                    last_message="fixed",
                ),
                head_shas=(SHA_BEFORE, SHA_AFTER),
                push_branch=True,
            )

        # Dev pushed; label flipped directly to validating.
        mocks[PUSH_BRANCH].assert_called_once()
        self.assertIn((ISSUE, VALIDATING), scenario.github.label_history)
        # And NOT through documenting -- docs run after reviewer
        # approval before `in_review`, not on the pushed-fix exit.
        self.assertNotIn((ISSUE, DOCUMENTING), scenario.github.label_history)
        self._pinned_data = scenario.github.pinned_data(ISSUE)
        # Review round reset so validating starts fresh on the new diff.
        self.assertEqual(self._pinned_data.get(REVIEW_ROUND), 0)
        # Bookmarks cleared after consumption.
        self.assertIsNone(self._pinned_data.get(PENDING_FIX_AT))
        self.assertIsNone(self._pinned_data.get(PENDING_FIX_ISSUE_MAX_ID))
        # Watermark advanced past the consumed comment.
        self.assertGreaterEqual(self._pinned_data.get(PR_LAST_COMMENT_ID), TRIGGER_ID)

    def test_timeout_parks_and_advances_watermarks(self) -> None:
        # On dev timeout `_handle_dev_fix_result` parks awaiting human.
        # The fixing handler still advances the in_review watermarks past
        # the consumed feedback so the next tick does not replay it and
        # busy-loop the dev on the same comment.
        long_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        comment = FakeComment(
            id=TRIGGER_ID,
            body="please fix",
            user=REPLIER,
            created_at=long_ago,
        )
        pr = self._open_pr()
        scenario = IssueScenario(*self._seed(pr=pr, issue_comments=[comment]))

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(timed_out=True),
                head_shas=(SHA_BEFORE,),
            )

        pinned_data = scenario.github.pinned_data(ISSUE)
        self.assertTrue(pinned_data.get(AWAITING_HUMAN))
        # Watermark advanced even though no fix landed -- the dev saw
        # the feedback via the resume prompt.
        self.assertGreaterEqual(pinned_data.get(PR_LAST_COMMENT_ID), TRIGGER_ID)
        # Did NOT advance to validating; stays in fixing for the
        # operator. (A pushed fix would relabel to validating.)
        self.assertNotIn((ISSUE, VALIDATING), scenario.github.label_history)
        self.assertNotIn((ISSUE, DOCUMENTING), scenario.github.label_history)

    # --- watermark advancement across all three surfaces ----------------

    def test_pushed_fix_advances_all_three_watermarks(self) -> None:
        # Feedback lands on three surfaces simultaneously: an issue
        # comment, an inline review comment, and a review summary.
        # After a pushed fix every watermark must move past the max id
        # consumed on that surface.
        long_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        issue_comment = FakeComment(
            id=TRIGGER_ID,
            body="rename foo",
            user=REPLIER,
            created_at=long_ago,
        )
        inline_comment = FakeComment(
            id=INLINE_FEEDBACK_ID,
            body="add a test for this branch",
            user=FakeUser(BOB),
            created_at=long_ago,
        )
        summary_review = FakePRReview(
            id=REVIEW_SUMMARY_FEEDBACK_ID,
            body="please update the doc string",
            state=CHANGES_REQUESTED,
            user=FakeUser(CAROL),
            submitted_at=long_ago,
        )
        self._pr = self._open_pr(
            review_comments=[inline_comment],
            reviews=[summary_review],
        )
        scenario = IssueScenario(
            *self._seed(
                pr=self._pr,
                issue_comments=[issue_comment],
                extra_state={
                    PR_LAST_REVIEW_COMMENT_ID: INLINE_FEEDBACK_ID - 1,
                    PR_LAST_REVIEW_SUMMARY_ID: REVIEW_SUMMARY_FEEDBACK_ID - 1,
                    PENDING_FIX_REVIEW_MAX_ID: INLINE_FEEDBACK_ID,
                    PENDING_FIX_REVIEW_SUMMARY_MAX_ID: REVIEW_SUMMARY_FEEDBACK_ID,
                },
            )
        )

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            self._mocks = self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(
                    session_id=DEV_SESSION,
                    last_message=PUSHED_MESSAGE,
                ),
                head_shas=(SHA_BEFORE, SHA_AFTER),
            )

        self._mocks[PUSH_BRANCH].assert_called_once()
        self.assertIn((ISSUE, VALIDATING), scenario.github.label_history)
        self.assertNotIn((ISSUE, DOCUMENTING), scenario.github.label_history)
        self._pinned_data = scenario.github.pinned_data(ISSUE)
        self.assertGreaterEqual(self._pinned_data.get(PR_LAST_COMMENT_ID), TRIGGER_ID)
        self.assertEqual(
            self._pinned_data.get(PR_LAST_REVIEW_COMMENT_ID),
            INLINE_FEEDBACK_ID,
        )
        self.assertEqual(
            self._pinned_data.get(PR_LAST_REVIEW_SUMMARY_ID),
            REVIEW_SUMMARY_FEEDBACK_ID,
        )
        # Prompt also quoted every surface.
        self._agent_call = self._mocks[RUN_AGENT].call_args
        self._prompt = self._agent_call.args[1]
        self.assertIn("rename foo", self._prompt)
        self.assertIn("add a test for this branch", self._prompt)
        self.assertIn("please update the doc string", self._prompt)


AUTHORIZATION = "authorized: go ahead and vendor the parser"


# The key each case puts its issue-thread half of the batch under.
ON_THE_THREAD = "issue_comments"

# Where each reader stands before a round, so "moved" and "left alone" are both
# concrete numbers rather than the absence of a key.
SEEDED_READERS = MappingProxyType({
    LAST_ACTION_COMMENT_ID: HISTORICAL_COMMENT_ID,
    PR_LAST_COMMENT_ID: INITIAL_PR_COMMENT_WATERMARK,
    PR_LAST_REVIEW_COMMENT_ID: 0,
    PR_LAST_REVIEW_SUMMARY_ID: 0,
})


def _settled():
    """A timestamp old enough that no quiet window is still waiting on it."""
    return support.now_utc() - timedelta(hours=1)


def _reply(comment_id: int, body: str):
    """One settled comment, on whichever surface a case puts it."""
    return FakeComment(
        id=comment_id, body=body, user=REPLIER, created_at=_settled(),
    )


def _run(message: str = "", **agent_fields) -> dict:
    """The fields one finished developer run comes back carrying."""
    return {"last_message": message, "session_id": DEV_SESSION, **agent_fields}


def _pinned() -> PinnedState:
    """A pinned comment carrying the four readers where the seed puts them."""
    return PinnedState(state_data=dict(SEEDED_READERS))


# The one reply the thread cases are a fix round over, so the prompt each
# asserts is the prompt this batch earns.
THE_REPLY = _reply(TRIGGER_ID, AUTHORIZATION)


def _readers_after(**moved) -> dict:
    """Where the four readers stand once `moved` has been settled."""
    return {**SEEDED_READERS, **moved}


# What a run that put the batch in front of an agent comes back as, and the
# heads the checkout reads around it. Every one of them delivered the prompt,
# so every one owes the same consumption record -- "delivered" is what the
# readers record, never "resolved".
DELIVERED_OUTCOMES = (
    ("pushed fix", _run(PUSHED_MESSAGE), (SHA_BEFORE, SHA_AFTER)),
    ("timeout park", _run(timed_out=True), (SHA_BEFORE,)),
    ("question park", _run("A or B?"), (SHA_SAME, SHA_SAME)),
    ("ack", _run("ACK: 'continue' names no defect"), (SHA_SAME, SHA_SAME)),
)

# What no reader may be advanced for: a launch the run circuit turned away
# before any process started, and a shutdown kill. Both leave the whole tick
# re-decidable, so the batch has to come back unread.
WITHHELD_OUTCOMES = (
    ("never invoked", _run(invoked=False)),
    ("shutdown killed", _run("partial", interrupted=True)),
)

# One batch per pull-request surface, and where the four readers stand after a
# round that consumed it: the surface's own reader moves and no other does.
PULL_REQUEST_BATCHES = (
    (
        "pr conversation",
        {"pr_issue_comments": [
            _reply(BATCH_PR_CONVERSATION_ID, "needs a rollback path"),
        ]},
        _readers_after(**{PR_LAST_COMMENT_ID: BATCH_PR_CONVERSATION_ID}),
    ),
    (
        "inline review",
        {"pr_fields": {"review_comments": [
            _reply(INLINE_FEEDBACK_ID, "this branch is unreachable"),
        ]}},
        _readers_after(**{PR_LAST_REVIEW_COMMENT_ID: INLINE_FEEDBACK_ID}),
    ),
    (
        "review summary",
        {"pr_fields": {"reviews": [FakePRReview(
            id=REVIEW_SUMMARY_FEEDBACK_ID,
            body="please tighten the error message",
            state=CHANGES_REQUESTED,
            user=FakeUser(CAROL),
            submitted_at=_settled(),
        )]}},
        _readers_after(**{PR_LAST_REVIEW_SUMMARY_ID: REVIEW_SUMMARY_FEEDBACK_ID}),
    ),
)


class FixingDeliverySettlementTest(unittest.TestCase, _FixingFixtureMixin):
    """Which reader one consumed fix batch settles, and which runs settle none.

    A fix round quotes every unread surface into one prompt, so what it
    consumed has to be recorded per surface: the issue thread is the surface
    `last_action_comment_id` speaks for, and the pull request's three surfaces
    are what the in-review watermarks speak for. Recording either over the
    other loses a reader's own question -- one hands an answered reply back to
    the next route, the other hides PR feedback no prompt ever carried.
    """

    def test_a_reply_settles_both_readers(self) -> None:
        for case, agent_fields, head_shas in DELIVERED_OUTCOMES:
            with self.subTest(outcome=case):
                mocks = self._deliver(
                    agent_fields=agent_fields,
                    head_shas=head_shas,
                    placed={ON_THE_THREAD: [THE_REPLY]},
                )

                # One developer, handed exactly this batch and nothing else.
                self.assertEqual(
                    only_prompt(mocks), pr_feedback_prompt([THE_REPLY]),
                )
                settled = self._readers()
                # The thread reader covers the reply, so a route change out of
                # `fixing` finds it answered; a park's own notice may carry the
                # mark further, over posts of ours and nothing else.
                self.assertGreaterEqual(settled[LAST_ACTION_COMMENT_ID], TRIGGER_ID)
                self.assertEqual(settled[PR_LAST_COMMENT_ID], TRIGGER_ID)

    def test_pr_surfaces_leave_the_thread_reader(self) -> None:
        # Nothing that advances `last_action_comment_id` has read the pull
        # request, so a round whose whole batch came off one of its three
        # surfaces may not touch it -- and each surface moves its own reader
        # and no other.
        for case, placed, expected in PULL_REQUEST_BATCHES:
            with self.subTest(surface=case):
                mocks = self._deliver(
                    agent_fields=_run(PUSHED_MESSAGE),
                    head_shas=(SHA_BEFORE, SHA_AFTER),
                    placed=placed,
                )

                mocks[RUN_AGENT].assert_called_once()
                self.assertEqual(self._readers(), expected)

    def test_a_withheld_run_settles_nothing(self) -> None:
        # Neither of these delivered anything: one never reached a process at
        # all and the other was killed mid-run, so both leave every reader
        # where it was for the next tick to re-discover the same batch.
        for case, agent_fields in WITHHELD_OUTCOMES:
            with self.subTest(outcome=case):
                mocks = self._deliver(
                    agent_fields=agent_fields,
                    head_shas=(SHA_BEFORE, SHA_AFTER),
                    placed={ON_THE_THREAD: [THE_REPLY]},
                )

                # The batch WAS handed to a launch -- one prompt, this batch
                # -- and none of it is recorded: what the guards refuse is the
                # RESULT, not the delivery attempt.
                self.assertEqual(
                    only_prompt(mocks), pr_feedback_prompt([THE_REPLY]),
                )
                self.assertEqual(self._readers(), SEEDED_READERS)
                self.assertEqual(self._github.label_history, [])
                self.assertEqual(self._github.posted_comments, [])

    def test_an_ack_settles_without_answering(self) -> None:
        # The validating route reached `fixing` on a reviewer's
        # CHANGES_REQUESTED, which asked for a concrete change -- so the ACK
        # fast path is not offered here and the round parks for a human with
        # its replay anchor intact. The batch is still settled: a developer
        # read it, which is all the readers record.
        mocks = self._deliver(
            agent_fields=_run("ACK: nothing to fix"),
            head_shas=(SHA_SAME, SHA_SAME),
            placed={ON_THE_THREAD: [THE_REPLY]},
            extra_state={
                PENDING_FIX_AT: None,
                PENDING_FIX_ISSUE_MAX_ID: None,
                PENDING_FIX_REVIEWER_COMMENT_ID: REVIEWER_FEEDBACK_ID,
            },
        )

        pinned_data = self._github.pinned_data(ISSUE)
        mocks[RUN_AGENT].assert_called_once()
        self.assertNotIn((ISSUE, IN_REVIEW), self._github.label_history)
        self.assertTrue(pinned_data.get(AWAITING_HUMAN))
        self.assertEqual(
            pinned_data.get(PENDING_FIX_REVIEWER_COMMENT_ID), REVIEWER_FEEDBACK_ID,
        )
        self.assertGreaterEqual(
            self._readers()[LAST_ACTION_COMMENT_ID], TRIGGER_ID,
        )

    def test_a_transaction_would_carry_the_same_pairs(self) -> None:
        # "Settle through a durable report transaction where one is present,
        # and directly otherwise" is only one rule if the two roads write the
        # same thing. The pairs this stage derives are therefore held to the
        # vocabulary a RECOVERED transaction is read back under, and then
        # applied by that owner's own ratchet -- a field outside the table, or
        # a value it will not take, refuses the whole recorded group and holds
        # a transaction whose feedback is already answered.
        batch = _models._FixingFeedback(
            issue_thread=[_reply(TRIGGER_ID, AUTHORIZATION)],
            pr_conversation=[
                _reply(BATCH_PR_CONVERSATION_ID, "needs a rollback path"),
            ],
            review_comments=[
                _reply(INLINE_FEEDBACK_ID, "this branch is unreachable"),
            ],
            review_summaries=[FakePRReview(
                id=REVIEW_SUMMARY_FEEDBACK_ID,
                body="please tighten the error message",
                state=CHANGES_REQUESTED,
                user=FakeUser(CAROL),
                submitted_at=_settled(),
            )],
        )
        pairs = _feedback._consumed_delivery(
            _pinned(), batch,
        ).consumed_pairs(_pinned())

        self.assertEqual(
            _consumed_values.recorded_pairs(
                [list(pair) for pair in pairs], _consumed_values.consumable,
            ),
            pairs,
        )
        directly, through_a_transaction = _pinned(), _pinned()
        _feedback._settle_consumed_feedback(directly, batch)
        _consumed_values.advance_consumed(through_a_transaction, pairs)
        self.assertEqual(through_a_transaction.data, directly.data)

    def _deliver(self, *, agent_fields, head_shas, placed, extra_state=None):
        """One fixing tick over a batch on whichever surfaces `placed` names."""
        pr = self._open_pr(**placed.get("pr_fields", {}))
        pr.issue_comments.extend(placed.get("pr_issue_comments", ()))
        scenario = IssueScenario(*self._seed(
            pr=pr,
            issue_comments=placed.get(ON_THE_THREAD, ()),
            extra_state={**SEEDED_READERS, **(extra_state or {})},
        ))
        self._github = scenario.github

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            return self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(**agent_fields),
                head_shas=head_shas,
            )

    def _readers(self) -> dict:
        """Where each of the four consumption readers stands after the tick."""
        pinned_data = self._github.pinned_data(ISSUE)
        return {field: pinned_data.get(field) for field in SEEDED_READERS}
