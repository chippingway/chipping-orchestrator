# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One requirements-drift resume's prompt, read back by the stages behind it.

#1790's second sequence. A human wrote a rebase instruction onto the issue
thread while a rebase was in flight; the drift road quoted it to the developer
and the issue later reached `workflow:fixing`, which handed the identical
words to a second developer. The crossing is what shows it: the drift resume
delivered the instruction exactly once, and only the stage the issue moves to
afterwards decides whether the same comment comes back as work.

The other half of the same record is what the resume did NOT read. A rebase
resume quotes the issue thread alone, so a pull-request conversation comment
numbered BELOW the instruction it consumed, an inline review comment and a
review summary are all still unread -- and the fix round behind it has to
deliver every one of them without delivering the instruction again.

The excerpt bound is the same question asked of the surface the resume DID
read. A thread whose tail alone fills the excerpt reaches the agent without
its head, so the words that head carried were delivered to nobody -- and the
round the issue reaches next is what still owes them.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from orchestrator.workflow.engine import (
    content_hash as _content_hash,
    drift as _engine_drift,
    prompt_context as _prompt_context,
)
from tests.support.fakes import (
    FakeComment,
    FakeGitHubClient,
    FakePR,
    FakePRRef,
    FakePRReview,
    FakeUser,
    make_issue,
)
from tests.workflow.fixtures import (
    DEFAULT_PR_HEAD_SHA,
    LABEL_FIXING,
    LABEL_IN_REVIEW,
    LABEL_VALIDATING,
    MEASURED_CANDIDATE_SHA,
    _agent,
    _issue_branch,
    _PatchedWorkflowMixin,
)
from tests.workflow.stages.fixing.prompt_expectations import (
    only_prompt,
    pr_feedback_prompt,
    spawned_nobody,
)

ISSUE = 1846
PR_NUMBER = 18460
BRANCH = _issue_branch(ISSUE)
RESOLVING_CONFLICT = "workflow:resolving_conflict"
HUMAN = "alice"
DEV_SESSION = "dev-sess"
DEV_AGENT = "claude"

# Where every reader stood when the instruction was written: below all three
# of the unread items and below the instruction itself.
READ_THROUGH = 100

# The pull request's own conversation carries a comment numbered BELOW the
# instruction the rebase resume goes on to consume, because GitHub numbers
# both surfaces in one ascending space and only one of them was read.
PR_FEEDBACK_ID = 150
REBASE_INSTRUCTION_ID = 200

# The two review surfaces this orchestrator never posts on, and never quotes
# into a rebase resume either.
INLINE_REVIEW_ID = 160
REVIEW_SUMMARY_ID = 170

REBASE_INSTRUCTION = "rebase onto main and force-push before you continue"
PR_FEEDBACK = "also handle the empty-input case"
INLINE_REVIEW = "this branch is unreachable"
REVIEW_SUMMARY = "one more pass, please"
DEV_QUESTION = "which of the two did you mean?"

# A reply far past the 4000-character excerpt bound, ending in words a prompt
# can be searched for: what the bound keeps is its tail, so the instruction
# above it is dropped from the prompt the resume delivers.
OVERSIZED_ID = 210
OVERSIZED_TAIL = "and the tail survives"
_PAST_THE_BOUND = 5000
_BEYOND_THE_BOUND = "b" * _PAST_THE_BOUND
OVERSIZED_REPLY = f"{_BEYOND_THE_BOUND} {OVERSIZED_TAIL}"

# The head the rebase starts from and the one its resolution leaves behind.
BEFORE_SHA = DEFAULT_PR_HEAD_SHA
RESOLVED_SHA = MEASURED_CANDIDATE_SHA

LAST_ACTION_COMMENT_ID = "last_action_comment_id"
PR_LAST_COMMENT_ID = "pr_last_comment_id"
PR_LAST_REVIEW_COMMENT_ID = "pr_last_review_comment_id"
PR_LAST_REVIEW_SUMMARY_ID = "pr_last_review_summary_id"
PENDING_FIX_ISSUE_IDS = "pending_fix_issue_ids"
STALE_HASH = "stale-hash"


def _settled() -> datetime:
    """A timestamp old enough that no quiet window is still waiting on it."""
    return datetime.now(UTC) - timedelta(hours=1)


def _said(comment_id: int, body: str) -> FakeComment:
    """One settled comment from a trusted human, on either IssueComment
    surface."""
    return FakeComment(
        id=comment_id, body=body, user=FakeUser(HUMAN), created_at=_settled(),
    )


def _drift_prompt(issue, conversation: str) -> str:
    """The whole prompt a rebase resume quoting exactly this thread gives.

    Built through the stage's own builder, so a case compares what the agent
    was really handed rather than looking for a phrase inside it: a second
    copy of the instruction, the pull request's conversation leaking onto a
    road that never reads it, and a review comment nobody quoted all read as a
    substring hit and none of them survives this comparison.
    """
    return _engine_drift._build_user_content_change_prompt(issue, conversation)


def _quoted(*spoken) -> str:
    """Those comments as the thread reader renders them into a prompt."""
    lines = []
    for comment in spoken:
        author = comment.user.login
        body = comment.body
        lines.append(f"@{author}: {body}")
    return "\n\n".join(lines)


class _RebasedUnderAnEdit(_PatchedWorkflowMixin):
    """A `workflow:resolving_conflict` issue a human wrote an instruction onto.

    Three items sit unread on surfaces this stage's resume never looks at --
    a pull-request comment numbered BELOW the instruction, an inline review
    comment and a review summary -- so what the crossing below reads back is
    a record that covered one surface and left three alone.
    """

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(
            ISSUE,
            label=RESOLVING_CONFLICT,
            body="updated requirements",
            comments=[_said(REBASE_INSTRUCTION_ID, REBASE_INSTRUCTION)],
        )
        self.github.add_issue(self.issue)
        self.pull_request = FakePR(
            number=PR_NUMBER,
            head_branch=BRANCH,
            head=FakePRRef(sha=BEFORE_SHA),
            mergeable=True,
            check_state="success",
            issue_comments=[_said(PR_FEEDBACK_ID, PR_FEEDBACK)],
            review_comments=[_said(INLINE_REVIEW_ID, INLINE_REVIEW)],
            reviews=[FakePRReview(
                id=REVIEW_SUMMARY_ID,
                body=REVIEW_SUMMARY,
                state="CHANGES_REQUESTED",
                user=FakeUser(HUMAN),
                submitted_at=_settled(),
            )],
        )
        self.github.add_pr(self.pull_request)
        self.github.seed_state(
            self.issue,
            pr_number=PR_NUMBER,
            branch=BRANCH,
            dev_agent=DEV_AGENT,
            dev_session_id=DEV_SESSION,
            conflict_round=0,
            review_round=1,
            user_content_hash=STALE_HASH,
            **{
                LAST_ACTION_COMMENT_ID: READ_THROUGH,
                PR_LAST_COMMENT_ID: READ_THROUGH,
                PR_LAST_REVIEW_COMMENT_ID: 0,
                PR_LAST_REVIEW_SUMMARY_ID: 0,
            },
        )

    def _pinned(self) -> dict:
        return self.github.pinned_data(ISSUE)

    def _unread(self) -> list:
        """The three items the rebase resume's own surface never covered."""
        return [
            self.pull_request.issue_comments[0],
            self.pull_request.review_comments[0],
            self.pull_request.reviews[0],
        ]

    def _rebase_resume(self) -> str:
        """The one prompt the body-edit resume hands the developer."""
        return only_prompt(self._run_resolving_conflict(
            self.github,
            self.issue,
            run_agent=_agent(session_id=DEV_SESSION, last_message="rebased"),
            has_new_commits=True,
            dirty_files=(),
            push_branch=True,
            head_shas=[BEFORE_SHA, RESOLVED_SHA],
        ))

    def _moves_to_review(self) -> dict:
        """A human's manual move onto `in_review`, and the tick it earns."""
        self.github.apply_foreign_label(self.issue, LABEL_IN_REVIEW)
        return self._run_in_review(
            self.github, self.issue, run_agent=_agent(session_id=DEV_SESSION),
        )

    def _fix_round(self) -> str:
        """The one prompt the fix round behind that move hands a developer."""
        return only_prompt(self._run_fixing(
            self.github,
            self.issue,
            run_agent=_agent(session_id=DEV_SESSION, last_message=DEV_QUESTION),
            head_shas=[RESOLVED_SHA, RESOLVED_SHA],
        ))


class DriftResumeConsumptionTest(_RebasedUnderAnEdit, unittest.TestCase):
    """The instruction one rebase resume delivered, and what it left unread."""

    def test_the_instruction_is_delivered_once(self) -> None:
        # The rebase resume quotes the instruction, resolves, and hands the
        # branch back to `validating`, recording the surface it read and no
        # other. Then #1790's move: a human puts the issue on `in_review`,
        # where the scan reads the instruction against the cursor the resume
        # settled and finds only the three items nobody was ever shown.
        self.assertEqual(
            self._rebase_resume(),
            _drift_prompt(self.issue, _quoted(self.issue.comments[0])),
        )
        self.assertIn((ISSUE, LABEL_VALIDATING), self.github.label_history)
        self._assert_read_the_thread_alone()

        spawned_nobody(self._moves_to_review())

        self.assertIn((ISSUE, LABEL_FIXING), self.github.label_history)
        # The bookmarks name the unread PR comment and never the instruction.
        self.assertEqual(
            self._pinned().get(PENDING_FIX_ISSUE_IDS), [PR_FEEDBACK_ID],
        )
        # One developer, handed the three unread items ENTIRE and alone.
        # Asserted whole rather than searched, because what the crossing is
        # about is the batch: a second copy of the instruction reads as a
        # substring hit and does not survive this comparison.
        self.assertEqual(self._fix_round(), pr_feedback_prompt(self._unread()))

    def test_what_the_excerpt_cut_is_still_owed(self) -> None:
        # A reply long enough that the excerpt keeps its tail and nothing
        # above it. The instruction under that cut reached no agent, so the
        # record leaves the issue-thread cursor below it and the fix round
        # the issue reaches next is the one that finally delivers it.
        self.issue.comments.append(_said(OVERSIZED_ID, OVERSIZED_REPLY))

        quoted = self._rebase_resume()

        whole = _quoted(*self.issue.comments)
        self.assertEqual(
            quoted,
            _drift_prompt(self.issue, whole[-_prompt_context._EXCERPT_CHARS:]),
        )
        self.assertNotIn(REBASE_INSTRUCTION, quoted)
        self.assertIn(OVERSIZED_TAIL, quoted)
        self.assertEqual(
            self._pinned().get(LAST_ACTION_COMMENT_ID), READ_THROUGH,
        )

        self._moves_to_review()

        self.assertIn(REBASE_INSTRUCTION, self._fix_round())

    def _assert_read_the_thread_alone(self) -> None:
        """The instruction answered, and every pull-request surface untouched.

        The rebase resume quotes the issue thread and nothing else, so the
        three cursors the pull request answers to stay exactly where the tick
        found them -- nothing on those surfaces reached the agent.
        """
        settled = self._pinned()
        self.assertEqual(
            settled.get(LAST_ACTION_COMMENT_ID), REBASE_INSTRUCTION_ID,
        )
        self.assertEqual(
            settled.get("user_content_hash"),
            _content_hash._compute_user_content_hash(self.issue, set()),
        )
        self.assertEqual(settled.get(PR_LAST_COMMENT_ID), READ_THROUGH)
        self.assertEqual(settled.get(PR_LAST_REVIEW_COMMENT_ID), 0)
        self.assertEqual(settled.get(PR_LAST_REVIEW_SUMMARY_ID), 0)


if __name__ == "__main__":
    unittest.main()
