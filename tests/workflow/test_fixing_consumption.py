# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One fix round's batch, read back by the stage a human moves the issue to.

A `workflow:fixing` round quotes the issue thread, the pull request's
conversation, its inline review comments and its review summaries into one
developer prompt. The issue thread is the one surface another stage also
delivers from, and `last_action_comment_id` is the field that says so -- the
implementing and validating awaiting-human resumes build their prompt out of
the replies past it. A round that consumed a reply and left that field behind
therefore leaves the reply looking unread to the stage a relabel hands the
issue to, which pays a second developer to deliver it again and reports the
duplicate back on the thread.

The crossing is what shows it: neither end is wrong alone. The round quotes the
reply exactly once, and only the stage the issue is moved to decides whether
the same reply comes back as work. The replay beside it is the other half of
the same field's contract -- the `pending_fix_*` bookmarks are not readers, so
an explicit retry still rebuilds the batch every reader has moved past.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from orchestrator import config
from tests.support.fakes import (
    FakeComment,
    FakeGitHubClient,
    FakePR,
    FakePRRef,
    FakeUser,
    make_issue,
)
from tests.workflow.fixtures import (
    DEFAULT_PR_HEAD_SHA,
    LABEL_FIXING,
    LABEL_VALIDATING,
    _agent,
    _PatchedWorkflowMixin,
)
from tests.workflow.stages.fixing.prompt_expectations import (
    only_prompt,
    pr_feedback_prompt,
    replayed_task,
)

ISSUE = 1844
PR_NUMBER = 4320
BRANCH = f"orchestrator/chippingway__orchestrator/issue-{ISSUE}"
HEAD_SHA = DEFAULT_PR_HEAD_SHA

DEV_AGENT = "claude"
DEV_SESSION = "dev-sess"
HUMAN = "alice"
ORCHESTRATOR = "orchestrator"

# The park that opened the wait and the reply that answered it, numbered in
# the one IssueComment id space GitHub gives the issue thread.
PARK_NOTICE_ID = 800
AUTHORIZATION_ID = 810
# The retry an operator types into the PULL REQUEST's conversation, numbered
# in the same IssueComment space the thread above is: the two surfaces share
# GitHub's numbering and share no reader at all.
PR_CONTINUE_ID = 820

PARK_NOTICE_BODY = ":raising_hand: waiting on a human."
AUTHORIZATION = "authorized: go ahead and vendor the parser"
CONTINUE_COMMAND = "/orchestrator continue"
DEV_QUESTION = "which of the two parsers did you mean?"

RUN_AGENT = "run_agent"
DEBOUNCE_SETTING = "IN_REVIEW_DEBOUNCE_SECONDS"
DEBOUNCE_SECONDS = 600
AWAITING_HUMAN = "awaiting_human"
PARK_REASON = "park_reason"
LAST_ACTION_COMMENT_ID = "last_action_comment_id"
PR_LAST_COMMENT_ID = "pr_last_comment_id"
PENDING_FIX_ISSUE_IDS = "pending_fix_issue_ids"
PENDING_FIX_AT_TS = "2026-05-24T00:00:00+00:00"
AGENT_TIMEOUT = "agent_timeout"


def _settled() -> datetime:
    """A timestamp old enough that no quiet window is still waiting on it."""
    return datetime.now(UTC) - timedelta(hours=1)


def _comment(comment_id: int, body: str, *, author: str = HUMAN) -> FakeComment:
    """One settled issue-thread comment."""
    return FakeComment(
        id=comment_id,
        body=body,
        user=FakeUser(author),
        created_at=_settled(),
    )


class _FixRoundFixtureMixin(_PatchedWorkflowMixin):
    """A `workflow:fixing` issue on the in_review route, mid-fix-round.

    The reply the round is about sits above both issue-space cursors, and the
    bookmarks the route recorded name it -- which is what makes the batch
    reconstructable after every reader has moved past it.
    """

    def _seed(self, *, issue_comments=(), pr_conversation=(), **overrides):
        gh = FakeGitHubClient()
        issue = make_issue(ISSUE, label=LABEL_FIXING, comments=[
            _comment(PARK_NOTICE_ID, PARK_NOTICE_BODY, author=ORCHESTRATOR),
            _comment(AUTHORIZATION_ID, AUTHORIZATION),
            *issue_comments,
        ])
        gh.add_issue(issue)
        gh.add_pr(FakePR(
            number=PR_NUMBER,
            head_branch=BRANCH,
            head=FakePRRef(sha=HEAD_SHA),
            mergeable=True,
            check_state="success",
            issue_comments=list(pr_conversation),
        ))
        pinned = {
            "pr_number": PR_NUMBER,
            "branch": BRANCH,
            "dev_agent": DEV_AGENT,
            "dev_session_id": DEV_SESSION,
            "review_round": 1,
            "orchestrator_comment_ids": [PARK_NOTICE_ID],
            PR_LAST_COMMENT_ID: PARK_NOTICE_ID,
            LAST_ACTION_COMMENT_ID: PARK_NOTICE_ID,
            "pr_last_review_comment_id": 0,
            "pr_last_review_summary_id": 0,
            "pending_fix_at": PENDING_FIX_AT_TS,
            "pending_fix_issue_max_id": AUTHORIZATION_ID,
            PENDING_FIX_ISSUE_IDS: [AUTHORIZATION_ID],
        }
        pinned.update(overrides)
        gh.seed_state(ISSUE, **pinned)
        return gh, issue

    def _seed_unsettled_boundary_park(self):
        """A park whose issue-action boundary sits below its own bookmarks.

        The round that opened it advanced the PR-side cursor past the
        authorization and left `last_action_comment_id` at the notice below
        it -- the state any issue carries once one of the two readers over a
        shared id space has been moved across a reply and the other has not.
        The retry arrives on the PULL REQUEST's conversation, so the batch the
        replay delivers spans two surfaces answering to two different readers.
        """
        return self._seed(
            pr_conversation=[_comment(PR_CONTINUE_ID, CONTINUE_COMMAND)],
            pr_last_comment_id=AUTHORIZATION_ID,
            awaiting_human=True,
            park_reason=AGENT_TIMEOUT,
        )

    def _newest(self, issue, body: str) -> None:
        """Put one reply at the top of the thread, above the round's notices.

        Numbered off the thread as it stands rather than by a constant,
        because the park this retry answers posted its own notice first: an
        operator types the command after reading that, so a lower number
        would model a comment that arrived before the answer it replies to.
        """
        issue.comments.append(_comment(
            max(seen.id for seen in issue.comments) + 1, body,
        ))

    def _authorization(self, issue):
        """The reply the round is about, as the handler reads it off GitHub."""
        return next(
            seen for seen in issue.comments if seen.id == AUTHORIZATION_ID
        )

    def _prompts(self, mocks) -> list[str]:
        """Every prompt string handed to an agent across one stage run."""
        return [call.args[1] for call in mocks[RUN_AGENT].call_args_list]

    def _tick(self, runner, gh, issue, **agent_fields):
        """One tick of `runner`, over a developer that makes no commit."""
        with patch.object(config, DEBOUNCE_SETTING, DEBOUNCE_SECONDS):
            return runner(
                gh,
                issue,
                run_agent=_agent(session_id=DEV_SESSION, **agent_fields),
                head_shas=[HEAD_SHA, HEAD_SHA],
            )


class DeliveredFixFeedbackTest(unittest.TestCase, _FixRoundFixtureMixin):
    """The reply the fix round answered is answered for the next stage too."""

    def test_a_manual_move_spawns_no_developer(self) -> None:
        gh, issue = self._seed()

        fixing_prompts = self._prompts(
            self._tick(self._run_fixing, gh, issue, last_message=DEV_QUESTION),
        )

        # One developer, handed the whole PR-feedback prompt built over the
        # authorization and nothing else. Asserted entire rather than searched,
        # because what the crossing is about is the BATCH the prompt carried:
        # a park notice of ours, a second copy of the reply, or a comment the
        # scan should have left behind all read as a substring hit and none of
        # them survives this comparison.
        self.assertEqual(
            fixing_prompts,
            [pr_feedback_prompt([self._authorization(issue)])],
        )
        self.assertTrue(gh.pinned_data(ISSUE).get(AWAITING_HUMAN))
        self.assertGreaterEqual(
            gh.pinned_data(ISSUE).get(LAST_ACTION_COMMENT_ID), AUTHORIZATION_ID,
        )

        gh.apply_foreign_label(issue, LABEL_VALIDATING)
        validating_mocks = self._tick(
            self._run_validating, gh, issue, last_message=DEV_QUESTION,
        )

        # Nothing is spawned at all: the reply is answered, so neither the
        # drift road nor the awaiting-human resume has anything to deliver,
        # and the park keeps waiting on the human it asked. Left unsettled,
        # this tick hands that same prompt to a second developer.
        self.assertEqual(self._prompts(validating_mocks), [])
        self.assertTrue(gh.pinned_data(ISSUE).get(AWAITING_HUMAN))

    def test_an_explicit_retry_still_replays(self) -> None:
        # The `pending_fix_*` bookmarks are a replay source rather than a
        # reader, so settling the round leaves them alone -- and an operator's
        # `/orchestrator continue` on the session-failure park rebuilds the
        # batch every reader has now moved past.
        gh, issue = self._seed()
        self._tick(self._run_fixing, gh, issue, timed_out=True)

        self.assertEqual(gh.pinned_data(ISSUE).get(PARK_REASON), AGENT_TIMEOUT)
        self.assertEqual(
            gh.pinned_data(ISSUE).get(PENDING_FIX_ISSUE_IDS), [AUTHORIZATION_ID],
        )

        self._newest(issue, CONTINUE_COMMAND)
        retry_mocks = self._tick(
            self._run_fixing, gh, issue, last_message=DEV_QUESTION,
        )

        # One developer, re-grounded on a fresh session and handed the
        # PRESERVED batch -- asserted entire: the re-grounding above the
        # divider and, below it, the batch the bookmarks rebuilt and nothing
        # else. Never the bare command, and never a second copy of the reply
        # the readers have moved past.
        self.assertEqual(
            replayed_task(only_prompt(retry_mocks)),
            pr_feedback_prompt([self._authorization(issue)]),
        )


class ReplayedFixFeedbackTest(unittest.TestCase, _FixRoundFixtureMixin):
    """A replay settles the reader each half of what it delivered owns."""

    def test_a_replay_across_surfaces_settles_both(self) -> None:
        # #1790's first sequence, on a park whose issue-action boundary is
        # still below its bookmarks: the authorization is on the ISSUE THREAD
        # and the retry that replays it is typed into the PULL REQUEST's
        # conversation. Flattened, the replay records what it delivered
        # against whichever reader the merged list is attributed to -- and the
        # boundary, the one field the stage a relabel hands the issue to
        # reads, stays below the reply this round just answered.
        gh, issue = self._seed_unsettled_boundary_park()

        retry_mocks = self._tick(
            self._run_fixing, gh, issue, last_message=DEV_QUESTION,
        )

        # One developer, handed the preserved authorization entire and alone:
        # never the bare command that asked for the retry.
        self.assertEqual(
            replayed_task(only_prompt(retry_mocks)),
            pr_feedback_prompt([self._authorization(issue)]),
        )
        pinned_data = gh.pinned_data(ISSUE)
        # The replayed half was read off the issue thread, so the issue-action
        # boundary moves with it; the command was read off the pull request,
        # so only the PR-side cursor covers that.
        self.assertGreaterEqual(
            pinned_data.get(LAST_ACTION_COMMENT_ID), AUTHORIZATION_ID,
        )
        self.assertGreaterEqual(
            pinned_data.get(PR_LAST_COMMENT_ID), PR_CONTINUE_ID,
        )

        gh.apply_foreign_label(issue, LABEL_VALIDATING)
        validating_mocks = self._tick(
            self._run_validating, gh, issue, last_message=DEV_QUESTION,
        )

        # Nothing is spawned: the authorization is answered for every reader
        # that owns a piece of it, so the move finds no work to pay for.
        self.assertEqual(self._prompts(validating_mocks), [])


if __name__ == "__main__":
    unittest.main()
