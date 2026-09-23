# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a review-cap grant records, and what stops it buying a second reset.

`/orchestrator add-review-rounds N` is answered on the thread rather than
handed to an agent, so the road acting on it records exactly the comment it
answers -- and only where that comment IS the command. A grant written at the
bottom of a long comment of guidance is guidance too: the round it buys quotes
the thread under its own 4000-character excerpt, which may not reach the head,
so crossing the whole comment here would spend words no prompt ever showed
anybody, and a launch the run circuit turned away would spend them with no
reviewer having run at all.

Left unread, the command outlives the cap it answered -- the batch a later cap
freezes reaches back below it and carries the same words again. What says it
was honored is the record written beside the round reset it bought, which is
durable exactly where that reset is: the notice goes out before the reviewer
runs, so a launch the lifetime run circuit refuses keeps the sentence and
discards the reset, and the very same command is what an agent-run grant hands
back to be honored for real.
"""

from __future__ import annotations

import unittest

from orchestrator.workflow.engine import (
    content_hash as _content_hash,
    run_limit_dispatch as _run_limit_dispatch,
    run_limit_values as _run_limit_values,
)
from tests.workflow.stages.validating import (
    validating_review_test_support as review_support,
)

config = review_support.config
_TEST_SPEC = review_support._TEST_SPEC
make_issue = review_support.make_issue
BEFORE_FIX_SHA = review_support.BEFORE_FIX_SHA
LABEL_VALIDATING = review_support.LABEL_VALIDATING
REVIEW_APPROVED_MESSAGE = review_support.REVIEW_APPROVED_MESSAGE
REVIEW_CAP_ISSUE = review_support.REVIEW_CAP_ISSUE
ACTION_COMMENT_ID = review_support.ACTION_COMMENT_ID
_agent = review_support._agent
_ReviewCapFixtureMixin = review_support.ReviewCapFixtureMixin

AWAITING_HUMAN = "awaiting_human"
PARK_REASON = "park_reason"
REVIEW_CAP = "review_cap"
REVIEW_ROUND = "review_round"
LAST_ACTION_COMMENT_ID = "last_action_comment_id"
USER_CONTENT_HASH = "user_content_hash"
OWES_A_ROUND = "validating_reviewer_owes_a_round"
CAP_RESET_MESSAGE = "review-cap reset"
RUN_AGENT = "run_agent"

# Where the prompt sits in the intercepted agent call.
PROMPT_ARGUMENT = 1

# Guidance long enough that the round's own excerpt cannot carry its head,
# with the grant written at the bottom of the very same comment.
_PAST_THE_BOUND = 5000
GRANT_COMMAND = "/orchestrator add-review-rounds 1"
MIXED_HEAD = "the retry has to back off before the third attempt"
MIXED_COMMAND = "\n".join(
    (MIXED_HEAD, "g" * _PAST_THE_BOUND, GRANT_COMMAND),
)

# A lifetime ledger with nothing left, and the command that widens it.
SPENT_ALLOWANCE = 3
MORE_RUNS_COMMAND = "/orchestrator add-agent-runs 3"
HUMAN_LOGIN = review_support.HUMAN_LOGIN
FakeComment = review_support.FakeComment
FakeUser = review_support.FakeUser
MORE_RUNS_COMMENT_ID = 1400
AGENT_RUN_ALLOWANCE = "agent_run_allowance"
AGENT_RUNS_USED = "agent_runs_used"
RUN_LIMIT_PARK = _run_limit_values.PARK_AGENT_RUN_LIMIT


def _before_the_comment() -> str:
    """The baseline an issue carries before anybody comments on it."""
    return _content_hash._compute_user_content_hash(
        make_issue(REVIEW_CAP_ISSUE, label=LABEL_VALIDATING), set(),
    )


class ReviewCapGrantInsideGuidanceTest(
    unittest.TestCase,
    _ReviewCapFixtureMixin,
):
    """A grant written at the bottom of a comment nobody has delivered."""

    def test_guidance_is_left_to_the_round(self) -> None:
        # The comment is not the command, so it is guidance too and this road
        # records none of it. The round the grant buys is what quotes the
        # thread, under a bound that cannot reach the head -- so the mark it
        # leaves stops below the comment it cut short, and those words stay
        # deliverable by the scan that owns the issue thread.
        github, _, mocks = self._capped_tick(
            _agent(last_message=REVIEW_APPROVED_MESSAGE),
        )

        prompt = mocks[RUN_AGENT].call_args[0][PROMPT_ARGUMENT]
        self.assertNotIn(MIXED_HEAD, prompt)
        self.assertIn(GRANT_COMMAND, prompt)
        self._assert_reviewer_spawn(github)
        state = self._capped(github)
        self.assertEqual(state.get(REVIEW_ROUND), config.MAX_REVIEW_ROUNDS - 1)
        self.assertEqual(state.get(LAST_ACTION_COMMENT_ID), ACTION_COMMENT_ID)

    def test_a_refused_launch_replays_the_grant(self) -> None:
        # A spent lifetime ledger. The circuit refuses the reviewer before a
        # process exists, and the handler returns without writing -- so the
        # round reset this grant staged is discarded while the notice it
        # posted stays on the thread. The command is therefore still owed,
        # and the agent-run grant that lifts the run-limit park hands back
        # the very park it was written on, for it to be honored for real.
        github, issue, mocks = self._capped_tick(
            _agent(last_message=REVIEW_APPROVED_MESSAGE),
            **{
                AGENT_RUN_ALLOWANCE: SPENT_ALLOWANCE,
                AGENT_RUNS_USED: SPENT_ALLOWANCE,
            },
        )

        mocks[RUN_AGENT].assert_not_called()
        state = self._capped(github)
        self.assertEqual(state.get(REVIEW_ROUND), config.MAX_REVIEW_ROUNDS)
        self.assertEqual(state.get(PARK_REASON), RUN_LIMIT_PARK)
        self.assertEqual(state.get(USER_CONTENT_HASH), _before_the_comment())
        self.assertIsNone(state.get(OWES_A_ROUND))

        self._buy_more_agent_runs(github, issue)
        bought = self._run_validating(
            github,
            issue,
            run_agent=_agent(last_message=REVIEW_APPROVED_MESSAGE),
            head_shas=[BEFORE_FIX_SHA],
        )

        bought[RUN_AGENT].assert_called_once()
        state = self._capped(github)
        self.assertEqual(state.get(REVIEW_ROUND), config.MAX_REVIEW_ROUNDS - 1)
        self.assertIsNone(state.get(PARK_REASON))

    def test_a_second_cap_is_not_granted(self) -> None:
        # The words the first grant left unread are still in the batch the
        # NEXT cap freezes, command included. Read as a fresh grant they
        # would reset that cap for free, and every cap after it. The answer
        # standing above the command is what says this road has dealt with
        # it, so the second cap keeps its park and its spent budget.
        github, issue, _ = self._capped_tick(
            _agent(last_message=REVIEW_APPROVED_MESSAGE),
        )
        self._park_at_the_cap_again(github, issue)

        mocks = self._run_validating(
            github, issue, run_agent=_agent(), head_shas=[BEFORE_FIX_SHA],
        )

        mocks[RUN_AGENT].assert_not_called()
        state = self._capped(github)
        self.assertEqual(state.get(REVIEW_ROUND), config.MAX_REVIEW_ROUNDS)
        self.assertEqual(state.get(PARK_REASON), REVIEW_CAP)
        self.assertEqual(
            len([
                body
                for _, body in github.posted_comments
                if CAP_RESET_MESSAGE in body
            ]),
            1,
        )

    def _capped_tick(self, review, **seed):
        """One `review_cap` tick answering the mixed grant comment."""
        github, issue = self._seeded(
            comment_body=MIXED_COMMAND,
            user_content_hash=_before_the_comment(),
            **seed,
        )
        mocks = self._run_validating(
            github, issue, run_agent=review, head_shas=[BEFORE_FIX_SHA],
        )
        return github, issue, mocks

    def _buy_more_agent_runs(self, github, issue) -> None:
        """Buy runs past the spent ledger, through the dispatch hold itself.

        The hold is asked on every tick the park stands, so the sentence it
        owes the thread is said on the one before the command can be read --
        which is why the issue is walked past it twice here.
        """
        self._held(github, issue)
        issue.comments.append(FakeComment(
            id=MORE_RUNS_COMMENT_ID,
            body=MORE_RUNS_COMMAND,
            user=FakeUser(HUMAN_LOGIN),
        ))
        self.assertFalse(self._held(github, issue))

    def _held(self, github, issue) -> bool:
        """Whether the spent-ledger hold keeps this tick off its handler."""
        return _run_limit_dispatch._run_limit_holds_the_tick(
            github, _TEST_SPEC, issue, github.read_pinned_state(issue), False,
        )

    def _park_at_the_cap_again(self, github, issue) -> None:
        """Put the issue back where its next spent budget leaves it."""
        spent = github.pinned_data(REVIEW_CAP_ISSUE)
        spent.update({
            AWAITING_HUMAN: True,
            PARK_REASON: REVIEW_CAP,
            REVIEW_ROUND: config.MAX_REVIEW_ROUNDS,
        })
        github.seed_state(issue, **spent)
